# %% 
# imports
import osmnx as ox
import networkx as nx
from utils.graph_builder import GraphBuilder
from utils.utils import shift_graph, plot_shifted_graph
from tqdm import tqdm

import shapely
from utils.graph_builder import get_turn_penalty, get_angle_between_edges

# %%
# fetch graph of all streets available by bike
place_name = 'Nürnberg'
# use specific overpass settings
ox.settings.overpass_settings = '[out:json][timeout:{timeout}][date:"2025-05-30T20:21:17Z"]{maxsize}'

bikeable_ways = (
        '["highway"]["area"!~"yes"]["access"!~"private"]'
        '["highway"!~"abandoned|bus_guideway|construction|corridor|elevator|escalator|footway|'
        'motor|no|planned|platform|proposed|raceway|razed|steps"]'
        '["bicycle"!~"no"]["service"!~"private"]'
    )

bikeable_areas = '["area"~"yes"]["bicycle"~"yes"]'
bikeable_footpaths = '["highway"~"footway"]["bicycle"~"yes|designated"]'
bikeable_crossings = '["crossing"~"yes"]["bicycle"~"yes"]'

#graph = ox.graph_from_place(query=place_name, simplify=False, retain_all=True, custom_filter=[bikeable_ways, bikeable_areas, bikeable_footpaths])
graph = ox.graph_from_bbox((11.052788,49.455830,11.053635,49.456263), simplify=False, retain_all=True, custom_filter=[bikeable_ways, bikeable_areas, bikeable_footpaths], truncate_by_edge=True)
print('number of edges in bikeable graph:', len(graph.edges))

not_bikeable_ways = '["highway"~"pedestrian"]["bicycle"!~"yes"]'
service_ways = '["highway"~"service"]["access"="no"]'
bus_only_ways = '["highway"~"service"]["bus"="yes"]'
trams_only_ways = '["highway"~"service"]["railway"="yes"]'

not_bikeable_graph = ox.graph_from_place(query=place_name, simplify=False, retain_all=True, custom_filter=[not_bikeable_ways, service_ways, bus_only_ways, trams_only_ways])
print('number of edges in not bikeable graph:', len(not_bikeable_graph.edges))

for e in tqdm(not_bikeable_graph.edges, desc='remove not bikeable edges', total=len(not_bikeable_graph.edges), unit='edges'):
    # remove edges that are not bikeable
    if graph.has_edge(*e):
        graph.remove_edge(*e)

print('number of edges in bikeable graph after removing not bikeable edges:', len(graph.edges))

graph = ox.simplification.simplify_graph(graph, remove_rings=False, edge_attrs_differ=['osmid'])
print('number of edges in bikeable graph after simplifying:', len(graph.edges))

ox.graph_to_gdfs(graph, nodes=False, edges=True).to_file('graph.gpkg', layer='shifted_routing_graph', driver='GPKG')
ox.graph_to_gdfs(graph, nodes=True, edges=False).to_file('graph.gpkg', layer='routing_graph_nodes', driver='GPKG')

for e in graph.edges(keys=True):
    print(e)
