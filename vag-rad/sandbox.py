#%%
# imports
import osmnx as ox
import igraph as ig
import time
from utils.utils import parse_junction_osmid, parse_old_edge_key, get_reversed_key
from utils.visualization_utils import plot_graph, plot_shifted_graph
import shapely
import geopandas as gpd
import networkx as nx
from collections import Counter
import matplotlib.colors
import matplotlib.pyplot as plt
from tqdm import tqdm
from utils.population_provider import GHSLPopulationProvider
from tqdm import tqdm
import numpy as np

#%%
# load graph from file
routing_graph = ox.load_graphml('simplified_bicycle_graph.graphml', node_dtypes={'osmid': str}, edge_dtypes={'weight': float, 'shifted_geometry': lambda x: shapely.from_wkt(x), 'osmid': parse_junction_osmid, 'penalty': float, 'slope_percentage': float, 'length': float, 'old_edge_key': parse_old_edge_key})

#%%
# add population data to nodes
population_provider = GHSLPopulationProvider()
for n in routing_graph.nodes:
    population = population_provider.get_population_at_point(shapely.Point(routing_graph.nodes[n]["x"], routing_graph.nodes[n]["y"]))
    routing_graph.nodes[n]['population'] = population

#%%
wg: ig.Graph = ig.Graph.from_networkx(routing_graph)

#%%
#polygon = shapely.box(49.464443, 11.160049, 49.467148, 11.167560)

def is_intersection_node(node) -> bool:
    return node['_nx_name'] != node['osmid']

def is_intersection_edge(edge) -> bool:
    return edge['turning_angle'] is not None

def is_within_polygon(node, polygon: shapely.Polygon) -> bool:
    point = shapely.Point(node['y'], node['x'])
    return point.within(polygon)

# get intersection nodes whom osmid is not already in the list
start_nodes = set()
target_nodes = set()
for node in wg.vs:
    in_degree = node.indegree()
    out_degree = node.outdegree()
    if in_degree == 0:
        start_nodes.add(node)
    if out_degree == 0:
        target_nodes.add(node)

for edge in wg.es:
    if is_intersection_edge(edge):
        source_node = wg.vs[edge.source]
        target_node = wg.vs[edge.target]

        start_nodes.add(source_node)
        target_nodes.add(source_node)

print(f'total number of nodes: {len(wg.vs)}')
print(f'found {len(start_nodes)} start nodes')
print(f'found {len(target_nodes)} target nodes')

#assert len(start_nodes) + len(target_nodes) == len(wg.vs), f"sum of start and target nodes ({len(start_nodes) + len(target_nodes)}) does not equal total number of nodes ({len(wg.vs)})"

def get_shifted_point(node):
    y = node['y_reversed']
    x = node['x_reversed']
    if y is not None and x is not None:
        return shapely.Point(x, y)
    
    y = node['y_not_reversed']
    x = node['x_not_reversed']
    if y is not None and x is not None:
        return shapely.Point(x, y)
    
    return shapely.Point(node['x'], node['y'])

gpd.GeoDataFrame({'osmid': [node['osmid'] for node in start_nodes], 'node_id': [node.index for node in start_nodes], 'geometry': [get_shifted_point(node) for node in start_nodes]}, geometry='geometry', crs='EPSG:4326').to_file('ebc_debug.gpkg', layer='start_nodes', driver='GPKG')

gpd.GeoDataFrame({'osmid': [node['osmid'] for node in target_nodes], 'node_id': [node.index for node in target_nodes], 'geometry': [get_shifted_point(node) for node in target_nodes]}, geometry='geometry', crs='EPSG:4326').to_file('ebc_debug.gpkg', layer='target_nodes', driver='GPKG')

#gpd.GeoDataFrame({'osmid': [node['osmid'] for node in duplicated_nodes], 'node_id': [node.index for node in duplicated_nodes], 'geometry': [get_shifted_point(node) for node in duplicated_nodes]}, geometry='geometry', crs='EPSG:4326').to_file('ebc_debug.gpkg', layer='duplicated_nodes', driver='GPKG')

# %%

start = time.time()
ebc = wg.edge_betweenness_weighted(directed=True, distances="weight", edge_weights="weight", sources=start_nodes, targets=target_nodes, node_weights="population", lower_limit=1000, upper_limit=4500, normalized=False)
end = time.time()
print(f'calculated edge betweenness centrality in {end - start} seconds')

#%%
start = time.time()
ebc_cutoff = wg.edge_betweenness(directed=True, weights="weight", normalized=False)
end = time.time()
print(f'calculated edge betweenness centrality in {end - start} seconds')
# %%
# normalize ebc values
norm_ebc = np.divide(ebc, max(ebc))
#%%
ebc_cutoff = np.divide(ebc_cutoff, max(ebc_cutoff))

# %%
ebc_diff = np.subtract(norm_ebc, ebc_cutoff)
ebc_diff = np.add(ebc_diff, 1.0)
ebc_diff = np.divide(ebc_diff, 2.0)

