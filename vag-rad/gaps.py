# %%
# imports
import osmnx as ox
import networkx as nx
import matplotlib
import matplotlib.pyplot as plt
from tqdm import tqdm
from collections import Counter
from  utils.graph_types import *
from utils.utils import *
import pickle
import igraph as ig
import time
import shapely
from geopandas import GeoDataFrame
from utils.graph_builder import get_turn_direction, TurnDirection
import geopandas as gpd
import rasterio

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

bicycle_graph =  ox.io.load_graphml('bicycle_graph.graphml', node_dtypes={'osmid': str}, edge_dtypes={'weight': float, 'osmid': parse_junction_osmid})

# %%
# load calculated routes from file
with open('calculated_routes.pickle', 'rb') as f:
    routes = pickle.load(f)

routes = [r for r in routes if correct_routes(r)]
# %%
# fetch graph of bicycle infrastructure
place_name = 'Nürnberg'
ox.settings.overpass_settings = '[out:json][timeout:{timeout}][date:"2025-08-16T20:21:30Z"]{maxsize}'
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
    result = get_gaps_for_route(route, routing_graph)
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
edge_benefits = ox.graph_to_gdfs(routing_graph, nodes=False, edges=True).loc[list(set(gaps))]

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

plot_edge_heatmap(gaps, routing_graph, expanded=False).to_file('graph.gpkg', layer='gaps', driver='GPKG')

plot_edge_heatmap(gaps, routing_graph, expanded=True).to_file('graph.gpkg', layer='gaps_exanded', driver='GPKG')

plot_edge_heatmap(gaps, routing_graph, expanded=False, metric='benefit').to_file('graph.gpkg', layer='gaps_benefit', driver='GPKG')

plot_edge_heatmap(gaps, routing_graph, expanded=True, metric='benefit').to_file('graph.gpkg', layer='gaps_exanded_benefit', driver='GPKG')

# %%
wg: ig.Graph = ig.Graph.from_networkx(routing_graph)

start = time.time()
ebc = wg.edge_betweenness(directed=True, cutoff=4500, weights="weight")
end = time.time()
print(f'calculated edge betweenness centrality in {end - start} seconds')

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
        gaps_df, _ = plot_shifted_graph(graph)
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

plot_ebc_gap_heatmap(ebc, routing_graph, expanded=False, metric='benefit').to_file('graph.gpkg', layer='gaps_ebc_benefit', driver='GPKG')

plot_ebc_gap_heatmap(ebc, routing_graph, expanded=True, metric='benefit').to_file('graph.gpkg', layer='gaps_ebc_exanded_benefit', driver='GPKG')

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

print(f'{percentage_of_traffic * 100:.2f}% of traffic goes over {len(important_edges)} edges. That are {len(important_edges) / len(edges_with_ebc) * 100:.2f}% of all edges in the graph.')

print(f'minimum edge betweenness centrality of important edges: {min([c for _, c in important_edges]):.0f}')

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
    if type(edge['osmid']) is not int and count > 10_000_000:
        if get_turn_direction(float(edge['turning_angle'])) == TurnDirection.LEFT:
            left_turns.append({
                'id': edge.index,
                'geometry': edge['shifted_geometry'],
                'ebc': count
            })
left_turns = GeoDataFrame(left_turns)
left_turns.to_file('graph.gpkg', layer='left_turns', driver='GPKG')

# %%
# get all edges that are gaps in the bike infrastructure and have a edge betweenness centrality of more than 10_000_000
gap_graph = routing_graph.copy()
edges_to_remove = []
for edge, count in zip(gap_graph.edges(data=True), ebc):
    s, d, data = edge
    if data.get('osmid', None) == None:
        edges_to_remove.append((s, d))
        continue

    if type(data['osmid']) is int:
        if not( data['osmid'] not in osmids_with_bike_infra and count > 10_000_000):
            edges_to_remove.append((s, d))
    else:
        edges_to_remove.append((s, d))

