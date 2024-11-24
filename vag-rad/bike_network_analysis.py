#%% imports
import osmnx as ox
import networkx as nx

# %% helper function
# calculate length of edges of a graph
def get_path_length(graph):
    if len(graph.edges) > 0:
        edges = ox.graph_to_gdfs(graph, nodes=False, edges=True)
        return sum(edges['length'])
    else:
        return 0

# %%
place_name = 'Nürnberg'
graph = ox.graph_from_place(place_name)

fig, ax = ox.plot_graph(graph)

# %% fetch graph of bicycle infrastructure
place_name = 'Nürnberg'
network_type = 'bike'
custome_filter = '["highway"="path"]["bicycle"=designated]'
graph = ox.graph_from_place(query=place_name, retain_all=True, custom_filter=custome_filter)

# %% some statistics of the whole graph
edges = ox.graph_to_gdfs(graph, nodes=False)
display(edges.explore())
print(f'number of edges: {len(edges)}')
print(f'length of component: {sum(edges["length"])} meters')
# %% explore connected components in graph
undirected_graph = graph.to_undirected()

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

print('top 10 of connected components by length')
for sub in sorted_components_by_length[:10]:
    map = ox.graph_to_gdfs(sub['graph'], nodes=False).explore()
    display(map)
    print(f'number of edges: {len(sub["graph"].edges)}')
    print(f'length of component: {sub["length"]} meters')

# %%