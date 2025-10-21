import matplotlib.pyplot as plt
import networkx as nx
import matplotlib.colors
import shapely
from utils.utils import get_reversed_key
from collections import Counter
from tqdm import tqdm
from geopandas import GeoDataFrame
from pandas import DataFrame

def plot_shifted_graph(graph: nx.MultiDiGraph, debug_marker=False) -> tuple[DataFrame, DataFrame | None]:
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
                                        applied filters: {data.get('applied_filters', None)}<br>
                                    </div>''')
    
    edges_df = GeoDataFrame(edges_df, crs='EPSG:4326').set_index(['u', 'v', 'key'])

    return edges_df, debug_marker_df

def plot_graph(graph: nx.MultiDiGraph, debug_marker=False) -> tuple[DataFrame, DataFrame | None]:
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

    for s, d, key, data in tqdm(graph.edges(data=True, keys=True), desc='Plotting edges', unit='edges'):

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


def plot_edge_betweenness_centrality(graph: nx.MultiDiGraph, ebc: list[float], expanded: bool = False) -> DataFrame:
    cmap = plt.get_cmap('turbo')
    edges_counter = Counter()

    for edge, count in tqdm(zip(graph.edges, ebc), desc='count edges', unit='route'):
        edges_counter[edge] = count

    # collapse edges with same nodes ie. edges with different directions
    if not expanded:
        print(f'number of edges: {len(edges_counter)}')
        for edge in list(edges_counter.keys()):
            reversed_edge = get_reversed_key(edge)
            if reversed_edge in edges_counter:
                edges_counter[edge] = edges_counter[edge] + edges_counter[reversed_edge]
                edges_counter.pop(reversed_edge)
        print(f'number of edges after collapsing: {len(edges_counter)}')

    max_value = edges_counter.most_common(1)[0][1]

    if expanded:
        edges_df, _ = plot_shifted_graph(graph)
    else:
        edges_df, _ = plot_graph(graph)

    to_remove_edges = []
    attributes = {
        'count': [], 
        'color': [], 
        'osmid': [], 
        'weight': [], 
        'length': [], 
        'penalty': [],
        'slope': []
    }
    for idx, _ in tqdm(edges_df.iterrows(), desc='add count to edges', unit='edge', total=len(edges_df)):
        try:
            count = edges_counter[idx]
            if count == 0:
                to_remove_edges.append(idx)
                continue
            if not expanded:
                try:
                    s, d, k = idx
                    graph.edges[s, d, k]['turning_angle']
                    to_remove_edges.append((s, d, k))
                    continue
                except KeyError:
                    pass
            attributes['count'].append(count)
            color = matplotlib.colors.to_hex(cmap(count/max_value))
            attributes['color'].append(color)
            attributes['osmid'].append(graph.edges[idx].get('osmid', None))
            weight = graph.edges[idx].get('weight', None)
            attributes['weight'].append(weight)
            length = graph.edges[idx].get('length', None)
            attributes['length'].append(length)
            penalty = graph.edges[idx].get('penalty', None)
            attributes['penalty'].append(penalty)
            attributes['slope'].append(graph.edges[idx].get('slope_percentage', None))
        except KeyError:
            to_remove_edges.append((s, d, k))
            continue

    # drop rows
    edges_df = edges_df.drop(to_remove_edges)

    # add column for count and add the counts list
    for key, value in attributes.items():
        edges_df[key] = value
    # only keep columns that are needed
    columns_to_keep = ['geometry', 'line_width']
    columns_to_keep.extend(list(attributes.keys()))

    return edges_df#.reset_index(drop=True)
