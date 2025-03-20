# %% 
# imports
import osmnx as ox
import networkx as nx
import pandas as pd
import os
import folium
import osmium
import math
from utils.polygon_filter import PolygonFilter
from utils.utils import *
import pickle
import leafmap.foliumap as leafmap
from pyproj import Transformer
from tqdm import tqdm
import rasterio
from utils.graph import split_nodes, get_turn_penalty

osm_to_geotiff = Transformer.from_crs("EPSG:4326", "EPSG:25832")
geotiff_to_osm = Transformer.from_crs("EPSG:25832", "EPSG:4326")

dat = rasterio.open('./DEM/nuernberg.tif')
# read all the data from the first band
z = dat.read()[0]

def get_elevation(lon, lat):
    x, y = osm_to_geotiff.transform(lat, lon)
    idx = dat.index(x, y, precision=1E-6)
    return dat.xy(*idx), z[idx]

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
# set node attributes
def set_node_attributes(graph: nx.DiGraph) -> nx.DiGraph:
    node_attributes: dict[int, dict[str, float]] = {}

    for osmid, data in graph.nodes(data=True):
        lat = data['y']
        lon = data['x']
        node_attributes[osmid]  = {
            'osmid': osmid, 
            'lat': lat, 
            'lon': lon
        }

    nx.set_node_attributes(graph, node_attributes)

    return graph

def set_node_elevation(graph: nx.DiGraph) -> nx.DiGraph:
    elevation_for_nodes: dict[int, dict[str, float]] = {}

    for osmid, data in graph.nodes(data=True):
        lat = data['y']
        lon = data['x']
        _, elevation = get_elevation(lon, lat)
        elevation_for_nodes[osmid]  = {
            'elevation': elevation
        }

    nx.set_node_attributes(graph, elevation_for_nodes)

    return graph

def set_edge_slope(graph: nx.DiGraph) -> nx.DiGraph:
    slope_percentages: dict[tuple[int, int], dict[str, float]] = {}

    for u, v, e_data in graph.edges(data=True):
        start_node = graph.nodes[u]
        dest_node = graph.nodes[v]
        
        hight_diff = dest_node['elevation'] - start_node['elevation']
        slope_percentage = (hight_diff / e_data['length']) * 100

        slope_percentages[u, v] = {'slope_percentage': float(slope_percentage)}
        
    nx.set_edge_attributes(graph, slope_percentages)

    return graph

def debug_plot(graph: nx.DiGraph):
    map = leafmap.Map(location=[49.451900, 11.076608], zoom_start=12, crs='EPSG3857')

    for node_id, node_data in graph.nodes(data=True):
        folium.Marker((node_data['y'], node_data['x']), f'osmid: {node_data["osmid"]}').add_to(map)

    for edge_start_id, edge_dest_id, edge_data in graph.edges(data=True):
        start_node = graph.nodes[edge_start_id]
        dest_node = graph.nodes[edge_dest_id]
        folium.PolyLine([(start_node['y'], start_node['x']), (dest_node['y'], dest_node['x'])], color='blue').add_to(map)

    return map

def is_tag_available(attribute: str, value: str, tags: dict[str, str]) -> bool:
    if attribute not in tags.keys():
        return False
    else:
        return tags[attribute] == value

def get_slope_penalty(slope: float) -> float:
    if slope < 2:
        return 1.0
    elif slope >= 2 and slope < 4:
        return 1.37
    elif slope >= 4 and slope < 6:
        return 2.2
    elif slope >= 6:
        return 4.24

def has_bike_lane(tags: dict[str, str]) -> bool:
    bike_lane_filter: list[tuple[str, str]] = [
        ("cycleway", "lane"),
        ("cycleway:right", "lane"),
        ("cycleway:left", "lane"),
        ("cycleway:both", "lane"),
        ("cycleway", "opposite")
    ]
    return any(is_tag_available(k, v, tags) for k, v in bike_lane_filter)

def has_bike_path(tags: dict[str, str]) -> bool:
    bike_path_filter: list[tuple[str, str]] = [
        ("bicycle", "designated"),
        ("highway", "cycleway"),
        ("cycleway", "track"),
        ("cycleway:right", "track"),
        ("cycleway:left", "track"),
        ("cycleway:both", "track")
    ]
    return any(is_tag_available(k, v, tags) for k, v in bike_path_filter)

def is_bike_road(tags: dict[str, str]) -> bool:
    bike_road_filter: list[tuple[str, str]] = [
        ('bicycle_road', 'yes')
    ]
    return any(is_tag_available(k, v, tags) for k, v in bike_road_filter)

