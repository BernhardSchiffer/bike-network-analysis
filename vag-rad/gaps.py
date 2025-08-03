# %%
# imports
import osmnx as ox
import networkx as nx
import matplotlib
import matplotlib.pyplot as plt
from tqdm import tqdm
from collections import Counter
from  utils.graph_types import *
from utils.utils import correct_routes, route_to_edge_ids, get_reversed_key, plot_graph
import pickle
import igraph as ig
import time
import shapely
from geopandas import GeoDataFrame
from utils.graph_builder import get_turn_direction
from utils.graph_builder import TurnDirection

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

#%%
# join all values to a singe list
def get_all_osmids(edge_osmid: int | list[int] | tuple[int|list[int], int|list[int]]) -> list[int]:
    if type(edge_osmid) is int:
        return [edge_osmid]
    if type(edge_osmid) is list:
        return edge_osmid
    if type(edge_osmid) is tuple:
        osmid_0, osmid_1 = edge_osmid
        if type(osmid_0) is int and type(osmid_1) is int:
            return [osmid_0, osmid_1]
        if type(osmid_0) is int and type(osmid_1) is list:
            return [osmid_0] + osmid_1
        if type(osmid_0) is list and type(osmid_1) is int:
            return osmid_0 + [osmid_1]
        if type(osmid_0) is list and type(osmid_1) is list:
            return osmid_0 + osmid_1
    return []

def is_osmid_in_edge_osmid(edge_osmid: int | list[int] | tuple[int|list[int], int|list[int]], osmid: int) -> bool:
    return osmid in get_all_osmids(edge_osmid)

# %%
# load graph from file
routing_graph =  ox.io.load_graphml('simplified_bicycle_graph.graphml', node_dtypes={'osmid': str}, edge_dtypes={'weight': float, 'shifted_geometry': lambda x: shapely.from_wkt(x), 'osmid': parse_junction_osmid})

graph = ox.io.load_graphml('bicycle_graph.graphml', node_dtypes={'osmid': str}, edge_dtypes={'weight': float, 'shifted_geometry': lambda x: shapely.from_wkt(x)})
# %%
# load calculated routes from file
with open('calculated_routes.pickle', 'rb') as f:
    routes = pickle.load(f)

routes = [r for r in routes if correct_routes(r)]
# %%
# fetch graph of bicycle infrastructure
place_name = 'Nürnberg'
ox.settings.overpass_settings = '[out:json][timeout:{timeout}][date:"2025-03-15T21:21:30Z"]{maxsize}'
network_type = 'bike'
bike_lane_filter = [
    '["cycleway"="lane"]',
    '["cycleway:right"="lane"]',
    '["cycleway:left"="lane"]',
    '["cycleway:both"="lane"]'
]
bike_path_filter = [
    '["bicycle"="designated"]',
    '["highway"="cycleway"]',
    '["cycleway"="track"]',
    '["cycleway:right"="track"]',
    '["cycleway:left"="track"]',
    '["cycleway:both"="track"]'
]
bike_road_filter = [
    '["bicycle_road"="yes"]'
]
custom_filter = []
custom_filter.extend(bike_lane_filter)
custom_filter.extend(bike_path_filter)
custom_filter.extend(bike_road_filter)
bike_infra_graph = ox.graph_from_place(query=place_name, retain_all=True, simplify=False, custom_filter=custom_filter)

osmids_with_bike_infra = set(ox.graph_to_gdfs(bike_infra_graph, edges=True, nodes=False)['osmid'].values)

# %%
# finding gaps between bicycle paths
def get_gaps_for_route(route: Route, graph: nx.MultiDiGraph):
    gaps: list[EdgeId] = []
    not_gaps: list[EdgeId] = []

    route_edges = route_to_edge_ids(route)
    for route_edge in route_edges:
        try:
            if graph.edges[route_edge]['osmid'] in osmids_with_bike_infra:
                not_gaps.append(route_edge)
            else:
                gaps.append(route_edge)
        except KeyError:
            continue
    return (gaps, not_gaps)

#%%
gaps: list[EdgeId] = []
not_gaps: list[EdgeId] = []
for route in tqdm(routes, desc='finding gaps in routes', unit='route'):
    result = get_gaps_for_route(route, graph)
    gaps.extend(result[0])
    not_gaps.extend(result[1])

print(f'{len(set(gaps))} road segments have no bike infrastructure')
print(f'{len(set(not_gaps))} road segments have bike infrastructure')

# write gaps to file
with open('gaps.pickle', 'wb') as f:
    pickle.dump(gaps, f)

