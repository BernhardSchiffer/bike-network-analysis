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
from utils.graph_types import *
import pickle
import numpy as np
import igraph as ig
import leafmap.foliumap as leafmap
from tqdm import tqdm

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
def plot_heat_map_of_edges(routes: list[Route | None], graph: nx.MultiDiGraph, expanded: bool = False) -> GeoDataFrame:
    cmap = plt.get_cmap('turbo')
    edges_counter = Counter()

    for route in tqdm(routes, desc='count edges', unit='route'):
        edges = route_to_edge_ids(route)
        edges_counter.update(edges)

    # collapse edges with same nodes ie. edges with different directions
    if not expanded:
        print(f'number of edges: {len(edges_counter)}')
        for edge in list(edges_counter.keys()):
            reversed_edge = get_reversed_key(edge)
            if reversed_edge in edges_counter:
                edges_counter[edge] = edges_counter[edge] + edges_counter[reversed_edge]
                edges_counter.pop(reversed_edge)
        print(f'number of edges after collapsing: {len(edges_counter)}')

    max_value = edges_counter.most_common(1)[0][1]

    if expanded:
        edges_df, _, _ = plot_shifted_graph(graph)
    else:
        edges_df = plot_graph(graph)

    to_remove_edges = []
    attributes = {
        'count': [], 
        'color': [], 
        'osmid': [], 
        'weight': [], 
        'length': [], 
        'penalty': [],
        'slope': []
    }
    for idx, _ in tqdm(edges_df.iterrows(), desc='add count to edges', unit='edge', total=len(edges_df)):
        try:
            count = edges_counter[idx]
            if count == 0:
                to_remove_edges.append(idx)
                continue
            if not expanded:
                try:
                    s, d, k = idx
                    graph.edges[s, d, k]['turning_angle']
                    to_remove_edges.append((s, d, k))
                    continue
                except KeyError:
                    pass
            attributes['count'].append(count)
            color = matplotlib.colors.to_hex(cmap(count/max_value))
            attributes['color'].append(color)
            attributes['osmid'].append(graph.edges[idx].get('osmid', None))
            weight = graph.edges[idx].get('weight', None)
            attributes['weight'].append(weight)
            length = graph.edges[idx].get('length', None)
            attributes['length'].append(length)
            penalty = graph.edges[idx].get('penalty', None)
            attributes['penalty'].append(penalty)
            attributes['slope'].append(graph.edges[idx].get('slope_percentage', None))
        except KeyError:
            to_remove_edges.append((s, d, k))
            continue

    # drop rows
    edges_df = edges_df.drop(to_remove_edges)

    # add column for count and add the counts list
    for key, value in attributes.items():
        edges_df[key] = value
    # only keep columns that are needed
    columns_to_keep = ['geometry', 'line_width']
    columns_to_keep.extend(list(attributes.keys()))
    
    return edges_df#.reset_index(drop=True)

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
graph = ox.io.load_graphml('expanded_bicycle_graph.graphml', node_dtypes={'osmid': str}, edge_dtypes={'weight': float})
graph_small = ox.io.load_graphml('small_bicycle_graph.graphml', node_dtypes={'osmid': str}, edge_dtypes={'weight': float})

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
# calculate shortest routes and plot on map
trips = df.head(10000)
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

# calculate direct route between starting and finishing nodes
# the lookup in the graph, i.e. in the a star algorithm, is too much overhead be more efficient than the djikstra algorithm
def distance(a, b):
    a = graph_small.nodes[a]
    b = graph_small.nodes[b]
    return ox.distance.euclidean(a['y'], a['x'], b['y'], b['x'])

print('start calculating routes')
start = time.time()
shortest_routes = ox.routing.shortest_path(graph_small, starting_node_ids, finishing_node_ids, cpus=CPU_COUNT, weight='length')
end = time.time()
print(f'finished calculating routes in {end - start} seconds')

# %%
# write calculated routes on file
file = open('calculated_shortest_routes.pickle', 'wb')
pickle.dump(shortest_routes, file)
file.close()

# %%
plot_heat_map_of_edges([ s for s in shortest_routes if correct_routes(s)], graph_small).save('shortest_routes.html')

# %%
# calculate trips based on the new weight metric based on osm features
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
valid_routes = [r for r in routes if correct_routes(r)]

plot_heat_map_of_edges(valid_routes, graph, expanded=False).to_file(filename='graph.gpkg', layer='path_usage', driver='GPKG')