#%%
def split_nodes(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    edge_lookup = ox.graph_to_gdfs(graph, nodes=False, edges=True)

    # save old edge keys
    old_edge_keys: dict[tuple[int, int], dict[str, float]] = {}
    for u, v, k in graph.edges(keys=True):
        old_edge_keys[u, v, k] = {'old_edge_key': (u, v, k)}
    nx.set_edge_attributes(graph, old_edge_keys)

    for node_id, node_data in tqdm([x for x in graph.nodes(data=True)], desc='splitting crossing nodes', total=len(graph.nodes), unit='nodes'):
        in_edges = graph.in_edges(node_id, data=True)
        out_edges = graph.out_edges(node_id, data=True)

        in_osm_ids = [e[2].get("osmid") for e in in_edges]
        out_osm_ids = [e[2].get("osmid") for e in out_edges]
        osmids = set()
        # map lists in list to tuple
        in_osm_ids = [tuple(i) if type(i) == list else i for i in in_osm_ids]
        out_osm_ids = [tuple(i) if type(i) == list else i for i in out_osm_ids]
        osmids.update(out_osm_ids)
        osmids.update(in_osm_ids)

        # only split nodes with more than one in and out edge and only if they are not the same street
        if len(in_edges) <= 0 or len(out_edges) <= 0 or (len(osmids) == 1):
            continue

        # create new nodes for each out edge
        out_nodes = []
        for out_edge_start, out_edge_dest, out_edge_data in out_edges:
            graph.add_nodes_from([ ((out_edge_start, out_edge_dest), node_data) ])
            out_nodes.append((out_edge_start, out_edge_dest))
            graph.add_edges_from([ ((out_edge_start, out_edge_dest), out_edge_dest, out_edge_data) ])

        # create new edges for each in edge and connect them to the out nodes
        for in_edge_start, in_edge_dest, in_edge_data in in_edges:
            # create new node for each in edge
            graph.add_nodes_from([((in_edge_start, in_edge_dest), node_data)])
            # create new edges to each out edge
            for out_node, out_edge in zip(out_nodes, out_edges):
                out_edge_data = out_edge[2]
                # TODO calculate turn angle and set attribute if street is the same or changes
                e1 = edge_lookup.loc[in_edge_data['old_edge_key'][0], in_edge_data['old_edge_key'][1], 0]
                e2 = edge_lookup.loc[out_edge_data['old_edge_key'][0], out_edge_data['old_edge_key'][1], 0]

                # skip if the edge is a u turn
                if shapely.reverse(e1['geometry']) == e2['geometry']:
                    continue

                turning_angle = get_angle_between_edges(e1['geometry'], e2['geometry'])
                penalty = get_turn_penalty(turning_angle)
                weight = 0.6*1000*(penalty - 1.0)
                graph.add_edge((in_edge_start, in_edge_dest), out_node, length=0.0, weight=weight, penalty=penalty, turning_angle=turning_angle, osmid=(in_edge_data['osmid'], out_edge_data['osmid']))
            # add edge from previous node to new in node
            graph.add_edges_from([((in_edge_start, in_edge_dest)[0], (in_edge_start, in_edge_dest), in_edge_data)])
        # remove old node
        graph.remove_node(node_id)

    return graph

graph_builder = GraphBuilder()
graph = graph_builder.set_node_attributes(graph)
graph = split_nodes(graph)

ox.graph_to_gdfs(graph, nodes=False, edges=True).to_file('graph.gpkg', layer='shifted_routing_graph', driver='GPKG')
ox.graph_to_gdfs(graph, nodes=True, edges=False).reset_index(drop=True).to_file('graph.gpkg', layer='routing_graph_nodes', driver='GPKG')

for e in graph.edges(keys=True):
    print(e)
#%%
graph = shift_graph(graph)

edges_df, nodes_df = plot_shifted_graph(graph, debug_marker=True)
edges_df.to_file(filename='graph.gpkg', layer='shifted_routing_graph', driver='GPKG')
nodes_df.to_file(filename='graph.gpkg', layer='routing_graph_nodes', driver='GPKG')

#%%
# set node and edge attributes
graph_builder = GraphBuilder()

# add paths where the street is oneway but bikes are allowed in both directions
edge_count_before = len(graph.edges)
graph = graph_builder.add_paths_for_bikeable_oneways(graph)
print(f'added {len(graph.edges) - edge_count_before} paths that are bikeable in both directions')

graph = graph_builder.set_node_attributes(graph)
graph = graph_builder.set_edge_slope(graph)

print('stats of graph before splitting crossing nodes:')
print('number of edges:', len(graph.edges))
print('number of nodes:', len(graph.nodes))

graph = split_nodes(graph)
graph = shift_graph(graph)

print('stats of graph after splitting crossing nodes:')
print('number of edges:', len(graph.edges))
print('number of nodes:', len(graph.nodes))

graph = graph_builder.set_edge_weights(graph)

# save graph to file
ox.io.save_graphml(nx.MultiDiGraph(graph), filepath='simplified_bicycle_graph.graphml')

# %%
# plot edges and nodes for debugging purposes
edges_df, nodes_df = plot_shifted_graph(graph, debug_marker=True)
edges_df.to_file(filename='graph.gpkg', layer='shifted_routing_graph', driver='GPKG')
nodes_df.to_file(filename='graph.gpkg', layer='routing_graph_nodes', driver='GPKG')

#plot_graph(graph).to_file(filename='graph.gpkg', layer='routing_graph', driver='GPKG')

# %%
print('number of nodes in graph:', len(graph.nodes))
intersection_nodes = [node for node, data in graph.nodes(data=True) if node != data['osmid']]
print(f'number of intersection nodes: {len(intersection_nodes)}')
# %%
for s, d, data in graph.edges(data=True):
    if data.get('weight', None) <= 0:
        print(f'edge {s} -> {d} has negative weight: {data["weight"]}')
# %%
import shapely
from shapely import LineString
from utils.graph_builder import get_turn_penalty
def get_angle_between_edges(e1: LineString, e2: LineString):
    # calculate bearing of edges
    e1_start = e1.coords[-2]
    e1_dest = e1.coords[-1]
    e1_bearing = ox.bearing.calculate_bearing(e1_start[1], e1_start[0], e1_dest[1], e1_dest[0])
    e2_start = e2.coords[0]
    e2_dest = e2.coords[1]
    e2_bearing = ox.bearing.calculate_bearing(e2_start[1], e2_start[0], e2_dest[1], e2_dest[0])

    bearing_diff = e2_bearing - e1_bearing
    # normalize to -180, 180
    # left turns are negative, right turns are positive
    return (bearing_diff+180)%360-180

line_1 = shapely.from_wkt('LINESTRING (11.1060245 49.4605566, 11.1061533 49.4606054, 11.1061887 49.4606189, 11.1067644 49.460846, 11.1069229 49.4609024)')
line_2 = shapely.from_wkt('LINESTRING (11.1069229 49.4609024, 11.1072176 49.460981)')
line_3 = shapely.reverse(line_1)

turning_angle = get_angle_between_edges(line_1, line_2)
penalty = get_turn_penalty(turning_angle)
weight = 0.6*1000*(penalty - 1.0)
weight

# %%
ox.graph_to_gdfs(graph, nodes=True, edges=False).to_file('graph.gpkg', layer='routing_graph_nodes', driver='GPKG')
# %%
out_values = {v for _, _, v in graph.out_edges(1778177995, data="osmid", keys=False)}
print(out_values)
in_values = {v for _, _, v in graph.in_edges(1778177995, data="osmid", keys=False)}
print(in_values)
len(in_values | out_values)
# %%
for successor in graph.successors(35499214):
    print(successor)
# %%
# %%
node_id = 35499213
in_edges = graph.in_edges(node_id, data=True)
out_edges = graph.out_edges(node_id, data=True)

in_osm_ids = [e[2].get("osmid") for e in in_edges]
out_osm_ids = [e[2].get("osmid") for e in out_edges]
osmids = set()
# map lists in list to tuple
in_osm_ids = [tuple(i) if type(i) == list else i for i in in_osm_ids]
out_osm_ids = [tuple(i) if type(i) == list else i for i in out_osm_ids]
osmids.update(out_osm_ids)
osmids.update(in_osm_ids)

print(len(out_edges))
# %%
