#%%
import psycopg2
import os
import json
import geopandas as gpd
import pandas as pd
from geopy import distance
from multiprocessing.pool import ThreadPool
import requests
from dotenv import load_dotenv
import tarfile
import datetime
import shutil
import csv
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.dates import DayLocator

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
def insert_list(sql, entries, single_commit=False, verbose=False):
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
                if verbose:
                    print(e)
                conn.rollback()
            else:
                conn.commit()
    else:
        try:
            cur.executemany(sql, entries)
        except psycopg2.IntegrityError as e:
            if verbose:
                print(e)
            conn.rollback()
        else:
            conn.commit()
    cur.close()
    conn.close()

def convert_float_to_int(float_value):
    try:
        return int(float_value)
    except:
        return None

# read files from archives
def get_files_in_daterange(path: str, date_start = None, date_end = None):
    file_names = []
    if date_start is None:
        start_date = datetime.datetime.min
    else:
        start_date = datetime.datetime.strptime(date_start, '%Y-%m-%d')

    if date_end is None:
        end_date = datetime.datetime.max
    else:
        end_date = datetime.datetime.strptime(date_end, '%Y-%m-%d')

    timestamp_pattern='%Y-%m-%d.tar.gz'
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith('.tar.gz'):
                file_date = datetime.datetime.strptime(file, timestamp_pattern)
                if start_date <= file_date <= end_date:
                    file_names.append(os.path.join(root, file))
    return file_names

def extract_archive_to_dir(archive: str, directory_path: str):
    with tarfile.open(archive, 'r:*') as r:
        r.extractall(directory_path)

#%%
# Import stations from the latests scraped file
insert_stations_tmp_sql = open("./sql/insert_stations_tmp.sql", "r").read()

def import_stations_from_file(filename):
    print(f"insert station records from: {filename}")
    f = open(f"{filename}", "r")
    try:
        data = json.load(f)
    except json.JSONDecodeError as e:
        print(f'Exception {e} while parsing {filename}')
        return
    
    try:
        places = data['countries'][0]['cities'][0]['places']
    except Exception as e:
        print(f'Error {e} with {filename}. No places found')
        return
    stations = []
    time = filename.split('/')[-1][:-5]

    for place in places:
        # stations
        if place['spot'] == True and place['bike'] == False:
            stations.append((
                place['uid'],
                place['name'],
                place['number'],
                f"POINT({place['lng']} {place['lat']})",
                place['bike_racks'],
                place['special_racks'],
                time
            ))

    insert_list(insert_stations_tmp_sql, stations, single_commit=False)

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
def file_key(filename):
    return filename.split('/')[-1][:-5]
#%%
insert_bikes_tmp_sql = open("./sql/insert_bike_records.sql", "r").read()

def import_bike_records_from_file(filename):
    print(f"insert bike records from: {filename}")
    f = open(f"{filename}", "r")
    try:
        data = json.load(f)
    except json.JSONDecodeError as e:
        print(f'Exception {e} while parsing {filename}')
        return
    time = filename.split('/')[-1][:-5]
    bike_records = []

    try:
        places = data['countries'][0]['cities'][0]['places']
    except Exception as e:
        print(f'Error {e} with {filename}. No places found')
        return

    for place in places:
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
#%%
# Import all bikes from scraped files into an temporary db-table
# Files get imported in parallel by multiple threads
directory = './scraping_data/'
path = './scraping_data/tmp'

file_names = get_files_in_daterange(directory, date_start='2024-01-01', date_end='2024-01-31')
for f in file_names:
    extract_archive_to_dir(f, path)

filenames = []
for root, dirs, files in os.walk(path):
    for file in files:
        filenames.append(os.path.join(root, file))

filenames.sort(key=file_key)

print('insert bike records')
with ThreadPool(processes=os.cpu_count()*2) as pool:
    pool.map(import_bike_records_from_file, filenames)

print('insert station records')
with ThreadPool(processes=os.cpu_count()*2) as pool:
    pool.map(import_stations_from_file, filenames)

def handler(func, path, exc_info):
    print("Inside handler")
    print(exc_info)

shutil.rmtree(path, onerror=handler)

#%%
# import unique stations into separate table
known_stations_sql = """select distinct on (st.station_id, st."name", st.short_name, st."position", st.bike_racks, st.special_racks) st.station_id, st."name", st.short_name, st."position", st.bike_racks, st.special_racks, st.created_at 
                        from stations_tmp st
                        order by st.station_id, st."name", st.short_name, st."position", st.bike_racks, st.special_racks, st.created_at asc;"""
insert_stations_sql = open("./sql/insert_stations.sql", "r").read()

conn = psycopg2.connect(
    host=POSTGRES_HOST,
    database=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    port=POSTGRES_PORT)
cur = conn.cursor()

