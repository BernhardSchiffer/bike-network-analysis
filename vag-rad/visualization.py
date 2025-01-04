#%%
import geopandas as gpd
import folium
from folium.plugins import HeatMap
from numpy import size
import psycopg2
import os
from dotenv import load_dotenv
import pandas as pd
import matplotlib.pyplot as plt
from  matplotlib.ticker import FuncFormatter
import datetime

#%%
# Setup environment
load_dotenv()

POSTGRES_USER = os.getenv('POSTGRES_USER')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')
POSTGRES_DB = os.getenv('POSTGRES_DB')
POSTGRES_HOST = os.getenv('POSTGRES_HOST')
POSTGRES_PORT = os.getenv('POSTGRES_PORT')

# %% 
# plot rides of one bike over time
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
                        and ST_Distance(r.starting_position, r.finishing_position) <= 20000
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

#%% plotte 10k an fahrten die kuerzer als 150m sind (GPS Ungenauigkeiten)
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
df['dist'][:].plot.hist(bins=200, logy=True, logx=True)

# %%
conn = psycopg2.connect(
    host=POSTGRES_HOST,
    database=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    port=POSTGRES_PORT)

df = pd.read_sql_query('select ST_Distance(r.starting_position, r.finishing_position) as dist from rides r where ST_Distance(r.starting_position, r.finishing_position) < 30000 order by dist desc;',con=conn)

conn.close()

df

df['Distances'] = pd.qcut(df['dist'], [0, 0.25, 0.5, 0.75, 1])
print(df.head())

# plotten in 100m schritten
plt.figure();
df['dist'][:].plot.hist(bins=300, logy=True)
# %% plotten in 200m schritten

plt.figure();
df['dist'][:].plot.hist(bins=150, logy=True)

# %%
conn = psycopg2.connect(
    host=POSTGRES_HOST,
    database=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    port=POSTGRES_PORT)

df = pd.read_sql_query("""select ST_Distance(r.starting_position, r.finishing_position) as dist from rides r 
                       where ST_Distance(r.starting_position, r.finishing_position) < 30000 
                       and ST_Distance(r.starting_position, r.finishing_position) > 150 
                       order by dist desc;"""
                       ,con=conn)

conn.close()
df

plt.figure();
df['dist'][:].plot.hist(bins=300, logy=False)

# %%
conn = psycopg2.connect(
    host=POSTGRES_HOST,
    database=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    port=POSTGRES_PORT)

df_rides_per_day = pd.read_sql_query("""select r.starting_time::date, count(*) from rides r 
                        where ST_Distance(r.starting_position, r.finishing_position) < 20000
                        and ST_Distance(r.starting_position, r.finishing_position) > 150 
                        and not (r.starting_time::date = '2023-10-10'
                        or r.starting_time::date = '2023-10-11')
                        group by r.starting_time::date
                        order by r.starting_time::date;"""
                       ,con=conn)

conn.close()
df_rides_per_day
# %%
# calculating ticks on x axis
d1 = df_rides_per_day['starting_time'].values[0]
print(f'first date in dataframe: {d1.isoformat()}')
d1 = d1 - datetime.timedelta(days=d1.weekday())
print(f'monday before:\t\t {d1.isoformat()}')

d2 = df_rides_per_day['starting_time'].values[-1]
print(f'last date in dataframe:\t {d2.isoformat()}')
d2 = d2 + datetime.timedelta(days=(7 - d2.weekday()))
print(f'monday after:\t\t {d2.isoformat()}')

x_ticks = pd.date_range(start=d1, end=d2, freq=datetime.timedelta(days=7)).tolist()

ax = df_rides_per_day.plot(x='starting_time', y='count', linestyle='--', marker='o', grid=True, figsize=(20, 4))
ax.set_xlabel('days')
ax.set_ylabel('number of rides per day')
plt.xticks(x_ticks, rotation=45)

plt.show()

# %%
# some stats about the ride distribution
print(f'min:\t {df_rides_per_day["count"].min()} on {df_rides_per_day["starting_time"][df_rides_per_day["count"].idxmin()].isoformat()}')
print(f'max:\t {df_rides_per_day["count"].max()} on {df_rides_per_day["starting_time"][df_rides_per_day["count"].idxmax()].isoformat()}')
print(f'mean:\t {df_rides_per_day["count"].mean()}')
print(f'median:\t {df_rides_per_day["count"].median()}')

df_rides_per_day.boxplot()
plt.show()

# %% 
conn = psycopg2.connect(
    host=POSTGRES_HOST,
    database=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    port=POSTGRES_PORT)

