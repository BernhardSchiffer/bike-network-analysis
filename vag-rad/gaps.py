# %%
# imports
import pickle
from collections import Counter

import geopandas as gpd
import igraph as ig
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import networkx as nx
import osmnx as ox
import osmnx.settings
import pandas as pd
import shapely
from geopandas import GeoDataFrame
from tqdm import tqdm

from utils.gap_evaluator import GapEvaluator
from utils.graph_builder import get_routing_graph_area, get_turn_direction
from utils.graph_types import LEFT, RIGHT, STRAIGHT, U_TURN, EdgeId, NodeId, Route
from utils.population_provider import GHSLPopulationProvider
from utils.service_area_provider import ServiceAreaProvider
from utils.utils import (
    correct_routes,
    get_reversed_key,
    is_sublist,
    parse_junction_osmid,
    parse_old_edge_key,
    route_to_edge_ids,
)
from utils.visualization_utils import (
    get_ebc_values_from_gpkg,
    plot_graph,
    plot_shifted_graph,
)


#%%
# join all values to a singe list
def get_all_osmids(edge_osmid: int | list[int] | tuple[int|list[int], int|list[int]]) -> list[int]:
    if type(edge_osmid) is int:
        return [edge_osmid]
    if type(edge_osmid) is list:
        return edge_osmid
    if type(edge_osmid) is tuple:
        osmid_0, osmid_1 = edge_osmid
        if type(osmid_0) is int and type(osmid_1) is int:
            return [osmid_0, osmid_1]
        if type(osmid_0) is int and type(osmid_1) is list:
            return [osmid_0] + osmid_1
        if type(osmid_0) is list and type(osmid_1) is int:
            return osmid_0 + [osmid_1]
        if type(osmid_0) is list and type(osmid_1) is list:
            return osmid_0 + osmid_1
    return []

def is_osmid_in_edge_osmid(edge_osmid: int | list[int] | tuple[int|list[int], int|list[int]], osmid: int) -> bool:
    return osmid in get_all_osmids(edge_osmid)

# %%
# load graph from file
routing_graph = ox.load_graphml('simplified_bicycle_graph.graphml', node_dtypes={'osmid': str}, edge_dtypes={'weight': float, 'shifted_geometry': lambda x: shapely.from_wkt(x), 'osmid': parse_junction_osmid, 'penalty': float, 'slope_percentage': float, 'length': float, 'old_edge_key': parse_old_edge_key})

bicycle_graph =  ox.load_graphml('bicycle_graph.graphml', node_dtypes={'osmid': int}, edge_dtypes={'weight': float, 'penalty': float, 'slope_percentage': float, 'length': float})

