# %% 
# imports
import matplotlib.colorbar
import osmnx as ox
import matplotlib
import matplotlib.pyplot as plt
import psycopg2
import os
from dotenv import load_dotenv
import folium
import geopandas as gpd
from collections import Counter
import time
import pickle

#%%
# Setup environment
load_dotenv()

POSTGRES_USER = os.getenv('POSTGRES_USER')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')
POSTGRES_DB = os.getenv('POSTGRES_DB')
POSTGRES_HOST = os.getenv('POSTGRES_HOST')
POSTGRES_PORT = os.getenv('POSTGRES_PORT')

# %% 
# fetch graph of all streets
place_name = 'Nürnberg'

graph = ox.graph_from_place(query=place_name, simplify=False, retain_all=True, network_type='bike')

# %% 
# some statistics of the graph
nodes = ox.graph_to_gdfs(graph, nodes=True, edges=False, node_geometry=True, fill_edge_geometry=False)
edges = ox.graph_to_gdfs(graph, nodes=False)
overall_length = sum(edges["length"])
display(edges.explore())
print(f'number of edges: {len(edges)}')
print(f'length of network: {overall_length} meters')

# %% 
# get rides of one bike over time
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

# %% 
# get rides of one bike over time
conn = psycopg2.connect(
    host=POSTGRES_HOST,
    database=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    port=POSTGRES_PORT)

sql = f"""select r.* from rides r 
            where ST_Distance(r.starting_position, r.finishing_position) < 20000
            and ST_Distance(r.starting_position, r.finishing_position) > 150 
            and r.starting_time::date != '2023-10-10'
            and r.starting_time::date != '2023-10-11'
            order by r.bike_id, r.starting_time;"""
finishing_pos_sql = f"""select r.id, r.finishing_position from rides r
                        where ST_Distance(r.starting_position, r.finishing_position) < 20000
                        and ST_Distance(r.starting_position, r.finishing_position) > 150 
                        and r.starting_time::date != '2023-10-10'
                        and r.starting_time::date != '2023-10-11'
                        order by r.bike_id, r.starting_time;"""

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
# calculate shortest routes and plot on map
trips = df.head(100000)
print(f'{len(trips)} trips')

starting_positions = trips['starting_position']
finishing_positions = trips['finishing_position']

print('start calculating nearest nodes')
start = time.time()
x = [p.x for p in starting_positions]
y = [p.y for p in starting_positions]
starting_node_ids = ox.distance.nearest_nodes(graph, x, y)

x = [p.x for p in finishing_positions]
y = [p.y for p in finishing_positions]
finishing_node_ids = ox.distance.nearest_nodes(graph, x, y)
end = time.time()
print(f'finished calculating nearest nodes in {end - start} seconds')

print('start calculating routes')
start = time.time()
routes = ox.routing.shortest_path(graph, starting_node_ids, finishing_node_ids, cpus=16)
end = time.time()
print(f'finished calculating routes in {end - start} seconds')

# %%
# write calculated routes on file
file = open('calculated_routes.txt', 'wb')
pickle.dump(routes, file)
file.close()

# %%
# load calculated routes from file
with open('calculated_routes.txt', 'rb') as f:
    routes = pickle.load(f)
# %%
# plot routes on a map
map = folium.Map(location=[49.451900, 11.076608], zoom_start=12, crs='EPSG3857')

for route in routes:
    if(route):
        positions = []
        for node_id in route:
            node = nodes.loc[node_id]
            positions.append((node['y'], node['x']))
        folium.PolyLine(positions).add_to(map)

display(map)

# %%
# calculate heat map for traveled edges
cmap = plt.get_cmap('turbo')
edges_counter = Counter()

for route in routes:
    if route:
        start_node = route[0]
        for node in route[1:]:
            edges_counter.update([(start_node, node)])
            start_node = node

map = folium.Map(location=[49.451900, 11.076608], zoom_start=12, crs='EPSG3857')

max_value = edges_counter.most_common(1)[0][1]

for edge, count in edges_counter.items():
    positions = []
    start, finish = edge
    for node_id in edge:
        node = nodes.loc[node_id]
        positions.append((node['y'], node['x']))
    color = matplotlib.colors.to_hex(cmap(count/max_value))
    folium.PolyLine(positions, color=color, tooltip=count).add_to(map)

display(map)

fig, ax = plt.subplots(figsize=(4,0.4))
colorbar = matplotlib.colorbar.ColorbarBase(ax, cmap=cmap, orientation = 'horizontal')
tick = int(max_value/5)
colorbar.set_ticklabels([0, tick, tick*2, tick*3, tick*4, max_value])
plt.show()

# %%
