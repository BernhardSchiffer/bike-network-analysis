#%%
# imports
import time
from collections import Counter
from typing import Callable

import geopandas as gpd
import igraph as ig
import matplotlib.colors
import matplotlib.pyplot as plt
import momepy as mp
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
import shapely
from tqdm import tqdm

from utils.demand_provider import VagRadDemandProvider
from utils.overpass_utils import fetch_city_polygon
from utils.population_provider import GHSLPopulationProvider
from utils.utils import (
    buffer_in_meters,
    get_reversed_key,
    parse_junction_osmid,
    parse_old_edge_key,
)
from utils.visualization_utils import plot_graph, plot_shifted_graph

type RenderOrderFunc = Callable[[float], float]

def default_render_order_func(count):
    return count

def plot_edge_betweenness_centrality(graph: nx.MultiDiGraph, ebc: list[float], expanded: bool = False, cmap = plt.get_cmap('turbo'), normalize: bool = True, render_order_func: RenderOrderFunc = default_render_order_func) -> gpd.GeoDataFrame:
    edges_counter = Counter()

    for edge, count in zip(graph.edges, ebc):
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

    if normalize:
        max_value = edges_counter.most_common(1)[0][1]
    else:
        max_value = 1.0

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
        'slope': [],
        'render_order': []
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
            transparency = cmap(count/max_value)[3]
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
            attributes['render_order'].append(render_order_func(count))
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
# load graph from file
routing_graph = ox.load_graphml('simplified_bicycle_graph.graphml', node_dtypes={'osmid': str}, edge_dtypes={'weight': float, 'shifted_geometry': lambda x: shapely.from_wkt(x), 'osmid': parse_junction_osmid, 'penalty': float, 'slope_percentage': float, 'length': float, 'old_edge_key': parse_old_edge_key})

# %%
# map edge length to kilometers
for u, v, key, data in routing_graph.edges(data=True, keys=True):
    length_m = data.get('length', None)
    if length_m is not None:
        routing_graph.edges[u, v, key]['length_km'] = length_m / 1000.0
#%%
# add population data to nodes
population_provider = GHSLPopulationProvider()
for node, data in tqdm(list(routing_graph.nodes(data=True)), desc='adding population counts to nodes', unit='node'):
    point = shapely.Point(data['x'], data['y'])
    population = population_provider.get_population_at_point(point)
    routing_graph.nodes[node]['population'] = population

# %%
def get_edge_tessellation(graph: nx.MultiDiGraph, area: shapely.Polygon) -> gpd.GeoDataFrame:
    edges: gpd.GeoDataFrame = ox.graph_to_gdfs(graph, nodes=False)
    area = gpd.GeoSeries([area], crs='EPSG:4326').to_crs('32633').iloc[0]

    # remove intersection edges. edges that habe 'turning_angle' attribute
    to_remove_edges = []
    for s, d, k, data in graph.edges(data=True, keys=True):
        try:
            data['turning_angle']
            to_remove_edges.append((s, d, k))
        except KeyError:
            pass
    edges = edges.drop(to_remove_edges).to_crs('32633')

    assert not edges.crs.is_geographic 

    tess = mp.Tessellation(edges, 'osmid', area)
    return tess.tessellation

def get_node_area_weights(graph: nx.MultiDiGraph, area: shapely.Polygon) -> pd.Series:
    nodes, edges = ox.graph_to_gdfs(graph, nodes=True, edges=True)

    tessalation = get_edge_tessellation(graph, area)
    tessalation['area'] = tessalation.geometry.area

    tessalation = tessalation.set_index('osmid')

    for idx, row in edges.iterrows():
        osm_id = row['osmid']
        # add area to rows
        try:
            tess_area = tessalation.loc[osm_id]['area']
            edges.at[idx, 'tess_area'] = tess_area
        except KeyError:
            edges.at[idx, 'tess_area'] = 0.0

    from_nodes = edges.groupby('u')['tess_area'].sum() / 2
    to_nodes = edges.groupby('v')['tess_area'].sum() / 2

    node_area_weights = from_nodes.add(to_nodes, fill_value=0)
    node_osmids = nodes['osmid']

    # join node osmid with area weights
    node_area_weights = node_area_weights.to_frame().join(node_osmids, how='left')
    node_area_weights.columns = ['area_weight', 'osmid']

    return node_area_weights.groupby('osmid')['area_weight'].sum()

# %%
# add area weights to nodes
place_name = 'Nürnberg'
nbg_area = fetch_city_polygon(place_name)

nbg_area: shapely.Polygon = buffer_in_meters(nbg_area, 5050)

