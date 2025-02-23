# %% 
# imports
import matplotlib.colorbar
import osmnx as ox
import networkx as nx
import matplotlib
import matplotlib.pyplot as plt
import psycopg2
import os
from dotenv import load_dotenv
import folium
import geopandas as gpd
from collections import Counter
import time
from utils.utils import *
import pickle
import numpy as np
import igraph as ig
import leafmap.foliumap as leafmap
from tqdm import tqdm

CPU_COUNT = 16

# %%
# helper functions
# plot routes on a map
def plot_routes(routes: list[list[int] | None], graph: nx.MultiDiGraph, with_markers: bool = False):
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
def plot_heat_map_of_edges(routes: list[list[int] | None], graph: nx.MultiDiGraph, expanded: bool = False):
    nodes = ox.graph_to_gdfs(graph, nodes=True, edges=False, node_geometry=True, fill_edge_geometry=False)
    cmap = plt.get_cmap('turbo')
    edges_counter = Counter()

    for route in routes:
        if route:
            start_node = route[0]
            for node in route[1:]:
                edges_counter.update([(start_node, node)])
                start_node = node

    map = leafmap.Map(location=[49.451900, 11.076608], zoom_start=12, crs='EPSG3857')

    max_value = edges_counter.most_common(1)[0][1]

    for edge, count in edges_counter.items():
        positions = []
        for node_id in edge:
            node = nodes.loc[node_id]
            positions.append((node['y'], node['x']))
        if not expanded:
            positions = set(positions)
            if(len(positions) == 1):
                continue
        color = matplotlib.colors.to_hex(cmap(count/max_value))
        folium.PolyLine(positions, color=color, tooltip=count).add_to(map)
    
    map.add_colormap(position='bottomright', width=4.0, height=0.3, vmin=0, vmax=max_value, cmap='turbo')
    return map

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
graph = ox.io.load_graphml('weighted_bicycle_graph.graphml', node_dtypes={'osmid': str}, edge_dtypes={'weight': float})
graph_small = ox.io.load_graphml('small_bicycle_graph.graphml', node_dtypes={'osmid': str}, edge_dtypes={'weight': float})

# some statistics of the graph
nodes = ox.graph_to_gdfs(graph, nodes=True, edges=False, node_geometry=True, fill_edge_geometry=False)
edges = ox.graph_to_gdfs(graph, nodes=False)

print(f'number of edges: {len(edges)}')
print(f'length of network: {sum(edges["length"])} meters')

# %% 
# get rides of all bikes over time
conn = psycopg2.connect(
    host=POSTGRES_HOST,
    database=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    port=POSTGRES_PORT)

sql = f"""select r.* from rides r 
            where ST_Distance(r.starting_position, r.finishing_position) < 20000
            and ST_Distance(r.starting_position, r.finishing_position) > 150 
            and EXTRACT(EPOCH FROM (r.finishing_time - r.starting_time)) <= 60 * 60 
            and r.starting_time::date != '2023-10-10'
            and r.starting_time::date != '2023-10-11'
            order by r.bike_id, r.starting_time
            limit 1000000;"""
finishing_pos_sql = f"""select r.id, r.finishing_position from rides r
                        where ST_Distance(r.starting_position, r.finishing_position) < 20000
                        and ST_Distance(r.starting_position, r.finishing_position) > 150 
                        and EXTRACT(EPOCH FROM (r.finishing_time - r.starting_time)) <= 60 * 60 
                        and r.starting_time::date != '2023-10-10'
                        and r.starting_time::date != '2023-10-11'
                        order by r.bike_id, r.starting_time
                        limit 1000000;"""

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
trips = df.head(1000000)
print(f'{len(trips)} trips')

starting_positions = trips['starting_position']
finishing_positions = trips['finishing_position']

print('start calculating nearest nodes')
start = time.time()
x = [p.x for p in starting_positions]
y = [p.y for p in starting_positions]
starting_node_ids = ox.distance.nearest_nodes(graph_small, x, y)

x = [p.x for p in finishing_positions]
y = [p.y for p in finishing_positions]
finishing_node_ids = ox.distance.nearest_nodes(graph_small, x, y)
end = time.time()
print(f'finished calculating nearest nodes in {end - start} seconds')

print('start calculating routes')
start = time.time()
shortest_routes = ox.routing.shortest_path(graph_small, starting_node_ids, finishing_node_ids, cpus=CPU_COUNT)
end = time.time()
print(f'finished calculating routes in {end - start} seconds')

# %%
# write calculated routes on file
file = open('calculated_shortest_routes.pickle', 'wb')
pickle.dump(shortest_routes, file)
file.close()

