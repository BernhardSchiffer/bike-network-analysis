import networkx as nx
import osmnx as ox
from folium import PolyLine
from geopandas import GeoDataFrame
import tarfile
import datetime
import os
import multiprocessing as mp
from utils.graph_types import *
import leafmap.foliumap as leafmap
import typing
import matplotlib
import shapely
from pyproj import Geod, Transformer
from tqdm import tqdm
import numpy as np

# calculate length of edges of a graph
def get_path_length(graph: nx.MultiGraph | nx.MultiDiGraph) -> float:
    if len(graph.edges) > 0:
        edges = ox.graph_to_gdfs(graph, nodes=False, edges=True)
        return sum(edges['length'])
    else:
        return 0
    
# plot edges of a graph on to a folium map
def plot_graph_on_map(
    graph: nx.MultiGraph | nx.MultiDiGraph, 
    map=leafmap.Map(location=[49.451900, 11.076608], zoom_start=12, crs='EPSG3857'), 
    color='blue'
) -> leafmap.Map:
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

def a_star(
    graph: nx.Graph, 
    orig: EdgeId, 
    dest: EdgeId, 
    heuristic: typing.Callable, 
    weight: str
) -> Route | None:
    try:
        return list(nx.astar_path(graph, orig, dest, heuristic=heuristic, weight=weight))
    except nx.exception.NetworkXNoPath:
        return None

