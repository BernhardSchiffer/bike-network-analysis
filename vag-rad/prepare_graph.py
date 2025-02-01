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
import pickle
import igraph as ig
import leafmap.foliumap as leafmap
from pyproj import Transformer
import numpy as np
from shapely.geometry import LineString

osm_to_geotiff = Transformer.from_crs("EPSG:4326", "EPSG:25832")
geotiff_to_osm = Transformer.from_crs("EPSG:25832", "EPSG:4326")

import rasterio
dat = rasterio.open('/Users/bernie/Downloads/DEM/nuernberg.tif')
# read all the data from the first band
z = dat.read()[0]

def get_elevation(lon, lat):
    x, y = osm_to_geotiff.transform(lat, lon)
    idx = dat.index(x, y, precision=1E-6)
    return dat.xy(*idx), z[idx]

# %%
# use specific overpass settings
ox.settings.overpass_settings = '[out:json][timeout:{timeout}][date:"2024-11-30T00:00:00Z"]{maxsize}'
# %% 
# use default overpass settings
ox.settings.overpass_settings = '[out:json][timeout:{timeout}]{maxsize}'

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

        slope_percentages[u, v] = {'slope_percentage': slope_percentage}
        
    nx.set_edge_attributes(graph, slope_percentages)

    return graph

def get_angle_between_edges(e1: LineString, e2: LineString):
    # calculate bearing of edges
    e1_start = e1.coords[0]
    e1_dest = e1.coords[1]
    e1_bearing = ox.bearing.calculate_bearing(e1_start[1], e1_start[0], e1_dest[1], e1_dest[0])
    e2_start = e2.coords[0]
    e2_dest = e2.coords[1]
    e2_bearing = ox.bearing.calculate_bearing(e2_start[1], e2_start[0], e2_dest[1], e2_dest[0])

    bearing_diff = e2_bearing - e1_bearing
    # normalize to -180, 180
    # left turns are negative, right turns are positive
    return (bearing_diff+180)%360-180

def split_nodes(graph: nx.DiGraph) -> nx.DiGraph:
    edge_lookup = ox.graph_to_gdfs(nx.MultiDiGraph(graph), nodes=False, edges=True)

    # save old edge keys
    old_edge_keys: dict[tuple[int, int], dict[str, float]] = {}
    for u, v in graph.edges():
        old_edge_keys[u, v] = {'old_edge_key': (u, v)}
    nx.set_edge_attributes(graph, old_edge_keys)

    for node_id, node_data in [x for x in graph.nodes(data=True)]:
        in_edges = graph.in_edges(node_id, data=True)
        out_edges = graph.out_edges(node_id, data=True)

        in_osm_ids = [e[2].get("osmid") for e in in_edges]
        out_osm_ids = [e[2].get("osmid") for e in out_edges]
        osmids = set()
        osmids.update(out_osm_ids)
        osmids.update(in_osm_ids)

        # only split nodes with more than one in and out edge and only if they are not the same street
        if len(in_edges) <= 0 or len(out_edges) <= 0 or (len(osmids) == 1):
            continue

        # create new nodes for each out edge
        out_nodes = []
        for o_s, o_d, o_data in out_edges:
            graph.add_nodes_from([((o_s, o_d), node_data)])
            out_nodes.append((o_s, o_d))
            graph.add_edges_from([((o_s, o_d), (o_s, o_d)[1], o_data)])

        # create new edges for each in edge and connect them to the out nodes
        for in_edge_start, in_edge_dest, in_edge_data in in_edges:
            # create new node for each in edge
            graph.add_nodes_from([((in_edge_start, in_edge_dest), node_data)])
            # create new edges to each out edge
            for out_node, out_edge in zip(out_nodes, out_edges):
                out_edge_data = out_edge[2]
                # TODO calculate turn angle and set attribute if street is the same or changes
                e1 = edge_lookup.loc[in_edge_data['old_edge_key'][0], in_edge_data['old_edge_key'][1], 0]['geometry']
                e2 = edge_lookup.loc[out_edge_data['old_edge_key'][0], out_edge_data['old_edge_key'][1], 0]['geometry']
                turning_angle = get_angle_between_edges(e1, e2)
                graph.add_edge((in_edge_start, in_edge_dest), out_node, length=0.0, turning_angle=turning_angle)
            # add edge from previous node to new in node
            graph.add_edges_from([((in_edge_start, in_edge_dest)[0], (in_edge_start, in_edge_dest), in_edge_data)])
        # remove old node
        graph.remove_node(node_id)

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

# %% 
# fetch graph of all streets available by bike
place_name = 'Nürnberg'


graph = ox.graph_from_place(query=place_name, simplify=False, retain_all=True, network_type='bike')
#graph = ox.graph_from_bbox((11.112403,49.454498,11.112832,49.454774), network_type='bike', simplify=False, retain_all=True, truncate_by_edge=True)

node_lookup = ox.graph_to_gdfs(graph, nodes=True, edges=False, node_geometry=True, fill_edge_geometry=False)
edge_lookup = ox.graph_to_gdfs(graph, nodes=False, edges=True)

graph = nx.DiGraph(graph)
#%%
print('edges:', len(graph.edges))
#for edge in graph.edges(data=True):
#    print(edge)

print('nodes:', len(graph.nodes))
#for node in graph.nodes(data=True):
#    print(node)
#%%
graph = set_node_attributes(graph)
graph = set_node_elevation(graph)
graph = set_edge_slope(graph)
graph = split_nodes(graph)
#%% 
print('edges:', len(graph.edges))
#for edge in graph.edges(data=True):
#    print(edge)

print('nodes:', len(graph.nodes))
#for node in graph.nodes(data=True):
#    print(node)
# %%

debug_plot(graph).save('debug.html')

# %%

for node_id, node_data in [x for x in graph.nodes(data=True)]:
    print(node_data)
    print(node_id)
    break
# %%
