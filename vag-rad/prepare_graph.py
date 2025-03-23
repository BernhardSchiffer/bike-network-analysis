# %% 
# imports
import osmnx as ox
import networkx as nx
import folium
import leafmap.foliumap as leafmap
from utils.graph_builder import GraphBuilder, split_nodes
from utils.utils import shift_graph

# %%
def debug_plot(graph: nx.DiGraph):
    map = leafmap.Map(location=[49.451900, 11.076608], zoom_start=12, crs='EPSG3857')

    for _, node_data in graph.nodes(data=True):
        folium.Marker((node_data['y'], node_data['x']), f'osmid: {node_data["osmid"]}').add_to(map)

    for edge_start_id, edge_dest_id, _ in graph.edges(data=True):
        start_node = graph.nodes[edge_start_id]
        dest_node = graph.nodes[edge_dest_id]
        folium.PolyLine([(start_node['y'], start_node['x']), (dest_node['y'], dest_node['x'])], color='blue').add_to(map)

    return map

# %%
# fetch graph of all streets available by bike
place_name = 'Nürnberg'
# use specific overpass settings
ox.settings.overpass_settings = '[out:json][timeout:{timeout}][date:"2025-03-15T21:21:30Z"]{maxsize}'

bikeable_ways = (
        '["highway"]["area"!~"yes"]["access"!~"private"]'
        '["highway"!~"abandoned|bus_guideway|construction|corridor|elevator|escalator|footway|'
        'motor|no|planned|platform|proposed|raceway|razed|steps"]'
        '["bicycle"!~"no"]["service"!~"private"]'
    )

bikeable_areas = '["area"~"yes"]["bicycle"~"yes"]'

graph = ox.graph_from_place(query=place_name, simplify=False, retain_all=True, custom_filter=[bikeable_ways, bikeable_areas])
#graph = ox.graph_from_bbox((11.112403,49.454498,11.112832,49.454774), network_type='bike', simplify=False, retain_all=True, truncate_by_edge=True)

graph = nx.DiGraph(graph)
#%%
# set node and edge attributes
graph_builder = GraphBuilder()
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
# %%
# save graph to file
ox.io.save_graphml(nx.MultiDiGraph(graph), filepath='expanded_bicycle_graph.graphml')

# %%
