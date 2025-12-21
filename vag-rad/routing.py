# %%
# imports 
import os
import pickle
import time
from collections import Counter

import folium
import geopandas as gpd
import leafmap.foliumap as leafmap
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import osmnx as ox
import osmnx.distance
import osmnx.routing
import pandas as pd
import psycopg2
import shapely
from dotenv import load_dotenv
from tqdm import tqdm

from utils.graph_types import Route
from utils.overpass_utils import fetch_city_polygon
from utils.utils import (
    buffer_in_meters,
    correct_routes,
    parse_junction_osmid,
    parse_old_edge_key,
    route_to_edge_ids,
)
from utils.visualization_utils import (
    compare_ebc_values,
    diff_render_order_func,
    get_ebc_values_from_gpkg,
    plot_edge_count,
)

# increase to parallelize route calculations
CPU_COUNT = 1

# %%
# helper functions
# plot routes on a map
def plot_routes(routes: list[Route | None], graph: nx.MultiDiGraph, with_markers: bool = False) -> leafmap.Map:
    nodes = ox.graph_to_gdfs(graph, nodes=True, edges=False, node_geometry=True, fill_edge_geometry=False)
    map = leafmap.Map(location=[49.451900, 11.076608], zoom_start=12, crs='EPSG3857')

    for idx, route in enumerate(routes):
        if with_markers:
            start_node = nodes.loc[route[0]]
            end_node = nodes.loc[route[-1]]
            folium.Marker((start_node['y'], start_node['x']), 'start').add_to(map)
            folium.Marker((end_node['y'], end_node['x']), 'destination').add_to(map)
        if route:
            positions = []
            for node_id in route:
                node = nodes.loc[node_id]
                positions.append((node['y'], node['x']))
            folium.PolyLine(positions, idx).add_to(map)

    return map

# calculate heat map for traveled edges
def get_edge_count(routes: list[Route | None], graph: nx.MultiDiGraph) -> list[float]:
    edges_counter = Counter()

    # initialize all edges with 0
    for edge in graph.edges(keys=True):
        edges_counter[edge] = 0

    for route in tqdm(routes, desc='count edges', unit='route'):
        edges = route_to_edge_ids(route)
        edges_counter.update(edges)
    
    count_values = []
    for u, v, key in graph.edges(keys=True):
        try:
            count_value = edges_counter[(u, v, key)]
            count_values.append(count_value)
        except KeyError:
            count_values.append(0.0)
    return count_values

#%%
# Setup environment
load_dotenv()

POSTGRES_USER = os.getenv('POSTGRES_USER')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')
POSTGRES_DB = os.getenv('POSTGRES_DB')
POSTGRES_HOST = os.getenv('POSTGRES_HOST')
POSTGRES_PORT = os.getenv('POSTGRES_PORT')

# %% 
# load weighted graph from file
graph = ox.load_graphml('simplified_bicycle_graph.graphml', 
                        node_dtypes={'osmid': str}, 
                        edge_dtypes={
                            'weight': float, 
                            'shifted_geometry': lambda x: shapely.from_wkt(x), 
                            'osmid': parse_junction_osmid, 
                            'penalty': float, 
                            'slope_percentage': float, 
                            'length': float, 
                            'old_edge_key': parse_old_edge_key
                            })

# some statistics of the graph
nodes = ox.graph_to_gdfs(graph, nodes=True, edges=False, node_geometry=True, fill_edge_geometry=False)
edges = ox.graph_to_gdfs(graph, nodes=False)

print(f'number of edges: {len(edges)}')
print(f'length of network: {sum(edges["length"])} meters')

# %% 
# get rides of all bikes over time
limit = 100000
minimal_distance = 250
max_distance = 20000
max_duration = 60 * 60

conn = psycopg2.connect(
    host=POSTGRES_HOST,
    database=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    port=POSTGRES_PORT)

sql = f"""select r.* from rides r 
            where ST_Distance(r.starting_position, r.finishing_position) < {max_distance}
            and ST_Distance(r.starting_position, r.finishing_position) > {minimal_distance} 
            and EXTRACT(EPOCH FROM (r.finishing_time - r.starting_time)) <= {max_duration} 
            and r.starting_time::date != '2023-10-10'
            and r.starting_time::date != '2023-10-11'
            order by r.bike_id, r.starting_time
            limit {limit};"""
