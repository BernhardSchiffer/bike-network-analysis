# %% 
# imports
import matplotlib.colorbar
import osmnx as ox
import networkx as nx
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import psycopg2
import os
from dotenv import load_dotenv
import folium
import geopandas as gpd
from collections import Counter
import time
import osmium
from utils.polygon_filter import PolygonFilter
from utils.utils import *

# %%
# helper functions
# plot routes on a map
def plot_routes(routes: list[list[int] | None], graph: nx.MultiDiGraph):
    nodes = ox.graph_to_gdfs(graph, nodes=True, edges=False, node_geometry=True, fill_edge_geometry=False)
    map = folium.Map(location=[49.451900, 11.076608], zoom_start=12, crs='EPSG3857')

    for route in routes:
        if(route):
            positions = []
            for node_id in route:
                node = nodes.loc[node_id]
                positions.append((node['y'], node['x']))
            folium.PolyLine(positions).add_to(map)

    return map

# calculate heat map for traveled edges
def plot_heat_map_of_edges(routes: list[list[int] | None], graph: nx.MultiDiGraph):
    nodes = ox.graph_to_gdfs(graph, nodes=True, edges=False, node_geometry=True, fill_edge_geometry=False)
    cmap = plt.get_cmap('turbo')
    edges_counter = Counter()

    for route in routes:
        if route:
            start_node = route[0]
            for node in route[1:]:
                edges_counter.update([(start_node, node)])
                start_node = node

    map = folium.Map(location=[49.451900, 11.076608], zoom_start=12, crs='EPSG3857')

    max_value = edges_counter.most_common(1)[0][1]

    for edge, count in edges_counter.items():
        positions = []
        for node_id in edge:
            node = nodes.loc[node_id]
            positions.append((node['y'], node['x']))
        color = matplotlib.colors.to_hex(cmap(count/max_value))
        folium.PolyLine(positions, color=color, tooltip=count).add_to(map)

    display(map)

    fig, ax = plt.subplots(figsize=(4,0.4))
    colorbar = matplotlib.colorbar.ColorbarBase(ax, cmap=cmap, orientation = 'horizontal')
    tick = int(max_value/5)
    colorbar.set_ticklabels([0, tick, tick*2, tick*3, tick*4, max_value])
    plt.show()

# %% 
# use specific overpass settings
ox.settings.overpass_settings = '[out:json][timeout:{timeout}][date:"2024-11-30T00:00:00Z"]{maxsize}'
# %% 
# use default overpass settings
ox.settings.overpass_settings = '[out:json][timeout:{timeout}]{maxsize}'

#%%
# Setup environment
load_dotenv()

POSTGRES_USER = os.getenv('POSTGRES_USER')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')
POSTGRES_DB = os.getenv('POSTGRES_DB')
POSTGRES_HOST = os.getenv('POSTGRES_HOST')
POSTGRES_PORT = os.getenv('POSTGRES_PORT')

# %% 
# fetch graph of all streets available by bike
place_name = 'Nürnberg'

graph = ox.graph_from_place(query=place_name, simplify=False, retain_all=True, network_type='bike')

# %% 
# some statistics of the graph
nodes = ox.graph_to_gdfs(graph, nodes=True, edges=False, node_geometry=True, fill_edge_geometry=False)
edges = ox.graph_to_gdfs(graph, nodes=False)
overall_length = sum(edges["length"])

print(f'number of edges: {len(edges)}')
print(f'length of network: {overall_length} meters')

# %% 
# get rides of all bikes over time
conn = psycopg2.connect(
    host=POSTGRES_HOST,
    database=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    port=POSTGRES_PORT)

sql = f"""select r.* from rides r 
            where ST_Distance(r.starting_position, r.finishing_position) < 20000
            and ST_Distance(r.starting_position, r.finishing_position) > 150 
            and r.starting_time::date != '2023-10-10'
            and r.starting_time::date != '2023-10-11'
            order by r.bike_id, r.starting_time
            limit 10000;"""
finishing_pos_sql = f"""select r.id, r.finishing_position from rides r
                        where ST_Distance(r.starting_position, r.finishing_position) < 20000
                        and ST_Distance(r.starting_position, r.finishing_position) > 150 
                        and r.starting_time::date != '2023-10-10'
                        and r.starting_time::date != '2023-10-11'
                        order by r.bike_id, r.starting_time
                        limit 10000;"""

df = gpd.read_postgis(
    sql, 
    conn, 
    geom_col='starting_position', 
    parse_dates='%Y-%m-%d %H:%M:%S')