sql = """select r.* from rides r 
        where ST_Distance(r.starting_position, r.finishing_position) < 20000
        and ST_Distance(r.starting_position, r.finishing_position) > 150 
        and r.starting_time::date != '2023-10-10'
        and r.starting_time::date != '2023-10-11'
        order by r.starting_time;"""
finishing_pos_sql = """select r.id, r.finishing_position from rides r
                        where ST_Distance(r.starting_position, r.finishing_position) < 20000
                        and ST_Distance(r.starting_position, r.finishing_position) > 150 
                        and r.starting_time::date != '2023-10-10'
                        and r.starting_time::date != '2023-10-11'
                        order by r.starting_time;"""
df_start_and_end_points = gpd.read_postgis(
    sql, 
    conn, 
    geom_col='starting_position', 
    parse_dates='%Y-%m-%d %H:%M:%S')

finishing_pos = gpd.read_postgis(
    finishing_pos_sql, 
    conn, 
    geom_col='finishing_position')
df_start_and_end_points.drop('finishing_position', axis=1, inplace=True)
df_start_and_end_points = df_start_and_end_points.merge(finishing_pos, on='id')

df_stations = gpd.read_postgis(
    """select s.* from stations s
        order by s.first_seen desc""", 
    conn, 
    geom_col='position', 
    parse_dates='%Y-%m-%d %H:%M:%S')

conn.close()
df_start_and_end_points
# %%
starting_positions = []
finishing_positions = [] 

for index, row in df_start_and_end_points.iterrows():
    starting_position = [row['starting_position'].y, row['starting_position'].x]
    finishing_position = [row['finishing_position'].y, row['finishing_position'].x]
    starting_positions.append(starting_position)
    finishing_positions.append(finishing_position)

# %% plot heatmap of finishing positions
map = folium.Map(location=[49.451900, 11.076608], zoom_start=12, crs='EPSG3857')
for idx, row in df_stations.iterrows():
    folium.CircleMarker([row['position'].y, row['position'].x], radius=1, color='black').add_to(map)
HeatMap(finishing_positions, radius=4, blur=5, overlay=True).add_to(map)

map

# %%
conn = psycopg2.connect(
    host=POSTGRES_HOST,
    database=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    port=POSTGRES_PORT)

df_rides_group_by_hour = pd.read_sql_query("""select date_part('hour', r.starting_time) as hour, count(*) as count from rides r
                where ST_Distance(r.starting_position, r.finishing_position) < 20000
                and ST_Distance(r.starting_position, r.finishing_position) > 150 
                and r.starting_time::date != '2023-10-10'
                and r.starting_time::date != '2023-10-11'
                group by date_part('hour', r.starting_time);"""
                ,con=conn)

df_hours = pd.read_sql_query("""select date_part('hour', hours.h) as hour, count(*) as count from 
                    (select distinct(date_trunc('hour', r.starting_time)) as h from rides r
                    where ST_Distance(r.starting_position, r.finishing_position) < 20000
                    and ST_Distance(r.starting_position, r.finishing_position) > 150 
                    and r.starting_time::date != '2023-10-10'
                    and r.starting_time::date != '2023-10-11') hours 
                group by date_part('hour', hours.h);"""
                ,con=conn)

conn.close()
df_rides_group_by_hour
df_hours.set_index('hour')
#%%
tmp = []

for idx, values in df_rides_group_by_hour.iterrows():
    normalized_value = values[1] / df_hours['count'][values[0]]
    tmp.append({'hour': values[0], 'count': normalized_value})

df_rides_group_by_hour_normalized = pd.DataFrame(data=tmp)
# %%
plt.figure();
ax = df_rides_group_by_hour_normalized.plot.bar(x='hour', y='count', grid=True, figsize=(7, 5))
ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: int(x)))
plt.xticks(rotation=90, size=6)
plt.show()

# %%
conn = psycopg2.connect(
    host=POSTGRES_HOST,
    database=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    port=POSTGRES_PORT)

df_rides_group_by_hour_per_day = pd.read_sql_query("""select date_trunc('hour', r.starting_time) as hour, count(*) as count from rides r
                where ST_Distance(r.starting_position, r.finishing_position) < 20000
                and ST_Distance(r.starting_position, r.finishing_position) > 150 
                and r.starting_time::date != '2023-10-10'
                and r.starting_time::date != '2023-10-11'
                group by date_trunc('hour', r.starting_time);"""
                ,con=conn)

conn.close()
df_rides_group_by_hour_per_day

# %%
plt.figure();
ax = df_rides_group_by_hour_per_day[:][204:700].plot.bar(x='hour', y='count', figsize=(25, 5), width=1, align='edge')
plt.xticks(rotation=90, size=6)
plt.show()
# %%