finishing_pos_sql = f"""select r.id, r.finishing_position from rides r
                        where ST_Distance(r.starting_position, r.finishing_position) < {max_distance}
                        and ST_Distance(r.starting_position, r.finishing_position) > {minimal_distance} 
                        and EXTRACT(EPOCH FROM (r.finishing_time - r.starting_time)) <= {max_duration} 
                        and r.starting_time::date != '2023-10-10'
                        and r.starting_time::date != '2023-10-11'
                        order by r.bike_id, r.starting_time
                        limit {limit};"""

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
# load all rentals from file
df_all = pd.read_csv('vag-rad-data/processed/All_Ausleihen_Kundendetails.csv')

df_all['starting_position'] = shapely.from_wkt(df_all['starting_position'])
df_all['finishing_position'] = shapely.from_wkt(df_all['finishing_position'])

df_all = gpd.GeoDataFrame(df_all, geometry='starting_position', crs='EPSG:4326')

# filter out trips that begin or end outside of the graph area
place_name = 'Nürnberg'
nbg_area = fetch_city_polygon(place_name)

graph_polygon = buffer_in_meters(nbg_area, 5000)

starting_positions_in_graph: list = gpd.GeoSeries(df_all['starting_position'], crs='EPSG:4326').sindex.query(graph_polygon, predicate='contains')
finishing_positions_in_graph: list = gpd.GeoSeries(df_all['finishing_position'], crs='EPSG:4326').sindex.query(graph_polygon, predicate='contains')

valid_indices = set(starting_positions_in_graph).intersection(set(finishing_positions_in_graph))
df = df_all.iloc[list(valid_indices)].reset_index(drop=True)

df

# %%
chunk_size = 100000
for i in range(0, len(df), chunk_size):
    # calculate shortest routes
    trips = df[i:i+chunk_size]
    print(f'computed {i}/{len(df)} trips for shortest routes')

    starting_positions = trips['starting_position']
    finishing_positions = trips['finishing_position']

    print('start calculating nearest nodes')
    start = time.time()
    x = [p.x for p in starting_positions]
    y = [p.y for p in starting_positions]
    starting_node_ids = osmnx.distance.nearest_nodes(graph, x, y)

    x = [p.x for p in finishing_positions]
    y = [p.y for p in finishing_positions]
    finishing_node_ids = osmnx.distance.nearest_nodes(graph, x, y)
    end = time.time()
    print(f'finished calculating nearest nodes in {end - start} seconds')

    print('start calculating routes')
    start = time.time()
    shortest_routes = ox.shortest_path(graph, starting_node_ids, finishing_node_ids, cpus=CPU_COUNT, weight='length')
    end = time.time()
    print(f'finished calculating routes in {end - start} seconds')

    # append calculated routes to file
    file = open('calculated_shortest_routes.pickle', 'ab')
    pickle.dump(shortest_routes, file)
    file.close()

# %%
chunk_size = 100000
for i in range(0, len(df), chunk_size):
    # calculate trips based on the new weight metric based on osm features
    trips = df[i:i+chunk_size]
    print(f'computed {i}/{len(df)} trips for shortest routes')

    starting_positions = trips['starting_position']
    finishing_positions = trips['finishing_position']

    print('start calculating nearest nodes')
    start = time.time()
    x = [p.x for p in starting_positions]
    y = [p.y for p in starting_positions]
    starting_node_ids = osmnx.distance.nearest_nodes(graph, x, y)

    x = [p.x for p in finishing_positions]
    y = [p.y for p in finishing_positions]
    finishing_node_ids = osmnx.distance.nearest_nodes(graph, x, y)
    end = time.time()
    print(f'finished calculating nearest nodes in {end - start} seconds')

    print('start calculating routes')
    start = time.time()
    routes = osmnx.routing.shortest_path(graph, starting_node_ids, finishing_node_ids, cpus=CPU_COUNT, weight='weight')
    end = time.time()
    print(f'finished calculating routes in {end - start} seconds')

    # write calculated routes on file
    file = open('calculated_routes.pickle', 'ab')
    pickle.dump(routes, file)
    file.close()