cur.execute(known_stations_sql)
stations = [(res[0], res[1], res[2], res[3], res[4], res[5], res[6]) for res in cur.fetchall()]

insert_list(insert_stations_sql, stations, single_commit=True)

# delete unnecessary entires in stations_tmp
delete_stations_tmp = f"""delete from stations_tmp
                        where station_id in ({', '.join(map(str, [s[0] for s in stations]))})"""

try:
    cur.execute(delete_stations_tmp)
except psycopg2.IntegrityError as e:
    print(e)
    conn.rollback()
else:
    conn.commit()

cur.close()
conn.close()

#%%
# import unique bikes into separate table
known_bike_ids_sql = """select distinct bt.id
                        from bikes_tmp bt;"""
insert_bikes_sql = open("./sql/insert_bikes.sql", "r").read()

conn = psycopg2.connect(
    host=POSTGRES_HOST,
    database=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    port=POSTGRES_PORT)
cur = conn.cursor()

cur.execute(known_bike_ids_sql)
bike_ids = [res[0] for res in cur.fetchall()]

cur.close()
conn.close()

def insert_unique_bikes(bike_id):
    print(bike_id)

    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        port=POSTGRES_PORT)

    bikes_df = pd.read_sql(
        f"""select bt.id, bt.vehicle_type_id, bt."time"
            from bikes_tmp bt 
            where bt.id = '{bike_id}'
            order by bt."time" asc;""", 
        conn,
        parse_dates='%Y-%m-%d %H:%M:%S')

    conn.close()

    tmp_df = bikes_df.drop_duplicates(subset=['id', 'vehicle_type_id'], keep='first')
    unique_bikes = [(t[0], t[1], t[2]) for t in tmp_df.values]

    insert_list(insert_bikes_sql, unique_bikes, single_commit=True)

print('insert unique bike records')
with ThreadPool(processes=os.cpu_count()*2) as pool:
    pool.map(insert_unique_bikes, bike_ids)

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
cur.execute("""select bt.id, count(bt.id) as anzahl
                from bikes_tmp bt
                group by bt.id
                order by anzahl desc""")
bike_ids = cur.fetchall()
bike_ids = [id[0] for id in bike_ids]

print(bike_ids)

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
    rides = []
    delete_bikes = []

    sql = f"select b.* from Bikes_Tmp b where b.id = '{bike_id}' order by b.""time"" asc;"
    df = gpd.read_postgis(
        sql, 
        conn, 
        geom_col='position', 
        parse_dates='%Y-%m-%d %H:%M:%S')
    
    stations_df = gpd.read_postgis(
        f"select s.* from Stations s", 
        conn, 
        geom_col='position', 
        parse_dates='%Y-%m-%d %H:%M:%S')
    
    bike_df = pd.read_sql(
        f"select b.* from Bikes b where b.bike_id = '{bike_id}'", 
        conn,
        parse_dates='%Y-%m-%d %H:%M:%S')
    
    conn.close()

    old_row = None
    for idx, row in df.iterrows():
        if idx == 0:
            old_row = row
            continue
        
        if(distance.distance(
            (old_row['position'].x, old_row['position'].y), 
            (row['position'].x, row['position'].y)).meters > 0.0):

            station_id_start = convert_float_to_int(old_row.get('station_id', None))
            station_id_end = convert_float_to_int(row.get('station_id', None))

            if station_id_start is not None:
                filtered = stations_df.query(f'station_id == {station_id_start} and first_seen <= "{old_row["time"].isoformat()}"')
                station_id_start = filtered.sort_values(by=['first_seen'], ascending=True).tail(1)['id'].item()
            if station_id_end is not None:
                filtered = stations_df.query(f'station_id == {station_id_end} and first_seen <= "{row["time"].isoformat()}"')
                station_id_end = filtered.sort_values(by=['first_seen'], ascending=True).tail(1)['id'].item()
        
            filtered = bike_df.query(f'first_seen <= "{old_row["time"].isoformat()}"')
            unique_bike_id = filtered.sort_values(by=['first_seen'], ascending=True).tail(1)['id'].item()

            ride = (
                unique_bike_id,
                old_row['time'].isoformat(),
                row['time'].isoformat(),
                str(old_row['position']),
                str(row['position']),
                station_id_start,
                station_id_end
            )
            rides.append(ride)

        delete_bikes.append((bike_id, old_row['time'].isoformat()))
        old_row = row
    
    insert_list(insert_ride_sql, rides, single_commit=True, verbose=True)
    insert_list(delete_bike_sql, delete_bikes)

#calc_trips_for_bike_ids('900005')

with ThreadPool(processes=os.cpu_count()*2) as pool:
    pool.map(calc_trips_for_bike_ids, bike_ids)

#%%
conn = psycopg2.connect(
    host=POSTGRES_HOST,
    database=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    port=POSTGRES_PORT)