for s, d in edges_to_remove:
    if gap_graph.has_edge(s, d):
        gap_graph.remove_edge(s, d)

gap_graph.graph['crs'] = 'EPSG:4326'
gap_graph
ox.graph_to_gdfs(gap_graph, nodes=False, edges=True).to_file('graph.gpkg', layer='gaps_above_10_000_000', driver='GPKG')

# %%
# map ebc count to bicycle graph to find connected components
max_ebc = 0
min_ebc = 0

for count, edge in zip(ebc, routing_graph.edges(data=True, keys=True)):
    u, v, key, data = edge
    try:
        old_edge_key = routing_graph.edges[u, v, key]['old_edge_key']
    except KeyError:
        continue
    old_u, old_v, old_key = split_tuple(old_edge_key[1:-1])
    bicycle_graph.edges[old_u, old_v, int(old_key)]['count'] = count

    osmid = data.get('osmid', None)
    if osmid is not None and osmid not in osmids_with_bike_infra:
        max_ebc = max(max_ebc, count)
        min_ebc = min(min_ebc, count)

for edge in bicycle_graph.edges(data=True, keys=True):
    u, v, key, data = edge

    osmid = data.get('osmid', None)
    if osmid is not None and osmid not in osmids_with_bike_infra:
        count = data.get('count', 0)
        color = matplotlib.colors.to_hex(plt.get_cmap('Reds')((count - min_ebc) / (max_ebc - min_ebc)))
    else:
        color = 'gray'
    bicycle_graph.edges[u, v, key]['color'] = color

ox.graph_to_gdfs(bicycle_graph, nodes=False, edges=True).to_file('graph.gpkg', layer='bicycle_graph_with_ebc', driver='GPKG')
# %%
# add count of reversed and not reveres edge
max_ebc = 0
min_ebc = 0
undirected_bicycle_graph = bicycle_graph.copy()
for edge in undirected_bicycle_graph.edges(data=True, keys=True):
    u, v, key, data = edge

    reversed_edge = get_reversed_key((u, v, key))
    r_u, r_v, r_key = reversed_edge
    try:
        count = data.get('count', 0) + undirected_bicycle_graph.edges[r_u, r_v, r_key].get('count', 0)
    except KeyError:
        count = data.get('count', 0)

    undirected_bicycle_graph.edges[(u, v, key)]['count'] = count

    osmid = data.get('osmid', None)
    if osmid is not None and osmid not in osmids_with_bike_infra:
        max_ebc = max(max_ebc, count)
        min_ebc = min(min_ebc, count)

# remove directed edges
undirected_bicycle_graph = nx.to_undirected(undirected_bicycle_graph)

# add color
for edge in undirected_bicycle_graph.edges(data=True, keys=True):
    u, v, key, data = edge

    osmid = data.get('osmid', None)
    if osmid is not None and osmid not in osmids_with_bike_infra:
        count = data.get('count', 0)
        color = matplotlib.colors.to_hex(plt.get_cmap('Reds')((count - min_ebc) / (max_ebc - min_ebc)))
    else:
        color = 'gray'
    undirected_bicycle_graph.edges[(u, v, key)]['color'] = color

ox.graph_to_gdfs(undirected_bicycle_graph, nodes=False, edges=True).to_file('graph.gpkg', layer='undirected_bicycle_graph_with_ebc', driver='GPKG')
# %%
gap_graph: nx.MultiGraph = undirected_bicycle_graph.copy()
for edge in undirected_bicycle_graph.edges(data=True, keys=True):
    u, v, key, data = edge

    osmid = data.get('osmid', None)
    count = data.get('count', 0)
    if osmid in osmids_with_bike_infra or count < 10_000_000:
        gap_graph.remove_edge(u, v, key)

# remove isolated nodes
isolated_nodes = list(nx.isolates(gap_graph))
gap_graph.remove_nodes_from(isolated_nodes)

gaps = nx.connected_components(gap_graph)
gaps = list(gaps)
print(f'found {len(gaps)} gaps in the bike infrastructure')