# %%
# load gaps from file
with open('gaps.pickle', 'rb') as f:
    gaps = pickle.load(f)
# %%

gap_counter = Counter(gaps)
edge_benefits = ox.graph_to_gdfs(graph, nodes=False, edges=True).loc[list(set(gaps))]

benefits = []
counts = []
for idx, data in edge_benefits.iterrows():
    counts.append(gap_counter[idx])
    benefit = data['length'] * gap_counter[idx]
    benefits.append(benefit)
edge_benefits = edge_benefits.assign(benefit=benefits)
edge_benefits = edge_benefits.assign(count=counts)

edge_benefits

# %%

def plot_edge_heatmap(gaps: list[EdgeId], graph: nx.MultiDiGraph, expanded: bool = False, metric: str = 'count'):
    cmap = plt.get_cmap('Reds')

    gap_counter = Counter(gaps)

    if not expanded:
        print(f'number of gaps: {len(gap_counter)}')
        for edge in list(gap_counter.keys()):
            reversed_edge = get_reversed_key(edge)
            if reversed_edge in gap_counter:
                gap_counter[edge] = gap_counter[reversed_edge] + gap_counter[edge]
                gap_counter.pop(reversed_edge)
        print(f'number of gaps after collapsing: {len(gap_counter)}')

    #benefits = gaps['benefit'].values
    #counts = gaps['count'].values
    #plt.scatter(counts, benefits, s=1)
    #plt.xlabel("count of rides on this gap")
    #plt.ylabel("overall benefit")
    #plt.grid()
    #plt.show()

    if expanded:
        gaps_df, _, _ = plot_shifted_graph(graph)
    else:
        gaps_df = plot_graph(graph)

    to_remove_edges = []
    attributes = {
        'count': [], 
        'benefit': [],
        'osmid': [], 
        'length': []
    }
    for idx, _ in tqdm(gaps_df.iterrows(), desc='add attributes to gaps', total=len(gaps_df), unit='gaps'):
        try:
            count = gap_counter[idx]
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
            attributes['osmid'].append(graph.edges[idx].get('osmid', None))
            length = graph.edges[idx].get('length', None)
            attributes['length'].append(length)
            attributes['benefit'].append(length * count)
        except KeyError:
            to_remove_edges.append(idx)
            continue

    gaps_df = gaps_df.drop(to_remove_edges)

    for key, value in attributes.items():
        gaps_df[key] = value

    if metric == 'count':
        max_value = gap_counter.most_common(1)[0][1]
    if metric == 'benefit':
        max_value = max(attributes['benefit'])
    
    colors = []
    for gap, data in gaps_df.iterrows():
        color = matplotlib.colors.to_hex(cmap(data[metric]/max_value))
        colors.append(color)
    gaps_df['color'] = colors
    # only keep columns that are needed
    columns_to_keep = ['geometry', 'line_width']
    columns_to_keep.extend(list(attributes.keys()))

    return gaps_df

plot_edge_heatmap(gaps, graph, expanded=False).to_file('graph.gpkg', layer='gaps', driver='GPKG')

plot_edge_heatmap(gaps, graph, expanded=True).to_file('graph.gpkg', layer='gaps_exanded', driver='GPKG')

plot_edge_heatmap(gaps, graph, expanded=False, metric='benefit').to_file('graph.gpkg', layer='gaps_benefit', driver='GPKG')

plot_edge_heatmap(gaps, graph, expanded=True, metric='benefit').to_file('graph.gpkg', layer='gaps_exanded_benefit', driver='GPKG')

# %%
wg: ig.Graph = ig.Graph.from_networkx(routing_graph)

