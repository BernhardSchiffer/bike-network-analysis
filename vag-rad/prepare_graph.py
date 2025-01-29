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
import numpy as np
import igraph as ig
import leafmap.foliumap as leafmap
from pyproj import Transformer

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
# fetch graph of all streets available by bike
place_name = 'Nürnberg'

graph = ox.graph_from_place(query=place_name, simplify=False, retain_all=True, network_type='bike')
graph = nx.DiGraph(graph)

# %%
# set node attributes
elevation_for_nodes: dict[int, dict[str, float]] = {}

for osmid, data in graph.nodes(data=True):
    lat = data['y']
    lon = data['x']
    _, elevation = get_elevation(lon, lat)
    elevation_for_nodes[osmid]  = {
        'osmid': osmid, 
        'lat': lat, 
        'lon': lon, 
        'elevation': elevation
    }

    # remove x and y because lat and lon are less ambiguous
    #del graph.nodes[osmid]['x']
    #del graph.nodes[osmid]['y']

nx.set_node_attributes(graph, elevation_for_nodes)
# %%
for osmid, data in graph.nodes(data=True):
    print(data)

# %%
slope_percentages: dict[tuple[int, int], dict[str, float]] = {}

for u, v, e_data in graph.edges(data=True):
    start_node = graph.nodes[u]
    dest_node = graph.nodes[v]
    
    hight_diff = dest_node['elevation'] - start_node['elevation']
    slope_percentage = (hight_diff / e_data['length']) * 100

    slope_percentages[u, v] = {'slope_percentage': slope_percentage}
    
nx.set_edge_attributes(graph, slope_percentages)
# %%
for edge in graph.edges(data=True):
    print(edge)
# %%