#%%

# get a polygon in the shape of a triangle
bigger_triangle = shapely.Polygon([(0, 0), (1, 0), (0.5, 1)])
bigger_triangle


# get a polygon that cuts the bigger triangle in half
polygon = shapely.Polygon([(0, 0.5), (1, 0.5), (0.5, -0.5)])

difference = shapely.difference(bigger_triangle, polygon)
print(type(difference))
print(difference.area)
print(difference.bounds)
display(difference)
# %%
import pyproj
from shapely.ops import transform
class GapEvaluator:
    def __init__(self):
        self.coverage_distance = 300
        self.buffer_value = 30
        self.protected_bike_infra_polygon = gpd.read_file('protected_bike_infra_coverage.gpkg', layer=f'protected_bike_infra_coverage_{self.buffer_value}').to_crs(4326)['geometry'].values[0]
        self.load_bicycle_routing_graph()
        self.load_population_data()

    def load_bicycle_routing_graph(self):
        routing_graph_edges = gpd.read_file('graph.gpkg', layer='original_graph_edges').to_crs(4326).set_index(['u', 'v', 'key'])
        routing_graph_nodes = gpd.read_file('graph.gpkg', layer='original_graph_nodes').to_crs(4326).set_index('osmid')
        routing_graph_nodes['osmid'] = routing_graph_nodes.index
        self.routing_graph = ox.graph_from_gdfs(routing_graph_nodes, routing_graph_edges)

    def load_population_data(self):
        self.population_src: rasterio.DatasetReader = rasterio.open('population_data/GHS_POP_E2025_GLOBE_R2023A_4326_3ss_V1_0_R4_C20.tif')
        # read all the data from the first band
        self.population_data = self.population_src.read()[0]

    def get_area_coverage(self, graph: nx.Graph) -> tuple[shapely.Polygon, list[shapely.LineString]]:
        reachable_edges = get_network_coverage(self.routing_graph, graph, travel_cost=300)
        
        unique_lines = get_unique_lines(reachable_edges['geometry'].values)

        reachable_area = gpd.GeoSeries(unique_lines, crs=4326).to_crs(25832).buffer(self.buffer_value, cap_style='square').to_crs(4326).union_all()

        graph_polygon = ox.graph_to_gdfs(graph, nodes=False, edges=True).to_crs(25832).buffer(self.buffer_value, cap_style='square').to_crs(4326).union_all()

        graph_polygon = shapely.union_all([reachable_area, graph_polygon])

        return graph_polygon, unique_lines

    # calculate area coverage
    def get_added_area_coverage(self, gap_polygon: shapely.Polygon) -> float:

        epsg_4326 = pyproj.CRS('EPSG:4326')
        epsg_25832 = pyproj.CRS('EPSG:25832')

        project = pyproj.Transformer.from_crs(epsg_4326, epsg_25832, always_xy=True).transform

        added_area: shapely.MultiPolygon | shapely.Polygon = shapely.difference(gap_polygon, self.protected_bike_infra_polygon)
        added_area = transform(project, added_area)

        return added_area.area
    
    def get_added_population(self, gap_polygon: shapely.Polygon) -> float:
        # calculating the population in the difference polygon of gap_polygon and protected_bike_infra_polygon
        added_area: shapely.MultiPolygon | shapely.Polygon = shapely.difference(gap_polygon, self.protected_bike_infra_polygon)

        # calculate population in added area polygon
        bbox_west = added_area.bounds[0]
        bbox_south = added_area.bounds[1]
        bbox_east = added_area.bounds[2]
        bbox_north = added_area.bounds[3]

        row_start ,col_start = self.population_src.index(bbox_west, bbox_north)
        row_end ,col_end = self.population_src.index(bbox_east, bbox_south)

        added_population = 0

        for row in range(row_start, row_end + 1):
            for col in range(col_start, col_end + 1):
                polygon = shapely.Polygon([
                    self.population_src.transform * (col, row),
                    self.population_src.transform * (col, row + 1),
                    self.population_src.transform * (col + 1, row + 1),
                    self.population_src.transform * (col + 1, row)
                ])
                
                intersection = polygon.intersection(added_area)
                if not intersection.is_empty:
                    added_population += intersection.area / polygon.area * self.population_data[row, col]
        
        return added_population