start = time.time()
ebc = wg.edge_betweenness(directed=True, cutoff=4500, weights="weight")
end = time.time()
print(f'calculated edge betweenness centrality in {end - start} seconds')
# %%
def plot_shifted_graph(graph: nx.MultiDiGraph, plot_original_graph=False, debug_marker=False) -> tuple[GeoDataFrame, GeoDataFrame, GeoDataFrame]:
    debug_marker_df = None

    if debug_marker:
        debug_marker_df = {'osmid': [], 'geometry': [], 'color': [], 'size': [], 'label': []}
    
        for node in graph.nodes:
            debug_marker_df['osmid'].append(graph.nodes[node]['osmid'])
            debug_marker_df['geometry'].append(shapely.Point([graph.nodes[node]['x'], graph.nodes[node]['y']]))
            debug_marker_df['color'].append(matplotlib.colors.to_hex('black'))
            debug_marker_df['size'].append(10)
            debug_marker_df['label'].append(f'{node} original')
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
    edges_df = {'u': [], 'v': [], 'key': [], 'geometry': [], 'color': [], 'line_width': [], 'tooltip': []}
    original_edges_df = {'v': [], 'u': [], 'key': [], 'geometry': [], 'color': [], 'line_width': []}

    for edge in tqdm(graph.edges(data=True), desc='Plotting edges', unit='edges'):
        s, d, data = edge

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
        edges_df['key'].append(0)
        edges_df['geometry'].append(data['shifted_geometry'])
        edges_df['color'].append(matplotlib.colors.to_hex(color))
        edges_df['line_width'].append(0.1)
        edges_df['tooltip'].append(f'''<div style="color:white">
                                        osmid: {data.get('osmid', None)}<br>
                                        edge: {s} -> {d}<br>
                                        geometry: {data['shifted_geometry']}<br>
                                        reversed: {reversed}<br>
                                        slope: {data.get('slope_percentage', None)}<br>
                                        penalty: {data.get('penalty', None)}<br>
                                        length: {data.get('length', None)}<br>
                                        weight: {data.get('weight', None)}<br>
                                    </div>''')

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
#%%
def plot_ebc_gap_heatmap(ebc, graph: nx.MultiDiGraph, expanded: bool = False, metric: str = 'count'):

    if len(ebc) != len(graph.edges):
        raise ValueError(f'length of ebc ({len(ebc)}) does not match length of graph edges ({len(graph.edges)})')

    cmap = plt.get_cmap('Reds')
    gap_counter = Counter()

    for edge, count in tqdm(zip(graph.edges, ebc), desc='count edges', unit='route'):
        edge_osmid = graph.edges[edge].get('osmid', None)
        if type(edge_osmid) == list:
            for osmid in edge_osmid:
                if osmid not in osmids_with_bike_infra and osmid is not None:
                    gap_counter[edge] = count
                    break
        elif type(edge_osmid) == tuple:
            for osmid in get_all_osmids(edge_osmid):
                if osmid not in osmids_with_bike_infra and osmid is not None:
                    gap_counter[edge] = count
                    break
        else:
            if edge_osmid not in osmids_with_bike_infra and edge_osmid is not None:
                gap_counter[edge] = count
    if not expanded:
        print(f'number of gaps: {len(gap_counter)}')
        for edge in list(gap_counter.keys()):
            reversed_edge = get_reversed_key(edge)
            if reversed_edge in gap_counter:
                gap_counter[edge] = gap_counter[reversed_edge] + gap_counter[edge]
                gap_counter.pop(reversed_edge)
        print(f'number of gaps after collapsing: {len(gap_counter)}')


   #edges_to_remove = []
   #for edge, count in zip(graph.edges, ebc):
   #    if expanded:
   #        if count < 10_000_000:
   #            edges_to_remove.append(edge)
   #    else:
   #        if count < 10_000_000:
   #            edges_to_remove.append(edge)

   #graph = graph.copy()
   #for edge in edges_to_remove:
   #    if graph.has_edge(*edge):
   #        graph.remove_edge(*edge)

    if expanded:
        gaps_df, _, _ = plot_shifted_graph(graph)
    else:
        gaps_df = ox.graph_to_gdfs(graph, nodes=False, edges=True)

    to_remove_edges = []
    attributes = {
        'count': [], 
        'benefit': [],
        'osmid': [], 
        'length': []
    }
    for idx, _ in tqdm(gaps_df.iterrows(), desc='add attributes to gaps', total=len(gaps_df), unit='gaps'):
        try:
            count = gap_counter[idx]
            if count == 0:
                to_remove_edges.append(idx)
                continue
            if not expanded:
                try:
                    graph.edges[idx]['turning_angle']
                    to_remove_edges.append(idx)
                    continue
                except KeyError:
                    pass
            attributes['count'].append(count)
            attributes['osmid'].append(graph.edges[idx].get('osmid', None))
            length = graph.edges[idx].get('length', None)
            attributes['length'].append(length)
            attributes['benefit'].append(length * count)
        except KeyError:
            to_remove_edges.append(idx)
            continue

    gaps_df = gaps_df.drop(to_remove_edges)

    for key, value in attributes.items():
        gaps_df[key] = value

    if metric == 'count':
        max_value = gap_counter.most_common(1)[0][1]
    if metric == 'benefit':
        max_value = max(attributes['benefit'])
    
    colors = []
    for gap, data in gaps_df.iterrows():
        color = matplotlib.colors.to_hex(cmap(data[metric]/max_value))
        colors.append(color)
    gaps_df['color'] = colors
    # only keep columns that are needed
    columns_to_keep = ['geometry', 'line_width']
    columns_to_keep.extend(list(attributes.keys()))

    return gaps_df

