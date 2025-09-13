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
from shapely import LineString
from shapely.geometry import Polygon
from tqdm import tqdm
import rasterio
from utils.graph_builder import GraphBuilder
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
# fetch graph of all streets available by bike
place_name = 'Nürnberg'
# use specific overpass settings
ox.settings.overpass_settings = '[out:json][timeout:{timeout}][date:"2025-08-16T20:21:30Z"]{maxsize}'

bikeable_ways = (
        '["highway"]["area"!~"yes"]["access"!~"private"]'
        '["highway"!~"abandoned|bus_guideway|construction|corridor|elevator|escalator|footway|'
        'motor|no|planned|platform|proposed|raceway|razed|steps"]'
        '["bicycle"!~"no"]["service"!~"private"]'
    )

bikeable_areas = '["area"~"yes"]["bicycle"~"yes"]'
bikeable_footpaths = '["highway"~"footway"]["bicycle"~"yes|designated|dismount"]'
bikeable_crossings = '["crossing"~"yes"]["bicycle"~"yes"]'

routing_graph = ox.graph_from_place(query=place_name, simplify=False, retain_all=True, custom_filter=[bikeable_ways, bikeable_areas, bikeable_footpaths])
print('number of edges in bikeable graph:', len(routing_graph.edges))

not_bikeable_ways = '["highway"~"pedestrian"]["bicycle"!~"yes"]'
service_ways = '["highway"~"service"]["access"="no"]'
bus_only_ways = '["highway"~"service"]["bus"="yes"]'
trams_only_ways = '["highway"~"service"]["railway"="yes"]'

not_bikeable_graph = ox.graph_from_place(query=place_name, simplify=False, retain_all=True, custom_filter=[not_bikeable_ways, service_ways, bus_only_ways, trams_only_ways])
print('number of edges in not bikeable graph:', len(not_bikeable_graph.edges))

for e in tqdm(not_bikeable_graph.edges, desc='remove not bikeable edges', total=len(not_bikeable_graph.edges), unit='edges'):
    # remove edges that are not bikeable
    if routing_graph.has_edge(*e):
        routing_graph.remove_edge(*e)

print('number of edges in bikeable graph after removing not bikeable edges:', len(routing_graph.edges))

routing_graph = ox.simplification.simplify_graph(routing_graph, remove_rings=False, edge_attrs_differ=['osmid'])

# add geometry to straight edges that do not have a geometry
for u, v, key, data in routing_graph.edges(data=True, keys=True):
    if data.get('geometry', None) is None:
        geometry = LineString([[routing_graph.nodes[u]['x'], routing_graph.nodes[u]['y']], [routing_graph.nodes[v]['x'], routing_graph.nodes[v]['y']]])
        routing_graph.edges[u, v, key]['geometry'] = geometry

print('number of edges in bikeable graph after simplifying:', len(routing_graph.edges))

# set node and edge attributes
graph_builder = GraphBuilder()

# add paths where the street is oneway but bikes are allowed in both directions
edge_count_before = len(routing_graph.edges)
routing_graph = graph_builder.add_paths_for_bikeable_oneways(routing_graph)
print(f'added {len(routing_graph.edges) - edge_count_before} paths that are bikeable in both directions')

routing_graph = graph_builder.set_node_attributes(routing_graph)
routing_graph = graph_builder.set_edge_slope(routing_graph)

routing_graph = graph_builder.set_edge_weights(routing_graph)

nodes_df, edges_df = ox.graph_to_gdfs(routing_graph, nodes=True, edges=True)
edges_df.to_file('graph.gpkg', layer='original_graph_edges', driver='GPKG')
nodes_df.drop(columns=['osmid']).to_file('graph.gpkg', layer='original_graph_nodes', driver='GPKG')

# fetch graph of bicycle infrastructure
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
bicycle_infrastructure = ox.graph_from_place(query=place_name, retain_all=True, custom_filter=custom_filter, simplify=False)
nbg_graph = ox.graph_from_place(query=place_name, retain_all=True, network_type='all_public')

bike_infra_osmids = set()
for u, v, key, data in bicycle_infrastructure.edges(data=True, keys=True):
    osmid = data.get('osmid', None)
    if osmid is not None:
        bike_infra_osmids.add(osmid)

bicycle_infrastructure_graph = routing_graph.copy()

