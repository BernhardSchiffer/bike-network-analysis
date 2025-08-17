import networkx as nx
import osmnx as ox
import shapely
from shapely.geometry import LineString
from tqdm import tqdm
from pyproj import Transformer
import rasterio
import pickle
import osmium
from utils.polygon_filter import PolygonFilter
import os
import pandas as pd
import math

def get_edge_by_osmid(graph: nx.MultiDiGraph, osmid: int) -> tuple[int, int, int]:
    for edge in graph.edges(data=True, keys=True):
        s, d, key, data = edge
        if data.get('osmid', None) == osmid:
            return s, d, key
    raise Exception(f'Edge with osmid {osmid} not found in graph')

def get_angle_between_edges(e1: LineString, e2: LineString):
    # calculate bearing of edges
    e1_start = e1.coords[-2]
    e1_dest = e1.coords[-1]
    e1_bearing = ox.bearing.calculate_bearing(e1_start[1], e1_start[0], e1_dest[1], e1_dest[0])
    e2_start = e2.coords[0]
    e2_dest = e2.coords[1]
    e2_bearing = ox.bearing.calculate_bearing(e2_start[1], e2_start[0], e2_dest[1], e2_dest[0])

    bearing_diff = e2_bearing - e1_bearing
    # normalize to -180, 180
    # left turns are negative, right turns are positive
    return (bearing_diff+180)%360-180

class TurnDirection:
    LEFT = -1
    STRAIGHT = 0
    RIGHT = 1
    U_TURN = 2

def get_turn_direction(turn_angle: float) -> TurnDirection:
    if turn_angle < -160:
        return TurnDirection.U_TURN
    elif turn_angle >= -160 and turn_angle < -45:
        return TurnDirection.LEFT
    elif turn_angle >= -45 and turn_angle < 45:
        return TurnDirection.STRAIGHT
    elif turn_angle >= 45 and turn_angle < 160:
        return TurnDirection.RIGHT
    elif turn_angle >= 160:
        return TurnDirection.U_TURN

def get_turn_penalty(turn_angle: float) -> float:
    turn_direction = get_turn_direction(turn_angle)
    if turn_direction == TurnDirection.STRAIGHT:
        return 1.00001
    elif turn_direction == TurnDirection.LEFT:
        return 1.08
    elif turn_direction == TurnDirection.RIGHT:
        return 1.04
    elif turn_direction == TurnDirection.U_TURN:
        return 1.00001