# %%
plot_heat_map_of_edges(shortest_routes, graph_small).save('shortest_routes.html')

# %%
# calculate trips based on the new weight metric based on osm features
trips = df.head(1000000)
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
routes = ox.routing.shortest_path(graph, starting_node_ids, finishing_node_ids, cpus=CPU_COUNT, weight='weight')
end = time.time()
print(f'finished calculating routes in {end - start} seconds')
# %%
# write calculated routes on file
file = open('calculated_routes.pickle', 'wb')
pickle.dump(routes, file)
file.close()

# %%
# plot heatmap of calculated routes
plot_heat_map_of_edges(routes, graph).save('weighted_routes.html')

# %%
# load calculated routes from file
with open('calculated_routes.pickle', 'rb') as f:
    routes = pickle.load(f)

# load calculated routes from file
with open('calculated_shortest_routes.pickle', 'rb') as f:
    shortest_routes = pickle.load(f)

# %%
# calculate detour factor of routes
def correct_routes(route: list[int]) -> bool:
    return route != None and len(route) > 1

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

#%%
shortest_route_lenghts = []
for route in tqdm(shortest_routes[:10000], desc='calculate length of shortest routes', unit='routes'):
    r = ox.routing.route_to_gdf(graph_small, route)
    route_length = r['length'].sum()
    shortest_route_lenghts.append(route_length)

weighted_route_lengths = []
for route in tqdm(routes[:10000], desc='calculate lenth of weighted routes', unit='routes'):
    r = ox.routing.route_to_gdf(graph, route)
    route_length = r['length'].sum()
    weighted_route_lengths.append(route_length)

# %%
detour_factors = []
for s_length, w_length in zip(shortest_route_lenghts, weighted_route_lengths):
    detour_factor = w_length / s_length
    detour_factors.append(detour_factor)
# %%
avg_detour_factor = np.average(detour_factors)
median_detour_factor = np.median(detour_factors)

print(f'average detour factor: {avg_detour_factor}')
print(f'median detour factor: {median_detour_factor}')
print(f'75 percentile: {np.percentile(detour_factors, 75)}')
print(f'85 percentile: {np.percentile(detour_factors, 85)}')
print(f'95 percentile: {np.percentile(detour_factors, 95)}')
print(f'99 percentile: {np.percentile(detour_factors, 99)}')

# %%
plt.boxplot(detour_factors)
# %%
max_value = max(detour_factors)
idx_max_value = detour_factors.index(max_value)

display(plot_routes([routes[idx_max_value]], graph, with_markers=True))#.save('max_detour_factor.html')
display(plot_routes([shortest_routes[idx_max_value]], graph_small, with_markers=True))#.save('max_detour_factor.html')
print(max_value)

# %%
# explore routes with certain detour factors
limit = 10
count = 0
for detour_factor, shortest_route, weighted_route in zip(detour_factors, shortest_routes, routes):
    if detour_factor > 3.0 and detour_factor < 5.0:
        print(f'detour factor: {detour_factor}')
        map = plot_routes([shortest_route, weighted_route], graph, with_markers=True)
        map.save(f'detour_factor_{detour_factor}.html')

        if limit != None:
            count = count + 1
            if count >= limit:
                break
# %%
# calculate betweenness centrality of all edges in graph
radius = 2500
start_nodes = []
dest_nodes= []
edges_counter = Counter()
count = 0
# for every node
print(f'start finding routes')
start = time.time()
for node in graph.nodes():
# get every node within certain range
    subgraph = nx.ego_graph(graph, node, radius=radius, distance='length')

    dest_nodes = dest_nodes + list(subgraph.nodes())
    start_nodes = start_nodes + ([node] * len(subgraph.nodes()))
    count = count + 1
    if count >= 100:
        break

end = time.time()
print(f'found {len(dest_nodes)} routes in {end - start} seconds')

# shortest path between all of them
print(f'start calculating {len(dest_nodes)} routes')
start = time.time()
routes = ox.shortest_path(graph, start_nodes, dest_nodes, weight='weight')
end = time.time()
print(f'calculated {len(routes)} routes in {end - start} seconds')

plot_heat_map_of_edges(routes, graph)

# %%
wg: ig.Graph = ig.Graph.from_networkx(graph)

# %%
ebc = wg.edge_betweenness(directed = False, cutoff = 4500, weights = "length")

# %%
nodes = ox.graph_to_gdfs(graph, nodes=True, edges=False, node_geometry=True, fill_edge_geometry=False)
cmap = plt.get_cmap('turbo')
map = leafmap.Map(location=[49.451900, 11.076608], zoom_start=12, crs='EPSG3857')