gap_evaluator = GapEvaluator()
#%%

# calculate different metrics for every gap
gaps_df_values = {'gap': [], 'gap_geometry': [], 'additional_coverage': [], 'additional_population_coverage': [], 'length': [], 'benefit': [], 'mean_ebc': [], 'max_ebc': [], 'min_ebc': [], 'vag_rad_usage': [], 'is_connecting_bike_infra': [], 'gap_polygon': [], 'reachable_edges': [], 'geometry': []}

for g in tqdm(gaps[:100], desc='calculating gap metrics', unit='gap'):
    gap = gap_graph.subgraph(g)
    length = 0
    lines = []
    ebc_values = []

    for edge in gap.edges(data=True, keys=True):
        u, v, key, data = edge
        length += data.get('length', 0)
        ebc_values.append(data.get('count', 0))
        line = data.get('geometry', None)
        if line is not None:
            lines.append(line)
    gap_geometry = shapely.MultiLineString(lines)
    max_ebc = max(ebc_values)
    min_ebc = min(ebc_values)
    mean_ebc = sum(ebc_values) / len(ebc_values)

    gaps_df_values['gap'].append(g)
    gaps_df_values['gap_geometry'].append(gap_geometry)
    gap_polygon, reachable_edges = gap_evaluator.get_area_coverage(gap)
    gaps_df_values['gap_polygon'].append(gap_polygon)
    gaps_df_values['reachable_edges'].append(shapely.MultiLineString(reachable_edges))
    gaps_df_values['additional_coverage'].append(gap_evaluator.get_added_area_coverage(gap_polygon))
    gaps_df_values['additional_population_coverage'].append(gap_evaluator.get_added_population(gap_polygon))
    gaps_df_values['length'].append(length)
    gaps_df_values['benefit'].append(length * mean_ebc)
    gaps_df_values['mean_ebc'].append(mean_ebc)
    gaps_df_values['max_ebc'].append(max_ebc)
    gaps_df_values['min_ebc'].append(min_ebc)
    gaps_df_values['vag_rad_usage'].append(None)
    gaps_df_values['is_connecting_bike_infra'].append(None)
    geometry = shapely.GeometryCollection([gap_geometry, gap_polygon, shapely.MultiLineString(reachable_edges)])
    gaps_df_values['geometry'].append(geometry)

gaps_df = gpd.GeoDataFrame(gaps_df_values, geometry='geometry', crs='EPSG:4326')
#%%
gaps_df
# %%
for idx, gap in gaps_df.iterrows():
    gap_gdf = gpd.GeoDataFrame([gap], geometry='geometry', crs='EPSG:4326')
    gap_gdf.to_file('gaps_analysis.gpkg', layer=f'gap_{idx}', driver='GPKG')
# %%
# iterate over gaps and save each gap as a layer in a geopackage
for idx, gap in gaps_df.iterrows():
    gap_gdf = gpd.GeoDataFrame([gap], geometry='gap_geometry', crs='EPSG:4326')
    gap_gdf.to_file('gaps_analysis.gpkg', layer=f'gap_geometry_{idx}', driver='GPKG')
    gap_polygon_gdf = gpd.GeoDataFrame([gap], geometry='gap_polygon', crs='EPSG:4326')
    gap_polygon_gdf.to_file('gaps_analysis.gpkg', layer=f'gap_polygon_{idx}', driver='GPKG')
    reachable_edges_gdf = gpd.GeoDataFrame([gap], geometry='reachable_edges', crs='EPSG:4326')
    reachable_edges_gdf.to_file('gaps_analysis.gpkg', layer=f'reachable_edges_{idx}', driver='GPKG')
# %%
