# %% 
# imports
import networkx as nx
import osmnx as ox
import shapely
from tqdm import tqdm

from utils.graph_builder import (
    GraphBuilder,
    route_choice_model_1,
    route_choice_model_2,
    split_nodes,
)
from utils.overpass_utils import fetch_city_polygon
from utils.utils import buffer_in_meters, shift_graph
from utils.visualization_utils import plot_shifted_graph

# %%
# fetch graph of all streets available by bike
# get nuremberg area
place_name = 'Nürnberg'
nbg_area = fetch_city_polygon(place_name)

# create bbox with 4km buffer around nuremberg area
query_polygon = buffer_in_meters(nbg_area, 4000)

# get poygon of boundingbox
#bbox = 10.963379,49.559561,10.964554,49.560205
#query_polygon = shapely.box(*bbox)

# use specific overpass settings
ox.settings.overpass_settings = '[out:json][timeout:{timeout}][date:"2025-10-21T20:21:22Z"]{maxsize}'

bikeable_ways = (
        '["highway"]["area"!~"yes"]["access"!~"private"]'
        '["highway"!~"abandoned|bus_guideway|construction|corridor|elevator|escalator|footway|'
        'motor|no|planned|platform|proposed|raceway|razed|steps"]'
        '["bicycle"!~"no"]["service"!~"private"]'
    )

bikeable_areas = '["area"~"yes"]["bicycle"~"yes"]'
bikeable_footpaths = '["highway"~"footway"]["bicycle"~"yes|designated|dismount"]'
bikeable_crossings = '["crossing"~"yes"]["bicycle"~"yes"]'

graph = ox.graph_from_polygon(polygon=query_polygon, simplify=False, retain_all=True, custom_filter=[bikeable_ways, bikeable_areas, bikeable_footpaths])

print('number of edges in bikeable graph:', len(graph.edges))

not_bikeable_ways = '["highway"~"pedestrian"]["bicycle"!~"yes"]'
service_ways = '["highway"~"service"]["access"="no"]'
bus_only_ways = '["highway"~"service"]["bus"="yes"]'
trams_only_ways = '["highway"~"service"]["railway"="yes"]'

try:
    not_bikeable_graph = ox.graph_from_polygon(polygon=query_polygon, simplify=False, retain_all=True, custom_filter=[not_bikeable_ways, service_ways, bus_only_ways, trams_only_ways])
    print('number of edges in not bikeable graph:', len(not_bikeable_graph.edges))

    for e in tqdm(not_bikeable_graph.edges, desc='remove not bikeable edges', total=len(not_bikeable_graph.edges), unit='edges'):
        # remove edges that are not bikeable
        if graph.has_edge(*e):
            graph.remove_edge(*e)

    print('number of edges in bikeable graph after removing not bikeable edges:', len(graph.edges))
except Exception as e:
    pass

graph = ox.simplify_graph(graph, remove_rings=False, edge_attrs_differ=['osmid'])

# add geometry to straight edges that do not have a geometry
for u, v, key, data in graph.edges(data=True, keys=True):
    if data.get('geometry', None) is None:
        geometry = shapely.LineString([[graph.nodes[u]['x'], graph.nodes[u]['y']], [graph.nodes[v]['x'], graph.nodes[v]['y']]])
        graph.edges[u, v, key]['geometry'] = geometry

print('number of edges in bikeable graph after simplifying:', len(graph.edges))

# set node and edge attributes
graph_builder = GraphBuilder(query_polygon, route_choice_model_1)

# add paths where the street is oneway but bikes are allowed in both directions
edge_count_before = len(graph.edges)
graph = graph_builder.add_paths_for_bikeable_oneways(graph)
print(f'added {len(graph.edges) - edge_count_before} paths that are bikeable in both directions')

edge_count_before = len(graph.edges)
graph = graph_builder.enforce_oneway_bikepaths(graph)
print(f'removed {edge_count_before - len(graph.edges)} edges that are oneway for bikes')

graph = graph_builder.set_node_attributes(graph)
graph = graph_builder.set_edge_slope(graph)

print('stats of graph before splitting crossing nodes:')
print('number of edges:', len(graph.edges))
print('number of nodes:', len(graph.nodes))

graph = split_nodes(graph)
# enforces turning restrictions
# these restrictions exist mainly for cars, and have not much of an effect on the routing behavior for bikes
#graph = graph_builder.enforce_restrictions(graph)
graph = shift_graph(graph)

print('stats of graph after splitting crossing nodes:')
print('number of edges:', len(graph.edges))
print('number of nodes:', len(graph.nodes))