def split_nodes(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    edge_lookup = ox.graph_to_gdfs(graph, nodes=False, edges=True)

    # save old edge keys
    old_edge_keys: dict[tuple[int, int, int], dict[str, float]] = {}
    for u, v, k in graph.edges(keys=True):
        old_edge_keys[u, v, k] = {'old_edge_key': (u, v, k)}
    nx.set_edge_attributes(graph, old_edge_keys)

    for node_id, node_data in tqdm([x for x in graph.nodes(data=True)], desc='splitting crossing nodes', total=len(graph.nodes), unit='nodes'):
        in_edges = graph.in_edges(node_id, data=True, keys=True)
        out_edges = graph.out_edges(node_id, data=True, keys=True)

        in_osm_ids = [e[3].get("osmid") for e in in_edges]
        out_osm_ids = [e[3].get("osmid") for e in out_edges]
        osmids = set()
        # map lists in list to tuple
        in_osm_ids = [tuple(i) if type(i) == list else i for i in in_osm_ids]
        out_osm_ids = [tuple(i) if type(i) == list else i for i in out_osm_ids]
        osmids.update(out_osm_ids)
        osmids.update(in_osm_ids)

        # only split nodes with more than one in and out edge
        if len(in_edges) <= 0 or len(out_edges) <= 0:
            continue

        # create new nodes for each out edge
        out_nodes = []
        for out_edge_start, out_edge_dest, out_edge_key, out_edge_data in out_edges:
            graph.add_nodes_from([ ((out_edge_start, out_edge_dest, out_edge_key), node_data) ])
            out_nodes.append((out_edge_start, out_edge_dest, out_edge_key))
            graph.add_edges_from([ ((out_edge_start, out_edge_dest, out_edge_key), out_edge_dest, out_edge_data) ])

        # create new edges for each in edge and connect them to the out nodes
        for in_edge_start, in_edge_dest, in_edge_key, in_edge_data in in_edges:
            # create new node for each in edge
            graph.add_nodes_from([((in_edge_start, in_edge_dest, in_edge_key), node_data)])
            # create new edges to each out edge
            for out_node, out_edge in zip(out_nodes, out_edges):
                out_edge_data = out_edge[3]
                # TODO calculate turn angle and set attribute if street is the same or changes
                e1 = edge_lookup.loc[in_edge_data['old_edge_key'][0], in_edge_data['old_edge_key'][1], in_edge_data['old_edge_key'][2]]
                e2 = edge_lookup.loc[out_edge_data['old_edge_key'][0], out_edge_data['old_edge_key'][1], out_edge_data['old_edge_key'][2]]

                # skip if the edge is a u turn
                if shapely.reverse(e1['geometry']) == e2['geometry']:
                    continue

                turning_angle = get_angle_between_edges(e1['geometry'], e2['geometry'])
                penalty = get_turn_penalty(turning_angle)
                weight = 0.6*1000*(penalty - 1.0)
                graph.add_edge((in_edge_start, in_edge_dest, in_edge_key), out_node, length=0.0, weight=weight, penalty=penalty, turning_angle=turning_angle, osmid=(in_edge_data['osmid'], out_edge_data['osmid']))
            # add edge from previous node to new in node
            graph.add_edges_from([(in_edge_start, (in_edge_start, in_edge_dest, in_edge_key), in_edge_data)])
        # remove old node
        graph.remove_node(node_id)

    return graph

def is_tag_available(attribute: str, value: str, tags: dict[str, str]) -> bool:
    if attribute not in tags.keys():
        return False
    else:
        return tags[attribute] == value

def get_slope_penalty(slope: float) -> float:
    if slope < 2:
        return 1.0
    elif slope >= 2 and slope < 4:
        return 1.37
    elif slope >= 4 and slope < 6:
        return 2.2
    elif slope >= 6:
        return 4.24

def has_bike_lane(tags: dict[str, str]) -> bool:
    bike_lane_filter: list[tuple[str, str]] = [
        ("cycleway", "lane"),
        ("cycleway:right", "lane"),
        ("cycleway:left", "lane"),
        ("cycleway:both", "lane")
    ]
    return any(is_tag_available(k, v, tags) for k, v in bike_lane_filter)

def has_bike_path(tags: dict[str, str]) -> bool:
    bike_path_filter: list[tuple[str, str]] = [
        ("bicycle", "designated"),
        ("highway", "cycleway"),
        ("cycleway", "track"),
        ("cycleway:right", "track"),
        ("cycleway:left", "track"),
        ("cycleway:both", "track")
    ]
    return any(is_tag_available(k, v, tags) for k, v in bike_path_filter)

def is_bike_road(tags: dict[str, str]) -> bool:
    bike_road_filter: list[tuple[str, str]] = [
        ('bicycle_road', 'yes')
    ]
    return any(is_tag_available(k, v, tags) for k, v in bike_road_filter)

def is_primary_road(tags: dict[str, str]) -> bool:
    primary_road_filter: list[tuple[str, str]] = [
        ('highway', 'primary')
    ]
    return any(is_tag_available(k, v, tags) for k, v in primary_road_filter)

def is_secondary_road(tags: dict[str, str]) -> bool:
    secondary_road_filter: list[tuple[str, str]] = [
        ('highway', 'secondary')
    ]
    return any(is_tag_available(k, v, tags) for k, v in secondary_road_filter)

def is_tertiary_road(tags: dict[str, str]) -> bool:
    tertiary_road_filter: list[tuple[str, str]] = [
        ('highway', 'tertiary')
    ]
    return any(is_tag_available(k, v, tags) for k, v in tertiary_road_filter)

def is_residential_road(tags: dict[str, str]) -> bool:
    residential_road_filter: list[tuple[str, str]] = [
        ('highway', 'residential')
    ]
    return any(is_tag_available(k, v, tags) for k, v in residential_road_filter)

def is_footpath(tags: dict[str, str]) -> bool:
    is_footpath = tags.get('foot', None) == 'designated'
    is_bikepath = tags.get('bicycle', None) == 'designated'
    return is_footpath and not is_bikepath

class GraphBuilder:
    def __init__(self):
        self.osm_to_geotiff = Transformer.from_crs("EPSG:4326", "EPSG:25832")
        self.geotiff_to_osm = Transformer.from_crs("EPSG:25832", "EPSG:4326")
        self.dat = rasterio.open('./DEM/nuernberg.tif')
        # read all the data from the first band
        self.z = self.dat.read()[0]
        self.load_osm_attributes()

    def load_osm_attributes(self):
        # load osm edge attributes from file
        edge_lookup_filename = 'osm_edges_with_attributes.pickle'

        if os.path.isfile(edge_lookup_filename):
            with open(edge_lookup_filename, 'rb') as f:
                self.edges_osm_data_lookup = pickle.load(f)
        else:
            # create lookup table for all edges in nuernberg with all their osm features
            place = ox.geocode_to_gdf('Nürnberg')

            edges_in_nbg = []

            for w in osmium.FileProcessor('mittelfranken-latest.osm.pbf').with_locations().with_filter(osmium.filter.EmptyTagFilter()).with_filter(osmium.filter.EntityFilter(osmium.osm.WAY)).with_filter(PolygonFilter(place.geometry[0])):
                obj = {}
                obj['osmid'] = w.id
                tags = {}
                for k, v in w.tags:
                    tags[k] = v
                obj['tags'] = tags
                edges_in_nbg.append(obj)

            self.edges_osm_data_lookup = pd.DataFrame(edges_in_nbg).set_index('osmid')

            # write osm edge attributes to file
            file = open(edge_lookup_filename, 'wb')
            pickle.dump(self.edges_osm_data_lookup, file)
            file.close()
    
    def load_osm_restrictions(self):
        node_lookup_filename = 'osm_restrictions.pickle'

        if os.path.isfile(node_lookup_filename):
            with open(node_lookup_filename, 'rb') as f:
                self.restrictions_osm_data_lookup = pickle.load(f)
        else:
            # create lookup table for all edges in nuernberg with all their osm features
            place = ox.geocode_to_gdf('Nürnberg')

            restrictions_in_nbg = []

            for r in osmium.FileProcessor('mittelfranken-latest.osm.pbf').with_locations().with_filter(osmium.filter.EmptyTagFilter()).with_filter(osmium.filter.EntityFilter(osmium.osm.RELATION)).with_filter(PolygonFilter(place.geometry[0])):
                if r.tags.get('type', None) == 'restriction':
                    obj = {}
                    obj['from'] = [m for m in r.members if m.role == 'from']
                    obj['to'] = [m for m in r.members if m.role == 'to']
                    obj['via'] = [m for m in r.members if m.role == 'via']
                    tags = {}
                    for k, v in r.tags:
                        tags[k] = v
                    obj['tags'] = tags
                    restrictions_in_nbg.append(obj)

            self.restrictions_osm_data_lookup = pd.DataFrame(restrictions_in_nbg)

            # write osm edge attributes to file
            file = open(node_lookup_filename, 'wb')
            pickle.dump(self.restrictions_osm_data_lookup, file)
            file.close()

    # add paths where the street is oneway but bikes are allowed in both directions
    def add_paths_for_bikeable_oneways(self, graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
        for u, v, key, data in tqdm(graph.edges(data=True, keys=True), desc='looking for bikeable onewaystreets', total=len(graph.edges), unit='edges'):
            osmid = data['osmid']
            tags = {}
            if type(osmid) == list:
                for id in osmid:
                    try:
                        tag = self.edges_osm_data_lookup.loc[osmid]['tags']
                    except:
                        pass
                    # merge two dictionaries
                    tags = {**tags, **tag}
            else:
                tags = self.edges_osm_data_lookup.loc[osmid]['tags']
            if data['oneway'] == True and (tags.get('oneway:bicycle', None) == 'no' or tags.get('cycleway', None) == 'opposite'):
                # check if the path is also oneway for bikes
                graph.edges[u, v, key]['oneway'] = False
                data_for_reversed_path = data.copy()
                data_for_reversed_path['reversed'] = True
                data_for_reversed_path['oneway'] = False
                try:
                    data_for_reversed_path['geometry'] = LineString(list(data['geometry'].coords)[::-1])
                except:
                    pass
                # add reversed path to graph
                graph.add_edge(v, u, key, **data_for_reversed_path)
        return graph

    def get_elevation(self, lon, lat):
        x, y = self.osm_to_geotiff.transform(lat, lon)
        idx = self.dat.index(x, y, precision=1E-6)
        return self.dat.xy(*idx), self.z[idx]
    
    # set node attributes
    def set_node_attributes(self, graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
        node_attributes: dict[int, dict[str, float]] = {}

        for osmid, data in graph.nodes(data=True):
            lat = data['y']
            lon = data['x']
            node_attributes[osmid]  = {
                'osmid': osmid, 
                'lat': lat, 
                'lon': lon
            }

        nx.set_node_attributes(graph, node_attributes)

        return graph

    def set_node_elevation(self, graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
        elevation_for_nodes: dict[int, dict[str, float]] = {}

        for osmid, data in graph.nodes(data=True):
            lat = data['y']
            lon = data['x']
            _, elevation = self.get_elevation(lon, lat)
            elevation_for_nodes[osmid]  = {
                'elevation': elevation
            }

        nx.set_node_attributes(graph, elevation_for_nodes)

        return graph

    def set_edge_slope(self, graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
        graph = self.set_node_elevation(graph)
        slope_percentages: dict[tuple[int, int], dict[str, float]] = {}

        for u, v, key, e_data in graph.edges(data=True, keys=True):
            start_node = graph.nodes[u]
            dest_node = graph.nodes[v]
            
            hight_diff = dest_node['elevation'] - start_node['elevation']
            slope_percentage = (hight_diff / e_data['length']) * 100

            slope_percentages[u, v, key] = {'slope_percentage': float(slope_percentage)}
            
        nx.set_edge_attributes(graph, slope_percentages)

        return graph    

    # define benefits and penalties for edges according to their osm features
    type filter = tuple[list[function], float]

    bike_lanes_separate: filter = ([has_bike_path], 0.84)
    bike_lanes_on_road: filter = ([has_bike_lane], 0.84)
    bike_boulevard: filter = ([is_bike_road], 0.90)
    primary_road: filter = ([is_primary_road], 8.15)
    secondary_road: filter = ([is_secondary_road], 2.00)
    tertiary_road: filter = ([is_tertiary_road], 1.37)
    residential_road: filter = ([is_residential_road], 1.10)
    footpath: filter = ([is_footpath], 1.2)

    benefit_lookup = [
        bike_lanes_separate,
        bike_lanes_on_road,
        bike_boulevard,
        primary_road,
        secondary_road,
        tertiary_road,
        residential_road,
        footpath
    ]

    def get_weight(self, u, v, data) -> float:
        try:
            osmid = data['osmid']
            if type(osmid) == list:
                for id in osmid:
                    try:
                        tags = self.edges_osm_data_lookup.loc[id, 'tags']
                    except:
                        pass
                # merge two dictionaries
                tags = {**tags, **tags}
            else:
                tags = self.edges_osm_data_lookup.loc[osmid, 'tags']
        except:
            raise ValueError(f'could not find edge with osmid {osmid}')
        
        penalties: float = []

        try:
            penalties.append(get_slope_penalty(data['slope_percentage']))
        except:
            pass

        try:
            penalties.append(get_turn_penalty(data['turning_angle']))
        except:
            pass

        bike_penalties = []
        for filter_functions, benefit in self.benefit_lookup:
            for f in filter_functions:
                if f(tags):
                    bike_penalties.append(benefit)
        if len(bike_penalties) > 0:
            penalties.append(min(bike_penalties))

        if len(penalties) == 0:
            return 1.0
        else:
            return math.prod(penalties)
    
    # calculate edge weights according to their osm features
    def set_edge_weights(self, graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
        weights: dict[tuple[int, int, int], dict[str, float]] = {}
        penalties: dict[tuple[int, int, int], dict[str, float]] = {}
        problematic_osmids = []
        for u, v, key, data in tqdm(graph.edges(data=True, keys=True), desc='calculating edge weights', total=len(graph.edges), unit='edges'):
            if type(data['osmid']) is tuple:
                continue
            try:
                penalty = self.get_weight(u, v, data)
                penalties[u,v,key] = {'penalty': penalty}
                weights[u,v,key] = {'weight': float(data['length'] * penalty)}
            except:
                problematic_osmids.append(data['osmid'])
                penalty = 1.0
                penalties[u,v,key] = {'penalty': penalty}
                weights[u,v,key] = {'weight': float(data['length'] * penalty)}

        if len(problematic_osmids) > 0:
            print(f'found problems with {len(problematic_osmids)} edges: {problematic_osmids}')
            #get_list_of_edges(problematic_osmids, self.edges_osm_data_lookup).explore()

        # add weight attribute to graph
        nx.set_edge_attributes(graph, weights)
        nx.set_edge_attributes(graph, penalties)

        return graph

    def enforce_restrictions(self, graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
        graph = graph.copy()
        # load restrictions
        self.load_osm_restrictions()
        restrictions = self.restrictions_osm_data_lookup

        for _, data in restrictions.iterrows():
            from_way = data['from']
            to_way = data['to']
            via_nodes = data['via']
            tags = data['tags']
            restriction_type = tags.get('restriction', None)
            
            match restriction_type:
                case 'only_straight_on' | 'only_right_turn' | 'only_left_turn' | 'only_u_turn':
                    try:
                        start = get_edge_by_osmid(graph, from_way[0].ref)[1]
                        dest = get_edge_by_osmid(graph, to_way[0].ref)[0]
                    except Exception as e:
                        continue
                    only_edge = (start, dest)

                    # get all edges that are not the only edge
                    edges_to_remove = []
                    for edge in graph.out_edges(start):
                        if edge != only_edge:
                            edges_to_remove.append(edge)
                    for edge in edges_to_remove:
                        try:
                            graph.remove_edge(*edge)
                        except nx.NetworkXError:
                            continue
                case 'no_straight_on' | 'no_right_turn' | 'no_left_turn' | 'no_u_turn' | 'no_entry':
                    try:
                        start = get_edge_by_osmid(graph, from_way[0].ref)[1]
                        dest = get_edge_by_osmid(graph, to_way[0].ref)[0]
                    except Exception as e:
                        continue

                    try:
                        graph.remove_edge(start, dest)
                    except nx.NetworkXError:
                        continue
                case _:
                    continue

        return graph
