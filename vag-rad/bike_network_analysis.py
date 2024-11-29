#%% imports
import matplotlib.colors
import osmnx as ox
import networkx as nx
import folium
import matplotlib
import matplotlib.pyplot as plt

# %% helper function
# calculate length of edges of a graph
def get_path_length(graph):
    if len(graph.edges) > 0:
        edges = ox.graph_to_gdfs(graph, nodes=False, edges=True)
        return sum(edges['length'])
    else:
        return 0

# plot edges of a graph on to a folium map
def plot_graph(graph, map=folium.Map(location=[49.451900, 11.076608], zoom_start=12, crs='EPSG3857'), color='blue'):
    if(len(graph.edges) > 0):
        df = ox.graph_to_gdfs(graph, nodes=False)
        for t in df['geometry'].values:
            coordinates = []
            for c in t.coords[:]:
                coordinates.append((c[1], c[0]))
            folium.PolyLine(coordinates, color=color).add_to(map)
    return map

# %% fetch graph of bicycle infrastructure
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
    '["highway"="path"]["bicycle"="designated"]',
    '["highway"="cycleway"]',
    '["cycleway"="track"]'
]
bike_road_filter = [
    '["bicycle_road"="yes"]'
]
custom_filter = bike_path_filter + bike_lane_filter + bike_road_filter
graph = ox.graph_from_place(query=place_name, retain_all=True, custom_filter=custom_filter)

# %% some statistics of the whole graph
edges = ox.graph_to_gdfs(graph, nodes=False)
overall_length = sum(edges["length"])
display(edges.explore())
print(f'number of edges: {len(edges)}')
print(f'length of network: {overall_length} meters')
# %% explore connected components in graph
undirected_graph = graph.to_undirected()

print(f'number of connected components: {nx.number_connected_components(undirected_graph)}')

# %% top connected components by number of edges
S = [undirected_graph.subgraph(c).copy() for c in sorted(nx.connected_components(undirected_graph), key=len, reverse=True)]

print('top 10 of connected components by number of edges')
for sub in S[:10]:
    edges = ox.graph_to_gdfs(sub, nodes=False, edges=True)

    map = edges.explore()
    display(map)
    print(f'number of edges: {len(edges)}')
    print(f'length of component: {sum(edges["length"])} meters')

# %% top connected components by length
list_of_components = []

for c in nx.connected_components(undirected_graph):
    component_graph = undirected_graph.subgraph(c).copy()
    list_of_components.append({'graph': component_graph, 'length': get_path_length(component_graph)})

sorted_components_by_length = sorted(list_of_components, key=lambda d: d['length'], reverse=True)

# %% plot components on one map
cmap = matplotlib.cm.get_cmap('tab10')
map = folium.Map(location=[49.451900, 11.076608], zoom_start=11, crs='EPSG3857')

for idx, c in enumerate(sorted_components_by_length):
    color = matplotlib.colors.to_hex(cmap(idx%10))
    plot_graph(c['graph'], map=map, color=color)

map

# %% top 10 of connected components by length
print('top 10 of connected components by length')
for sub in sorted_components_by_length[:10]:
    edges = ox.graph_to_gdfs(sub['graph'], nodes=False)
    display(edges.explore())
    print(f'number of edges: {len(edges)}')
    print(f'length of component: {sub["length"]} meters')
    print(f'{(sum(edges["length"])/overall_length)*100}% of whole network')

# %% 
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