max_value = max(ebc)

for edge, count in zip(graph.edges(), ebc):
    if('turning_angle' in edge[2]):
        continue
    positions = []
    for node_id in edge:
        node = nodes.loc[node_id]
        positions.append((node['y'], node['x']))
    color = matplotlib.colors.to_hex(cmap(count/max_value))
    folium.PolyLine(positions, color=color, tooltip=count).add_to(map)

map.add_colormap(position=(55,3), width=4.0, height=0.3, vmin=0, vmax=max_value, cmap='turbo')
map.save('ebc_length.html')

# %%
# fetch graph of bicycle infrastructure
place_name = 'Nürnberg'
network_type = 'bike'
bike_lane_filter = [
    '["cycleway"="lane"]',
    '["cycleway:right"="lane"]',
    '["cycleway:left"="lane"]',
    '["cycleway:both"="lane"]',
    '["cycleway"="opposite"]'
]
bike_path_filter = [
    '["bicycle"="designated"]',
    '["highway"="cycleway"]',
    '["cycleway"="track"]',
    '["cycleway:right"="track"]',
    '["cycleway:left"="track"]',
    '["cycleway:both"="track"]'
]
bike_road_filter = [
    '["bicycle_road"="yes"]'
]
custom_filter = bike_path_filter
bike_infra_graph = ox.graph_from_place(query=place_name, retain_all=True, simplify=False, custom_filter=custom_filter)

# %%
# finding gaps between bicycle paths
gaps = []
not_gap = []
bike_infra_edges = ox.graph_to_gdfs(bike_infra_graph, edges=True, nodes=False)
for route in tqdm(routes, desc='finding gaps in routes', unit='route'):
    es = ox.routing.route_to_gdf(graph, route, weight='weight')
    for idx, row in es.iterrows():
        if row['osmid'] not in bike_infra_edges['osmid'].values:
            gaps.append(row)
        else:
            not_gap.append(row)
gaps_df = gpd.GeoDataFrame(gaps)
print(f'{len(gaps)} road segments have no bike infrastructure')
print(f'{len(not_gap)} road segments have bike infrastructure')

# %%
def calc_benefits(edges: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    edges_counter = Counter()

    for idx, e in edges.iterrows():
        edges_counter.update([idx])

    edges = edges.drop_duplicates(inplace=False)

    benefits = []
    for idx, data in edges.iterrows():
        benefit = data['length'] * edges_counter[idx]
        benefits.append(benefit)
    edges = edges.assign(benefit=benefits)
    return edges

def plot_edge_heatmap(edges: gpd.GeoDataFrame):
    cmap = plt.get_cmap('Reds')
    edges_counter = Counter()

    for idx, e in edges.iterrows():
        edges_counter.update([idx])

    edges = edges.drop_duplicates(inplace=False)

    benefits = []
    for idx, data in edges.iterrows():
        benefit = data['length'] * edges_counter[idx]
        benefits.append(benefit)
    edges = edges.assign(benefit=benefits)

    benefits = []
    counts = []
    for idx, data in edges.iterrows():
        benefits.append(data['benefit'])
        counts.append(edges_counter[idx])
    plt.scatter(counts, benefits, s=1)
    plt.xlabel("count of rides on this gap")
    plt.ylabel("overall benefit")
    plt.show()

    max_benefit = max(edges['benefit'].values)

    map = leafmap.Map(location=[49.451900, 11.076608], zoom_start=12, crs='EPSG3857')

    max_count = edges_counter.most_common(1)[0][1]

    for edge_id, data in edges.iterrows():
        p1, p2 = data['geometry'].coords
        p1 = (p1[1], p1[0])
        p2 = (p2[1], p2[0])
        color = matplotlib.colors.to_hex(cmap(data['benefit']/max_benefit))
        folium.PolyLine((p1, p2), color=color, tooltip=f"count: {edges_counter[edge_id]}; benefit: {data['benefit']}").add_to(map)
    
    map.add_colormap(position='bottomright', width=4.0, height=0.3, vmin=0, vmax=max_benefit, cmap='Reds')
    return map

plot_edge_heatmap(gaps_df).save('gaps_benefit.html')

# %%
not_gap_df = gpd.GeoDataFrame(not_gap)

# %%
plot_edge_heatmap(not_gap_df)

# %%
#filter dataframe for items with osmid not nan
unique_gaps = gaps_df[gaps_df['osmid'].notna()].drop_duplicates(subset='osmid', keep='first')
unique_gaps

# %%
