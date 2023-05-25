#%%
import psycopg2
import os
import json
import geopandas as gpd
from geopy import distance
from multiprocessing.pool import ThreadPool
import requests
from dotenv import load_dotenv

#%%
# Setup environment
load_dotenv()

POSTGRES_USER = os.getenv('POSTGRES_USER')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')
POSTGRES_DB = os.getenv('POSTGRES_DB')
POSTGRES_HOST = os.getenv('POSTGRES_HOST')
POSTGRES_PORT = os.getenv('POSTGRES_PORT')

#%%
# Helperfunction to insert lists into the database
# Possibility to commit entries individually
def insert_list(sql, entries, single_commit=False):
    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        port=POSTGRES_PORT)
    cur = conn.cursor()

    if single_commit:
        for entry in entries:
            try:
                cur.execute(sql, entry)
            except psycopg2.IntegrityError:
                conn.rollback()
            else:
                conn.commit()
    else:
        try:
            cur.executemany(sql, entries)
        except psycopg2.IntegrityError:
            conn.rollback()
        else:
            conn.commit()
    cur.close()
    conn.close()

#%%
# Import stations from the latests scraped file
path = './scraping_data/'
filenames = os.listdir(path)
filenames = [f for f in filenames if os.path.isfile(path+f)]
filenames = sorted(filenames)

insert_stations_sql = open("./sql/insert_stations.sql", "r").read()

def import_stations_from_file(filename):
    f = open(f"{path}{filename}", "r")
    data = json.load(f)
    stations = []

    for place in data['countries'][0]['cities'][0]['places']:
        # stations
        if place['spot'] == True and place['bike'] == False:
            stations.append((
                place['uid'],
                place['name'],
                place['number'],
                f"POINT({place['lat']} {place['lng']})",
                place['bike_racks'],
                place['special_racks']
            ))

    insert_list(insert_stations_sql, stations, single_commit=True)

import_stations_from_file(filenames[-1])

#%%
# Get Bike-Types from api directly and import it into separate table
bike_types = []
api_url = "https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_dv/en/vehicle_types.json"
response = requests.get(api_url)

for bike_type in response.json()['data']['vehicle_types']:
    bike_types.append((
        int(bike_type['vehicle_type_id']), 
        bike_type['vehicle_image'],
        bike_type['name'],
        bike_type['description'],
        bike_type['form_factor'],
        bike_type['rider_capacity'],
        bike_type['propulsion_type']
    ))

f = open("./sql/insert_bike_types.sql", "r")
insert_bike_types_sql = f.read()

insert_list(insert_bike_types_sql, bike_types, single_commit=True)

#%%
# Import all bikes from scraped files into an temporary db-table
# Files get imported in parallel by multiple threads
path = './scraping_data/'
filenames = os.listdir(path)
filenames = [f for f in filenames if os.path.isfile(path+f)]
filenames = sorted(filenames)

insert_bikes_tmp_sql = open("./sql/insert_bike_records.sql", "r").read()

def import_bike_records_from_file(filename):
    print(filename)
    f = open(f"{path}{filename}", "r")
    data = json.load(f)
    time = filename.split('.')[0]
    bike_records = []

    for place in data['countries'][0]['cities'][0]['places']:
        # bikes parked at stations
        if place['spot'] == True and place['bike'] == False:
            position = f"POINT({place['lat']} {place['lng']})"
            station_id = place['uid']
            for bike in place['bike_list']:
                bike_records.append((
                    bike['number'],
                    bike['bike_type'],
                    time,
                    position,
                    station_id
                ))
        # bikes not parked at stations e.g. parked in the free floating area  
        if place['spot'] == False and place['bike'] == True:
            bike_records.append((
                place['bike_list'][0]['number'],
                place['bike_list'][0]['bike_type'],
                time,
                f"POINT({place['lat']} {place['lng']})",
                None
            ))

    insert_list(insert_bikes_tmp_sql, bike_records)

with ThreadPool(processes=os.cpu_count()) as pool:
    pool.map(import_bike_records_from_file, filenames)

#%%
# import unique bikes into separate table
known_bikes_sql = """select bt.id, bt.vehicle_type_id from bikes_tmp bt 
                    group by bt.id, bt.vehicle_type_id;"""
insert_bikes_sql = open("./sql/insert_bikes.sql", "r").read()

conn = psycopg2.connect(
    host=POSTGRES_HOST,
    database=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    port=POSTGRES_PORT)
cur = conn.cursor()

cur.execute(known_bikes_sql)
bikes = [(res[0], res[1]) for res in cur.fetchall()]

for bike in bikes:
    try:
        cur.execute(insert_bikes_sql, bike)
    except psycopg2.IntegrityError:
        conn.rollback()
    else:
        conn.commit()

cur.close()
conn.close()

# %%
def convert_float_to_int(float_value):
    try:
        return int(float_value)
    except:
        return None
# %%
# Calculate trips for every bike out of scraped data
# Bike records getting deleted after successful trip computation
# This code can be restarted after error.
# bike trips are computed in parallel.
conn = psycopg2.connect(
    host=POSTGRES_HOST,
    database=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    port=POSTGRES_PORT)
cur = conn.cursor()

# get all bike ids
cur.execute('select id from bikes group by id;')
bike_ids = cur.fetchall()
bike_ids = [id[0] for id in bike_ids]

cur.close()
conn.close()

insert_ride_sql = open('./sql/insert_rides.sql', 'r').read()
delete_bike_sql = open('./sql/delete_bike_by_time.sql', 'r').read()

def calc_trips_for_bike_ids(bike_id):
    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        port=POSTGRES_PORT)
    cur = conn.cursor()

    sql = f"""select b.* from Bikes_Tmp b 
            where b.id = '{bike_id}' 
            order by b.""time"" asc;"""
    df = gpd.read_postgis(
        sql, 
        conn, 
        geom_col='position', 
        parse_dates='%Y-%m-%d %H:%M:%S')

    old_row = None
    for idx, row in df.iterrows():
        if idx == 0:
            old_row = row
            continue
        
        if(distance.distance(
            (old_row['position'].x, old_row['position'].y), 
            (row['position'].x, row['position'].y)).meters > 0.0):
        
            ride = (
                bike_id,
                old_row['time'].isoformat(),
                row['time'].isoformat(),
                str(old_row['position']),
                str(row['position']),
                convert_float_to_int(old_row.get('station_id', None)),
                convert_float_to_int(row.get('station_id', None)),
            )
            try:
                cur.execute(insert_ride_sql, ride)
                cur.execute(delete_bike_sql, (bike_id, old_row['time'].isoformat()))
            except psycopg2.IntegrityError:
                conn.rollback()
            else:
                conn.commit()
                old_row = row
        else:
            try:
                cur.execute(delete_bike_sql, (bike_id, old_row['time'].isoformat()))
            except psycopg2.IntegrityError:
                conn.rollback()
            else:
                conn.commit()
                old_row = row
    cur.close()
    conn.close()

with ThreadPool(processes=os.cpu_count()) as pool:
    pool.map(calc_trips_for_bike_ids, bike_ids)

#%%
