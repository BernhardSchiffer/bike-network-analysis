from collections import Counter

import matplotlib.colors
import matplotlib.pyplot as plt
import networkx as nx
import shapely
from geopandas import GeoDataFrame
from pandas import DataFrame
from tqdm import tqdm

from utils.utils import get_reversed_key


def plot_shifted_graph(graph: nx.MultiDiGraph) -> tuple[GeoDataFrame, GeoDataFrame]:
    nodes_data = {'osmid': [], 'geometry': [], 'label': []}

    for node in graph.nodes:
        try:
            x_shifted = graph.nodes[node]['x_shifted']
            y_shifted = graph.nodes[node]['y_shifted']
            nodes_data['geometry'].append(shapely.Point([x_shifted, y_shifted]))
            nodes_data['label'].append(f'{node}')
            nodes_data['osmid'].append(graph.nodes[node]['osmid'])
        except:
            x_shifted = graph.nodes[node]['x']
            y_shifted = graph.nodes[node]['y']
            nodes_data['geometry'].append(shapely.Point([x_shifted, y_shifted]))
            nodes_data['label'].append(f'{node}')
            nodes_data['osmid'].append(graph.nodes[node]['osmid'])
        
    nodes_df = GeoDataFrame(nodes_data, crs='EPSG:4326')
    
    # plot edges
    edges_data = {'u': [], 'v': [], 'key': [], 'osmid': [], 'geometry': [], 'color': [], 'tooltip': []}

    for s, d, key, data in graph.edges(data=True, keys=True):
        try:
            data['shifted_geometry']
        except KeyError:
            continue

        reversed = data.get('reversed', None)

        if reversed:
            color = 'red'
        if not reversed:
            color = 'blue'
        # nodes at intersections only have one of those attributes (*_reversed, *_not_reversed) because they are only traversed in one direction
        if reversed is None:
            color = 'green'

        color = data['color'] if 'color' in data else color

        edges_data['u'].append(s)
        edges_data['v'].append(d)
        edges_data['key'].append(key)
        edges_data['osmid'].append(data.get('osmid', None))
        edges_data['geometry'].append(data['shifted_geometry'])
        edges_data['color'].append(matplotlib.colors.to_hex(color))
        edges_data['tooltip'].append(f'''<div style="color:white">
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
    
    edges_df = GeoDataFrame(edges_data, crs='EPSG:4326')
    edges_df.set_index(['u', 'v', 'key'], inplace=True)

    return edges_df, nodes_df

def plot_graph(graph: nx.MultiDiGraph) -> tuple[GeoDataFrame, GeoDataFrame]:
    already_added_nodes: set[str] = set()
    nodes_data = {'osmid': [], 'geometry': [], 'label': []}

    for node in graph.nodes:
        osmid = graph.nodes[node]['osmid']
        if osmid in already_added_nodes:
            continue
        already_added_nodes.add(osmid)
        nodes_data['osmid'].append(osmid)
        nodes_data['geometry'].append(shapely.Point([graph.nodes[node]['x'], graph.nodes[node]['y']]))
        nodes_data['label'].append(node)
        
    nodes_df = GeoDataFrame(nodes_data, crs='EPSG:4326')
    
    # plot edges
    edges_data = {'u': [], 'v': [], 'key': [], 'geometry': [], 'color': [], 'tooltip': []}

    for s, d, key, data in graph.edges(data=True, keys=True):
        color = data['color'] if 'color' in data else 'black'

        edges_data['u'].append(s)
        edges_data['v'].append(d)
        edges_data['key'].append(key)
        edges_data['geometry'].append(data.get('geometry', None))
        edges_data['color'].append(matplotlib.colors.to_hex(color))
        edges_data['tooltip'].append(f'''<div style="color:white">
                                        osmid: {data.get('osmid', None)}<br>
                                        edge: {s} -> {d}<br>
                                    </div>''')
    
    edges_df = GeoDataFrame(edges_data, crs='EPSG:4326')
    edges_df.set_index(['u', 'v', 'key'], inplace=True)

    return edges_df, nodes_df


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