plot_ebc_gap_heatmap(ebc, routing_graph, expanded=False).to_file('graph.gpkg', layer='gaps_ebc', driver='GPKG')

plot_ebc_gap_heatmap(ebc, routing_graph, expanded=True).to_file('graph.gpkg', layer='gaps_ebc_exanded', driver='GPKG')

#plot_ebc_gap_heatmap(ebc, routing_graph, expanded=False, metric='benefit').to_file('graph.gpkg', layer='gaps_ebc_benefit', driver='GPKG')

#plot_ebc_gap_heatmap(ebc, routing_graph, expanded=True, metric='benefit').to_file('graph.gpkg', layer='gaps_ebc_exanded_benefit', driver='GPKG')

#%%
gap_osmids: dict[int, int] = dict()
for edge, count in zip(graph.edges, ebc):
    if count < 10_000_000:
        continue

    edge_osmid = graph.edges[edge].get('osmid', None)
    if type(edge_osmid) == list:
        for osmid in edge_osmid:
            if osmid not in osmids_with_bike_infra and osmid is not None:
                gap_osmids[osmid] = gap_osmids.get(osmid, 0) + count
    elif type(edge_osmid) == tuple:
        for osmid in get_all_osmids(edge_osmid):
            if osmid not in osmids_with_bike_infra and osmid is not None:
                gap_osmids[osmid] = gap_osmids.get(osmid, 0) + count
    else:
        if edge_osmid not in osmids_with_bike_infra and edge_osmid is not None:
            gap_osmids[edge_osmid] = gap_osmids.get(edge_osmid, 0) + count

gap_osmids

#%%
nbg_graph = ox.graph_from_place(query='Nürnberg', retain_all=True, simplify=False, network_type='all')

nbg_graph = ox.simplification.simplify_graph(nbg_graph, edge_attrs_differ=['osmid'])

#%%
counter = Counter()
for edge in nbg_graph.edges:
    edge_osmid = nbg_graph.edges[edge].get('osmid', None)
    counter[edge_osmid] += 1

counter.most_common(100)
# %%
# plot edge betweenness centrality
edges_with_ebc = sorted([(x,z) for x, z in zip(wg.es, ebc)], key=lambda x: x[1], reverse=False)
edges_with_ebc = [x for x in edges_with_ebc if type(x[0]['osmid']) is list or type(x[0]['osmid']) is int]
counts = [c for e, c in edges_with_ebc]
plt.scatter(range(len(counts)), counts, s=1, c='blue')
plt.ylabel('edge betweenness centrality')
plt.yticks(range(0, int(max(counts)), 10_000_000))
plt.title('edge betweenness centrality of all edges')
plt.grid()
plt.show()

#%%
# get most important edges in the graph. X% of traffic goes over x amount if edges
important_edges = []
percentage_of_traffic = 0.4
sum_of_ebc = sum([c for _, c in edges_with_ebc]) * percentage_of_traffic

for edge, count in reversed(edges_with_ebc):
    sum_of_ebc = sum_of_ebc - count
    if sum_of_ebc >= 0:
        important_edges.append((edge, count))
    else:
        print(f'found {len(important_edges)} important edges with a rest ebc of {sum_of_ebc + count}')
        break

print(f'{percentage_of_traffic * 100}% of traffic goes over {len(important_edges)} edges. That are {len(important_edges) / len(edges_with_ebc) * 100}% of all edges in the graph.')

print(f'minimum edge betweenness centrality of important edges: {min([c for _, c in important_edges])}')

df = list()
for edge, count in important_edges:
    df.append({
        'osmid': edge['osmid'],
        'geometry': edge['geometry'],
        'ebc': count
    })
important_edges_df = GeoDataFrame(df, geometry='geometry')
important_edges_df.to_file('graph.gpkg', layer=f'{percentage_of_traffic * 100}_traffic_edges', driver='GPKG')

# %%
# plot edge betweenness centrality of edges with and without bike infrastructure
osmids = dict()
for edge, count in zip(wg.es, ebc):
    if type(edge['osmid']) is list:
        for osmid in edge['osmid']:
            osmids[osmid] = { 'count': count, 'edge': edge}
    elif type(edge['osmid']) is int:
        osmids[edge['osmid']] = { 'count': count, 'edge': edge}