graph = graph_builder.set_edge_weights(graph)

# remove unconnected nodes
graph.remove_nodes_from(list(nx.isolates(graph)))

# save graph to file
#ox.save_graphml(nx.MultiDiGraph(graph), filepath='simplified_bicycle_graph.graphml')

# %%
# plot edges and nodes for debugging purposes
edges_df, nodes_df = plot_shifted_graph(graph, debug_marker=True)
edges_df.to_file(filename='debug_graph.gpkg', layer='shifted_routing_graph', driver='GPKG')
nodes_df.to_file(filename='debug_graph.gpkg', layer='routing_graph_nodes', driver='GPKG')

#plot_graph(graph).to_file(filename='graph.gpkg', layer='routing_graph', driver='GPKG')

# %%
print('number of nodes in graph:', len(graph.nodes))
intersection_nodes = [node for node, data in graph.nodes(data=True) if node != data['osmid']]
print(f'number of intersection nodes: {len(intersection_nodes)}')

# %%
# fetch graph of all streets available by bike
# get nuremberg area
place_name = 'Nürnberg'
nbg_area = fetch_city_polygon(place_name)

# create bbox with 4km buffer around nuremberg area
query_polygon = buffer_in_meters(nbg_area, 4000)

# use specific overpass settings
ox.settings.overpass_settings = '[out:json][timeout:{timeout}][date:"2025-10-21T20:21:22Z"]{maxsize}'

bikeable_ways = (
        '["highway"]["area"!~"yes"]["access"!~"private"]'
        '["highway"!~"abandoned|bus_guideway|construction|corridor|elevator|escalator|footway|'
        'motor|no|planned|platform|proposed|raceway|razed|steps"]'
        '["bicycle"!~"no"]["service"!~"private"]'
    )

bikeable_areas = '["area"~"yes"]["bicycle"~"yes"]'
bikeable_footpaths = '["highway"~"footway"]["bicycle"~"yes|designated|dismount"]'
bikeable_crossings = '["crossing"~"yes"]["bicycle"~"yes"]'

graph = ox.graph_from_polygon(polygon=query_polygon, simplify=False, retain_all=True, custom_filter=[bikeable_ways, bikeable_areas, bikeable_footpaths])

print('number of edges in bikeable graph:', len(graph.edges))

not_bikeable_ways = '["highway"~"pedestrian"]["bicycle"!~"yes"]'
service_ways = '["highway"~"service"]["access"="no"]'
bus_only_ways = '["highway"~"service"]["bus"="yes"]'
trams_only_ways = '["highway"~"service"]["railway"="yes"]'

not_bikeable_graph = ox.graph_from_polygon(polygon=query_polygon, simplify=False, retain_all=True, custom_filter=[not_bikeable_ways, service_ways, bus_only_ways, trams_only_ways])
print('number of edges in not bikeable graph:', len(not_bikeable_graph.edges))

for e in tqdm(not_bikeable_graph.edges, desc='remove not bikeable edges', total=len(not_bikeable_graph.edges), unit='edges'):
    # remove edges that are not bikeable
    if graph.has_edge(*e):
        graph.remove_edge(*e)

print('number of edges in bikeable graph after removing not bikeable edges:', len(graph.edges))

graph = ox.simplify_graph(graph, remove_rings=False, edge_attrs_differ=['osmid'])

# add geometry to straight edges that do not have a geometry
for u, v, key, data in graph.edges(data=True, keys=True):
    if data.get('geometry', None) is None:
        geometry = shapely.LineString([[graph.nodes[u]['x'], graph.nodes[u]['y']], [graph.nodes[v]['x'], graph.nodes[v]['y']]])
        graph.edges[u, v, key]['geometry'] = geometry

print('number of edges in bikeable graph after simplifying:', len(graph.edges))

# set node and edge attributes
graph_builder = GraphBuilder(query_polygon, route_choice_model_1)

# add paths where the street is oneway but bikes are allowed in both directions
edge_count_before = len(graph.edges)
graph = graph_builder.add_paths_for_bikeable_oneways(graph)
print(f'added {len(graph.edges) - edge_count_before} paths that are bikeable in both directions')

graph = graph_builder.set_node_attributes(graph)
graph = graph_builder.set_edge_slope(graph)
graph = graph_builder.set_edge_weights(graph)

# remove unconnected nodes
graph.remove_nodes_from(list(nx.isolates(graph)))

# save graph to file
ox.save_graphml(nx.MultiDiGraph(graph), filepath='bicycle_graph.graphml')

# %%
