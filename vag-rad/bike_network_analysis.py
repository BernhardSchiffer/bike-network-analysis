# %% 
# imports
import matplotlib.colors
import osmium.filter
import osmium.osm
import osmnx as ox
import networkx as nx
import folium
import matplotlib
import matplotlib.pyplot as plt
import osmium
from collections import Counter

from utils.polygon_filter import PolygonFilter
from utils.utils import *

# %% 
# evaluation of osm features in Nürnberg
print("Total number of objects in Mittelfranken:", sum(1 for o in osmium.FileProcessor('mittelfranken-latest.osm.pbf')))

print("Of which are ways with tags:", sum(1 for o in osmium.FileProcessor('mittelfranken-latest.osm.pbf').with_filter(osmium.filter.EmptyTagFilter()).with_filter(osmium.filter.EntityFilter(osmium.osm.WAY))))

place = ox.geocode_to_gdf('Nürnberg')
print("Of which are ways within Nürnberg:",
      sum(1 for o in osmium.FileProcessor('mittelfranken-latest.osm.pbf').with_locations().with_filter(osmium.filter.EmptyTagFilter()).with_filter(osmium.filter.EntityFilter(osmium.osm.WAY)).with_filter(PolygonFilter(place.geometry[0]))))

# %%
# get all osm tags of ways in Nürnberg
place = ox.geocode_to_gdf('Nürnberg')
stats = Counter()

edges_in_nbg = []

for w in osmium.FileProcessor('mittelfranken-latest.osm.pbf').with_locations().with_filter(osmium.filter.EmptyTagFilter()).with_filter(osmium.filter.EntityFilter(osmium.osm.WAY)).with_filter(PolygonFilter(place.geometry[0])):
    for k, v in w.tags:
        stats.update([(k, v)])

# %%
# get all bicycle related tags in Nürnberg
bicycle_tags = []
for (key, value) in stats.keys():
    if('cycle' in key or 'cycle' in value):
        bicycle_tags.append((key, value))

print(f'there are {len(bicycle_tags)} tags bicycle related tags')

tmp = {}
for k, v in stats.items():
    if(k in bicycle_tags):
        tmp[k] = v

bicycle_stats = Counter(tmp)
display(bicycle_stats.most_common(len(bicycle_stats)))

sorted(bicycle_stats.most_common(len(bicycle_stats)))
# %%
#f = open('./bicycle_attributes.txt', 'w')
#for entry in sorted(bicycle_stats.most_common(len(bicycle_stats))):
#    ((k, v), c) = entry
#    f.write(f'{k}, {v}\n')
#f.close()

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
graph = ox.graph_from_place(query=place_name, retain_all=True, custom_filter=custom_filter)

# %% 
# some statistics of the graph
edges = ox.graph_to_gdfs(graph, nodes=False)
overall_length = sum(edges["length"])
display(edges.explore())
print(f'number of edges: {len(edges)}')
print(f'length of network: {overall_length} meters')
# %% 
# explore connected components in graph
undirected_graph = graph.to_undirected()

print(f'number of connected components: {nx.number_connected_components(undirected_graph)}')

# %% 
# find all connected components in graph
list_of_components = []

for c in nx.connected_components(undirected_graph):
    component_graph = undirected_graph.subgraph(c).copy()
    list_of_components.append({'graph': component_graph, 'length': get_path_length(component_graph)})

sorted_components_by_length = sorted(list_of_components, key=lambda d: d['length'], reverse=True)

# %% 
# plot all connected components on one map
cmap = matplotlib.cm.get_cmap('tab10')
map = folium.Map(location=[49.451900, 11.076608], zoom_start=11, crs='EPSG3857')

for idx, c in enumerate(sorted_components_by_length):
    color = matplotlib.colors.to_hex(cmap(idx%10))
    plot_graph(c['graph'], map=map, color=color)

map

# %% 
# top 10 of connected components by length
print('top 10 of connected components by length')
for sub in sorted_components_by_length[:10]:
    edges = ox.graph_to_gdfs(sub['graph'], nodes=False)
    display(edges.explore())
    print(f'number of edges: {len(edges)}')
    print(f'length of component: {sub["length"]} meters')
    print(f'{(sum(edges["length"])/overall_length)*100}% of whole network')

# %% 
# statistics of connected components
lengths = []

for c in list_of_components:
    lengths.append(c['length'])

lengths = sorted(lengths, reverse=True)
plt.boxplot(lengths)
plt.title('length of components')
plt.show()

plt.boxplot(lengths[10:])
plt.title('length of components without top 10')
plt.show()

print(f'average length of component: {sum(lengths)/len(lengths)} meters')
print(f'median length of component: {lengths[int(len(lengths)/2)]} meters')

# %%