bike_id = '900005'

bike_df = pd.read_sql(
    f"select b.* from Bikes b where b.bike_id = '{bike_id}'", 
    conn,
    parse_dates='%Y-%m-%d %H:%M:%S')

conn.close()

bike_df
#%%
filtered = bike_df.query(f'first_seen <= "2023-10-23 13:06:02.819823"')
filtered.sort_values(by=['first_seen'], ascending=True).tail(1)['id'].item()

# %%
# get unique bikes per day
def get_bikes_from_file(filename):
    #print(f"get bikes from: {filename}")
    f = open(f"{filename}", "r")
    try:
        data = json.load(f)
    except json.JSONDecodeError as e:
        print(f'Exception {e} while parsing {filename}')
        return
    
    bike_records = set()

    try:
        places = data['countries'][0]['cities'][0]['places']
    except Exception as e:
        print(f'Error {e} with {filename}. No places found')
        return

    for place in places:
        # bikes parked at stations
        if place['spot'] == True and place['bike'] == False:
            for bike in place['bike_list']:
                bike_records.add(bike['number'])
        # bikes not parked at stations e.g. parked in the free floating area  
        if place['spot'] == False and place['bike'] == True:
            bike_records.add(place['bike_list'][0]['number'])

    return bike_records

def handler(func, path, exc_info):
    print("Inside handler")
    print(exc_info)

directory = './scraping_data/'

with open('available_bikes_per_day.csv', 'w', newline='') as csvfile:
    fieldnames = ['date', 'bikes']
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=';')
    writer.writeheader()

dates = pd.date_range('2023-05-22', '2023-08-31')
for date in dates:
    print(date.date())
    path = f'{directory}{date.date()}'
    date_string = str(date.date())
    file = get_files_in_daterange(directory, date_start=date_string, date_end=date_string)
    if len(file) <= 0:
        print(f'file for {date.date()} not found')
        continue
    else:
        extract_archive_to_dir(file[0], path)

    filenames = []
    for root, dirs, files in os.walk(path):
        for file in files:
            filenames.append(os.path.join(root, file))

    unique_bikes = set()
    with ThreadPool() as pool:
        for bikes in pool.map(get_bikes_from_file, filenames, chunksize=60):
            if bikes is not None:
                unique_bikes.update(bikes)

    with open('available_bikes_per_day.csv', 'a', newline='') as csvfile:
        fieldnames = ['date', 'bikes']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=';')
        writer.writerows([
            {'date': date.date(), 'bikes': ','.join(unique_bikes)}
        ])

    shutil.rmtree(path, onerror=handler)

# %%
# read csv
def get_unique_bikes_in_date_range(dict, date_start, date_end):
    unique_bikes = []

    dates = pd.date_range(date_start, date_end)
    for date in dates:
        try:
            unique_bikes.append(len(dict[date.date().isoformat()]))
        except:
            pass
            
    return unique_bikes

with open('available_bikes_per_day.csv', 'r', newline='') as csvfile:
    fieldnames = ['date', 'bikes']
    reader = csv.DictReader(csvfile, fieldnames=fieldnames, delimiter=';')
    # skip header
    next(reader, None)

    available_bikes = {}
    for row in reader:
        bikes = row['bikes'].split(',')
        available_bikes[row['date']] = bikes

    monthly_available_bikes = {}
    for month_start, month_end in zip(pd.date_range('2023-01', '2024-02', freq='MS'), pd.date_range('2023-01', '2024-02', freq='M')):
        monthly_available_bikes[f'{month_start.year} {month_start.date().strftime("%B")}'] = get_unique_bikes_in_date_range(available_bikes, month_start, month_end)

    monthly_available_bikes = dict((k, v) for k, v in monthly_available_bikes.items() if len(v) > 0)

    for k, v in monthly_available_bikes.items():
        print(f'average available bikes in {k}: {np.mean(v)}')
        print(f'median available bikes in {k}: {np.median(v)}')
    
    fig, ax = plt.subplots()
    ax.boxplot(monthly_available_bikes.values())
    ax.set_xticklabels(monthly_available_bikes.keys())
# %%
x_data = []
y_data = []
for date in pd.date_range('2023-01', '2024-02', freq='D'):
    x_data.append(date.date().isoformat())
    b = available_bikes.get(date.date().isoformat(), None)
    if b is None:
        y_data.append(None)
    else:
        y_data.append(len(b))

f, ax = plt.subplots(1)
plt.plot(x_data, y_data)
plt.xticks(rotation=45)
ax.set_ylim(ymin=0, ymax=max([x for x in y_data if x is not None]) + 200)
ax.xaxis.set_major_locator(DayLocator(interval=7))
ax.xaxis.set_minor_locator(DayLocator())
fig.tight_layout()
plt.show()
# %%
