import networkx as nx
import osmnx as ox
from folium import PolyLine
from geopandas import GeoDataFrame
import tarfile
import datetime
import os
import multiprocessing as mp
from utils.types import *
import leafmap.foliumap as leafmap

# calculate length of edges of a graph
def get_path_length(graph: nx.MultiGraph | nx.MultiDiGraph) -> float:
    if len(graph.edges) > 0:
        edges = ox.graph_to_gdfs(graph, nodes=False, edges=True)
        return sum(edges['length'])
    else:
        return 0
    
# plot edges of a graph on to a folium map
def plot_graph(graph: nx.MultiGraph | nx.MultiDiGraph, map=leafmap.Map(location=[49.451900, 11.076608], zoom_start=12, crs='EPSG3857'), color='blue') -> leafmap.Map:
    if(len(graph.edges) > 0):
        df = ox.graph_to_gdfs(graph, nodes=False)
        for t in df['geometry'].values:
            coordinates = []
            for c in t.coords[:]:
                coordinates.append((c[1], c[0]))
            PolyLine(coordinates, color=color).add_to(map)
    return map

def get_list_of_edges(osmids: list[str], df: GeoDataFrame) -> GeoDataFrame:
    merged_df: GeoDataFrame = None
    for osmid in osmids:
        tmp = df.loc[df['osmid'] == osmid]
        if merged_df is not None:
            merged_df.add(tmp)
        else:
            merged_df = tmp
    return merged_df

# read files from archives
def get_files_in_daterange(path: str, date_start = None, date_end = None) -> list[str]:
    file_names = []
    if date_start is None:
        start_date = datetime.datetime.min
    else:
        start_date = datetime.datetime.strptime(date_start, '%Y-%m-%d')

    if date_end is None:
        end_date = datetime.datetime.max
    else:
        end_date = datetime.datetime.strptime(date_end, '%Y-%m-%d')

    timestamp_pattern='%Y-%m-%d.tar.gz'
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith('.tar.gz'):
                file_date = datetime.datetime.strptime(file, timestamp_pattern)
                if start_date <= file_date <= end_date:
                    file_names.append(os.path.join(root, file))
    return file_names

def extract_archive_to_dir(archive: str, directory_path: str):
    with tarfile.open(archive, 'r:*') as r:
        r.extractall(directory_path)

def handler(func, path, exc_info):
    print("Inside handler")
    print(exc_info)

def a_star(graph, orig, dest, heuristic, weight) -> Route | None:
    try:
        return list(nx.astar_path(graph, orig, dest, heuristic=heuristic, weight=weight))
    except nx.exception.NetworkXNoPath:
        return None

def shortest_path_a_star(
        graph: nx.MultiDiGraph, 
        starting_nodes: list[NodeId], 
        destination_nodes: list[NodeId], 
        heuristic: function, 
        weight: str = 'length', 
        cpus: int = 1
    ) -> list[Route | None]:
    args = ((graph, o, d, heuristic, weight) for o, d in zip(starting_nodes, destination_nodes))
    with mp.get_context().Pool(cpus) as pool:
        paths = pool.starmap_async(a_star, args).get()
    return paths

# convert route to list of edge ids
def route_to_edge_ids(route: Route) -> list[EdgeId]:
    edges = []
    for idx in range(len(route) - 1):
        edges.append((route[idx], route[idx + 1], 0))
    return edges
