# %% 
# imports
import osmnx as ox
import networkx as nx
import pandas as pd
import numpy as np
import os
import folium
import osmium
import math
from utils.polygon_filter import PolygonFilter
from utils.utils import *
import pickle
import leafmap.foliumap as leafmap
from pyproj import Transformer
from shapely.geometry import LineString
from tqdm import tqdm
from kmodes.kmodes import KModes
from kmodes.kprototypes import KPrototypes
import matplotlib.pyplot as plt

# %%
# load osm edge attributes from file
edge_lookup_filename = 'osm_edges_with_attributes.pickle'

if os.path.isfile(edge_lookup_filename):
    with open(edge_lookup_filename, 'rb') as f:
        edges_osm_data_lookup = pickle.load(f)
else:
    # create lookup table for all edges in nuernberg with all their osm features
    place = ox.geocode_to_gdf('Nürnberg')

    edges_in_nbg = []

    for w in osmium.FileProcessor('mittelfranken-latest.osm.pbf').with_locations().with_filter(osmium.filter.EmptyTagFilter()).with_filter(osmium.filter.EntityFilter(osmium.osm.WAY)).with_filter(PolygonFilter(place.geometry[0])):
        obj = {}
        obj['osmid'] = w.id
        tags = {}
        for k, v in w.tags:
            tags[k] = v
        obj['tags'] = tags
        edges_in_nbg.append(obj)

    edges_osm_data_lookup = pd.DataFrame(edges_in_nbg).set_index('osmid')

    # write osm edge attributes to file
    file = open(edge_lookup_filename, 'wb')
    pickle.dump(edges_osm_data_lookup, file)
    file.close()

# %%
graph = ox.io.load_graphml('weighted_bicycle_graph.graphml', node_dtypes={'osmid': str}, edge_dtypes={'weight': float})

# some statistics of the graph
edges = ox.graph_to_gdfs(graph, nodes=False)
# %%
# get all distinct osmids of the edges in the graph
osmids = edges['osmid'].unique()
print(f'Number of distinct osmids in the graph: {len(osmids)}')

osm_edges = pd.DataFrame()
dfs = []
for osmid, data in tqdm(edges_osm_data_lookup.iterrows(), desc='Processing OSM edges', unit='osmids', total=edges_osm_data_lookup.shape[0]):
    if osmid not in osmids:
        continue
    df_dictionary = pd.DataFrame([data['tags']], index=[osmid])
    dfs.append(df_dictionary)
print(f'merge {len(dfs)} dataframes')
osm_edges = pd.concat(dfs, copy=False)
# %%
osm_edges
# %%
unique_attributes = pd.DataFrame.from_records([(col, osm_edges[col].nunique()) for col in osm_edges.columns],columns=['Column_Name', 'Num_Unique']).sort_values(by=['Num_Unique'])
with pd.option_context('display.max_rows', None, 'display.max_columns', None):  # more options can be specified also
    print(unique_attributes)
# %%
osm_edges.value_counts()
# %%
pd.DataFrame.from_records([(col, osm_edges[col].value_counts()) for col in osm_edges.columns])
# %%
[osm_edges[col].value_counts() for col in osm_edges.columns]

# %%
# trying different number of clusters
k_modes_stats = {
    'Huang': {},
    'Cao': {},
    'random': {},
}
# %%
for init_method, k_modes_stat in k_modes_stats.items():
    print(f'Init method: {init_method}')
    range_of_clusters = range(2, 41)
    range_of_clusters = [i for i in range_of_clusters if i not in k_modes_stats[init_method]]
    for num_of_clusters in tqdm(range_of_clusters, desc='Number of clusters'):
        if(num_of_clusters in k_modes_stats):
            continue
        km = KModes(n_clusters=num_of_clusters, init=init_method, n_jobs=os.cpu_count())
        km.fit(osm_edges.fillna(''))
        k_modes_stats[init_method][num_of_clusters] = km.cost_
        print(f'Number of clusters: {num_of_clusters}, cost: {km.cost_}')
# %%
for init_method, k_modes_stat in k_modes_stats.items():
    k_modes_stat = dict(sorted(k_modes_stat.items()))
    plt.plot(k_modes_stat.keys(), k_modes_stat.values(), label=init_method)
plt.legend()
plt.ylabel('Cost')
plt.xlabel('Number of clusters')
plt.title('Cost of clustering for different number of clusters - k-modes')
plt.grid()
plt.show()
        
# %%
k_modes_stats = dict(sorted(k_modes_stats.items()))
plt.plot(k_modes_stats.keys(), k_modes_stats.values())
plt.ylabel('Cost')
plt.xlabel('Number of clusters')
plt.title('Cost of clustering for different number of clusters - k-modes')
plt.grid()
plt.show()

# %%
k_modes_stats['Huang'] = k_modes_stats
# %%
k_prototypes_stats = {}
# %%
range_of_clusters = range(2, 4)
range_of_clusters = [i for i in range_of_clusters if i not in k_prototypes_stats]
for num_of_clusters in tqdm(range_of_clusters, desc='Number of clusters'):
    if(num_of_clusters in k_prototypes_stats):
        continue
    kp = KPrototypes(n_clusters=num_of_clusters, init='Cao', n_jobs=4)
    kp.fit(osm_edges.fillna(''), categorical=[i for i in range(0, len(osm_edges.columns))])
    k_prototypes_stats[num_of_clusters] = kp.cost_
    print(f'Number of clusters: {num_of_clusters}, cost: {kp.cost_}')
# %%
k_prototypes_stats = dict(sorted(k_prototypes_stats.items()))
plt.plot(k_prototypes_stats.keys(), k_prototypes_stats.values())
plt.ylabel('Cost')
plt.xlabel('Number of clusters')
plt.title('Cost of clustering for different number of clusters - k-prototypes')
plt.grid()
plt.show()

# %%