def is_primary_road(tags: dict[str, str]) -> bool:
    primary_road_filter: list[tuple[str, str]] = [
        ('highway', 'primary')
    ]
    return any(is_tag_available(k, v, tags) for k, v in primary_road_filter)

def is_secondary_road(tags: dict[str, str]) -> bool:
    secondary_road_filter: list[tuple[str, str]] = [
        ('highway', 'secondary')
    ]
    return any(is_tag_available(k, v, tags) for k, v in secondary_road_filter)

def is_tertiary_road(tags: dict[str, str]) -> bool:
    tertiary_road_filter: list[tuple[str, str]] = [
        ('highway', 'tertiary')
    ]
    return any(is_tag_available(k, v, tags) for k, v in tertiary_road_filter)

def is_residential_road(tags: dict[str, str]) -> bool:
    residential_road_filter: list[tuple[str, str]] = [
        ('highway', 'residential')
    ]
    return any(is_tag_available(k, v, tags) for k, v in residential_road_filter)

# define benefits and penalties for edges according to their osm features
type filter = tuple[list[function], float]

bike_lanes_separate: filter = ([has_bike_path], 0.84)
bike_lanes_on_road: filter = ([has_bike_lane], 0.84)
bike_boulevard: filter = ([is_bike_road], 0.90)
primary_road: filter = ([is_primary_road], 8.15)
secondary_road: filter = ([is_secondary_road], 2.40)
tertiary_road: filter = ([is_tertiary_road], 1.37)
residential_road: filter = ([is_residential_road], 1.10)

benefit_lookup = [
    bike_lanes_separate,
    bike_lanes_on_road,
    bike_boulevard,
    primary_road,
    secondary_road,
    tertiary_road,
    residential_road
]

def get_weight(u, v, data) -> float:
    try:
        osmid = data['osmid']
        tags = edges_osm_data_lookup.loc[osmid, 'tags']
    except:
        raise ValueError(f'could not find edge with osmid {osmid}')
    
    penalties: float = []

    try:
        penalties.append(get_slope_penalty(data['slope_percentage']))
    except:
        pass

    try:
        penalties.append(get_turn_penalty(data['turning_angle']))
    except:
        pass

    for filter_functions, benefit in benefit_lookup:
        for f in filter_functions:
            if f(tags):
                penalties.append(benefit)

    if len(penalties) == 0:
        return 1.0
    else:
        return math.prod(penalties)

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

graph = ox.graph_from_place(query=place_name, simplify=False, retain_all=True, custom_filter=[bikeable_ways, bikeable_areas])
#graph = ox.graph_from_bbox((11.112403,49.454498,11.112832,49.454774), network_type='bike', simplify=False, retain_all=True, truncate_by_edge=True)

node_lookup = ox.graph_to_gdfs(graph, nodes=True, edges=False, node_geometry=True, fill_edge_geometry=False)
edge_lookup = ox.graph_to_gdfs(graph, nodes=False, edges=True)

graph = nx.DiGraph(graph)
#%%
# set node and edge attributes
graph = set_node_attributes(graph)
graph = set_node_elevation(graph)
graph = set_edge_slope(graph)

print('stats of graph before splitting crossing nodes:')
print('number of edges:', len(graph.edges))
print('number of nodes:', len(graph.nodes))

graph = split_nodes(graph)

print('stats of graph after splitting crossing nodes:')
print('number of edges:', len(graph.edges))
print('number of nodes:', len(graph.nodes))

#%%
# calculate edge weights according to their osm features
weights: dict[tuple[int, int], dict[str, float]] = {}
problematic_osmids = []
for u, v, data in tqdm(graph.edges(data=True), desc='calculating edge weights', total=len(graph.edges), unit='edges'):
    if 'osmid' not in data.keys():
        weights[u,v] = {'weight': data['length']}
        continue

    try:
        weight = get_weight(u, v, data)
        weights[u,v] = {'weight': float(data['length'] * weight)}
    except:
        problematic_osmids.append(data['osmid'])

if len(problematic_osmids) > 0:
    print(f'found problems with {len(problematic_osmids)} edges')
    get_list_of_edges(problematic_osmids, edges_osm_data_lookup).explore()

# add weight attribute to graph
nx.set_edge_attributes(graph, weights)

# %%
# save graph to file
ox.io.save_graphml(nx.MultiDiGraph(graph), filepath='expanded_bicycle_graph.graphml')

# %%
