import matplotlib.colorbar
import osmnx as ox
import networkx as nx
import matplotlib
import matplotlib.pyplot as plt
import psycopg2
import os
from dotenv import load_dotenv
import folium
import geopandas as gpd
from collections import Counter
import time
from utils.utils import *
import pickle
import numpy as np
import igraph as ig
import leafmap.foliumap as leafmap
from tqdm import tqdm
import multiprocessing as mp

def route_to_edge_ids(route: list[str]) -> list[tuple[str, str, int]]:
    edges = []
    for idx in range(len(route) - 1):
        edges.append((route[idx], route[idx + 1], 0))
    return edges

def get_gaps_for_route(route: list[str], graph_edges: gpd.GeoDataFrame, bike_infra_graph_edges: gpd.GeoDataFrame):
    gaps = []
    not_gap = []

    route_edges = route_to_edge_ids(route)
    for route_edge in route_edges:
        edge_df = graph_edges.loc[route_edge]
        if edge_df['osmid'] is np.nan:
            continue
        if edge_df['osmid'] not in bike_infra_graph_edges['osmid'].values:
            gaps.append(edge_df)
        else:
            not_gap.append(edge_df)
    return (gaps, not_gap)