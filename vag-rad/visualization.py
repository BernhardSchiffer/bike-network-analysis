#%%
import geopandas as gpd
import folium
import psycopg2
import os
from dotenv import load_dotenv
import pandas as pd
import matplotlib.pyplot as plt

#%%
# Setup environment
load_dotenv()

POSTGRES_USER = os.getenv('POSTGRES_USER')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')
POSTGRES_DB = os.getenv('POSTGRES_DB')
POSTGRES_HOST = os.getenv('POSTGRES_HOST')
POSTGRES_PORT = os.getenv('POSTGRES_PORT')

#%%
conn = psycopg2.connect(
    host=POSTGRES_HOST,
    database=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    port=POSTGRES_PORT)

bike_id = 901857
sql = f"""select r.* from rides r
        join bikes b on r.bike_id = b.id
        where b.bike_id = '{bike_id}' 
        order by r.starting_time;"""
finishing_pos_sql = f"""select r.id, r.finishing_position from rides r
                        join bikes b on r.bike_id = b.id
                        where b.bike_id = '{bike_id}'
                        and ST_Distance(r.starting_position, r.finishing_position) >= 150
                        order by r.starting_time;"""

df = gpd.read_postgis(
    sql, 
    conn, 
    geom_col='starting_position', 
    parse_dates='%Y-%m-%d %H:%M:%S')

finishing_pos = gpd.read_postgis(
    finishing_pos_sql, 
    conn, 
    geom_col='finishing_position')
df.drop('finishing_position', axis=1, inplace=True)
df = df.merge(finishing_pos, on='id')
conn.close()

map = folium.Map(location=[49.451900, 11.076608], zoom_start=12, crs='EPSG3857')

for index, row in df.iterrows():
    starting_position = (row['starting_position'].y, row['starting_position'].x,)
    finishing_position = (row['finishing_position'].y, row['finishing_position'].x)

    folium.PolyLine(
        [starting_position, finishing_position]
    ).add_to(map)

map

#%%
conn = psycopg2.connect(
    host=POSTGRES_HOST,
    database=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    port=POSTGRES_PORT)

sql = f"""select r.* from rides r 
        where ST_Distance(starting_position, finishing_position) <= 150"""
finishing_pos_sql = f"""select r.id, r.finishing_position from rides r
                        where ST_Distance(starting_position, finishing_position) <= 150
                        limit 10000;"""
df = gpd.read_postgis(
    sql, 
    conn, 
    geom_col='starting_position', 
    parse_dates='%Y-%m-%d %H:%M:%S')

finishing_pos = gpd.read_postgis(
    finishing_pos_sql, 
    conn, 
    geom_col='finishing_position')
df.drop('finishing_position', axis=1, inplace=True)
df = df.merge(finishing_pos, on='id')
conn.close()

map = folium.Map(location=[49.451900, 11.076608], zoom_start=12, crs='EPSG3857')

for index, row in df.iterrows():
    starting_position = (row['starting_position'].y, row['starting_position'].x,)
    finishing_position = (row['finishing_position'].y, row['finishing_position'].x)

    folium.PolyLine(
        [starting_position, finishing_position]
    ).add_to(map)

map

# %%
conn = psycopg2.connect(
    host=POSTGRES_HOST,
    database=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    port=POSTGRES_PORT)

df = pd.read_sql_query('select ST_Distance(r.starting_position, r.finishing_position) as dist from rides r order by dist desc;',con=conn)

conn.close()

df

df['Distances'] = pd.qcut(df['dist'], [0, 0.25, 0.5, 0.75, 1])
print(df.head())

plt.figure();
df['dist'][:].plot.hist(bins=200, logy=False, logx=False)

plt.figure();
df['dist'][:].plot.hist(bins=200, logy=True, logx=True)

# %%
conn = psycopg2.connect(
    host=POSTGRES_HOST,
    database=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    port=POSTGRES_PORT)

df = pd.read_sql_query('select ST_Distance(r.starting_position, r.finishing_position) as dist from rides r where ST_Distance(r.starting_position, r.finishing_position) < 20000 order by dist desc;',con=conn)

conn.close()

df

df['Distances'] = pd.qcut(df['dist'], [0, 0.25, 0.5, 0.75, 1])
print(df.head())

plt.figure();
df['dist'][:].plot.hist(bins=200, logy=True)
# %%

plt.figure();
df['dist'][:].plot.hist(bins=100, logy=True)