edges_to_remove = []
for u, v, key, data in bicycle_infrastructure_graph.edges(data=True, keys=True):
    osmid = data.get('osmid', None)
    if osmid is None or osmid not in bike_infra_osmids:
        edges_to_remove.append((u, v, key))

bicycle_infrastructure_graph.remove_edges_from(edges_to_remove)

bicycle_infrastructure_graph.remove_nodes_from(list(nx.isolates(bicycle_infrastructure_graph)))

ox.graph_to_gdfs(bicycle_infrastructure_graph, nodes=True, edges=False).drop(columns=['osmid']).to_file('graph.gpkg', layer='bicycle_infrastructure_nodes', driver='GPKG')
ox.graph_to_gdfs(bicycle_infrastructure_graph, nodes=False, edges=True).to_file('graph.gpkg', layer='bicycle_infrastructure', driver='GPKG')

# %%
place_name = 'Nürnberg'
# use specific overpass settings
ox.settings.overpass_settings = '[out:json][timeout:{timeout}][date:"2025-08-16T20:21:30Z"]{maxsize}'

filters = {
    'cycleway_lane': '["cycleway"="lane"]',
    'cycleway:right_lane': '["cycleway:right"="lane"]',
    'cycleway:left_lane': '["cycleway:left"="lane"]',
    'cycleway:both_lane': '["cycleway:both"="lane"]',
    'cycleway_opposite': '["cycleway"="opposite"]',
    'cycleway_track': '["cycleway"="track"]',
    'cycleway:right_track': '["cycleway:right"="track"]',
    'cycleway:left_track': '["cycleway:left"="track"]',
    'cycleway:both_track': '["cycleway:both"="track"]',
    'bicycle_designated': '["bicycle"="designated"]',
    'highway_cycleway': '["highway"="cycleway"]',
    'bicycle_road': '["bicycle_road"="yes"]'
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
buffer_value = 50
distance = 300

try:
    reachable_edges = gpd.read_file('protected_bike_infra_coverage.gpkg', layer=f'reachable_streets_{distance}')
except Exception:
    reachable_edges = get_network_coverage(routing_graph, bicycle_infrastructure_graph, distance)

unique_lines = get_unique_lines(reachable_edges['geometry'].values)

gpd.GeoDataFrame(geometry=unique_lines, crs=4326).to_file('protected_bike_infra_coverage.gpkg', layer=f'reachable_streets_{distance}', driver='GPKG')

reachable_area = gpd.GeoDataFrame(geometry=unique_lines, crs=4326).to_crs(25832).buffer(buffer_value, cap_style='square').to_crs(4326).union_all()

bike_way_polygon = ox.graph_to_gdfs(bicycle_infrastructure_graph, nodes=False, edges=True).to_crs(25832).buffer(buffer_value, cap_style='square').to_crs(4326).union_all()

protected_bike_infra_coverage = shapely.union_all([reachable_area, bike_way_polygon])

# save bike network polygon for later use
gpd.GeoDataFrame(geometry=[protected_bike_infra_coverage], crs=4326).to_file('protected_bike_infra_coverage.gpkg', layer=f'protected_bike_infra_coverage_{buffer_value}', driver='GPKG')
# %%
nbg_place = ox.geocode_to_gdf('Nürnberg')
nbg_polygon = nbg_place['geometry'].values[0]

population_src: rasterio.DatasetReader = rasterio.open('population_data/GHS_POP_E2025_GLOBE_R2023A_4326_3ss_V1_0_R4_C20.tif')
# read all the data from the first band
population_data = population_src.read()[0]

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

            intersection = polygon.intersection(protected_bike_infra_coverage)
            if not intersection.is_empty:
                population_near_bike_infra += intersection.area / polygon.area * population_data[row, col]

print(f'Total population in Nürnberg: {total_population:.0f}')
print(f'Population near protected bike infrastructure: {population_near_bike_infra:.0f}')
print(f'Population near protected bike infrastructure: {population_near_bike_infra / total_population * 100:.2f}%')
print(f'The area 300 meters away from bike infrastructure covers {protected_bike_infra_coverage.area / nbg_polygon.area * 100:.2f}% of Nürnberg')

# %%
# read bike network polygon from file
protected_bike_infra_coverage = gpd.read_file('protected_bike_infra_coverage.gpkg', layer=f'protected_bike_infra_coverage_{30}').to_crs(4326)['geometry'].values[0]
protected_bike_infra_coverage
# %%