# %%
# load calculated routes from file
routes = []
with open('calculated_routes.pickle', 'rb') as f:
    while 1:
        try:
            routes.extend(pickle.load(f))
        except EOFError:
            break
print(f'loaded {len(routes)} routes from file')

# load calculated routes from file
shortest_routes = []
with open('calculated_shortest_routes.pickle', 'rb') as f:
    while 1:
        try:
            shortest_routes.extend(pickle.load(f))
        except EOFError:
            break
print(f'loaded {len(shortest_routes)} shortest routes from file')

# %%
# calculate length of routes
df_all['shortest_route_length'] = np.nan
df_all['route_length'] = np.nan

calculated_routes_idx = 0
for idx, _ in tqdm(df_all.iterrows(), desc='calculate route lengths', total=len(df_all), unit='route'):
    if idx not in valid_indices:
        continue

    r = shortest_routes[calculated_routes_idx]
    if correct_routes(r):
        r = route_to_edge_ids(r)
        route_length = sum([graph.edges[edge]['length'] for edge in r])
        df_all.at[idx, 'shortest_route_length'] = route_length
    else:
        df_all.at[idx, 'shortest_route_length'] = np.nan

    r = routes[calculated_routes_idx]
    if correct_routes(r):
        r = route_to_edge_ids(r)
        route_length = sum([graph.edges[edge]['length'] for edge in r])
        df_all.at[idx, 'route_length'] = route_length
    else:
        df_all.at[idx, 'route_length'] = np.nan
    
    calculated_routes_idx = calculated_routes_idx + 1

# %%
df_all

# %%
# plot heatmap of calculated routes
counts_values_shortest = get_edge_count([ s for s in shortest_routes if correct_routes(s)], graph)
plot_edge_count(graph, counts_values_shortest, expanded=True, cmap=plt.get_cmap('turbo')).to_file(filename='graph.gpkg', layer='shortest_path_usage', driver='GPKG')

counts_values_weighted = get_edge_count([ r for r in routes if correct_routes(r)], graph)
plot_edge_count(graph, counts_values_weighted, expanded=True, cmap=plt.get_cmap('turbo')).to_file(filename='graph.gpkg', layer='weighted_path_usage', driver='GPKG')

# %%
# plot histogram of route lengths of shortest routes
route_lengths = df_all['shortest_route_length'].dropna().tolist()

print(f'average length of shortest routes: {np.average(route_lengths)} meters')
print(f'median length of shortest routes: {np.median(route_lengths)} meters')
print(f'max length of shortest routes: {max(route_lengths)} meters')
print(f'min length of shortest routes: {min(route_lengths)} meters')
print('---')

print(f'75 percentile: {np.percentile(route_lengths, 75)}')
print(f'85 percentile: {np.percentile(route_lengths, 85)}')
print(f'95 percentile: {np.percentile(route_lengths, 95)}')
print(f'99 percentile: {np.percentile(route_lengths, 99)}')

# get bins for every 50 meters
max_distance = 10000
distance_step = 50
bins = np.arange(0, max_distance + distance_step, distance_step)

# show histogram of route lengths shorter than 5000 meters
plt.figure(figsize=(10, 6))
plt.hist([l for l in route_lengths if l < max_distance], bins=bins, color='#0072B2')
plt.title('Histogram of Shortest Route Lengths for VAG-Rad Rentals')
plt.xlabel('Route Length (meters)')
plt.ylabel('Number of Rentals')
plt.xticks(range(0, 10001, 500), rotation=45)
plt.yticks(range(0, 90001, 10000))
plt.grid()
plt.savefig('shortest_route_lengths_histogram.png', dpi=300)

# group routes by length
length_groups = {'0-500': 0, '500-1000': 0, '1000-2000': 0, '2000-5000': 0, '5000-10000': 0, '10000-20000': 0, '20000-50000': 0, '50000+': 0}