print(f'max ebc diff: {max(ebc_diff)}')
print(f'min ebc diff: {min(ebc_diff)}')
#%%
cmap = matplotlib.colors.LinearSegmentedColormap.from_list('blue_red_transparent', [(0, ('blue', 1.0)), (0.5, 'none'), (1, ('red', 1.0))], N=256)

cmap
# %%
def plot_edge_betweenness_centrality(graph: nx.MultiDiGraph, ebc: list[float], expanded: bool = False) -> gpd.GeoDataFrame:
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
        edges_df, _ = plot_shifted_graph(graph)
    else:
        edges_df, _ = plot_graph(graph)

    to_remove_edges = []
    attributes = {
        'count': [], 
        'color': [], 
        'transparency': [],
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
            color = matplotlib.colors.to_hex(cmap(count))
            transparency = cmap(count)[3]
            attributes['color'].append(color)
            attributes['transparency'].append(transparency)
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

# %%
plot_edge_betweenness_centrality(routing_graph, ebc_cutoff, expanded=True).to_file('ebc_debug.gpkg', layer='ebc_weight', driver='GPKG')
# %%

max_ebc = np.max(ebc)
max_ebc_cutoff = np.max(ebc_cutoff)

print(f'max ebc: {max_ebc}')
print(f'max ebc cutoff: {max_ebc_cutoff}')

ebc_normalized = [value / max_ebc for value in ebc]
ebc_cutoff_normalized = [value / max_ebc_cutoff for value in ebc_cutoff]

# %%
ebc_normalized
# %%
ebc_cutoff_normalized
# %%
np.subtract(ebc_normalized, ebc_cutoff_normalized)
# %%
populations = [routing_graph.nodes[n]['area_weight'] for n in routing_graph.nodes]
print(f'max population: {max(populations)}')
print(f'min population: {min(populations)}')
print(f'total population: {sum(populations)}')
print(f'area of nurenberg: {nbg_area.area}')
# %%
population_norm = {}
total = sum(populations)
for idx1, p1 in tqdm(enumerate(populations[:1000]), desc='normalize populations', unit='node'):
    tmp = []
    for idx2, p2 in enumerate(populations):
        if idx1 == idx2:
            tmp.append(0)
        tmp.append(p1 * (p2 / (total - p1)))
    population_norm[idx1] = tmp
#%%
for idx in population_norm:
    x = sum(population_norm[idx])
    if x > 1:
        print(f'sum of normalized populations: {x}')
# %%

for i in population_norm:
    print(i)
    break

# %%
import momepy as mp
from utils.population_provider import NurenbergDistrictPopulationProvider

nbg_population_provider = NurenbergDistrictPopulationProvider()
#%%
nbg_area = nbg_population_provider.nuremberg_area

nbg_area = gpd.GeoDataFrame(geometry=[nbg_area], crs='EPSG:4326').to_crs('32633').buffer(50).values[0]
nbg_area
# %%
edges: gpd.GeoDataFrame = ox.graph_to_gdfs(routing_graph, nodes=False)

# remove intersection edges. edges that habe 'turning_angle' attribute
to_remove_edges = []
for idx, row in edges.iterrows():
    try:
        s, d, k = idx
        routing_graph.edges[s, d, k]['turning_angle']
        to_remove_edges.append((s, d, k))
    except KeyError:
        pass
edges = edges.drop(to_remove_edges)
edges.to_crs('32633', inplace=True)
# %%
edges.crs.is_geographic
#%%
tess = mp.Tessellation(edges, 'osmid', nbg_area)
# %%
t = tess.tessellation
t.to_crs('EPSG:4326').to_file('ebc_debug.gpkg', layer='tessellation', driver='GPKG')
t['area'] = t.geometry.area
t

# %%
t = t.set_index('osmid')
t
# %%
for idx, row in edges.iterrows():
    osm_id = row['osmid']
    # add area to rows
    try:
        area = t.loc[osm_id]['area']
        edges.at[idx, 'tess_area'] = area
    except KeyError:
        edges.at[idx, 'tess_area'] = 0.0
#%%
edges
# %%
from_nodes = edges.groupby('u')['tess_area'].sum() / 2
to_nodes = edges.groupby('v')['tess_area'].sum() / 2
# %%
node_area_weights = from_nodes.add(to_nodes, fill_value=0)
node_area_weights

# %%
# add node osmid 
nodes = ox.graph_to_gdfs(routing_graph, edges=False)
node_osmids = nodes['osmid']
# %%
# join node osmid with area weights
node_area_weights = node_area_weights.to_frame().join(node_osmids, how='left')
node_area_weights.columns = ['area_weight', 'osmid']
node_area_weights
# %%
tmp = node_area_weights.groupby('osmid')['area_weight'].sum()
# %%
# get value from series
#%%
for node, data in routing_graph.nodes(data=True):
    osmid = data['osmid']
    try:
        area_weight = tmp[osmid]
        routing_graph.nodes[node]['area_weight'] = area_weight
    except KeyError:
        routing_graph.nodes[n]['area_weight'] = 0.0
# %%
