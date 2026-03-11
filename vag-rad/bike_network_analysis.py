# %% 
# imports
from collections import Counter

import folium
import geopandas as gpd
import matplotlib
import matplotlib.colors
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import osmium
import osmnx as ox
import osmnx.settings
import shapely
from IPython.display import display
from matplotlib.cm import get_cmap
from osmium import FileProcessor
from osmium.filter import EmptyTagFilter, EntityFilter
from osmium.osm import WAY
from tqdm import tqdm

from utils.overpass_utils import fetch_city_polygon, query_overpass
from utils.polygon_filter import PolygonFilter
from utils.population_provider import (
    GHSLPopulationProvider,
    NurenbergDistrictPopulationProvider,
)
from utils.service_area_provider import ServiceAreaProvider
from utils.utils import get_path_length

# %% 
# evaluation of osm features in Nürnberg
print("Total number of objects in Mittelfranken:", sum(1 for o in osmium.FileProcessor('mittelfranken-latest.osm.pbf')))

print("Of which are ways with tags:", sum(1 for o in FileProcessor('mittelfranken-latest.osm.pbf').with_filter(EmptyTagFilter()).with_filter(EntityFilter(WAY))))

place = ox.geocode_to_gdf('Nürnberg')
print("Of which are ways within Nürnberg:",
      sum(1 for o in FileProcessor('mittelfranken-latest.osm.pbf').with_locations().with_filter(EmptyTagFilter()).with_filter(EntityFilter(WAY)).with_filter(PolygonFilter(place.geometry[0]))))

# %%
# get all osm tags of ways in Nürnberg
place = ox.geocode_to_gdf('Nürnberg')
stats = Counter()

edges_in_nbg = []

for w in FileProcessor('mittelfranken-latest.osm.pbf').with_locations().with_filter(EmptyTagFilter()).with_filter(EntityFilter(WAY)).with_filter(PolygonFilter(place.geometry[0])):
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
# fetch osmids of bicycle infrastructure in Nürnberg
place_name = 'Nürnberg'
query_polygon = fetch_city_polygon(place_name)

xmin, ymin, xmax, ymax = query_polygon.bounds
bbox = (ymin, xmin, ymax, xmax)

protected_bike_infra = f"""
(
    way["bicycle"="designated"]{bbox};
    way["highway"="cycleway"]{bbox};
    way["cycleway"="track"]{bbox};
    way["cycleway:right"="track"]{bbox};
    way["cycleway:left"="track"]{bbox};
    way["cycleway:both"="track"]{bbox};
);
-
way["bicycle_road"~"yes"]{bbox};
"""

all_bike_infra = f"""
way["cycleway"="lane"]{bbox};
way["cycleway:right"="lane"]{bbox};
way["cycleway:left"="lane"]{bbox};
way["cycleway:both"="lane"]{bbox};
way["cycleway"="opposite"]{bbox};
way["bicycle"="designated"]{bbox};
way["highway"="cycleway"]{bbox};
way["cycleway"="track"]{bbox};
way["cycleway:right"="track"]{bbox};
way["cycleway:left"="track"]{bbox};
way["cycleway:both"="track"]{bbox};
way["bicycle_road"="yes"]{bbox};
"""

protected_bike_infra_osmids = query_overpass(protected_bike_infra).get_way_ids()

all_bike_infra_osmids = query_overpass(all_bike_infra).get_way_ids()

# %%
# construct graphs of protected and all bicycle infrastructure
bicycle_graph =  ox.load_graphml('bicycle_graph.graphml', node_dtypes={'osmid': int}, edge_dtypes={'weight': float, 'penalty': float, 'slope_percentage': float, 'length': float})

# construct bicycle infrastructure graph
bicycle_infrastructure_graph = bicycle_graph.copy()
edges_to_remove = []
for u, v, key, data in bicycle_infrastructure_graph.edges(data=True, keys=True):
    osmid = data.get('osmid', None)
    if osmid is None or osmid not in all_bike_infra_osmids:
        edges_to_remove.append((u, v, key))
bicycle_infrastructure_graph.remove_edges_from(edges_to_remove)
bicycle_infrastructure_graph.remove_nodes_from(list(nx.isolates(bicycle_infrastructure_graph)))

ox.graph_to_gdfs(bicycle_infrastructure_graph, nodes=True, edges=False).drop(columns=['osmid']).to_file('graph.gpkg', layer='bicycle_infrastructure_nodes', driver='GPKG')
ox.graph_to_gdfs(bicycle_infrastructure_graph, nodes=False, edges=True).to_file('graph.gpkg', layer='bicycle_infrastructure', driver='GPKG')