#get_edge_tessellation(routing_graph, nbg_area).to_crs('EPSG:4326').to_file('ebc.gpkg', layer='tessellation', driver='GPKG')

node_area_weights_file = 'node_area_weights.pkl'
try:
    node_weights = pd.read_pickle(node_area_weights_file)
except FileNotFoundError:
    node_weights = get_node_area_weights(routing_graph, nbg_area)
    node_weights.to_pickle(node_area_weights_file)

for node, data in tqdm(list(routing_graph.nodes(data=True)), desc='adding covered area to nodes', unit='node'):
    osmid = data['osmid']
    try:
        area_weight = node_weights[osmid]
        routing_graph.nodes[node]['area_weight'] = area_weight
    except KeyError:
        routing_graph.nodes[node]['area_weight'] = 0.0

# %%
# add vag rad demand to nodes
vag_rad_demand_provider = VagRadDemandProvider()

points: dict[shapely.Point, tuple[float, float]] = {}

for node, data in tqdm(list(routing_graph.nodes(data=True)), desc='adding vag rad demand to nodes', unit='node'):
    point = shapely.Point(data['x'], data['y'])
    # check if demand at point was already calculated
    if (point in points):
        demand = points[point]
    else:
        demand = vag_rad_demand_provider.get_demand_at_point(point)
        points[point] = demand
    routing_graph.nodes[node]['vag_rad_demand_starts'] = demand[0]
    routing_graph.nodes[node]['vag_rad_demand_endings'] = demand[1]

#%%
# create igraph from networkx graph for ebc calculation
wg: ig.Graph = ig.Graph.from_networkx(routing_graph)

#%%
# get start and target nodes for ebc calculation
def is_intersection_edge(edge) -> bool:
    return edge['turning_angle'] is not None

start_nodes = set()
target_nodes = set()

# get nodes that are at the end of dead ends
for node in wg.vs:
    in_degree = node.indegree()
    out_degree = node.outdegree()
    if in_degree == 0:
        start_nodes.add(node)
    if out_degree == 0:
        target_nodes.add(node)

# get intersection nodes
for edge in wg.es:
    if is_intersection_edge(edge):
        source_node = wg.vs[edge.source]
        target_node = wg.vs[edge.target]

        start_nodes.add(source_node)
        target_nodes.add(source_node)

print(f'total number of nodes: {len(wg.vs)}')
print(f'found {len(start_nodes)} start nodes')
print(f'found {len(target_nodes)} target nodes')

# plot start and target nodes
def get_shifted_point(node):
    y = node['y_shifted']
    x = node['x_shifted']
    if y is not None and x is not None:
        return shapely.Point(x, y)
    
    return shapely.Point(node['x'], node['y'])

gpd.GeoDataFrame({'osmid': [node['osmid'] for node in start_nodes], 'node_id': [node.index for node in start_nodes], 'geometry': [get_shifted_point(node) for node in start_nodes]}, geometry='geometry', crs='EPSG:4326').to_file('ebc.gpkg', layer='start_nodes', driver='GPKG')

gpd.GeoDataFrame({'osmid': [node['osmid'] for node in target_nodes], 'node_id': [node.index for node in target_nodes], 'geometry': [get_shifted_point(node) for node in target_nodes]}, geometry='geometry', crs='EPSG:4326').to_file('ebc.gpkg', layer='target_nodes', driver='GPKG')

# %%
# create enum for weight_function
from enum import Enum


class weight_function(Enum):
    SPACIAL_NORMALIZATION = 'spacial_normalization'
    GRAVITY_MODEL = 'gravity_model'
    EXPONENTIAL_GRAVITY_MODEL = 'exponential_gravity_model'
    WEIGHT_MULTIPLICATION = 'weight_multiplication'

class weight_combinator(Enum):
    MULTIPLY = 'multiply'
    ADD = 'add'

class node_weight:
    def __init__(self, weight_function: weight_function, source_weights: str, target_weights: str, combinator: weight_combinator = weight_combinator.MULTIPLY, factor: float = 1.0):
        self.weight_function = weight_function
        self.source_weights = source_weights
        self.target_weights = target_weights
        self.combinator = combinator
        self.factor = factor

    def to_dict(self) -> dict:
        return {
            'weight_function': self.weight_function.value,
            'source_weights': self.source_weights,
            'target_weights': self.target_weights,
            'combinator': self.combinator.value,
            'factor': self.factor
        }

area_normalization = node_weight(weight_function.SPACIAL_NORMALIZATION, 'area_weight', 'area_weight').to_dict()

population_weights = node_weight(weight_function.GRAVITY_MODEL, 'population', 'population').to_dict()

