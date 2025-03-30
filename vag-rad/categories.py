# %% 
# imports
import osmnx as ox
import pandas as pd
import numpy as np
import os
import folium
import osmium
from utils.polygon_filter import PolygonFilter
from utils.utils import *
import pickle
import leafmap.foliumap as leafmap
from tqdm import tqdm
from kmodes.kmodes import KModes
from kmodes.kprototypes import KPrototypes
import matplotlib.pyplot as plt
from tqdm import tqdm
from collections import Counter

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
graph = ox.io.load_graphml('expanded_bicycle_graph.graphml', node_dtypes={'osmid': str}, edge_dtypes={'weight': float})

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
unique_attributes = pd.DataFrame.from_records(
    [(
        col, 
        len(osm_edges[col].dropna(inplace=False)), 
        len(osm_edges[col].dropna(inplace=False))/len(osm_edges)*100, 
        osm_edges[col].nunique()
    ) for col in osm_edges.columns],columns=['Column_Name', 'Num_Values', 'Percentage', 'Num_Unique']).sort_values(by=['Num_Values'], ascending=False)
with pd.option_context('display.max_rows', None, 'display.max_columns', None):
    print(unique_attributes)
# %%
osm_edges['source'].value_counts()

# %%
for col in osm_edges.columns:
    print(f'Column: {col}')
    print(f'Number of values: {len(osm_edges[col].dropna(inplace=False))}')
    print(f'Percentage of values: {len(osm_edges[col].dropna(inplace=False))/len(osm_edges)*100:.2f}%')
    print(f'Number of unique values: {osm_edges[col].nunique()}')
    print(osm_edges[col].value_counts())
    print('------------------------------------')
# %%
columns_to_keep = ['foot', 'highway', 'lanes', 'maxspeed', 'zone:maxspeed', 'oneway', 'shoulder', 'sidewalk', 'junction', 'lit', 'width', 'bicycle', 'sidewalk:left', 'sidewalk:right', 'sidewalk:both', 'sidewalk:left:bicycle', 'cycleway', 'cycleway:lane', 'cycleway:left', 'cycleway:left:lane', 'cycleway:right', 'cycleway:right:lane', 'cycleway:both', 'cycleway:both:lane', 'cycleway:both:segregated', 'bicycle_road', 'service', 'segregated', 'bridge', 'parking:left', 'parking:right', 'parking:both', 'oneway:bicycle', 'ramp', 'footway', 'embedded_rails', 'area', 'railway']

osm_edges_tmp = osm_edges[columns_to_keep]

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
        km.fit(osm_edges_tmp.fillna(''))
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
km_classifier = KModes(n_clusters=20, n_init=100, init='Huang', n_jobs=os.cpu_count()/2, verbose=1)
km_classifier.fit(osm_edges_tmp.fillna(''))

# save the model
pickle.dump(km_classifier, open('k-modes_classifier/km_classifier_20.pkl', 'wb'))

# %%
km_classifier = pickle.load(open('k-modes_classifier/km_classifier_20.pkl', 'rb'))
osm_edges_tmp['cluster_20'] = km_classifier.predict(osm_edges_tmp.fillna(''))

# %%
centroids = pd.DataFrame(km_classifier.cluster_centroids_, columns=osm_edges_tmp.columns[:-1])
with pd.option_context('display.max_rows', None, 'display.max_columns', None):
    display(centroids.replace('', np.nan).dropna(axis=1, how='all').fillna(''))

# %%
for cluster in range(20):
    print(f'Cluster {cluster}')
    with pd.option_context('display.max_rows', 100, 'display.max_columns', 100):
        display(osm_edges_tmp[osm_edges_tmp['cluster_20'] == cluster].replace('', np.nan).dropna(axis=1, how='all').fillna(''))
# %%

for cluster_num in range(20):
    cluster = osm_edges_tmp[osm_edges_tmp['cluster_20'] == cluster_num].replace('', np.nan).dropna(axis=1, how='all').fillna('')
    print(f'Cluster {cluster_num}: {len(cluster)}')
    for col in cluster.columns:
        if(cluster[col].value_counts().idxmax() != ''):
            print(f'{col}: {cluster[col].value_counts().idxmax()} ({cluster[col].value_counts().values.max()})')
    print()