for route_length in route_lengths:
    if route_length < 500:
        length_groups['0-500'] += 1
    elif route_length < 1000:
        length_groups['500-1000'] += 1
    elif route_length < 2000:
        length_groups['1000-2000'] += 1
    elif route_length < 5000:
        length_groups['2000-5000'] += 1
    elif route_length < 10000:
        length_groups['5000-10000'] += 1
    elif route_length < 20000:
        length_groups['10000-20000'] += 1
    elif route_length < 50000:
        length_groups['20000-50000'] += 1
    else:
        length_groups['50000+'] += 1

print('---')
print('Route length distribution for shortest routes:')
for group, count in length_groups.items():
    print(f'{group} meters: {count} routes ({count / len(route_lengths):.2%})')

# %%
# plot histogram of route lengths of weighted routes
route_lengths = df_all['route_length'].dropna().tolist()

print(f'average length of weighted routes: {np.average(route_lengths)} meters')
print(f'median length of weighted routes: {np.median(route_lengths)} meters')
print(f'max length of weighted routes: {max(route_lengths)} meters')
print(f'min length of weighted routes: {min(route_lengths)} meters')
print('---')

print(f'75 percentile: {np.percentile(route_lengths, 75)}')
print(f'85 percentile: {np.percentile(route_lengths, 85)}')
print(f'95 percentile: {np.percentile(route_lengths, 95)}')
print(f'99 percentile: {np.percentile(route_lengths, 99)}')

# get bins for every 50 meters
max_distance = 10000
distance_step = 50
bins = np.arange(0, max_distance + distance_step, distance_step)

# show histogram of route lengths shorter than 5000 meters
plt.figure(figsize=(10, 6))
plt.hist([l for l in route_lengths if l < max_distance], bins=bins, color='#0072B2')
plt.title('Histogram of Route Lengths for VAG-Rad Rentals with Route Choice Model')
plt.xlabel('Route Length (meters)')
plt.ylabel('Number of Rentals')
plt.xticks(range(0, 10001, 500), rotation=45)
plt.yticks(range(0, 90001, 10000))
plt.grid()
plt.savefig('weighted_route_lengths_histogram.png', dpi=300)

# group routes by length
length_groups = {'0-500': 0, '500-1000': 0, '1000-2000': 0, '2000-5000': 0, '5000-10000': 0, '10000-20000': 0, '20000-50000': 0, '50000+': 0}

for route_length in route_lengths:
    if route_length < 500:
        length_groups['0-500'] += 1
    elif route_length < 1000:
        length_groups['500-1000'] += 1
    elif route_length < 2000:
        length_groups['1000-2000'] += 1
    elif route_length < 5000:
        length_groups['2000-5000'] += 1
    elif route_length < 10000:
        length_groups['5000-10000'] += 1
    elif route_length < 20000:
        length_groups['10000-20000'] += 1
    elif route_length < 50000:
        length_groups['20000-50000'] += 1
    else:
        length_groups['50000+'] += 1

print('---')
print('Route length distribution for weighted routes:')
for group, count in length_groups.items():
    print(f'{group} meters: {count} routes ({count / len(route_lengths):.2%})')

# %%
max_distance = 10000
distance_step = 50
bins = np.arange(0, max_distance + distance_step, distance_step)

plt.figure(figsize=(10, 6))
plt.hist([l for l in df_all['shortest_route_length'].dropna().tolist() if l < max_distance], bins=bins, color='#1f78b4', alpha=0.5)
plt.hist([l for l in df_all['route_length'].dropna().tolist() if l < max_distance], bins=bins, color='#33a02c', alpha=0.5)
plt.title('Histogram of Route Lengths for VAG-Rad Rentals')
plt.xlabel('Route Length (meters)')
plt.ylabel('Number of Rentals')
plt.xticks(range(0, 10001, 500), rotation=45)
plt.yticks(range(0, 90001, 10000))
plt.legend(['Shortest Routes', 'Weighted Routes'], loc='upper right')
plt.grid()
plt.savefig('combined_route_lengths_histogram.png', dpi=300)
# %%
def get_route_geometry(route: Route, graph: nx.MultiDiGraph) -> shapely.LineString:
    edge_geometries = []
    edges = route_to_edge_ids(route)
    for edge in edges:
        edge_data = graph.edges[edge]
        geom = edge_data.get('shifted_geometry', None)
        if geom is None:
            raise ValueError(f'Edge {edge} has no shifted_geometry')
        edge_geometries.append(geom)
    # combine all edge geometries into one linestring
    route_geometry = shapely.ops.linemerge(edge_geometries)
    return route_geometry