# construct protected bicycle infrastructure graph
protected_bicycle_infrastructure_graph = bicycle_graph.copy()
edges_to_remove = []
for u, v, key, data in protected_bicycle_infrastructure_graph.edges(data=True, keys=True):
    osmid = data.get('osmid', None)
    if osmid is None or osmid not in protected_bike_infra_osmids:
        edges_to_remove.append((u, v, key))
protected_bicycle_infrastructure_graph.remove_edges_from(edges_to_remove)
protected_bicycle_infrastructure_graph.remove_nodes_from(list(nx.isolates(protected_bicycle_infrastructure_graph)))

ox.graph_to_gdfs(protected_bicycle_infrastructure_graph, nodes=True, edges=False).drop(columns=['osmid']).to_file('graph.gpkg', layer='protected_bicycle_infrastructure_nodes', driver='GPKG')
ox.graph_to_gdfs(protected_bicycle_infrastructure_graph, nodes=False, edges=True).to_file('graph.gpkg', layer='protected_bicycle_infrastructure', driver='GPKG')

# %%
place_name = 'Nürnberg'
# use specific overpass settings
osmnx.settings.overpass_settings = '[out:json][timeout:{timeout}][date:"2025-10-21T20:21:22Z"]{maxsize}'

filters = {
    'cycleway_lane': '["cycleway"="lane"]',
    'cycleway:right_lane': '["cycleway:right"="lane"]',
    'cycleway:left_lane': '["cycleway:left"="lane"]',
    'cycleway:both_lane': '["cycleway:both"="lane"]',
    'cycleway_track': '["cycleway"="track"]',
    'cycleway:right_track': '["cycleway:right"="track"]',
    'cycleway:left_track': '["cycleway:left"="track"]',
    'cycleway:both_track': '["cycleway:both"="track"]',
    'bicycle_designated': '["bicycle"="designated"]',
    'highway_cycleway': '["highway"="cycleway"]',
    'bicycle_road': '["bicycle_road"="yes"]',
    'sidewalk_bicycle': [
        '["foot"="designated"]["bicycle"="yes"]',
        '["sidewalk:right:foot"="designated"]["sidewalk:right:bicycle"="yes"]',
        '["sidewalk:left:foot"="designated"]["sidewalk:left:bicycle"="yes"]',
        '["sidewalk:both:foot"="designated"]["sidewalk:both:bicycle"="yes"]'
    ]
}

for filter in tqdm(filters.items(), desc="Fetching OSM data"):
    filter_name = filter[0]
    filter_query = filter[1]

    graph = ox.graph_from_place(query=place_name, retain_all=True, custom_filter=filter_query, simplify=False)
    ox.graph_to_gdfs(graph, nodes=False, edges=True).to_file('osm_queries.gpkg', layer=filter_name, driver='GPKG')

# %% 
# some statistics of the graph
edges = ox.graph_to_gdfs(bicycle_infrastructure_graph, nodes=False)
overall_length = sum(edges["length"])
display(edges.explore())
print(f'number of edges: {len(edges)}')
print(f'length of network: {overall_length} meters')
# %% 
# explore connected components in graph
undirected_graph = bicycle_infrastructure_graph.to_undirected()

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
cmap = get_cmap('tab10')
map = folium.Map(location=[49.451900, 11.076608], zoom_start=11, crs='EPSG3857')

for idx, c in enumerate(sorted_components_by_length):
    color = matplotlib.colors.to_hex(cmap(idx%10))
    #plot_graph(c['graph'], map=map, color=color)
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
# analyse the coverage of the bike network
service_area_provider = ServiceAreaProvider(
    coverage_distance=300,
    buffer_value=50,
    routing_graph=bicycle_graph)

# %%
def remove_edges_below_length_threshold(graph: nx.MultiDiGraph, length_threshold: float) -> nx.MultiGraph:
    g = graph.copy()
    g = osmnx.convert.to_undirected(g)
    components = nx.connected_components(g)
    edges_to_remove = []
    for c in components:
        component_graph = g.subgraph(c).copy()
        length = get_path_length(component_graph)
        if length < length_threshold:
            edges_to_remove.extend(list(component_graph.edges))
    g.remove_edges_from(edges_to_remove)
    g.remove_nodes_from(list(nx.isolates(g)))
    return g

