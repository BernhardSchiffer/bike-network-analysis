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
            except psycopg2.IntegrityError as e:
                conn.rollback()
            else:
                conn.commit()
    else:
        try:
            cur.executemany(sql, entries)
        except psycopg2.IntegrityError as e:
            print(e)
            conn.rollback()
        else:
            conn.commit()
    cur.close()
    conn.close()

#%%
# Import stations from the latests scraped file
filenames = []
path = './scraping_data/data/'
for root, dirs, files in os.walk(path):
    for file in files:
        filenames.append(os.path.join(root, file))

filenames = sorted(filenames)

insert_stations_sql = open("./sql/insert_stations.sql", "r").read()

def import_stations_from_file(filename):
    print(filename)
    f = open(f"{filename}", "r")
    try:
        data = json.load(f)
    except json.JSONDecodeError as e:
        print(f'Exception {e} while parsing {filename}')
        return
    stations = []

    for place in data['countries'][0]['cities'][0]['places']:
        # stations
        if place['spot'] == True and place['bike'] == False:
            stations.append((
                place['uid'],
                place['name'],
                place['number'],
                f"POINT({place['lng']} {place['lat']})",
                place['bike_racks'],
                place['special_racks']
            ))

    insert_list(insert_stations_sql, stations, single_commit=True)

#import_stations_from_file(filenames[-1])

with ThreadPool(processes=os.cpu_count()) as pool:
    pool.map(import_stations_from_file, filenames)

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
filenames = []
path = './scraping_data/data/'
for root, dirs, files in os.walk(path):
    for file in files:
        filenames.append(os.path.join(root, file))

insert_bikes_tmp_sql = open("./sql/insert_bike_records.sql", "r").read()

def import_bike_records_from_file(filename):
    print(filename)
    f = open(f"{filename}", "r")
    try:
        data = json.load(f)
    except json.JSONDecodeError as e:
        print(f'Exception {e} while parsing {filename}')
        return
    time = filename.split('/')[-1][:-5]
    bike_records = []

    for place in data['countries'][0]['cities'][0]['places']:
        # bikes parked at stations
        if place['spot'] == True and place['bike'] == False:
            position = f"POINT({place['lng']} {place['lat']})"
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
                f"POINT({place['lng']} {place['lat']})",
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
cur.execute('select id from bikes_tmp group by id;')
bike_ids = cur.fetchall()
bike_ids = [id[0] for id in bike_ids]

cur.close()
conn.close()

insert_ride_sql = open('./sql/insert_rides.sql', 'r').read()
delete_bike_sql = open('./sql/delete_bike_by_time.sql', 'r').read()

def calc_trips_for_bike_ids(bike_id):
    print(f'bike-id: {bike_id}')
    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        port=POSTGRES_PORT)
    cur = conn.cursor()
    rides = []
    delete_bikes = []

    sql = f"select b.* from Bikes_Tmp b where b.id = '{bike_id}' order by b.""time"" asc;"
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
            rides.append(ride)

        delete_bikes.append((bike_id, old_row['time'].isoformat()))
        old_row = row
    
    try:
        cur.executemany(insert_ride_sql, rides)
        cur.executemany(delete_bike_sql, delete_bikes)
    except psycopg2.IntegrityError as e:
        print(e)
        conn.rollback()
    else:
        conn.commit()
    cur.close()
    conn.close()

#calc_trips_for_bike_ids('900956')

with ThreadPool(processes=os.cpu_count()) as pool:
    pool.map(calc_trips_for_bike_ids, bike_ids)

#%%
filename = './scraping_data/data/2023-06-01/2023-06-01T14:02:37.689260+00:00.json'

#time = filename.split('.')[0]
filename.split('/')[-1][:-5]
