import datetime
import multiprocessing as mp
import os
import tarfile
import typing

import geopandas as gpd
import leafmap.foliumap as leafmap
import networkx as nx
import numpy as np
import osmnx as ox
import shapely
from folium import PolyLine
from geopandas import GeoDataFrame
from pyproj import CRS, Geod, Transformer
from shapely.ops import transform
from tqdm import tqdm

from utils.graph_types import *


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
    merged_df: GeoDataFrame = gpd.GeoDataFrame()
    for osmid in osmids:
        tmp = df.loc[df['osmid'] == osmid]
        merged_df.add(tmp)
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

# filter out routes that are not valid
def correct_routes(route: Route) -> bool:
    return route != None and len(route) > 1

def a_star(
    graph: nx.Graph, 
    orig: EdgeId, 
    dest: EdgeId, 
    heuristic: typing.Callable, 
    weight: str
) -> Route | None:
    try:
        return list(nx.astar_path(graph, orig, dest, heuristic=heuristic, weight=weight))
    except nx.NetworkXNoPath:
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

def transform_coordinates(coords: list[list[float]], transformer: Transformer) -> list[float]:
    return [transformer.transform(coord[0], coord[1]) for coord in coords]

def shift_graph(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    graph = graph.copy()

    # calculate shifted coordinates for each node
    for node in tqdm(graph.nodes, desc='Calculating shifted coordinates', unit='nodes'):
        in_edges = list(graph.in_edges(node, data=True))
        out_edges = list(graph.out_edges(node, data=True))
        edges = in_edges + out_edges

        shifted_points = []
        street_edges = []

        for edge in edges:
            s, d, data = edge
            # edge is an edge that represents a turning option at an intersection
            # the nodes of this edge are the same as the intersection node
            if 'turning_angle' in data.keys():
                continue
            else:
                # edge represents a street
                street_edges.append(edge)
            
            try:
                line: shapely.LineString = data['geometry']
            except KeyError:
                line = shapely.LineString([[graph.nodes[s]['x'], graph.nodes[s]['y']], [graph.nodes[d]['x'], graph.nodes[d]['y']]])
            
            line_coords = list(line.coords)
            if line_coords[0] == line_coords[-1]:
                # line is closed
                # move last and first point slightly
                first_point = line.interpolate(0.00001)
                last_point = line.interpolate(line.length - 0.00001)
                line = shapely.LineString([first_point] + list(line.coords[1:-1]) + [last_point])

            shifted_line = line.parallel_offset(0.00001, side='right', join_style='mitre')
            if shifted_line.is_empty:
                shifted_line = line
            
            try:
                if s == node:
                    shifted_coords = shifted_line.coords[0]
                else:
                    shifted_coords = shifted_line.coords[-1]
            except IndexError:
                print(s, d, data)
                print('IndexError:', shifted_line)
            
            shifted_points.append((shifted_coords[0], shifted_coords[-1]))

        x_shifted = np.mean([coord[0] for coord in shifted_points])
        y_shifted = np.mean([coord[-1] for coord in shifted_points])

        if len(shifted_points) == 1 and len(street_edges) == 1:
            s, d, data = street_edges[0]
            try:
                line: shapely.LineString = data['geometry']
            except KeyError:
                s_x, s_y = (graph.nodes[s]['x'], graph.nodes[s]['y'])
                d_x, d_y = (graph.nodes[d]['x'], graph.nodes[d]['y'])
                line = shapely.LineString([[s_x, s_y], [d_x, d_y]])

            line_coords = list(line.coords)
            if line_coords[0] == line_coords[-1]:
                # line is closed
                # move last and first point slightly
                first_point = line.interpolate(0.00001)
                last_point = line.interpolate(line.length - 0.00001)
                line = shapely.LineString([first_point] + list(line.coords[1:-1]) + [last_point])
            shifted_line = line.parallel_offset(0.00001, side='right', join_style='mitre')
            if shifted_line.is_empty:
                shifted_line = line

            if street_edges[0] in in_edges:
                shifted_point = shifted_line.line_interpolate_point(shifted_line.length - 0.00002)
            else:
                shifted_point = shifted_line.line_interpolate_point(-(shifted_line.length - 0.00002))
            
            x_shifted = shifted_point.x
            y_shifted = shifted_point.y

        graph.nodes[node]['x_shifted'] = x_shifted
        graph.nodes[node]['y_shifted'] = y_shifted

    for s, d, key, data in graph.edges(data=True, keys=True):
        try:
            line: shapely.LineString = data['geometry']
            line_coords = list(line.coords)
            if line_coords[0] == line_coords[-1]:
                # line is closed
                # move last and first point slightly
                first_point = line.interpolate(0.00001)
                last_point = line.interpolate(line.length - 0.00001)
                line = shapely.LineString([first_point] + list(line.coords[1:-1]) + [last_point])
            line = line.parallel_offset(0.00001, side='right', join_style='mitre')
            if line.is_empty:
                line = data['geometry']

            line = list(line.coords)
            try:
                line[0] = (graph.nodes[s]['x_shifted'], graph.nodes[s]['y_shifted'])
                line[-1] = (graph.nodes[d]['x_shifted'], graph.nodes[d]['y_shifted'])
            except KeyError:
                line[0] = (graph.nodes[s]['x'], graph.nodes[s]['y'])
                line[-1] = (graph.nodes[d]['x'], graph.nodes[d]['y'])
            line = shapely.LineString(line)
        except KeyError:
            try:
                start = [graph.nodes[s]['y_shifted'], graph.nodes[s]['x_shifted']]
            except:
                try:
                    start = [graph.nodes[s]['y_shifted'], graph.nodes[s]['x_shifted']]
                except:
                    start = [graph.nodes[s]['y'], graph.nodes[s]['x']]
            try:
                dest = [graph.nodes[d]['y_shifted'], graph.nodes[d]['x_shifted']]
            except:
                try:
                    dest = [graph.nodes[d]['y_shifted'], graph.nodes[d]['x_shifted']]
                except:
                    dest = [graph.nodes[d]['y'], graph.nodes[d]['x']]
            line = shapely.LineString([start[::-1], dest[::-1]])
            pass
        
        graph.edges[s, d, key]['shifted_geometry'] = line

    return graph

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
            u0, u1, u2 = split_tuple(u[0][1:-1])
            u[0] = (int(u1), int(u0), int(u2))
        else:
            u[0] = int(u[0])
        if is_tuple(u[1]):
            u0, u1, u2 = split_tuple(u[1][1:-1])
            u[1] = (int(u1), int(u0), int(u2))
        else:
            u[1] = int(u[1])
        u = [u[1], u[0], int(u[2])]
        u = str(tuple(u))
    if is_tuple(v):
        v = split_tuple(v[1:-1])
        if is_tuple(v[0]):
            v0, v1, v2 = split_tuple(v[0][1:-1])
            v[0] = (int(v1), int(v0), int(v2))
        else:
            v[0] = int(v[0])
        if is_tuple(v[1]):
            v0, v1, v2 = split_tuple(v[1][1:-1])
            v[1] = (int(v1), int(v0), int(v2))
        else:
            v[1] = int(v[1])
        v = [v[1], v[0], int(v[2])]
        v = str(tuple(v))

    return (v, u, k)

def split_outside_brackets(string):
    result = []
    bracket_depth = 0
    last_split = 0

    for i, char in enumerate(string):
        if char == '[':
            bracket_depth += 1
        elif char == ']':
            bracket_depth -= 1
        elif char == ',' and bracket_depth == 0:
            result.append(string[last_split:i].strip())
            last_split = i + 1

    # Füge den letzten Teil hinzu
    result.append(string[last_split:].strip())
    return result

assert split_outside_brackets('[12345678, [12345678, 87654321]], [12345679, 98765432]') == ['[12345678, [12345678, 87654321]]', '[12345679, 98765432]']

def parse_junction_osmid(og_osmid: str | int) -> tuple[int|list[int], int|list[int]] | int:
    if type(og_osmid) is int:
        return og_osmid
    if og_osmid.isdigit():
        return int(og_osmid)
    
    osmid = split_outside_brackets(og_osmid[1:-1])
    osmid_0 = osmid[0].strip()
    osmid_1 = osmid[1].strip()

    if osmid_0.isdigit():
        osmid_0 = int(osmid_0)
    elif osmid_0.startswith('[') and osmid_0.endswith(']'):
        osmid_0 = osmid_0[1:-1].split(',')
        osmid_0 = [int(x.strip()) for x in osmid_0]

    if osmid_1.isdigit():
        osmid_1 = int(osmid_1)
    elif osmid_1.startswith('[') and osmid_1.endswith(']'):
        osmid_1 = osmid_1[1:-1].split(',')
        osmid_1 = [int(x.strip()) for x in osmid_1]

    return (osmid_0, osmid_1)

assert parse_junction_osmid('12345678') == 12345678
assert parse_junction_osmid('(12345678, 87654321)') == (12345678, 87654321)
assert parse_junction_osmid('(12345678, [87654321, 12345679])') == (12345678, [87654321, 12345679])
assert parse_junction_osmid('([12345678, 87654321], 12345679)') == ([12345678, 87654321], 12345679)
assert parse_junction_osmid('([12345678, 87654321], [12345679, 98765432])') == ([12345678, 87654321], [12345679, 98765432])

def get_unique_lines(lines: list[shapely.MultiLineString | shapely.LineString]) -> list[shapely.LineString]:
    reachable_edges = gpd.GeoSeries(lines, crs=4326)
    unique_lines = set(reachable_edges.explode().values)
    return list(unique_lines)

def is_sublist(small: list, big: list) -> bool:
    # Convert to string representation
    big_str = ','.join(map(str, big))
    small_str = ','.join(map(str, small))

    res = big_str.find(small_str) != -1
    return res

def parse_old_edge_key(s: str) -> tuple[int, int, int]:
    s = s.strip('()')
    parts: list[int] = list()
    str_parts = s.split(',')
    for part in str_parts:
        parts.append(int(part.strip()))
    if len(parts) != 3:
        raise ValueError(f'expected 3 parts in old_edge_key but got {len(parts)} parts')
    return (parts[0], parts[1], parts[2])

def buffer_in_meters(geometry: shapely.Geometry, buffer_m: float) -> shapely.Geometry:
    wgs84 = CRS('EPSG:4326')
    utm = CRS('EPSG:25832')

    project = Transformer.from_crs(wgs84, utm, always_xy=True).transform
    project_back = Transformer.from_crs(utm, wgs84, always_xy=True).transform

    # project to epsg 25832
    utm_geometry = transform(project, geometry)
    # buffer in meters
    buffered_geometry = utm_geometry.buffer(buffer_m)
    # project back to epsg 4326
    buffered_wgs84_geometry = transform(project_back, buffered_geometry)
    return buffered_wgs84_geometry