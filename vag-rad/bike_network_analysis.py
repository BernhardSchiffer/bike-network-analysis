# %% 
# imports
import osmium.filter
import osmium.osm
import osmnx as ox
import networkx as nx
import folium
import matplotlib
import matplotlib.pyplot as plt
import osmium
from collections import Counter
import geopandas as gpd
from shapely.geometry import Polygon
from tqdm import tqdm
import rasterio
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
nbg_graph = ox.graph_from_place(query=place_name, retain_all=True, network_type='all_public')

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
# analyse the coverage of the bike network

# get all edges that are on the shortest path from a node to all other nodes in a certain radius
def get_shortest_path_edges(graph: nx.MultiDiGraph, node: int, radius: float):
    subgraph = nx.ego_graph(graph, node, radius=radius, distance='length', undirected=True)
    if subgraph.edges is None or len(subgraph.edges) == 0:
        return None
    else:
        return ox.graph_to_gdfs(subgraph, nodes=False, edges=True)

def get_area_near_node(graph: nx.MultiDiGraph, node: int, radius: float) -> Polygon:
    edges = get_shortest_path_edges(graph, node, radius)
    if edges is None:
        return None
    edges = edges.to_crs(3043).buffer(50).to_crs(4326)
    return Polygon(edges.unary_union.exterior.coords)

polygons = []
for node in tqdm(list(graph.nodes)):
    if node not in nbg_graph.nodes:
        continue
    area = get_area_near_node(nbg_graph, node, radius=300)
    if area is not None:
        polygons.append(area)

# %%
overall_polygon = gpd.GeoSeries(polygons).unary_union
gpd.GeoDataFrame(geometry=[gpd.GeoSeries(polygons).unary_union], crs=4326).explore()

#%%
bike_way_polygon = ox.graph_to_gdfs(graph, nodes=False, edges=True).to_crs(3043).buffer(30).to_crs(4326).unary_union
gpd.GeoDataFrame(geometry=[bike_way_polygon], crs=4326).explore()
# %%
protected_bike_infra_coverage = gpd.GeoDataFrame(geometry=[gpd.GeoSeries([gpd.GeoSeries(polygons).unary_union, bike_way_polygon]).unary_union], crs=4326)
# %%
protected_bike_infra_coverage['geometry'].values[0]
# %%
protected_bike_infra_coverage.explore()
# %%
nbg_polygon = ox.geocode_to_gdf('Nürnberg').to_crs(3043)['geometry']
nbg_polygon

# %%
protected_bike_infra_coverage.to_crs(3043).area / nbg_polygon.area * 100
# %%
population_src: rasterio.DatasetReader = rasterio.open('GHS_POP_E2025_GLOBE_R2023A_4326_3ss_V1_0_R4_C20.tif')
# read all the data from the first band
population_data = population_src.read()[0]

# %%
nbg_place = ox.geocode_to_gdf('Nürnberg')
nbg_polygon = nbg_place['geometry'].values[0]

row_start ,col_start = population_src.index(nbg_place['bbox_west'], nbg_place['bbox_north'])
row_end ,col_end = population_src.index(nbg_place['bbox_east'], nbg_place['bbox_south'])

total_population = 0
population_near_bike_infra = 0

for row in range(row_start, row_end + 1):
    for col in range(col_start, col_end + 1):
        polygon = Polygon([
            population_src.transform * (col, row),
            population_src.transform * (col, row + 1),
            population_src.transform * (col + 1, row + 1),
            population_src.transform * (col + 1, row)
        ])
        if nbg_polygon.contains(polygon):
            total_population += population_data[row, col]

            intersection = polygon.intersection(protected_bike_infra_coverage['geometry'].values[0])
            if not intersection.is_empty:
                population_near_bike_infra += intersection.area / polygon.area * population_data[row, col]
    
print(f'Total population in Nürnberg: {total_population}')
print(f'Population near protected bike infrastructure: {population_near_bike_infra}')
print(f'Population near protected bike infrastructure: {population_near_bike_infra / total_population * 100:.2f}%')
# %%
gpd.GeoDataFrame(geometry=[intersection], crs=4326).explore()

# %%
bike_way_polygon

# %%
# save bike network polygon for later use
gpd.GeoDataFrame(geometry=[protected_bike_infra_coverage], crs=4326).to_file('protected_bike_infra_coverage.gpkg', layer='protected_bike_infra_coverage', driver='GPKG')

# %%
# read bike network polygon from file
protected_bike_infra_coverage = gpd.read_file('protected_bike_infra_coverage.gpkg', layer='protected_bike_infra_coverage').to_crs(4326)['geometry'].values[0]
