#%%
import geopandas as gpd
import folium
import psycopg2
import os
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
conn = psycopg2.connect(
    host=POSTGRES_HOST,
    database=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    port=POSTGRES_PORT)

bike_id = 900405
sql = f"""select r.* from rides r 
        where r.bike_id = '{bike_id}' 
        order by r.starting_time;"""
finishing_pos_sql = f"""select r.id, r.finishing_position from rides r
                        where r.bike_id = '{bike_id}'
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

# %%
df
# %%
map = folium.Map(location=[49.451900, 11.076608], zoom_start=12)

for index, row in df.iterrows():
    starting_position = (row['starting_position'].x, row['starting_position'].y)
    finishing_position = (row['finishing_position'].x, row['finishing_position'].y)

    folium.PolyLine(
        [starting_position, finishing_position]
    ).add_to(map)

map

# %%