# %%
# fetch graph of bicycle infrastructure
place_name = 'Nürnberg'
query_polygon = get_routing_graph_area(place_name, 5000)
osmnx.settings.overpass_settings = '[out:json][timeout:{timeout}][date:"2025-10-21T20:21:22Z"]{maxsize}'
network_type = 'bike'
bike_lane_filter = [
    '["cycleway"="lane"]',
    '["cycleway:right"="lane"]',
    '["cycleway:left"="lane"]',
    '["cycleway:both"="lane"]'
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
custom_filter = []
custom_filter.extend(bike_lane_filter)
custom_filter.extend(bike_path_filter)
custom_filter.extend(bike_road_filter)
bike_infra_graph = ox.graph_from_polygon(query_polygon, retain_all=True, simplify=False, custom_filter=custom_filter)
osmids_with_bike_infra = set(edge[2]['osmid'] for edge in bike_infra_graph.edges(data=True) if edge[2].get('osmid', None) is not None)

filter = []
filter.extend(bike_path_filter)
filter.extend(bike_road_filter)
protected_bike_infra_graph = ox.graph_from_polygon(query_polygon, retain_all=True, simplify=False, custom_filter=filter)
osmids_with_protected_bike_infra = set(edge[2]['osmid'] for edge in protected_bike_infra_graph.edges(data=True) if edge[2].get('osmid', None) is not None)

# %%
# finding gaps between bicycle paths
def get_gaps_for_route(route: Route, graph: nx.MultiDiGraph):
    gaps: list[EdgeId] = []
    not_gaps: list[EdgeId] = []

    route_edges = route_to_edge_ids(route)
    for route_edge in route_edges:
        try:
            if graph.edges[route_edge]['osmid'] in osmids_with_bike_infra:
                not_gaps.append(route_edge)
            else:
                gaps.append(route_edge)
        except KeyError:
            continue
    return (gaps, not_gaps)

#%%
# load calculated routes from file
with open('calculated_routes.pickle', 'rb') as f:
    routes = pickle.load(f)

routes = [r for r in routes if correct_routes(r)]

# %%
# find gaps through calculated routes
gaps: list[EdgeId] = []
not_gaps: list[EdgeId] = []
for route in tqdm(routes, desc='finding gaps in routes', unit='route'):
    result = get_gaps_for_route(route, routing_graph)
    gaps.extend(result[0])
    not_gaps.extend(result[1])

print(f'{len(set(gaps))} road segments have no bike infrastructure')
print(f'{len(set(not_gaps))} road segments have bike infrastructure')

# write gaps to file
with open('gaps.pickle', 'wb') as f:
    pickle.dump(gaps, f)

# %%
# load gaps from file
with open('gaps.pickle', 'rb') as f:
    gaps = pickle.load(f)
# %%

gap_counter = Counter(gaps)
edge_benefits = ox.graph_to_gdfs(routing_graph, nodes=False, edges=True).loc[list(set(gaps))]

benefits = []
counts = []
for idx, data in edge_benefits.iterrows():
    counts.append(gap_counter[idx])
    benefit = data['length'] * gap_counter[idx]
    benefits.append(benefit)
edge_benefits = edge_benefits.assign(benefit=benefits)
edge_benefits = edge_benefits.assign(count=counts)

edge_benefits

# %%
def plot_edge_heatmap(gaps: list[EdgeId], graph: nx.MultiDiGraph, expanded: bool = False, metric: str = 'count'):
    cmap = plt.get_cmap('Reds')

    gap_counter = Counter(gaps)

    if not expanded:
        print(f'number of gaps: {len(gap_counter)}')
        for edge in list(gap_counter.keys()):
            reversed_edge = get_reversed_key(edge)
            if reversed_edge in gap_counter:
                gap_counter[edge] = gap_counter[reversed_edge] + gap_counter[edge]
                gap_counter.pop(reversed_edge)
        print(f'number of gaps after collapsing: {len(gap_counter)}')

    #benefits = gaps['benefit'].values
    #counts = gaps['count'].values
    #plt.scatter(counts, benefits, s=1)
    #plt.xlabel("count of rides on this gap")
    #plt.ylabel("overall benefit")
    #plt.grid()
    #plt.show()

    if expanded:
        gaps_df, _ = plot_shifted_graph(graph)
    else:
        gaps_df, _ = plot_graph(graph)

    to_remove_edges = []
    attributes = {
        'count': [], 
        'benefit': [],
        'osmid': [], 
        'length': []
    }
    for idx, _ in tqdm(gaps_df.iterrows(), desc='add attributes to gaps', total=len(gaps_df), unit='gaps'):
        try:
            count = gap_counter[idx]
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
            attributes['osmid'].append(graph.edges[idx].get('osmid', None))
            length = graph.edges[idx].get('length', None)
            attributes['length'].append(length)
            attributes['benefit'].append(length * count)
        except KeyError:
            to_remove_edges.append(idx)
            continue

    gaps_df = gaps_df.drop(to_remove_edges)

    for key, value in attributes.items():
        gaps_df[key] = value

    if metric == 'count':
        max_value = gap_counter.most_common(1)[0][1]
    if metric == 'benefit':
        max_value = max(attributes['benefit'])
    
    colors = []
    for gap, data in gaps_df.iterrows():
        color = mcolors.to_hex(cmap(data[metric]/max_value))
        colors.append(color)
    gaps_df['color'] = colors
    # only keep columns that are needed
    columns_to_keep = ['geometry', 'line_width']
    columns_to_keep.extend(list(attributes.keys()))

    return gaps_df

plot_edge_heatmap(gaps, routing_graph, expanded=False).to_file('graph.gpkg', layer='gaps', driver='GPKG')

plot_edge_heatmap(gaps, routing_graph, expanded=True).to_file('graph.gpkg', layer='gaps_exanded', driver='GPKG')

plot_edge_heatmap(gaps, routing_graph, expanded=False, metric='benefit').to_file('graph.gpkg', layer='gaps_benefit', driver='GPKG')

plot_edge_heatmap(gaps, routing_graph, expanded=True, metric='benefit').to_file('graph.gpkg', layer='gaps_exanded_benefit', driver='GPKG')

# %%
# load ebc values from file
ebc = get_ebc_values_from_gpkg('ebc.gpkg', 'ebc_area_normalization_population_exponential', routing_graph)

wg: ig.Graph = ig.Graph.from_networkx(routing_graph)
#%%
def plot_ebc_gap_heatmap(ebc, graph: nx.MultiDiGraph, expanded: bool = False, metric: str = 'count'):

    if len(ebc) != len(graph.edges):
        raise ValueError(f'length of ebc ({len(ebc)}) does not match length of graph edges ({len(graph.edges)})')

    cmap = plt.get_cmap('Reds')
    gap_counter = Counter()

    for edge, count in tqdm(zip(graph.edges, ebc), desc='count edges', unit='route'):
        edge_osmid = graph.edges[edge].get('osmid', None)
        if type(edge_osmid) == list:
            for osmid in edge_osmid:
                if osmid not in osmids_with_bike_infra and osmid is not None:
                    gap_counter[edge] = count
                    break
        elif type(edge_osmid) == tuple:
            for osmid in get_all_osmids(edge_osmid):
                if osmid not in osmids_with_bike_infra and osmid is not None:
                    gap_counter[edge] = count
                    break
        else:
            if edge_osmid not in osmids_with_bike_infra and edge_osmid is not None:
                gap_counter[edge] = count
    if not expanded:
        print(f'number of gaps: {len(gap_counter)}')
        for edge in list(gap_counter.keys()):
            reversed_edge = get_reversed_key(edge)
            if reversed_edge in gap_counter:
                gap_counter[edge] = gap_counter[reversed_edge] + gap_counter[edge]
                gap_counter.pop(reversed_edge)
        print(f'number of gaps after collapsing: {len(gap_counter)}')


   #edges_to_remove = []
   #for edge, count in zip(graph.edges, ebc):
   #    if expanded:
   #        if count < 10_000_000:
   #            edges_to_remove.append(edge)
   #    else:
   #        if count < 10_000_000:
   #            edges_to_remove.append(edge)

   #graph = graph.copy()
   #for edge in edges_to_remove:
   #    if graph.has_edge(*edge):
   #        graph.remove_edge(*edge)

    if expanded:
        gaps_df, _ = plot_shifted_graph(graph)
    else:
        gaps_df = ox.graph_to_gdfs(graph, nodes=False, edges=True)

    to_remove_edges = []
    attributes = {
        'count': [], 
        'benefit': [],
        'osmid': [], 
        'length': []
    }
    for idx, _ in tqdm(gaps_df.iterrows(), desc='add attributes to gaps', total=len(gaps_df), unit='gaps'):
        try:
            count = gap_counter[idx]
            if count == 0:
                to_remove_edges.append(idx)
                continue
            if not expanded:
                try:
                    graph.edges[idx]['turning_angle']
                    to_remove_edges.append(idx)
                    continue
                except KeyError:
                    pass
            attributes['count'].append(count)
            attributes['osmid'].append(graph.edges[idx].get('osmid', None))
            length = graph.edges[idx].get('length', None)
            attributes['length'].append(length)
            attributes['benefit'].append(length * count)
        except KeyError:
            to_remove_edges.append(idx)
            continue

    gaps_df = gaps_df.drop(to_remove_edges)

    for key, value in attributes.items():
        gaps_df[key] = value

    if metric == 'count':
        max_value = gap_counter.most_common(1)[0][1]
    if metric == 'benefit':
        max_value = max(attributes['benefit'])
    
    colors = []
    for gap, data in gaps_df.iterrows():
        color = mcolors.to_hex(cmap(data[metric]/max_value))
        colors.append(color)
    gaps_df['color'] = colors
    # only keep columns that are needed
    columns_to_keep = ['geometry', 'line_width']
    columns_to_keep.extend(list(attributes.keys()))

    return gaps_df

plot_ebc_gap_heatmap(ebc, routing_graph, expanded=False).to_file('graph.gpkg', layer='gaps_ebc', driver='GPKG')

plot_ebc_gap_heatmap(ebc, routing_graph, expanded=True).to_file('graph.gpkg', layer='gaps_ebc_exanded', driver='GPKG')

plot_ebc_gap_heatmap(ebc, routing_graph, expanded=False, metric='benefit').to_file('graph.gpkg', layer='gaps_ebc_benefit', driver='GPKG')

plot_ebc_gap_heatmap(ebc, routing_graph, expanded=True, metric='benefit').to_file('graph.gpkg', layer='gaps_ebc_exanded_benefit', driver='GPKG')

# %%
# plot edge betweenness centrality
edges_with_ebc = sorted([(x,z) for x, z in zip(wg.es, ebc)], key=lambda x: x[1], reverse=False)
edges_with_ebc = [x for x in edges_with_ebc if type(x[0]['osmid']) is list or type(x[0]['osmid']) is int]
counts = [c for e, c in edges_with_ebc]
plt.scatter(range(len(counts)), counts, s=1, c='blue')
plt.ylabel('edge betweenness centrality')
plt.yticks(range(0, int(max(counts)), 10_000_000))
plt.title('edge betweenness centrality of all edges')
plt.grid()
plt.show()

#%%
# get most important edges in the graph. X% of traffic goes over x amount if edges
important_edges = []
percentage_of_traffic = 0.9
sum_of_ebc = sum([c for _, c in edges_with_ebc]) * percentage_of_traffic

for edge, count in reversed(edges_with_ebc):
    sum_of_ebc = sum_of_ebc - count
    if sum_of_ebc >= 0:
        important_edges.append((edge, count))
    else:
        print(f'found {len(important_edges)} important edges with a rest ebc of {sum_of_ebc + count}')
        break

print(f'{percentage_of_traffic * 100:.2f}% of traffic goes over {len(important_edges)} edges. That are {len(important_edges) / len(edges_with_ebc) * 100:.2f}% of all edges in the graph.')

print(f'minimum edge betweenness centrality of important edges: {min([c for _, c in important_edges]):.0f}')

df = list()
for edge, count in important_edges:
    df.append({
        'osmid': edge['osmid'],
        'geometry': edge['geometry'],
        'ebc': count
    })
important_edges_df = GeoDataFrame(df, geometry='geometry')
important_edges_df.to_file('graph.gpkg', layer=f'{percentage_of_traffic * 100}_traffic_edges', driver='GPKG')

# %%
# plot edge betweenness centrality of edges with and without bike infrastructure
osmids = dict()
for edge, count in zip(wg.es, ebc):
    if type(edge['osmid']) is list:
        for osmid in edge['osmid']:
            osmids[osmid] = { 'count': count, 'edge': edge}
    elif type(edge['osmid']) is int:
        osmids[edge['osmid']] = { 'count': count, 'edge': edge}


# sort osmids by count
sorted_osmids = sorted(osmids.items(), key=lambda x: x[1]['count'], reverse=False)

bike_infra_x = []
bike_infra_y = []
not_bike_infra_x = []
not_bike_infra_y = []
for idx, (osmid, data) in enumerate(sorted_osmids):
    if osmid in osmids_with_bike_infra:
        bike_infra_x.append(idx)
        bike_infra_y.append(data['count'])
    else:
        not_bike_infra_x.append(idx)
        not_bike_infra_y.append(data['count'])

fig, axs = plt.subplots(2, sharex=True, sharey=True)

axs[0].set_title('edges with bike infrastructure')
axs[0].scatter(bike_infra_x, bike_infra_y, s=1, c='green')
axs[0].set_ylabel('edge betweenness centrality')

axs[1].set_title('edges without bike infrastructure')
axs[1].scatter(not_bike_infra_x, not_bike_infra_y, s=1, c='red')
axs[1].set_ylabel('edge betweenness centrality')

plt.show()

# %%
# get all crossing connections
crossing_edges = []
counts = []
for edge, count in zip(wg.es, ebc):
    if type(edge['osmid']) is not int and type(edge['osmid']) is not list:
        crossing_edges.append(edge)
        counts.append(count)

crossings = {}
for edge, count in zip(crossing_edges, counts):
    turning_direction = get_turn_direction(float(edge['turning_angle']))
    if crossings.get(turning_direction) is None:
        crossings[turning_direction] = []
    crossings[turning_direction].append(count)

fig = plt.figure()
ax1 = fig.add_subplot(111)

for direction, c in crossings.items():
    if direction == STRAIGHT:
        color = 'blue'
    elif direction == LEFT:
        color = 'green'
    elif direction == RIGHT:
        color = 'red'
    elif direction == U_TURN:
        color = 'orange'

    ax1.scatter(range(len(c)), sorted(c), c=color, s=1)

plt.legend(['straight', 'left', 'right', 'u-turn'], loc='upper left')
plt.ylabel('edge betweenness centrality')
plt.title('edge betweenness centrality of crossing connections depending of the turning direction')
plt.show()
# %%
# get important turns. turns that are above a ebc of 10_000_000
left_turns = []
for edge, count in zip(wg.es, ebc):
    if type(edge['osmid']) is not int and count > 10_000_000:
        if get_turn_direction(float(edge['turning_angle'])) == LEFT:
            left_turns.append({
                'id': edge.index,
                'geometry': edge['shifted_geometry'],
                'ebc': count
            })
left_turns = GeoDataFrame(left_turns)
left_turns.to_file('graph.gpkg', layer='left_turns', driver='GPKG')

# %%
# map ebc count to bicycle graph to find connected components
max_ebc: float = 0
min_ebc: float = 0

for count, edge in zip(ebc, routing_graph.edges(data=True, keys=True)):
    u, v, key, data = edge
    try:
        old_edge_key = routing_graph.edges[u, v, key]['old_edge_key']
    except KeyError:
        continue
    old_u, old_v, old_key = old_edge_key
    bicycle_graph.edges[old_u, old_v, old_key]['count'] = count

    osmid = data.get('osmid', None)
    if osmid is not None and osmid not in osmids_with_bike_infra:
        max_ebc = max(max_ebc, count)
        min_ebc = min(min_ebc, count)

for edge in bicycle_graph.edges(data=True, keys=True):
    u, v, key, data = edge

    osmid = data.get('osmid', None)
    if osmid is not None and osmid not in osmids_with_bike_infra:
        count = data.get('count', 0)
        color: str = mcolors.to_hex(plt.get_cmap('Reds')((count - min_ebc) / (max_ebc - min_ebc)))
    else:
        color = 'gray'
    bicycle_graph.edges[u, v, key]['color'] = color

ox.graph_to_gdfs(bicycle_graph, nodes=False, edges=True).to_file('graph.gpkg', layer='bicycle_graph_with_ebc', driver='GPKG')

# %%
# initialize gap evaluator
population_provider = GHSLPopulationProvider()
# %%
service_area_provider = ServiceAreaProvider(
    coverage_distance=300,
    buffer_value=50,
    routing_graph=bicycle_graph)

service_area_provider = ServiceAreaProvider(
    coverage_distance=300,
    buffer_value=30,
    routing_graph=bicycle_graph)
# %%
gap_evaluator = GapEvaluator(
    population_provider,
    service_area_provider,
    osmids_with_bike_infra,
    osmids_with_protected_bike_infra)

# %%
# find all paths in an directed graph from a start node
def find_all_paths(graph: nx.MultiDiGraph, start_node: NodeId) -> list[list[NodeId]]:
    paths = []

    def dfs(current_node: NodeId, current_path: list[NodeId]):
        current_path.append(current_node)
        neighbors = list(graph.successors(current_node))
        if not neighbors:
            paths.append(current_path.copy())
        else:
            for neighbor in neighbors:
                dfs(neighbor, current_path)
        current_path.pop()

    dfs(start_node, [])
    return paths

def get_osmids_from_path(graph: nx.MultiDiGraph, path: list[NodeId]) -> list[int]:
    osmids = list()
    for node in path:
        osmid = graph.nodes[node].get('osmid', None)
        if osmid is not None and osmid not in osmids:
            osmids.append(int(osmid))
    return osmids

def find_starting_nodes(graph: nx.MultiDiGraph) -> list[NodeId]:
    starting_nodes = []
    for node in graph.nodes:
        if graph.in_degree(node) == 0 and graph.out_degree(node) > 0:
            starting_nodes.append(node)
    return starting_nodes

def find_gaps(graph: nx.MultiDiGraph) -> list[list[int]]:
    gaps: list[list[int]] = []
    starting_nodes: list[NodeId] = find_starting_nodes(graph)
    for start_node in tqdm(starting_nodes, desc='finding gaps', unit='start_node'):
        paths = find_all_paths(graph, start_node)
        for path in paths:
            path_osmids = get_osmids_from_path(graph, path)
            if len(path_osmids) > 0:
                gaps.append(path_osmids)
    return gaps
#%%
def is_relevant_edge(edge: EdgeId, graph: nx.MultiDiGraph) -> bool:
    u, v, key = edge
    count: float = graph.edges[u, v, key].get('count', 0)
    reversed_edge = get_reversed_key(edge)
    u_reversed, v_reversed, key_reversed = reversed_edge
    if graph.has_edge(u_reversed, v_reversed, key_reversed):
        reversed_count: float = graph.edges[u_reversed, v_reversed, key_reversed].get('count', 0)
    else:
        reversed_count: float = 0
    
    if count >= 8_000_000:
        return True
    else:
        return False

for count, edge in zip(ebc, routing_graph.edges(data=True, keys=True)):
    u, v, key, data = edge
    routing_graph.edges[u, v, key]['count'] = count

directed_gap_graph = routing_graph.copy()
for edge in routing_graph.edges(data=True, keys=True):
    u, v, key, data = edge

    if not is_relevant_edge((u, v, key), routing_graph):
        directed_gap_graph.remove_edge(u, v, key)
    else:
        osmid = data.get('osmid', None)
        if osmid is None:
            directed_gap_graph.remove_edge(u, v, key)
        elif type(osmid) is int and osmid in osmids_with_bike_infra:
            directed_gap_graph.remove_edge(u, v, key)
        elif type(osmid) is tuple and all(os in osmids_with_bike_infra for os in get_all_osmids(osmid)):
            directed_gap_graph.remove_edge(u, v, key)

# remove isolated nodes
isolated_nodes = list(nx.isolates(directed_gap_graph))
directed_gap_graph.remove_nodes_from(isolated_nodes)

plot_shifted_graph(directed_gap_graph)[0].to_file('graph.gpkg', layer='directed_gap_graph', driver='GPKG')

gaps = find_gaps(directed_gap_graph)
print(f'found {len(gaps)} gaps in the directed graph')

# %%
# check if gap is a subset of another gap
unique_gaps = []
for idx, gap in enumerate(gaps):
    gap_is_sublist = False
    for other_idx, other_gap in enumerate(gaps):
        if idx == other_idx:
            continue
        if is_sublist(gap, other_gap):
            gap_is_sublist = True
            break
    if not gap_is_sublist:
        unique_gaps.append(gap)
print(f'found {len(unique_gaps)} unique gaps in the directed graph')
# %%
num_of_gaps_in_both_directions = 0
for idx, gap in enumerate(unique_gaps):
    for other_idx, other_gap in enumerate(unique_gaps):
        if idx == other_idx:
            continue
        if gap == list(reversed(list(other_gap))):
            num_of_gaps_in_both_directions += 1
            break

print(f'found {num_of_gaps_in_both_directions} gaps that are the same in both directions')

#%%
gap_evaluator.with_connectedness_metrics(False)
gap_evaluator.with_population_metrics(True)
gap_evaluator.with_area_coverage_metrics(True)
gaps_df = gap_evaluator.calculate_gap_metrics(unique_gaps, bicycle_graph)
gaps_df

# %%
for idx, gap in gaps_df.iterrows():
    gap_gdf = gpd.GeoDataFrame([gap], geometry='geometry', crs='EPSG:4326')
    gap_gdf.to_file('gaps_analysis.gpkg', layer=f'gap_{idx}', driver='GPKG')
# %%
# sort gaps by added population coverage
gaps_df = gaps_df.sort_values(by='additional_population_coverage', ascending=False)
gaps_df.head(20)
# %%
# iterate over gaps and save each gap as a layer in a geopackage
for idx, gap in tqdm(gaps_df[:10].iterrows(), desc='saving gaps to geopackage', unit='gap'):
    gap_gdf = gpd.GeoDataFrame([gap], geometry='gap_geometry', crs='EPSG:4326')
    gap_gdf.to_file('gaps_analysis.gpkg', layer=f'gap_geometry_{idx}', driver='GPKG')
    gap_polygon_gdf = gpd.GeoDataFrame([gap], geometry='gap_polygon', crs='EPSG:4326')
    gap_polygon_gdf.to_file('gaps_analysis.gpkg', layer=f'gap_polygon_{idx}', driver='GPKG')
    reachable_edges_gdf = gpd.GeoDataFrame([gap], geometry='reachable_edges', crs='EPSG:4326')
    reachable_edges_gdf.to_file('gaps_analysis.gpkg', layer=f'reachable_edges_{idx}', driver='GPKG')

# %%
ranked_gaps = gpd.GeoDataFrame()
tmp_gaps_df = gaps_df.sort_values(by='additional_population_coverage', ascending=False)
# add top 1 gaps to ranked_gaps
top_gap = tmp_gaps_df.head(1)
ranked_gaps = pd.concat([ranked_gaps, top_gap])

# add gap polygon to protected bike infra polygon
gap_evaluator.protected_bike_infra_polygon = shapely.union_all([gap_evaluator.protected_bike_infra_polygon, top_gap['gap_polygon'].values[0]])
tmp_gaps_df = tmp_gaps_df.drop(top_gap.index)

for _ in tqdm(range(10), desc='ranking gaps', unit='iteration'):
    for idx, gap in tmp_gaps_df.iterrows():
        gap_polygon = gap['gap_polygon']
        added_area_coverage = gap_evaluator.get_added_area_coverage(gap_polygon)
        tmp_gaps_df.at[idx, 'additional_coverage'] = added_area_coverage

        added_population_coverage = gap_evaluator.get_added_population(gap_polygon)
        tmp_gaps_df.at[idx, 'additional_population_coverage'] = added_population_coverage

    tmp_gaps_df = tmp_gaps_df.sort_values(by='additional_population_coverage', ascending=False)
    top_gap = tmp_gaps_df.head(1)
    ranked_gaps = pd.concat([ranked_gaps, top_gap])
    gap_evaluator.protected_bike_infra_polygon = shapely.union_all([gap_evaluator.protected_bike_infra_polygon, top_gap['gap_polygon'].values[0]])
    tmp_gaps_df = tmp_gaps_df.drop(top_gap.index)

ranked_gaps
# %%

gap1 = gaps_df.loc[72]
gap2 = gaps_df.loc[4]

print(f'gap1: {gap1['gap']}')
print(f'gap2: {gap2['gap']}')

# %%
def jaccard_index(list1: list[int], list2: list[int]) -> float:
    set1 = set(list1)
    set2 = set(list2)
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union != 0 else 0.0

print(jaccard_index(gap1['gap'], gap2['gap']))
# %%
list1 = [7, 6, 5]
list2 = [5, 6, 7]

jaccard_index(list2, list1)

# %%
line1 = gap1['gap_geometry']
line2 = gap2['gap_geometry']

# get the percentage of overlap between two lines
def line_overlap_percentage(line1: shapely.LineString | shapely.MultiLineString, line2: shapely.LineString | shapely.MultiLineString) -> float:
    intersection = line1.intersection(line2)
    if intersection.is_empty:
        return 0.0
    return intersection.length / min(line1.length, line2.length)

line_overlap_percentage(line1, line2)

# %%
overlaps = []
for idx1, gap1 in gaps_df.iterrows():
    for idx2, gap2 in gaps_df.iterrows():
        if idx1 == idx2:
            continue
        overlap = line_overlap_percentage(gap1['gap_geometry'], gap2['gap_geometry'])
        overlaps.append((idx1, idx2, overlap))
#%%
# get boxplot of overlaps
overlap_values = [o[2] for o in overlaps]
plt.figure(figsize=(10, 6))
plt.boxplot(overlap_values)
plt.title('Boxplot of Line Overlap Percentages Between Gaps')
plt.ylabel('Overlap Percentage')
plt.show()
# %%
# get number of overlaps above a certain threshold
threshold = 0.4
num_overlaps_above_threshold = len([o for o in overlaps if o[2] > threshold])
print(f'Number of overlaps above {threshold * 100}%: {num_overlaps_above_threshold / len(overlaps) * 100:.2f}%')
# %%
# combine gaps if they are similar enough
print(f'len before combining: {len(unique_gaps)}')
iteration = 0
while True:
    print(f'combination iteration {iteration}')
    combinations = 0
    for idx1, gap1 in enumerate(unique_gaps):
        line1 = ox.graph_to_gdfs(bicycle_graph.subgraph(gap1), nodes=False, edges=True)['geometry'].unary_union
        for idx2, gap2 in enumerate(unique_gaps):
            if gap1 == gap2:
                continue
            line2 = ox.graph_to_gdfs(bicycle_graph.subgraph(gap2), nodes=False, edges=True)['geometry'].unary_union
            overlap = line_overlap_percentage(line1, line2)
            if overlap > 0.4:
                print(f'combining gap {idx1} and gap {idx2} with overlap {overlap * 100:.2f}%')
                combined_gap = list(set(gap1).union(set(gap2)))
                unique_gaps.remove(gap1)
                unique_gaps.remove(gap2)
                unique_gaps.append(combined_gap)
                combinations += 1
                break
    if combinations == 0:
        break
    iteration += 1

print(f'len after combining: {len(unique_gaps)}')
#%%
unique_gaps
# %%
# get geometry of subgraph
gap_subgraph = bicycle_graph.subgraph(unique_gaps[0])
gap_gdf = ox.graph_to_gdfs(gap_subgraph, nodes=False, edges=True)['geometry'].unary_union
gap_gdf['geometry'].unary_union

# %%