df_all[df_all['shortest_route_length'] > 10000.0]
# %%
# show routes that are longer than 20 km
route_geometries = []
for idx, route in enumerate(routes):
    if not correct_routes(route):
        continue
    r = route_to_edge_ids(route)
    route_length = sum([graph.edges[edge]['length'] for edge in r])
    if route_length > 18000 and route_length < 25000:
        route_geometry = get_route_geometry(route, graph)
        route_geometries.append(route_geometry)
        if len(route_geometries) >= 10:
            break

for idx, tmp in enumerate(route_geometries):
    gpd.GeoDataFrame({'geometry': [tmp]}, geometry='geometry', crs='EPSG:4326').to_file(filename='long_routes.gpkg', layer=f'route_{idx}', driver='GPKG')
# %%
routes = {idx: r for idx, r in enumerate(routes)}
shortest_routes = {idx: r for idx, r in enumerate(shortest_routes)}

removed_idx = set()
for idx, r in shortest_routes.items():
    if(not correct_routes(r)):
        removed_idx.add(idx)

for idx, r in routes.items():
    if(not correct_routes(r)):
        removed_idx.add(idx)

for idx in removed_idx:
    shortest_routes.pop(idx)
    routes.pop(idx)

shortest_routes = [r for idx, r in shortest_routes.items()]
routes = [r for idx, r in routes.items()]

# %%
# calculate detour factor of routes
shortest_route_lengths = df_all[df_all['shortest_route_length'].notna() & df_all['route_length'].notna()]['shortest_route_length'].to_list()

weighted_route_lengths = df_all[df_all['shortest_route_length'].notna() & df_all['route_length'].notna()]['route_length'].to_list()

# remove routes with zero length
valid_indices = [i for i, l in enumerate(shortest_route_lengths) if l > 0 and weighted_route_lengths[i] > 0]
shortest_route_lengths = [shortest_route_lengths[i] for i in valid_indices]
weighted_route_lengths = [weighted_route_lengths[i] for i in valid_indices]

detour_factors = []
for s_length, w_length in zip(shortest_route_lengths, weighted_route_lengths):
    detour_factor = w_length / s_length
    detour_factors.append(detour_factor)

avg_detour_factor = np.average(detour_factors)
median_detour_factor = np.median(detour_factors)

print(f'average detour factor: {avg_detour_factor}')
print(f'median detour factor: {median_detour_factor}')
print(f'75 percentile: {np.percentile(detour_factors, 75)}')
print(f'85 percentile: {np.percentile(detour_factors, 85)}')
print(f'95 percentile: {np.percentile(detour_factors, 95)}')
print(f'99 percentile: {np.percentile(detour_factors, 99)}')

# %%
# load ebc values from file
ebc = get_ebc_values_from_gpkg('ebc.gpkg', 'ebc_area_normalization_bike_sharing', graph)

count_shortest_routes = get_ebc_values_from_gpkg('graph.gpkg', 'shortest_path_usage', graph)
count_weighted_routes = get_ebc_values_from_gpkg('graph.gpkg', 'weighted_path_usage', graph)

diff_weighted_shortest_routes = compare_ebc_values(count_weighted_routes, count_shortest_routes)
diff_ebc_weighted_routes = compare_ebc_values(ebc, count_weighted_routes)

plot_edge_count(graph, diff_weighted_shortest_routes, expanded=True, cmap=plt.get_cmap('PiYG'), normalize=False, render_order_func=diff_render_order_func).to_file(filename='graph.gpkg', layer='diff_weighted_shortest', driver='GPKG')

plot_edge_count(graph, diff_ebc_weighted_routes, expanded=True, cmap=plt.get_cmap('PiYG'), normalize=False, render_order_func=diff_render_order_func).to_file(filename='graph.gpkg', layer='diff_ebc_weighted', driver='GPKG')

# %%