def shortest_path_a_star(
    graph: nx.MultiDiGraph, 
    starting_nodes: list[NodeId], 
    destination_nodes: list[NodeId], 
    heuristic: typing.Callable, 
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

def get_arrow_head(start: list[float], dest: list[float], color: str) -> leafmap.folium.RegularPolygonMarker:
    geodesic = Geod(ellps='WGS84')
    rot = geodesic.inv(dest[1], dest[0], start[1], start[0])[0]+90
    line = shapely.LineString([start, dest])
    arrow_pos = line.line_interpolate_point(line.length - 0.000001)
    arrow_pos = [arrow_pos.coords[0][0], arrow_pos.coords[0][1]]
    return leafmap.folium.RegularPolygonMarker(location=arrow_pos, color=color, fill=True, fill_color=color, fill_opacity=1, number_of_sides=3, rotation=rot, radius=5)

def shift_graph(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    osm_to_gk = Transformer.from_crs("EPSG:4326", "EPSG:31468")
    gk_to_osm = Transformer.from_crs("EPSG:31468", "EPSG:4326")
    
    graph = graph.copy()

    # calculate shifted coordinates for each node
    for node in tqdm(graph.nodes, desc='Calculating shifted coordinates', unit='nodes'):
        in_edges = list(graph.in_edges(node, data=True))
        out_edges = list(graph.out_edges(node, data=True))
        edges = in_edges + out_edges
        reversed_coords = []
        not_reversed_coords = []
        street_edges = []
        for edge in edges:
            s, d, data = edge
            # edge is an edge that represents a turning option at an intersection
            # the nodes of this edge are the same as the intersection node
            if graph.nodes[s]['x'] == graph.nodes[d]['x'] and graph.nodes[s]['y'] == graph.nodes[d]['y']:
                continue
            else:
                # edge represents a street
                street_edges.append(edge)
            s_x, s_y = osm_to_gk.transform(graph.nodes[s]['x'], graph.nodes[s]['y'])
            d_x, d_y = osm_to_gk.transform(graph.nodes[d]['x'], graph.nodes[d]['y'])
            line = shapely.LineString([[s_x, s_y], [d_x, d_y]])
            shifted_line = line.parallel_offset(1, side='right')
            
            if s == node:
                shifted_coords = shifted_line.coords[0]
            else:
                shifted_coords = shifted_line.coords[1]
            
            if data['reversed']:
                reversed_coords.append((shifted_coords[0], shifted_coords[1]))
            else:
                not_reversed_coords.append((shifted_coords[0], shifted_coords[1]))

        x_reversed = np.mean([coord[0] for coord in reversed_coords])
        y_reversed = np.mean([coord[1] for coord in reversed_coords])

        x_not_reversed = np.mean([coord[0] for coord in not_reversed_coords])
        y_not_reversed = np.mean([coord[1] for coord in not_reversed_coords])

        if (len(not_reversed_coords) == 1 or len(reversed_coords) == 1) and len(street_edges) == 1:
            s, d, data = street_edges[0]
            s_x, s_y = osm_to_gk.transform(graph.nodes[s]['x'], graph.nodes[s]['y'])
            d_x, d_y = osm_to_gk.transform(graph.nodes[d]['x'], graph.nodes[d]['y'])
            line = shapely.LineString([[s_x, s_y], [d_x, d_y]])
            line = line.parallel_offset(1, side='right')
            if street_edges[0] in in_edges:
                shifted_point = line.line_interpolate_point(line.length - 2)
            else:
                shifted_point = line.line_interpolate_point(-(line.length - 2))
            
            if len(not_reversed_coords) == 1:
                x_not_reversed = shifted_point.x
                y_not_reversed = shifted_point.y
            else:
                x_reversed = shifted_point.x
                y_reversed = shifted_point.y

        if len(reversed_coords) > 0:
            x_reversed, y_reversed = gk_to_osm.transform(x_reversed, y_reversed)
            graph.nodes[node]['x_reversed'] = x_reversed
            graph.nodes[node]['y_reversed'] = y_reversed
        if len(not_reversed_coords) > 0:
            x_not_reversed, y_not_reversed = gk_to_osm.transform(x_not_reversed, y_not_reversed)
            graph.nodes[node]['x_not_reversed'] = x_not_reversed
            graph.nodes[node]['y_not_reversed'] = y_not_reversed

    return graph

def plot_shifted_graph(graph: nx.MultiDiGraph, plot_original_graph=False, debug_marker=False) -> tuple[GeoDataFrame, GeoDataFrame, GeoDataFrame]:
    debug_marker_df = None
    if debug_marker:
        debug_marker_df = {'geometry': [], 'color': [], 'size': [], 'label': []}
    
        for node in graph.nodes:
            debug_marker_df['geometry'].append(shapely.Point([graph.nodes[node]['y'], graph.nodes[node]['x']]))
            debug_marker_df['color'].append(matplotlib.colors.to_hex('black'))
            debug_marker_df['size'].append(10)
            debug_marker_df['label'].append(f'{node} original')
            try:
                x_reversed = graph.nodes[node]['x_reversed']
                y_reversed = graph.nodes[node]['y_reversed']
                debug_marker_df['geometry'].append(shapely.Point([y_reversed, x_reversed]))
                debug_marker_df['color'].append(matplotlib.colors.to_hex('red'))
                debug_marker_df['size'].append(10)
                debug_marker_df['label'].append(f'{node} reversed')
            except:
                pass
            try:
                x_not_reversed = graph.nodes[node]['x_not_reversed']
                y_not_reversed = graph.nodes[node]['y_not_reversed']
                debug_marker_df['geometry'].append(shapely.Point([y_not_reversed, x_not_reversed]))
                debug_marker_df['color'].append(matplotlib.colors.to_hex('blue'))
                debug_marker_df['size'].append(10)
                debug_marker_df['label'].append(f'{node} not reversed')
            except:
                pass
        debug_marker_df = GeoDataFrame(debug_marker_df, crs='EPSG:4326')

    # plot edges
    edges_df = {'u': [], 'v': [], 'key': [], 'geometry': [], 'color': [], 'line_width': []}
    original_edges_df = {'v': [], 'u': [], 'key': [], 'geometry': [], 'color': [], 'line_width': []}

    for edge in tqdm(graph.edges(data=True), desc='Plotting edges', unit='edges'):
        s, d, data = edge
        try:
            reversed = data['reversed']
        except:
            reversed = None

        if reversed == True:
            color = 'red'
            start = [graph.nodes[s]['y_reversed'], graph.nodes[s]['x_reversed']]
            dest = [graph.nodes[d]['y_reversed'], graph.nodes[d]['x_reversed']]
        if reversed == False:
            color = 'blue'
            start = [graph.nodes[s]['y_not_reversed'], graph.nodes[s]['x_not_reversed']]
            dest = [graph.nodes[d]['y_not_reversed'], graph.nodes[d]['x_not_reversed']]
        # nodes at intersections only have one of those attributes (*_reversed, *_not_reversed) because they are only traversed in one direction
        if reversed is None:
            color = 'green'
            try:
                start = [graph.nodes[s]['y_reversed'], graph.nodes[s]['x_reversed']]
            except:
                try:
                    start = [graph.nodes[s]['y_not_reversed'], graph.nodes[s]['x_not_reversed']]
                except:
                    start = [graph.nodes[s]['y'], graph.nodes[s]['x']]
            try:
                dest = [graph.nodes[d]['y_reversed'], graph.nodes[d]['x_reversed']]
            except:
                try:
                    dest = [graph.nodes[d]['y_not_reversed'], graph.nodes[d]['x_not_reversed']]
                except:
                    dest = [graph.nodes[d]['y'], graph.nodes[d]['x']]
        
        color = data['color'] if 'color' in data else color

        edges_df['u'].append(s)
        edges_df['v'].append(d)
        edges_df['key'].append(0)
        edges_df['geometry'].append(shapely.LineString([start[::-1], dest[::-1]]))
        edges_df['color'].append(matplotlib.colors.to_hex(color))
        edges_df['line_width'].append(0.1)

        # plot original edge
        if plot_original_graph:
            start = [graph.nodes[s]['y'], graph.nodes[s]['x']]
            dest = [graph.nodes[d]['y'], graph.nodes[d]['x']]
            original_edges_df['u'].append(s)
            original_edges_df['v'].append(d)
            original_edges_df['key'].append(0)
            original_edges_df['geometry'].append(shapely.LineString([start[::-1], dest[::-1]]))
            original_edges_df['color'].append(matplotlib.colors.to_hex('black'))
            original_edges_df['line_width'].append(0.1)
    
    edges_df = GeoDataFrame(edges_df, crs='EPSG:4326').set_index(['u', 'v', 'key'])
    original_edges_df = GeoDataFrame(original_edges_df, crs='EPSG:4326').set_index(['u', 'v', 'key'])

    return edges_df, original_edges_df, debug_marker_df

def plot_graph(graph: nx.MultiDiGraph) -> GeoDataFrame:
    # plot edges
    edges_df = {'u': [], 'v': [], 'key': [], 'geometry': [], 'color': [], 'line_width': []}

    for edge in tqdm(graph.edges(data=True), desc='Plotting edges', unit='edges'):
        s, d, _ = edge
        start = [graph.nodes[s]['y'], graph.nodes[s]['x']]
        dest = [graph.nodes[d]['y'], graph.nodes[d]['x']]
        edges_df['u'].append(s)
        edges_df['v'].append(d)
        edges_df['key'].append(0)
        edges_df['geometry'].append(shapely.LineString([start[::-1], dest[::-1]]))
        edges_df['color'].append(matplotlib.colors.to_hex('black'))
        edges_df['line_width'].append(0.1)
    
    edges_df = GeoDataFrame(edges_df, crs='EPSG:4326').set_index(['u', 'v', 'key'])

    return edges_df

def is_tuple(s: str) -> bool:
    if type(s) != str:
        return False
    return s[0] == '(' and s[-1] == ')'

def split_tuple(s: str) -> list[str]:
    parts = []
    part = ''
    inside_tuple = False
    for c in s:
        if c == '(':
            inside_tuple = True
        elif c == ')':
            inside_tuple = False
        if c == ',' and not inside_tuple:
            parts.append(part)
            part = ''
        else:
            part = part + c
    parts.append(part)

    # remove leading and trailing whitespaces
    parts = [p.strip() for p in parts]
    return parts

def get_reversed_key(k: EdgeId) -> EdgeId:
    u, v, k = k
    #check if string is tuple
    if is_tuple(u):    
        u = split_tuple(u[1:-1])
        if is_tuple(u[0]):
            u0, u1 = split_tuple(u[0][1:-1])
            u[0] = (int(u1), int(u0))
        else:
            u[0] = int(u[0])
        if is_tuple(u[1]):
            u0, u1 = split_tuple(u[1][1:-1])
            u[1] = (int(u1), int(u0))
        else:
            u[1] = int(u[1])
        u = u[::-1]
        u = str(tuple(u))
    if is_tuple(v):
        v = split_tuple(v[1:-1])
        if is_tuple(v[0]):
            v0, v1 = split_tuple(v[0][1:-1])
            v[0] = (int(v1), int(v0))
        else:
            v[0] = int(v[0])
        if is_tuple(v[1]):
            v0, v1 = split_tuple(v[1][1:-1])
            v[1] = (int(v1), int(v0))
        else:
            v[1] = int(v[1])
        v = v[::-1]
        v = str(tuple(v))

    return (v, u, k)
