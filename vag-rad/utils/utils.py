import networkx as nx
import osmnx as ox
from folium import PolyLine
import geopandas as gpd
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
import subprocess

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

def transform_coordinates(coords: list[float], transformer: Transformer) -> list[float]:
    return [transformer.transform(coord[0], coord[1]) for coord in coords]

def shift_graph(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
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
            
            try:
                line: shapely.LineString = data['geometry']
            except KeyError:
                line = shapely.LineString([[graph.nodes[s]['x'], graph.nodes[s]['y']], [graph.nodes[d]['x'], graph.nodes[d]['y']]])
            
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
            
            if data['reversed']:
                reversed_coords.append((shifted_coords[0], shifted_coords[-1]))
            else:
                not_reversed_coords.append((shifted_coords[0], shifted_coords[-1]))

        x_reversed = np.mean([coord[0] for coord in reversed_coords])
        y_reversed = np.mean([coord[-1] for coord in reversed_coords])

        x_not_reversed = np.mean([coord[0] for coord in not_reversed_coords])
        y_not_reversed = np.mean([coord[-1] for coord in not_reversed_coords])

        if (len(not_reversed_coords) == 1 or len(reversed_coords) == 1) and len(street_edges) == 1:
            s, d, data = street_edges[0]
            try:
                line: shapely.LineString = data['geometry']
            except KeyError:
                s_x, s_y = (graph.nodes[s]['x'], graph.nodes[s]['y'])
                d_x, d_y = (graph.nodes[d]['x'], graph.nodes[d]['y'])
                line = shapely.LineString([[s_x, s_y], [d_x, d_y]])
            shifted_line = line.parallel_offset(0.00001, side='right', join_style='mitre')
            if shifted_line.is_empty:
                shifted_line = line

            if street_edges[0] in in_edges:
                shifted_point = shifted_line.line_interpolate_point(shifted_line.length - 0.00002)
            else:
                shifted_point = shifted_line.line_interpolate_point(-(shifted_line.length - 0.00002))
            
            if len(not_reversed_coords) == 1:
                x_not_reversed = shifted_point.x
                y_not_reversed = shifted_point.y
            else:
                x_reversed = shifted_point.x
                y_reversed = shifted_point.y

        if len(reversed_coords) > 0:
            #x_reversed, y_reversed = gk_to_osm.transform(x_reversed, y_reversed)
            graph.nodes[node]['x_reversed'] = x_reversed
            graph.nodes[node]['y_reversed'] = y_reversed
        if len(not_reversed_coords) > 0:
            #x_not_reversed, y_not_reversed = gk_to_osm.transform(x_not_reversed, y_not_reversed)
            graph.nodes[node]['x_not_reversed'] = x_not_reversed
            graph.nodes[node]['y_not_reversed'] = y_not_reversed

    for edge in graph.edges(data=True, keys=True):
        s, d, key, data = edge
        try:
            line: shapely.LineString = data['geometry']
            line = line.parallel_offset(0.00001, side='right', join_style='mitre')
            if line.is_empty:
                line = data['geometry']

            if data['reversed']:
                line = list(line.coords)
                try:
                    line[0] = (graph.nodes[s]['x_reversed'], graph.nodes[s]['y_reversed'])
                    line[-1] = (graph.nodes[d]['x_reversed'], graph.nodes[d]['y_reversed'])
                except KeyError:
                    line[0] = (graph.nodes[s]['x'], graph.nodes[s]['y'])
                    line[-1] = (graph.nodes[d]['x'], graph.nodes[d]['y'])
            else:
                line = list(line.coords)
                try:
                    line[0] = (graph.nodes[s]['x_not_reversed'], graph.nodes[s]['y_not_reversed'])
                    line[-1] = (graph.nodes[d]['x_not_reversed'], graph.nodes[d]['y_not_reversed'])
                except KeyError:
                    line[0] = (graph.nodes[s]['x'], graph.nodes[s]['y'])
                    line[-1] = (graph.nodes[d]['x'], graph.nodes[d]['y'])
            line = shapely.LineString(line)
        except KeyError:
            s, d, key, data = edge
            try:
                reversed = data['reversed']
            except:
                reversed = None

            if reversed == True:
                start = [graph.nodes[s]['y_reversed'], graph.nodes[s]['x_reversed']]
                dest = [graph.nodes[d]['y_reversed'], graph.nodes[d]['x_reversed']]
            if reversed == False:
                start = [graph.nodes[s]['y_not_reversed'], graph.nodes[s]['x_not_reversed']]
                dest = [graph.nodes[d]['y_not_reversed'], graph.nodes[d]['x_not_reversed']]
            # nodes at intersections only have one of those attributes (*_reversed, *_not_reversed) because they are only traversed in one direction
            if reversed is None:
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
            line = shapely.LineString([start[::-1], dest[::-1]])
            pass
        
        graph.edges[s, d, key]['shifted_geometry'] = line

    return graph

def plot_shifted_graph(graph: nx.MultiDiGraph, debug_marker=False) -> tuple[GeoDataFrame, GeoDataFrame]:
    debug_marker_df = None

    if debug_marker:
        debug_marker_df = {'osmid': [], 'geometry': [], 'color': [], 'size': [], 'label': []}
    
        for node in graph.nodes:
            try:
                x_reversed = graph.nodes[node]['x_reversed']
                y_reversed = graph.nodes[node]['y_reversed']
                debug_marker_df['geometry'].append(shapely.Point([x_reversed, y_reversed]))
                debug_marker_df['color'].append(matplotlib.colors.to_hex('red'))
                debug_marker_df['size'].append(10)
                debug_marker_df['label'].append(f'{node} reversed')
                debug_marker_df['osmid'].append(graph.nodes[node]['osmid'])
            except:
                pass
            try:
                x_not_reversed = graph.nodes[node]['x_not_reversed']
                y_not_reversed = graph.nodes[node]['y_not_reversed']
                debug_marker_df['geometry'].append(shapely.Point([x_not_reversed, y_not_reversed]))
                debug_marker_df['color'].append(matplotlib.colors.to_hex('blue'))
                debug_marker_df['size'].append(10)
                debug_marker_df['label'].append(f'{node} not reversed')
                debug_marker_df['osmid'].append(graph.nodes[node]['osmid'])
            except:
                pass
            
        debug_marker_df = GeoDataFrame(debug_marker_df, crs='EPSG:4326')
    
    # plot edges
    edges_df = {'u': [], 'v': [], 'key': [], 'osmid': [], 'geometry': [], 'color': [], 'line_width': [], 'tooltip': []}

    for s, d, key, data in tqdm(graph.edges(data=True, keys=True), desc='Plotting edges', unit='edges'):

        try:
            reversed = data['reversed']
        except:
            reversed = None

        if reversed == True:
            color = 'red'
        if reversed == False:
            color = 'blue'
        # nodes at intersections only have one of those attributes (*_reversed, *_not_reversed) because they are only traversed in one direction
        if reversed is None:
            color = 'green'

        color = data['color'] if 'color' in data else color

        edges_df['u'].append(s)
        edges_df['v'].append(d)
        edges_df['key'].append(key)
        edges_df['osmid'].append(data.get('osmid', None))
        edges_df['geometry'].append(data['shifted_geometry'])
        edges_df['color'].append(matplotlib.colors.to_hex(color))
        edges_df['line_width'].append(0.1)
        edges_df['tooltip'].append(f'''<div style="color:white">
                                        osmid: {data.get('osmid', None)}<br>
                                        edge: {s} -> {d}<br>
                                        reversed: {reversed}<br>
                                        slope: {data.get('slope_percentage', None)}<br>
                                        penalty: {data.get('penalty', None)}<br>
                                        length: {data.get('length', None)}<br>
                                        weight: {data.get('weight', None)}<br>
                                        turning angle: {data.get('turning_angle', None)}<br>
                                    </div>''')
    
    edges_df = GeoDataFrame(edges_df, crs='EPSG:4326').set_index(['u', 'v', 'key'])

    return edges_df, debug_marker_df

def plot_graph(graph: nx.MultiDiGraph, debug_marker=False) -> tuple[GeoDataFrame, GeoDataFrame]:
    debug_marker_df = None

    if debug_marker:
        debug_marker_df = {'osmid': [], 'geometry': [], 'color': [], 'size': [], 'label': []}
    
        for node in graph.nodes:
            debug_marker_df['osmid'].append(graph.nodes[node]['osmid'])
            debug_marker_df['geometry'].append(shapely.Point([graph.nodes[node]['x'], graph.nodes[node]['y']]))
            debug_marker_df['color'].append(matplotlib.colors.to_hex('black'))
            debug_marker_df['size'].append(10)
            debug_marker_df['label'].append(f'{node} original')
            
        debug_marker_df = GeoDataFrame(debug_marker_df, crs='EPSG:4326')
    
    # plot edges
    edges_df = {'u': [], 'v': [], 'key': [], 'geometry': [], 'color': [], 'line_width': [], 'tooltip': []}

    for s, d, key, data in tqdm(graph.edges(data=True), desc='Plotting edges', unit='edges'):

        color = data['color'] if 'color' in data else 'black'

        edges_df['u'].append(s)
        edges_df['v'].append(d)
        edges_df['key'].append(key)
        edges_df['geometry'].append(data.get('geometry', None))
        edges_df['color'].append(matplotlib.colors.to_hex(color))
        edges_df['line_width'].append(0.1)
        edges_df['tooltip'].append(f'''<div style="color:white">
                                        osmid: {data.get('osmid', None)}<br>
                                        edge: {s} -> {d}<br>
                                    </div>''')
    
    edges_df = GeoDataFrame(edges_df, crs='EPSG:4326').set_index(['u', 'v', 'key'])

    return edges_df, debug_marker_df

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

# call QGIS processing algorithm for network analysis
def get_network_coverage(routing_graph: nx.MultiDiGraph, coverage_graph: nx.MultiDiGraph, travel_cost: int) -> GeoDataFrame:
    path_to_qgis_processing = '/Applications/QGIS.app/Contents/MacOS/bin/qgis_process'
    geopackage_file = 'tmp.gpkg'
    result_file = 'bike_path_coverage.gpkg'

    ox.graph_to_gdfs(routing_graph, nodes=False, edges=True).to_file(geopackage_file, layer='routing_graph', driver='GPKG')
    ox.graph_to_gdfs(coverage_graph, nodes=True, edges=False).drop(columns=['osmid']).to_file(geopackage_file, layer='starting_points', driver='GPKG')

    # call QGIS processing algorithm over terminal
    result = subprocess.run([path_to_qgis_processing, 'run', 'qgis:serviceareafromlayer', 'PROJECT_PATH=/Users/bernie/Documents/mittelfranken_fahrradwege.qgz', f'INPUT={geopackage_file}|layername=routing_graph', f'START_POINTS={geopackage_file}|layername=starting_points', f'STRATEGY={0}', f'TRAVEL_COST={travel_cost}', f'OUTPUT_LINES={result_file}'], capture_output=True)

    if result.returncode != 0:
        print(f"Error occurred: {result.stderr.decode()}")
        print(result)
        return None

    reachable_edges = gpd.read_file(result_file)

    #remove temporary files
    os.remove(geopackage_file)
    os.remove(result_file)

    return reachable_edges

def get_unique_lines(lines: list[shapely.MultiLineString | shapely.LineString]) -> list[shapely.LineString]:
    reachable_edges = gpd.GeoSeries(lines, crs=4326)
    unique_lines = set(reachable_edges.explode().values)
    return list(unique_lines)