population_weights_exponential = node_weight(weight_function.EXPONENTIAL_GRAVITY_MODEL, 'population', 'population').to_dict()

vag_rad_weights = node_weight(weight_function.GRAVITY_MODEL, 'vag_rad_demand_starts', 'vag_rad_demand_endings').to_dict()

target_nodes = list(target_nodes)
start_nodes = list(start_nodes)

# weighted cutoff
start = time.time()
ebc = wg.edge_betweenness_weighted(directed=True, distances="weight", edge_weights="weight", sources=start_nodes, targets=target_nodes, node_weights=[], lower_limit=0, upper_limit=5000, normalized=False)
end = time.time()
print(f'calculated edge betweenness centrality in {end - start} seconds')
plot_edge_betweenness_centrality(routing_graph, ebc, expanded=True).to_file('ebc.gpkg', layer='ebc_cutoff', driver='GPKG')

# 0 to cutoff
start = time.time()
ebc = wg.edge_betweenness_weighted(directed=True, distances="length", edge_weights="weight", sources=start_nodes, targets=target_nodes, node_weights=[], lower_limit=0, upper_limit=5000, normalized=False)
end = time.time()
print(f'calculated edge betweenness centrality in {end - start} seconds')
plot_edge_betweenness_centrality(routing_graph, ebc, expanded=True).to_file('ebc.gpkg', layer='ebc_length', driver='GPKG')

# lower and upper limit
start = time.time()
ebc = wg.edge_betweenness_weighted(directed=True, distances="length", edge_weights="weight", sources=start_nodes, targets=target_nodes, node_weights=[], lower_limit=500, upper_limit=5000, normalized=False)
end = time.time()
print(f'calculated edge betweenness centrality in {end - start} seconds')
plot_edge_betweenness_centrality(routing_graph, ebc, expanded=True).to_file('ebc.gpkg', layer='ebc_500_5000', driver='GPKG')

# area normalization
start = time.time()
ebc = wg.edge_betweenness_weighted(directed=True, distances="length", edge_weights="weight", sources=start_nodes, targets=target_nodes, node_weights=[area_normalization], lower_limit=500, upper_limit=5000, normalized=False)
end = time.time()
print(f'calculated edge betweenness centrality in {end - start} seconds')
plot_edge_betweenness_centrality(routing_graph, ebc, expanded=True).to_file('ebc.gpkg', layer='ebc_area_normalization', driver='GPKG')

# area normalization + population weights
start = time.time()
ebc = wg.edge_betweenness_weighted(directed=True, distances="length", edge_weights="weight", sources=start_nodes, targets=target_nodes, node_weights=[population_weights], lower_limit=500, upper_limit=5000, normalized=False)
end = time.time()
print(f'calculated edge betweenness centrality in {end - start} seconds')
plot_edge_betweenness_centrality(routing_graph, ebc, expanded=True).to_file('ebc.gpkg', layer='ebc_population', driver='GPKG')

# area normalization + population weights
start = time.time()
ebc = wg.edge_betweenness_weighted(directed=True, distances="length", edge_weights="weight", sources=start_nodes, targets=target_nodes, node_weights=[area_normalization, population_weights], lower_limit=500, upper_limit=5000, normalized=False)
end = time.time()
print(f'calculated edge betweenness centrality in {end - start} seconds')
plot_edge_betweenness_centrality(routing_graph, ebc, expanded=True).to_file('ebc.gpkg', layer='ebc_area_normalization_population', driver='GPKG')

# area normalization + population weights exponential
start = time.time()
ebc = wg.edge_betweenness_weighted(directed=True, distances="length_km", edge_weights="weight", sources=start_nodes, targets=target_nodes, node_weights=[area_normalization, population_weights_exponential], lower_limit=0.5, upper_limit=5, normalized=False)
end = time.time()
print(f'calculated edge betweenness centrality in {end - start} seconds')
plot_edge_betweenness_centrality(routing_graph, ebc, expanded=True).to_file('ebc.gpkg', layer='ebc_area_normalization_population_exponential', driver='GPKG')

# area normalization + population vag rad weights
start = time.time()
ebc = wg.edge_betweenness_weighted(directed=True, distances="length", edge_weights="weight", sources=start_nodes, targets=target_nodes, node_weights=[area_normalization, vag_rad_weights], lower_limit=500, upper_limit=5000, normalized=False)
end = time.time()
print(f'calculated edge betweenness centrality in {end - start} seconds')
plot_edge_betweenness_centrality(routing_graph, ebc, expanded=True).to_file('ebc.gpkg', layer='ebc_area_normalization_bike_sharing', driver='GPKG')