plot_heat_map_of_edges(valid_routes, graph, expanded=True).to_file(filename='graph.gpkg', layer='path_usage_expanded', driver='GPKG')

# %%
# load calculated routes from file
with open('calculated_routes.pickle', 'rb') as f:
    routes = pickle.load(f)

# load calculated routes from file
with open('calculated_shortest_routes.pickle', 'rb') as f:
    shortest_routes = pickle.load(f)

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
# calculate length of routes
shortest_route_lengths = []
for route in tqdm(shortest_routes, desc='calculate length of shortest routes', unit='routes'):
    r = route_to_edge_ids(route)
    route_length = sum([graph_small.edges[edge]['length'] for edge in r])
    shortest_route_lengths.append(route_length)

weighted_route_lengths = []
for route in tqdm(routes, desc='calculate length of weighted routes', unit='routes'):
    r = route_to_edge_ids(route)
    route_length = sum([graph.edges[edge]['length'] for edge in r])
    weighted_route_lengths.append(route_length)

# calculate detour factor of routes
detour_factors = []
for s_length, w_length in zip(shortest_route_lengths, weighted_route_lengths):
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
start = time.time()
ebc = wg.edge_betweenness(directed=True, cutoff=4500, weights="weight")
end = time.time()
print(f'calculated edge betweenness centrality in {end - start} seconds')

# %%
def plot_edge_betweenness_centrality(graph: nx.MultiDiGraph, ebc: list[float], expanded: bool = False) -> GeoDataFrame:
    cmap = plt.get_cmap('turbo')
    edges_counter = Counter()

    for edge, count in tqdm(zip(graph.edges, ebc), desc='count edges', unit='route'):
        edges_counter[edge] = count

    # collapse edges with same nodes ie. edges with different directions
    if not expanded:
        print(f'number of edges: {len(edges_counter)}')
        for edge in list(edges_counter.keys()):
            reversed_edge = get_reversed_key(edge)
            if reversed_edge in edges_counter:
                edges_counter[edge] = edges_counter[edge] + edges_counter[reversed_edge]
                edges_counter.pop(reversed_edge)
        print(f'number of edges after collapsing: {len(edges_counter)}')

    max_value = edges_counter.most_common(1)[0][1]

    if expanded:
        edges_df, _, _ = plot_shifted_graph(graph)
    else:
        edges_df = plot_graph(graph)

    to_remove_edges = []
    attributes = {
        'count': [], 
        'color': [], 
        'osmid': [], 
        'weight': [], 
        'length': [], 
        'penalty': [],
        'slope': []
    }
    for idx, _ in tqdm(edges_df.iterrows(), desc='add count to edges', unit='edge', total=len(edges_df)):
        try:
            count = edges_counter[idx]
            if count == 0:
                to_remove_edges.append(idx)
                continue
            if not expanded:
                try:
                    s, d, k = idx
                    graph.edges[s, d, k]['turning_angle']
                    to_remove_edges.append((s, d, k))
                    continue
                except KeyError:
                    pass
            attributes['count'].append(count)
            color = matplotlib.colors.to_hex(cmap(count/max_value))
            attributes['color'].append(color)
            attributes['osmid'].append(graph.edges[idx].get('osmid', None))
            weight = graph.edges[idx].get('weight', None)
            attributes['weight'].append(weight)
            length = graph.edges[idx].get('length', None)
            attributes['length'].append(length)
            penalty = graph.edges[idx].get('penalty', None)
            attributes['penalty'].append(penalty)
            attributes['slope'].append(graph.edges[idx].get('slope_percentage', None))
        except KeyError:
            to_remove_edges.append((s, d, k))
            continue

    # drop rows
    edges_df = edges_df.drop(to_remove_edges)

    # add column for count and add the counts list
    for key, value in attributes.items():
        edges_df[key] = value
    # only keep columns that are needed
    columns_to_keep = ['geometry', 'line_width']
    columns_to_keep.extend(list(attributes.keys()))

    return edges_df#.reset_index(drop=True)

plot_edge_betweenness_centrality(graph, ebc).to_file(filename='graph.gpkg', layer='ebc_length', driver='GPKG')

plot_edge_betweenness_centrality(graph, ebc, expanded=True).to_file(filename='graph.gpkg', layer='ebc_length_expanded', driver='GPKG')
# %%