# compute the coverage of the bicycle infrastructure
meaningful_bicycle_infra_graph = remove_edges_below_length_threshold(bicycle_infrastructure_graph, length_threshold=200)

bike_infra_coverage, _ = service_area_provider.get_service_area(meaningful_bicycle_infra_graph)


# compute the coverage of protected bicycle infrastructure
meaningful_bicycle_infra_graph = remove_edges_below_length_threshold(protected_bicycle_infrastructure_graph, length_threshold=200)

protected_bike_infra_coverage, _ = service_area_provider.get_service_area(meaningful_bicycle_infra_graph)

# %%
nbg_place = ox.geocode_to_gdf('Nürnberg')
nbg_polygon = nbg_place['geometry'].values[0]

gpd.GeoDataFrame(geometry=[nbg_polygon], crs=4326, columns=['geometry']).to_file('bike_infra_coverage.gpkg', layer='nbg_polygon', driver='GPKG')

population_provider = NurenbergDistrictPopulationProvider()

nbg_total_population = population_provider.get_population_in_polygon(nbg_polygon)

population_near_bike_infra = population_provider.get_population_in_polygon(bike_infra_coverage)

population_near_protected_bike_infra = population_provider.get_population_in_polygon(protected_bike_infra_coverage)

print(f'Total population in Nürnberg: {nbg_total_population:.0f}')
print('---')
print(f'Population near protected bike infrastructure: {population_near_protected_bike_infra:.0f} ({population_near_protected_bike_infra / nbg_total_population * 100:.2f}%)')
print(f'The area 300 meters away from protected bike infrastructure covers {shapely.intersection(nbg_polygon, protected_bike_infra_coverage).area / nbg_polygon.area * 100:.2f}% of Nürnberg')
print('---')
print(f'Population near any bike infrastructure: {population_near_bike_infra:.0f} ({population_near_bike_infra / nbg_total_population * 100:.2f}%)')
print(f'The area 300 meters away from any bike infrastructure covers {shapely.intersection(nbg_polygon, bike_infra_coverage).area / nbg_polygon.area * 100:.2f}% of Nürnberg')

# %%
# save for visualization
gpd.GeoDataFrame(geometry=[shapely.intersection(nbg_polygon, bike_infra_coverage)], crs=4326, columns=['geometry']).to_file('bike_infra_coverage.gpkg', layer='all_bike_infra_coverage_nbg', driver='GPKG')

gpd.GeoDataFrame(geometry=[shapely.intersection(nbg_polygon, protected_bike_infra_coverage)], crs=4326, columns=['geometry']).to_file('bike_infra_coverage.gpkg', layer='protected_bike_infra_coverage_nbg', driver='GPKG')

edges = ox.graph_to_gdfs(protected_bicycle_infrastructure_graph, nodes=False, edges=True)
all_lines = shapely.MultiLineString(edges['geometry'].values)
all_lines = shapely.intersection(nbg_polygon, all_lines)
gpd.GeoDataFrame(geometry=[all_lines], crs=4326, columns=['geometry']).to_file('bike_infra_coverage.gpkg', layer='protected_bike_infra_nbg', driver='GPKG')

edges = ox.graph_to_gdfs(bicycle_infrastructure_graph, nodes=False, edges=True)
all_lines = shapely.MultiLineString(edges['geometry'].values)
all_lines = shapely.intersection(nbg_polygon, all_lines)
gpd.GeoDataFrame(geometry=[all_lines], crs=4326, columns=['geometry']).to_file('bike_infra_coverage.gpkg', layer='all_bike_infra_nbg', driver='GPKG')

# %%
# plot the distribution of the length of protected bike infrastructure
components = nx.connected_components(osmnx.convert.to_undirected(protected_bicycle_infrastructure_graph))

length_of_components = [get_path_length(protected_bicycle_infrastructure_graph.subgraph(c)) for c in components]

boxplt = plt.boxplot(length_of_components)
plt.title('length of protected bike infrastructure components')
plt.ylabel('length in meters')
plt.xticks([1], ['protected bike infrastructure'])
# show the plot to a y value of 2000
plt.ylim(0, 2000)
plt.show()

print(boxplt['boxes'][0].get_ydata())

print(f'average length of component: {np.mean(length_of_components)} meters')
print(f'median length of component: {np.median(length_of_components)} meters')
print(f'shortest component: {min(length_of_components)} meters')
print(f'longest component: {max(length_of_components)} meters')
percentailes = [5, 10, 20, 30]
for p in percentailes:
    print(f'{p}th percentile: {np.percentile(length_of_components, p)} meters')

# %%
