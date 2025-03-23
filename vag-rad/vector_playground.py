#%%
import osmnx as ox
from utils.utils import *
from utils.graph_builder import split_nodes
from utils.utils import shift_graph, plot_shifted_graph, plot_graph

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

#graph = ox.graph_from_bbox(bbox=(11.112325,49.454484,11.112778,49.454985), simplify=False, retain_all=True, custom_filter=[bikeable_ways, bikeable_areas], truncate_by_edge=True)

graph = ox.graph_from_place(query=place_name, simplify=False, retain_all=True, custom_filter=[bikeable_ways, bikeable_areas], truncate_by_edge=True)

graph = split_nodes(nx.DiGraph(graph))

# %%

shifted_graph = shift_graph(graph)
edges_df, _, _ = plot_shifted_graph(shifted_graph)
edges_df.to_file(filename='graph.gpkg', layer='shifted_graph', driver='GPKG')

plot_graph(graph).to_file(filename='graph.gpkg', layer='original_graph', driver='GPKG')
# %%