# %%
# read ebc from geopackage
def get_ebc_values_from_gpkg(gpkg_filename: str, layer_name: str, graph: nx.MultiDiGraph) -> list[float]:
    ebc_gdf = gpd.read_file(gpkg_filename, layer=layer_name)
    # set index to u, v, key
    ebc_gdf = ebc_gdf.set_index(['u', 'v', 'key'])
    
    ebc_values = []
    for u, v, key in graph.edges(keys=True):
        try:
            ebc_value = ebc_gdf.loc[u, v, key]['count']
            ebc_values.append(ebc_value)
        except KeyError:
            ebc_values.append(0.0)
    return ebc_values

# compare two ebc value lists
def compare_ebc_values(ebc1: list[float], ebc2: list[float]) -> list[float]:
    if len(ebc1) != len(ebc2):
        raise ValueError('ebc1 and ebc2 must have the same length')
    
    # normalize both lists to [0, 1]
    ebc1 = np.divide(ebc1, max(ebc1))
    ebc2 = np.divide(ebc2, max(ebc2))

    # bring differences to range [0, 1] with 0.5 as no difference
    ebc_diff = np.subtract(ebc1, ebc2)
    ebc_diff = np.add(ebc_diff, 1.0)
    ebc_diff = np.divide(ebc_diff, 2.0)

    return ebc_diff

# give higher difference values a higher render order
def diff_render_order_func(count):
    return abs(0.5 - count)

# %%
# load computed ebc values
ebc_cutoff = get_ebc_values_from_gpkg('ebc.gpkg', 'ebc_cutoff', routing_graph)

ebc_length = get_ebc_values_from_gpkg('ebc.gpkg', 'ebc_length', routing_graph)

ebc_500_5000 = get_ebc_values_from_gpkg('ebc.gpkg', 'ebc_500_5000', routing_graph)

ebc_population = get_ebc_values_from_gpkg('ebc.gpkg', 'ebc_population', routing_graph)

ebc_area_normalization_population = get_ebc_values_from_gpkg('ebc.gpkg', 'ebc_area_normalization_population', routing_graph)

ebc_area_normalization_population_exponential = get_ebc_values_from_gpkg('ebc.gpkg', 'ebc_area_normalization_population_exponential', routing_graph)

# plot differences
# weight vs length
ebc_diff = compare_ebc_values(ebc_cutoff, ebc_length)
plot_edge_betweenness_centrality(routing_graph, ebc_diff, expanded=True, cmap=plt.get_cmap('PiYG'), normalize=False, render_order_func=diff_render_order_func).to_file('ebc.gpkg', layer='ebc_diff_weight_vs_length', driver='GPKG')

# upper limit vs lower and upper limit
ebc_diff = compare_ebc_values(ebc_length, ebc_500_5000)
plot_edge_betweenness_centrality(routing_graph, ebc_diff, expanded=True, cmap=plt.get_cmap('PiYG'), normalize=False, render_order_func=diff_render_order_func).to_file('ebc.gpkg', layer='ebc_diff_length_vs_500_5000', driver='GPKG')

# length vs population
ebc_diff = compare_ebc_values(ebc_length, ebc_population)
plot_edge_betweenness_centrality(routing_graph, ebc_diff, expanded=True, cmap=plt.get_cmap('PiYG'), normalize=False, render_order_func=diff_render_order_func).to_file('ebc.gpkg', layer='ebc_diff_length_vs_population', driver='GPKG')

# length vs area normalization + population
ebc_diff = compare_ebc_values(ebc_length, ebc_area_normalization_population)
plot_edge_betweenness_centrality(routing_graph, ebc_diff, expanded=True, cmap=plt.get_cmap('PiYG'), normalize=False, render_order_func=diff_render_order_func).to_file('ebc.gpkg', layer='ebc_diff_length_vs_area_normalization_population', driver='GPKG')

# population vs area normalization + population
ebc_diff = compare_ebc_values(ebc_population, ebc_area_normalization_population)
plot_edge_betweenness_centrality(routing_graph, ebc_diff, expanded=True, cmap=plt.get_cmap('PiYG'), normalize=False, render_order_func=diff_render_order_func).to_file('ebc.gpkg', layer='ebc_diff_population_vs_area_normalization_population', driver='GPKG')

# area normalization + population vs area normalization + population exponential
ebc_diff = compare_ebc_values(ebc_area_normalization_population, ebc_area_normalization_population_exponential)
plot_edge_betweenness_centrality(routing_graph, ebc_diff, expanded=True, cmap=plt.get_cmap('PiYG'), normalize=False, render_order_func=diff_render_order_func).to_file('ebc.gpkg', layer='ebc_diff_area_normalization_population_vs_exponential', driver='GPKG')

# %%