# %%
def plot_clusters_on_map(graph, osm_edges, color_palette):
    edges = ox.graph_to_gdfs(graph, nodes=False)

    for cluster_num in osm_edges['cluster_20'].unique():
        graph_map = leafmap.Map(location=[49.451900, 11.076608], zoom_start=12, crs='EPSG3857')
        cluster_edges = osm_edges[osm_edges['cluster_20'] == cluster_num]

        # get all edges from edges where osmid is in cluster_edges
        tmp = edges[edges['osmid'].isin(cluster_edges.index)]
        for _, edge in tmp.iterrows():
            edge_nodes = edge['geometry'].coords
            folium.PolyLine([(edge_nodes[0][1], edge_nodes[0][0]), (edge_nodes[1][1], edge_nodes[1][0])], color='red').add_to(graph_map)
        cluster = osm_edges[osm_edges['cluster_20'] == cluster_num].replace('', np.nan).dropna(axis=1, how='all').fillna('')
        print(f'Cluster {cluster_num}: {len(cluster)}')
        for col in cluster.columns:
            if(cluster[col].value_counts().idxmax() != ''):
                print(f'{col}: {cluster[col].value_counts().idxmax()} ({cluster[col].value_counts().values.max()})')
        display(graph_map)

plot_clusters_on_map(graph, osm_edges_tmp, ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'lightred', 'beige', 'darkblue', 'darkgreen', 'cadetblue', 'darkpurple', 'white', 'pink', 'lightblue'])

# %%
# remove last collumn
osm_edges_tmp = osm_edges_tmp.drop(columns=['cluster_20'])
# %%
# get gaps from file
with open('gaps.pickle', 'rb') as f:
    gaps = pickle.load(f)

# %%
gap_stats = {}
gap_counter = Counter(gaps)
max_count = gap_counter.most_common(1)[0][1]

for gap, count in tqdm(gap_counter.items(), desc='Processing gaps', unit='gaps', total=len(gap_counter)):
    gap_stats[gap] = {
        'count': count,
        'benefit': edges.loc[gap]['length'] * count,
        'count_percentage': count / max_count * 100,
    }
gap_stats = pd.DataFrame.from_dict(gap_stats, orient='index').sort_values(by=['count_percentage'], ascending=False)

gap_stats.head(100)
    
# %%
# get osmids of the gaps
gap_counter = Counter(gaps)
max_count = gap_counter.most_common(1)[0][1]
gap_osmids = []
for gap, count in gap_counter.items():
    try:
        if count / max_count * 100 < 10.0:
            continue
        gap_osmids.append(graph.edges[gap]['osmid'])
    except KeyError:
        continue
gap_osmids = set(gap_osmids)
print(f'Number of distinct osmids in the gaps: {len(gap_osmids)}')
# %%

osm_gap_attributes = pd.DataFrame()
dfs = []
for osmid, data in tqdm(edges_osm_data_lookup.iterrows(), desc='Processing OSM edges', unit='osmids', total=edges_osm_data_lookup.shape[0]):
    if osmid not in gap_osmids:
        continue
    df_dictionary = pd.DataFrame([data['tags']], index=[osmid])
    dfs.append(df_dictionary)
print(f'merge {len(dfs)} dataframes')
osm_gap_attributes = pd.concat(dfs, copy=False)
# %%
osm_gap_attributes

# %%
osm_gap_attributes = osm_gap_attributes[[col for col in osm_gap_attributes.columns if col in columns_to_keep]]
# %%
k_modes_stats = {
    'Huang': {},
    'Cao': {},
    'random': {},
}

for init_method, k_modes_stat in k_modes_stats.items():
    print(f'Init method: {init_method}')
    range_of_clusters = range(2, 41)
    range_of_clusters = [i for i in range_of_clusters if i not in k_modes_stats[init_method]]
    for num_of_clusters in tqdm(range_of_clusters, desc='Number of clusters'):
        if(num_of_clusters in k_modes_stats):
            continue
        km = KModes(n_clusters=num_of_clusters, init=init_method, n_jobs=os.cpu_count())
        km.fit(osm_gap_attributes.fillna(''))
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
gap_km_classifier = KModes(n_clusters=20, n_init=100, init='Huang', n_jobs=os.cpu_count()/2, verbose=1)
gap_km_classifier.fit(osm_gap_attributes.fillna(''))
# %%
osm_gap_attributes['cluster_20'] = gap_km_classifier.predict(osm_gap_attributes.fillna(''))
# %%
plot_clusters_on_map(graph, osm_gap_attributes, ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'lightred', 'beige', 'darkblue', 'darkgreen', 'cadetblue', 'darkpurple', 'white', 'pink', 'lightblue'])
# %%
