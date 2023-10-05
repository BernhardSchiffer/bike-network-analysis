#%%
import osmnx as ox

#%%
%matplotlib inline
G = ox.graph_from_place('Nuremberg, Bavaria, Germany', network_type='bike')
fig, ax = ox.plot_graph(ox.project_graph(G))

#%%
ox.folium.plot_graph_folium(G)
# %%
for n in list(G.nodes)[:10]:
    print(n)

#%%
list(G.edges)[:10]
# %%

ox.