def plot_difference_between_edge_betweenness_and_route_count(graph: nx.MultiDiGraph, ebc: list[float], routes: list[EdgeId], expanded: bool = False) -> GeoDataFrame:
    cmap = plt.get_cmap('coolwarm')

    ebc_counter = Counter()
    for edge, count in zip(graph.edges, ebc):
        ebc_counter[edge] = count

    edges_counter = Counter()
    for route in routes:
        edges = route_to_edge_ids(route)
        edges_counter.update(edges)

    # collapse edges with same nodes ie. edges with different directions
    if not expanded:
        print(f'number of edges: {len(edges_counter)}')
        for edge in list(edges_counter.keys()):
            reversed_edge = get_reversed_key(edge)
            if reversed_edge in edges_counter:
                edges_counter[edge] = edges_counter[edge] + edges_counter[reversed_edge]
                edges_counter.pop(reversed_edge)
        print(f'number of edges after collapsing: {len(edges_counter)}')
        print(f'number of edges: {len(ebc_counter)}')
        for edge in list(ebc_counter.keys()):
            reversed_edge = get_reversed_key(edge)
            if reversed_edge in ebc_counter:
                ebc_counter[edge] = ebc_counter[edge] + ebc_counter[reversed_edge]
                ebc_counter.pop(reversed_edge)
        print(f'number of edges after collapsing: {len(ebc_counter)}')

    # normalize values
    max_value = ebc_counter.most_common(1)[0][1]
    for edge, count in ebc_counter.items():
        ebc_counter[edge] = count / max_value

    # normalize values
    max_value = edges_counter.most_common(1)[0][1]
    for edge, count in edges_counter.items():
        edges_counter[edge] = count / max_value

    if expanded:
        edges_df, _, _ = plot_shifted_graph(graph)
    else:
        edges_df = plot_graph(graph)

    to_remove_edges = []
    attributes = {
        'count_rwd': [],
        'count_ebc': [],
        'diff': [],
        'color': [], 
        'osmid': [], 
        'weight': [], 
        'length': [], 
        'penalty': [],
        'slope': []
    }
    for idx, _ in tqdm(edges_df.iterrows(), desc='add count to edges', unit='edge', total=len(edges_df)):
        try:
            count = edges_counter[idx]
            count_ebc = ebc_counter[idx]
            if count == 0 and count_ebc == 0:
                to_remove_edges.append(idx)
                continue
            if not expanded:
                try:
                    s, d, k = idx
                    graph.edges[s, d, k]['turning_angle']
                    to_remove_edges.append((s, d, k))
                    continue
                except KeyError:
                    pass
            
            attributes['count_rwd'].append(count)
            attributes['count_ebc'].append(count_ebc)
            # get difference between ebc and route count
            diff = count_ebc - count
            attributes['diff'].append(diff)
            attributes['osmid'].append(graph.edges[idx].get('osmid', None))
            weight = graph.edges[idx].get('weight', None)
            attributes['weight'].append(weight)
            length = graph.edges[idx].get('length', None)
            attributes['length'].append(length)
            penalty = graph.edges[idx].get('penalty', None)
            attributes['penalty'].append(penalty)
            attributes['slope'].append(graph.edges[idx].get('slope_percentage', None))
        except KeyError:
            to_remove_edges.append((s, d, k))
            continue
    
    attributes['diff'] = np.interp(attributes['diff'], (min(attributes['diff']), max(attributes['diff'])), (0, +1))
    for diff in attributes['diff']:
        color = matplotlib.colors.to_hex(cmap(diff))
        attributes['color'].append(color)

    # drop rows
    edges_df = edges_df.drop(to_remove_edges)

    # add column for count and add the counts list
    for key, value in attributes.items():
        edges_df[key] = value
    # only keep columns that are needed
    columns_to_keep = ['geometry', 'line_width']
    columns_to_keep.extend(list(attributes.keys()))

    return edges_df#.reset_index(drop=True)

valid_routes = [r for r in routes if correct_routes(r)]

plot_difference_between_edge_betweenness_and_route_count(graph, ebc, valid_routes).to_file(filename='graph.gpkg', layer='usage_diff', driver='GPKG')

plot_difference_between_edge_betweenness_and_route_count(graph, ebc, valid_routes, expanded=True).to_file(filename='graph.gpkg', layer='usage_diff_expanded', driver='GPKG')
# %%