# sort osmids by count
sorted_osmids = sorted(osmids.items(), key=lambda x: x[1]['count'], reverse=False)

bike_infra_x = []
bike_infra_y = []
not_bike_infra_x = []
not_bike_infra_y = []
for idx, (osmid, data) in enumerate(sorted_osmids):
    if osmid in osmids_with_bike_infra:
        bike_infra_x.append(idx)
        bike_infra_y.append(data['count'])
    else:
        not_bike_infra_x.append(idx)
        not_bike_infra_y.append(data['count'])

fig, axs = plt.subplots(2, sharex=True, sharey=True)

axs[0].set_title('edges with bike infrastructure')
axs[0].scatter(bike_infra_x, bike_infra_y, s=1, c='green')
axs[0].set_ylabel('edge betweenness centrality')

axs[1].set_title('edges without bike infrastructure')
axs[1].scatter(not_bike_infra_x, not_bike_infra_y, s=1, c='red')
axs[1].set_ylabel('edge betweenness centrality')

plt.show()

# %%
# get all crossing connections
crossing_edges = []
counts = []
for edge, count in zip(wg.es, ebc):
    if type(edge['osmid']) is not int and type(edge['osmid']) is not list:
        crossing_edges.append(edge)
        counts.append(count)

crossings = {}
for edge, count in zip(crossing_edges, counts):
    turning_direction = get_turn_direction(float(edge['turning_angle']))
    if crossings.get(turning_direction) is None:
        crossings[turning_direction] = []
    crossings[turning_direction].append(count)

fig = plt.figure()
ax1 = fig.add_subplot(111)

for direction, c in crossings.items():
    if direction == TurnDirection.STRAIGHT:
        color = 'blue'
    elif direction == TurnDirection.LEFT:
        color = 'green'
    elif direction == TurnDirection.RIGHT:
        color = 'red'
    elif direction == TurnDirection.U_TURN:
        color = 'orange'

    ax1.scatter(range(len(c)), sorted(c), c=color, s=1)

plt.legend(['straight', 'left', 'right', 'u-turn'], loc='upper left')
plt.ylabel('edge betweenness centrality')
plt.title('edge betweenness centrality of crossing connections depending of the turning direction')
plt.show()
# %%
# get important turns. turns that are above a ebc of 10_000_000
left_turns = []
for edge, count in zip(wg.es, ebc):
    if type(edge['osmid']) is not int and type(edge['osmid']) is not list and count > 1_000_000:
        if get_turn_direction(float(edge['turning_angle'])) == TurnDirection.LEFT:
            left_turns.append({
                'id': edge.index,
                'geometry': edge['geometry'],
                'ebc': count
            })
left_turns = GeoDataFrame(left_turns)
left_turns.to_file('graph.gpkg', layer='left_turns', driver='GPKG')

# %%
gdf_tmp = ox.graph_to_gdfs(graph, nodes=True, edges=True)
# %%
print(gdf_tmp[1].total_bounds)
print(gdf_tmp[0].total_bounds)  # get bounds of the graph

# %%
# get all edges that are gaps in the bike infrastructure and have a edge betweenness centrality of more than 10_000_000
gap_graph = routing_graph.copy()
edges_to_remove = []
for edge, count in zip(gap_graph.edges(data=True), ebc):
    s, d, data = edge
    if data.get('osmid', None) == None:
        edges_to_remove.append((s, d))
        continue

    if type(data['osmid']) is list:
        for osmid in data['osmid']:
            if not(osmid not in osmids_with_bike_infra and count > 10_000_000):
                edges_to_remove.append((s, d))
    elif type(data['osmid']) is int:
        if not( data['osmid'] not in osmids_with_bike_infra and count > 10_000_000):
            edges_to_remove.append((s, d))

for s, d in edges_to_remove:
    if gap_graph.has_edge(s, d):
        gap_graph.remove_edge(s, d)

gap_graph.graph['crs'] = 'EPSG:4326'
gap_graph
ox.graph_to_gdfs(gap_graph, nodes=False, edges=True).to_file('graph.gpkg', layer='gaps_above_10_000_000', driver='GPKG')

# %%
for igraph_edge, nx_edge in zip(wg.es, routing_graph.edges(data=True)):
    print(igraph_edge)
    print(nx_edge)
    break
# %%
gap_graph.graph['crs'] = 'EPSG:4326'
# %%
26756070
'20946765', '(20946765, 960085578)'

# %%