finishing_pos = gpd.read_postgis(
    finishing_pos_sql, 
    conn, 
    geom_col='finishing_position')
df.drop('finishing_position', axis=1, inplace=True)
df = df.merge(finishing_pos, on='id')
conn.close()

# %%
# calculate shortest routes and plot on map
trips = df.head(1000)
print(f'{len(trips)} trips')

starting_positions = trips['starting_position']
finishing_positions = trips['finishing_position']

print('start calculating nearest nodes')
start = time.time()
x = [p.x for p in starting_positions]
y = [p.y for p in starting_positions]
starting_node_ids = ox.distance.nearest_nodes(graph, x, y)

x = [p.x for p in finishing_positions]
y = [p.y for p in finishing_positions]
finishing_node_ids = ox.distance.nearest_nodes(graph, x, y)
end = time.time()
print(f'finished calculating nearest nodes in {end - start} seconds')

print('start calculating routes')
start = time.time()
routes = ox.routing.shortest_path(graph, starting_node_ids, finishing_node_ids, cpus=1)
end = time.time()
print(f'finished calculating routes in {end - start} seconds')

plot_heat_map_of_edges(routes, graph)

# %%
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

edges_lookup = pd.DataFrame(edges_in_nbg).set_index('osmid')
# %%
# define benefits and penalties for edges according to their osm features
bike_lane_filter: list[tuple[str, str]] = [
    ("cycleway", "lane"),
    ("cycleway:right", "lane"),
    ("cycleway:left", "lane"),
    ("cycleway:both", "lane"),
    ("cycleway", "opposite")
]
bike_path_filter: list[tuple[str, str]] = [
    ("bicycle", "designated"),
    ("highway", "cycleway"),
    ("cycleway", "track"),
    ("cycleway:right", "track"),
    ("cycleway:left", "track"),
    ("cycleway:both", "track")
]
bike_road_filter: list[tuple[str, str]] = [
    ('bicycle_road', 'yes')
]

bike_lanes_separate = (bike_path_filter, 0.5)

bike_lanes_on_road = (bike_lane_filter, 0.8)

benefit_lookup = [bike_lanes_separate, bike_lanes_on_road]

def is_tag_available(attribute: str, value: str, tags: dict[str, str]) -> bool:
    if attribute not in tags.keys():
        return False
    else:
        return tags[attribute] == value
    
def any_attributes_present(filter_tags: tuple[str, str], edge_tags: dict[str, str]):
    return any(is_tag_available(k, v, edge_tags) for k, v in filter_tags)


def get_weight(osmid: int) -> float:
    try:
        tags = edges_lookup.loc[osmid, 'tags']
    except:
        raise ValueError(f'could not find edge with osmid {osmid}')
    
    for filter_tags, benefit in benefit_lookup:
        if any_attributes_present(filter_tags, tags):
            return benefit
    return 1.0

# %%
# calculate edge weights according to their osm features
print(f'starting to calculate edges weights')
start = time.time()
weight: dict[tuple[int, int], dict[str, float]] = {}
problematic_osmids = []
for u, v, k in graph.edges:
    data = graph.edges[u,v,k]
    try:
        benefit = get_weight(data['osmid'])
    except:
        problematic_osmids.append(data['osmid'])
    weight[u,v,k] = {'weight': data['length'] * benefit}

end = time.time()
print(f'successfully calculated weight of {len(weight)} edges in {end - start} seconds')

if len(problematic_osmids) > 0:
    print(f'found problems with {len(problematic_osmids)} edges')
    get_list_of_edges(problematic_osmids, edges_lookup).explore()

# %%
# add weight attribute to graph
nx.set_edge_attributes(graph, weight)

# %%
# calculate trips based on the new weight metric based on osm features
trips = df.head(1000)
print(f'{len(trips)} trips')

starting_positions = trips['starting_position']
finishing_positions = trips['finishing_position']

print('start calculating nearest nodes')
start = time.time()
x = [p.x for p in starting_positions]
y = [p.y for p in starting_positions]
starting_node_ids = ox.distance.nearest_nodes(graph, x, y)

x = [p.x for p in finishing_positions]
y = [p.y for p in finishing_positions]
finishing_node_ids = ox.distance.nearest_nodes(graph, x, y)
end = time.time()
print(f'finished calculating nearest nodes in {end - start} seconds')

print('start calculating routes')
start = time.time()
routes = ox.routing.shortest_path(graph, starting_node_ids, finishing_node_ids, cpus=1, weight='weight')
end = time.time()
print(f'finished calculating routes in {end - start} seconds')

plot_heat_map_of_edges(routes, graph)

# %%
