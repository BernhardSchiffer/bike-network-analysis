import os
import pickle
from typing import Callable

import geopandas as gpd
import networkx as nx
import osmium
import osmnx as ox
import pandas as pd
import shapely
from osmium.filter import EmptyTagFilter, EntityFilter
from osmium.osm import RELATION, WAY
from osmnx.bearing import calculate_bearing
from shapely.geometry import LineString
from tqdm import tqdm

from utils.elevation_provider import DEMElevationProvider
from utils.graph_types import LEFT, RIGHT, STRAIGHT, U_TURN, EdgeId, TurnDirection
from utils.polygon_filter import PolygonFilter


def get_edge_by_osmid(graph: nx.MultiDiGraph, osmid) -> EdgeId:
    for edge in graph.edges(data=True, keys=True):
        s, d, key, data = edge
        if data.get('osmid', None) == osmid:
            return s, d, key
    raise Exception(f'Edge with osmid {osmid} not found in graph')

def get_edge_by_osmid_indexed(lookup: gpd.GeoDataFrame, osmid: str) -> EdgeId:
    try:
        result = lookup.loc[osmid]
    except KeyError:
        raise KeyError(f'Edge with osmid {osmid} not found in lookup')

    if type(result) is gpd.GeoDataFrame or type(result) is pd.DataFrame:
        raise Exception(f'Multiple edges with osmid {osmid} found in lookup')
    if type(result) is gpd.GeoSeries or type(result) is pd.Series:
        return tuple(result[['u', 'v', 'key']].values)

def get_angle_between_edges(e1: LineString, e2: LineString):
    # calculate bearing of edges
    e1_start = e1.coords[-2]
    e1_dest = e1.coords[-1]
    e1_bearing = calculate_bearing(e1_start[1], e1_start[0], e1_dest[1], e1_dest[0])
    e2_start = e2.coords[0]
    e2_dest = e2.coords[1]
    e2_bearing = calculate_bearing(e2_start[1], e2_start[0], e2_dest[1], e2_dest[0])

    bearing_diff = e2_bearing - e1_bearing
    # normalize to -180, 180
    # left turns are negative, right turns are positive
    return (bearing_diff+180)%360-180

def get_turn_direction(turn_angle: float) -> TurnDirection:
    if turn_angle < -60:
        return LEFT
    elif turn_angle >= -60 and turn_angle <= 60:
        return STRAIGHT
    elif turn_angle > 60:
        return RIGHT
    else:
        raise ValueError(f'Invalid turn angle: {turn_angle}')

def get_turn_penalty(turn_angle: float) -> float:
    turn_direction = get_turn_direction(turn_angle)
    if turn_direction == STRAIGHT:
        return 0.00001
    elif turn_direction == LEFT:
        return 423
    elif turn_direction == RIGHT:
        return 221
    else:
        raise ValueError(f'Invalid turn direction: {turn_direction}')

def split_nodes(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    edge_lookup = ox.graph_to_gdfs(graph, nodes=False, edges=True)

    # save old edge keys
    old_edge_keys: dict[EdgeId, dict[str, EdgeId]] = {}
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
        in_osm_ids = [tuple(i) if type(i) is list else i for i in in_osm_ids]
        out_osm_ids = [tuple(i) if type(i) is list else i for i in out_osm_ids]
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
                weight = penalty
                graph.add_edge((in_edge_start, in_edge_dest, in_edge_key), out_node, length=0.0, weight=weight, penalty=penalty, turning_angle=turning_angle, osmid=(in_edge_data['osmid'], out_edge_data['osmid']))
            # add edge from previous node to new in node
            graph.add_edges_from([(in_edge_start, (in_edge_start, in_edge_dest, in_edge_key), in_edge_data)])
        # remove old node
        graph.remove_node(node_id)

    return graph

def get_slope_penalty(slope: float) -> float:
    if slope < 2:
        return 0.0
    elif slope >= 2 and slope < 4:
        return 0.371
    elif slope >= 4 and slope < 6:
        return 1.203
    elif slope >= 6:
        return 3.239
    else:
        raise ValueError(f'Invalid slope value: {slope}')
    
type Forward = 'Forward'
type Backward = 'Backward'
type StreetDirection = Forward | Backward

type OsmTags = dict[str, str]
type StreetFeatureFilter = Callable[[OsmTags, StreetDirection], bool]
type RouteChoice = tuple[StreetFeatureFilter, float]

def is_tag_available(attribute: str, value: str, tags: OsmTags) -> bool:
    if attribute not in tags.keys():
        return False
    else:
        return tags[attribute] == value

def has_bike_lane(tags: OsmTags, direction: StreetDirection) -> bool:
    bike_lane_filter: list[tuple[str, str]] = [
        ("cycleway", "lane"),
        ("cycleway:both", "lane")
    ]
    if any(is_tag_available(k, v, tags) for k, v in bike_lane_filter):
        return True
    elif is_tag_available('cycleway:right', 'lane', tags) and direction == Forward:
        return True
    elif is_tag_available('cycleway:left', 'lane', tags) and direction == Backward:
        return True
    else:
        return False

def has_bike_path(tags: OsmTags, direction: StreetDirection) -> bool:
    bike_path_filter: list[tuple[str, str]] = [
        ("bicycle", "designated")
    ]
    return all(is_tag_available(k, v, tags) for k, v in bike_path_filter)

def has_exclusive_bike_path(tags: OsmTags, direction: StreetDirection) -> bool:
    exclusive_bike_path_filter: list[tuple[str, str]] = [
        ("highway", "cycleway"),
        ("bicycle", "designated")
    ]
    return all(is_tag_available(k, v, tags) for k, v in exclusive_bike_path_filter)
    
def has_bike_track(tags: OsmTags, direction: StreetDirection) -> bool:
    bike_track_filter: list[tuple[str, str]] = [
        ("cycleway", "track"),
        ("cycleway:both", "track")
    ]
    if any(is_tag_available(k, v, tags) for k, v in bike_track_filter):
        return True
    elif is_tag_available('cycleway:right', 'track', tags) and direction == Forward:
        return True
    elif is_tag_available('cycleway:left', 'track', tags) and direction == Backward:
        return True
    else:
        return False

def is_bike_road(tags: OsmTags, direction: StreetDirection) -> bool:
    return tags.get('bicycle_road', None) == 'yes'

def is_primary_road(tags: OsmTags, direction: StreetDirection) -> bool:
    return tags.get('highway', None) == 'primary'

def is_secondary_road(tags: OsmTags, direction: StreetDirection) -> bool:
    return tags.get('highway', None) == 'secondary'

def is_tertiary_road(tags: OsmTags, direction: StreetDirection) -> bool:
    return tags.get('highway', None) == 'tertiary'

def is_residential_road(tags: OsmTags, direction: StreetDirection) -> bool:
    return tags.get('highway', None) == 'residential'

def is_bikeable_padestrian_street(tags: OsmTags, direction: StreetDirection) -> bool:
    pedestrian_street_filter: list[tuple[str, str]] = [
        ('highway', 'pedestrian'),
        ('bicycle', 'yes')
    ]
    return all(is_tag_available(k, v, tags) for k, v in pedestrian_street_filter)

def bike_dismount_required(tags: OsmTags, direction: StreetDirection) -> bool:
    return tags.get('bicycle', None) == 'dismount'

def is_segregated(tags: OsmTags, direction: StreetDirection) -> bool:
    return tags.get('segregated', None) == 'yes'

def is_not_segregated(tags: OsmTags, direction: StreetDirection) -> bool:
    return tags.get('segregated', None) == 'no'

def is_shared_bike_and_footpath(tags: OsmTags, direction: StreetDirection) -> bool:
    is_footpath = tags.get('foot', None) == 'designated'
    bike_is_allowed = tags.get('bicycle', None) == 'yes'
    return is_footpath and bike_is_allowed

def is_segregated_bike_and_footpath(tags: OsmTags, direction: StreetDirection) -> bool:
    return is_shared_bike_and_footpath(tags, direction) and is_segregated(tags, direction)

def is_not_segregated_bike_and_footpath(tags: OsmTags, direction: StreetDirection) -> bool:
    return is_shared_bike_and_footpath(tags, direction) and is_not_segregated(tags, direction)

def is_bikeable_sidewalk(tags: OsmTags, direction: StreetDirection) -> bool:
    sidewalk_bicycle_filter: list[tuple[str, str]] = [
        ("foot", "designated"),
        ("sidewalk:both:foot", "designated")
    ]
    bicycle_filter: list[tuple[str, str]] = [
        ("bicycle", "yes"),
        ("sidewalk:both:bicycle", "yes")
    ]
    is_footpath = any(is_tag_available(k, v, tags) for k, v in sidewalk_bicycle_filter)
    is_sidewalk_bikeable = any(is_tag_available(k, v, tags) for k, v in bicycle_filter)
    if is_footpath and is_sidewalk_bikeable:
        return True
    elif is_tag_available('sidewalk:right:foot', 'designated', tags) and is_tag_available('sidewalk:right:bicycle', 'yes', tags) and direction == Forward:
        return True
    elif is_tag_available('sidewalk:left:foot', 'designated', tags) and is_tag_available('sidewalk:left:bicycle', 'yes', tags) and direction == Backward:
        return True
    else:
        return False

# define benefits and penalties for edges according to their osm features
route_choice_model_1: list[RouteChoice] = [
    (has_bike_lane, -0.16),
    (has_bike_path, -0.16),
    (has_exclusive_bike_path, -0.16),
    (has_bike_track, -0.16),
    (is_bike_road, -0.10),
    (is_primary_road, 7.15),
    (is_secondary_road, 1.00),
    (is_tertiary_road, 0.37),
    (is_residential_road, 0.10),
    (is_bikeable_padestrian_street, 0.20),
    (bike_dismount_required, 0.40),
    (is_segregated_bike_and_footpath, 0.10),
    (is_not_segregated_bike_and_footpath, 0.20),
    (is_bikeable_sidewalk, 0.30)
]

def get_lanes(tags: OsmTags, direction: StreetDirection | None, default: int) -> int:
    if direction is None:
        lanes = tags.get('lanes', default)
    elif direction == Forward:
        lanes = tags.get('lanes:forward', default)
    elif direction == Backward:
        lanes = tags.get('lanes:backward', default)
    try:
        return int(lanes)
    except ValueError:
        return default
    
def is_large_road(tags: OsmTags, direction: StreetDirection) -> bool:
    return any(is_tag_available('highway', hw, tags) for hw in ['primary', 'secondary', 'tertiary', 'unclassified']) and (get_lanes(tags, None, default=1) >= 3 or (get_lanes(tags, Forward, default=1) >= 2 or get_lanes(tags, Backward, default=1) >= 2))

def large_road_with_bike_track(tags: OsmTags, direction: StreetDirection) -> bool:
    return is_large_road(tags, direction) and has_bike_track(tags, direction)

def large_road_with_bike_lane(tags: OsmTags, direction: StreetDirection) -> bool:
    return is_large_road(tags, direction) and has_bike_lane(tags, direction)

def large_road_no_bike_infra(tags: OsmTags, direction: StreetDirection) -> bool:
    return is_large_road(tags, direction) and not has_bike_lane(tags, direction) and not has_bike_track(tags, direction)

def is_medium_road(tags: OsmTags, direction: StreetDirection) -> bool:
    return any(is_tag_available('highway', hw, tags) for hw in ['primary', 'secondary', 'tertiary', 'unclassified']) and not get_lanes(tags, None, default=5) >= 3 and not (get_lanes(tags, Forward, default=5) >= 2 or get_lanes(tags, Backward, default=5) >= 2)

def medium_road_with_bike_track(tags: OsmTags, direction: StreetDirection) -> bool:
    return is_medium_road(tags, direction) and has_bike_track(tags, direction)

def medium_road_with_bike_lane(tags: OsmTags, direction: StreetDirection) -> bool:
    return is_medium_road(tags, direction) and has_bike_lane(tags, direction)

def medium_road_no_bike_infra(tags: OsmTags, direction: StreetDirection) -> bool:
    return is_medium_road(tags, direction) and not has_bike_lane(tags, direction) and not has_bike_track(tags, direction)

def residential_road_with_bike_track(tags: OsmTags, direction: StreetDirection) -> bool:
    return is_residential_road(tags, direction) and has_bike_track(tags, direction)

def residential_road_with_bike_lane(tags: OsmTags, direction: StreetDirection) -> bool:
    return is_residential_road(tags, direction) and has_bike_lane(tags, direction)

def residential_road_no_bike_infra(tags: OsmTags, direction: StreetDirection) -> bool:
    return is_residential_road(tags, direction) and not has_bike_lane(tags, direction) and not has_bike_track(tags, direction)

def is_shared_path(tags: OsmTags, direction: StreetDirection) -> bool:
    return tags.get('highway', None) in ['path', 'track', 'service']

def is_wrong_way(tags: OsmTags, direction: StreetDirection) -> bool:
    if tags.get('oneway', None) == 'yes' and direction == Backward:
        return True
    else:
        return False

def has_gravel(tags: OsmTags, direction: StreetDirection) -> bool:
    return tags.get('surface', None) == 'gravel'

def has_cobblestone(tags: OsmTags, direction: StreetDirection) -> bool:
    return tags.get('surface', None) == 'cobblestone'

def is_padestrian_zone(tags: OsmTags, direction: StreetDirection) -> bool:
    return tags.get('highway', None) == 'pedestrian'

def is_cycleway(tags: OsmTags, direction: StreetDirection) -> bool:
    return tags.get('highway', None) == 'cycleway'

def is_footway(tags: OsmTags, direction: StreetDirection) -> bool:
    return tags.get('highway', None) == 'footway'

route_choice_model_2: list[RouteChoice] = [
    (medium_road_with_bike_track, 0.0),
    (medium_road_with_bike_lane, 0.050),
    (medium_road_no_bike_infra, 0.113),
    (large_road_with_bike_track, -0.016),
    (large_road_with_bike_lane, 0.289),
    (large_road_no_bike_infra, 0.230),
    (residential_road_with_bike_track, 0.090),
    (residential_road_with_bike_lane, -0.085),
    (residential_road_no_bike_infra, 0.174),
    (is_shared_path, 0.156),
    (is_wrong_way, 0.506),
    (has_gravel, 0.130),
    (has_cobblestone, 0.271),
    (is_padestrian_zone, 0.368),
    (is_cycleway, -0.038),
    (is_footway, 0.506),
]

class GraphBuilder:
    def __init__(self, area: shapely.Polygon | shapely.MultiPolygon, route_choices: list[RouteChoice]):
        self.area = area
        self.osm_data_dir = 'osm_data'
        self.osm_data_file = f'{self.osm_data_dir}/bayern-latest.osm.pbf'
        self.elevation_provider = DEMElevationProvider()
        self.load_osm_attributes(area)
        self.route_choices = route_choices

    def load_osm_attributes(self, area: shapely.Polygon | shapely.MultiPolygon):
        # load osm edge attributes from file
        edge_lookup_filename = f'{self.osm_data_dir}/osm_edges_with_attributes.pickle'

        if os.path.isfile(edge_lookup_filename):
            with open(edge_lookup_filename, 'rb') as f:
                self.edges_osm_data_lookup = pickle.load(f)
        else:
            # create lookup table for all edges in area with all their osm features
            edges_in_area = []

            for w in osmium.FileProcessor(self.osm_data_file).with_locations().with_filter(EmptyTagFilter()).with_filter(EntityFilter(WAY)).with_filter(PolygonFilter(area)):
                obj = {}
                obj['osmid'] = w.id
                tags = {}
                for k, v in w.tags:
                    tags[k] = v
                obj['tags'] = tags
                edges_in_area.append(obj)

            self.edges_osm_data_lookup = pd.DataFrame(edges_in_area).set_index('osmid')

            # write osm edge attributes to file
            file = open(edge_lookup_filename, 'wb')
            pickle.dump(self.edges_osm_data_lookup, file)
            file.close()
    
    def load_osm_restrictions(self, area: shapely.Polygon | shapely.MultiPolygon):
        node_lookup_filename = f'{self.osm_data_dir}/osm_restrictions.pickle'

        if os.path.isfile(node_lookup_filename):
            with open(node_lookup_filename, 'rb') as f:
                self.restrictions_osm_data_lookup = pickle.load(f)
        else:
            # create lookup table for all edges in area with all their osm features
            restrictions_in_area = []

            for r in osmium.FileProcessor(self.osm_data_file).with_locations().with_filter(EmptyTagFilter()).with_filter(EntityFilter(RELATION)):
                if r.tags.get('type', None) == 'restriction':
                    obj = {}
                    obj['from'] = [m for m in r.members if m.role == 'from']
                    obj['to'] = [m for m in r.members if m.role == 'to']
                    obj['via'] = [m for m in r.members if m.role == 'via']
                    tags = {}
                    for k, v in r.tags:
                        tags[k] = v
                    obj['tags'] = tags
                    restrictions_in_area.append(obj)

            self.restrictions_osm_data_lookup = pd.DataFrame(restrictions_in_area)

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
    
    def enforce_oneway_bikepaths(self, graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
        edges_to_remove: list[EdgeId] = []
        for u, v, key, data in tqdm(graph.edges(data=True, keys=True), desc='enforcing oneway bike paths', total=len(graph.edges), unit='edges'):
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
            if tags.get('oneway:bicycle', None) == 'yes' and data.get('reversed', False) == True:
                if graph.has_edge(u, v, key):
                    edges_to_remove.append((u, v, key))
        print(f'removing {len(edges_to_remove)} edges that are oneway for bikes')
        graph.remove_edges_from(edges_to_remove)
        return graph
    
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

        for idx, data in graph.nodes(data=True):
            lat = data['y']
            lon = data['x']
            elevation = self.elevation_provider.get_elevation(lon, lat)
            elevation_for_nodes[idx] = {
                'elevation': elevation
            }

        nx.set_node_attributes(graph, elevation_for_nodes)

        return graph

    def set_edge_slope(self, graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
        graph = self.set_node_elevation(graph)
        slope_percentages: dict[tuple[int, int, int], dict[str, float]] = {}

        for u, v, key, e_data in graph.edges(data=True, keys=True):
            start_node = graph.nodes[u]
            dest_node = graph.nodes[v]
            
            hight_diff = dest_node['elevation'] - start_node['elevation']
            slope_percentage = (hight_diff / e_data['length']) * 100

            slope_percentages[u, v, key] = {'slope_percentage': float(slope_percentage)}
            
        nx.set_edge_attributes(graph, slope_percentages)

        return graph

    def get_weight(self, u, v, data: dict) -> float:
        try:
            osmid = data['osmid']
            streetDirection: StreetDirection
            if not data.get('reversed', False):
                streetDirection = Forward
            else:
                streetDirection = Backward
            if type(osmid) is list:
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
        
        penalties: list[float] = [1.0]

        try:
            penalties.append(get_slope_penalty(data['slope_percentage']))
        except:
            pass

        for filter_function, benefit in self.route_choices:
            if filter_function(tags, streetDirection):
                penalties.append(benefit)
        
        return sum(penalties)
        
    def get_applied_filters(self, u, v, data) -> list[str]:
        try:
            osmid = data['osmid']
            streetDirection: StreetDirection
            if not data.get('reversed', False):
                streetDirection = Forward
            else:
                streetDirection = Backward
            if type(osmid) is list:
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

        applied_filters = []
        for filter_function, benefit in self.route_choices:
            if filter_function(tags, streetDirection):
                applied_filters.append(filter_function.__name__)
        
        return applied_filters
    
    # calculate edge weights according to their osm features
    def set_edge_weights(self, graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
        weights: dict[tuple[int, int, int], dict[str, float]] = {}
        penalties: dict[tuple[int, int, int], dict[str, float]] = {}
        applied_filters: dict[tuple[int, int, int], dict[str, list[str]]] = {}
        problematic_osmids = []
        for u, v, key, data in tqdm(graph.edges(data=True, keys=True), desc='calculating edge weights', total=len(graph.edges), unit='edges'):
            if type(data['osmid']) is tuple:
                # skip edges that are created during node splitting
                # can be used to penalize node attributes later
                continue
            try:
                penalty = self.get_weight(u, v, data)
                penalties[u,v,key] = {'penalty': penalty}
                weights[u,v,key] = {'weight': float(data['length'] * (1.0 + penalty))}
                applied_filters[u,v,key] = {'applied_filters': self.get_applied_filters(u, v, data)}
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
        nx.set_edge_attributes(graph, applied_filters)

        return graph

    def enforce_restrictions(self, graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
        graph = graph.copy()
        # load restrictions
        self.load_osm_restrictions(self.area)
        restrictions = self.restrictions_osm_data_lookup

        edge_osmid_to_key_lookup = ox.graph_to_gdfs(graph, nodes=False, edges=True)
        # parsing osmid to string because dataframe index does not support tuples
        edge_osmid_to_key_lookup['osmid'] = edge_osmid_to_key_lookup['osmid'].apply(lambda x: str(x))
        edge_osmid_to_key_lookup = edge_osmid_to_key_lookup.reset_index().set_index('osmid', drop=True)
        # Ensure it's a GeoDataFrame
        edge_osmid_to_key_lookup = gpd.GeoDataFrame(edge_osmid_to_key_lookup, geometry='geometry')

        for _, data in tqdm(restrictions.iterrows(), desc='enforcing routing restrictions', total=len(restrictions), unit='restrictions'):
            from_way = data['from']
            to_way = data['to']
            via_nodes = data['via']
            tags = data['tags']
            restriction_type = tags.get('restriction', None)

            match restriction_type:
                case 'only_straight_on' | 'only_right_turn' | 'only_left_turn' | 'only_u_turn':
                    try:
                        restricted_edge = get_edge_by_osmid_indexed(edge_osmid_to_key_lookup, str((from_way[0].ref, to_way[0].ref)))
                    except KeyError:
                        continue
                    except (IndexError, Exception) as e:
                        print(f'Error occurred while processing restriction {data}: {e}')
                        continue
                    # get all edges that are not the only edge
                    edges_to_remove = []
                    for edge in graph.out_edges(restricted_edge[0], keys=True):
                        if edge != restricted_edge:
                            edges_to_remove.append(edge)
                    for edge in edges_to_remove:
                        try:
                            graph.remove_edge(*edge)
                        except nx.NetworkXError:
                            continue
                case 'no_straight_on' | 'no_right_turn' | 'no_left_turn' | 'no_u_turn':
                    try:
                        restricted_edge = get_edge_by_osmid_indexed(edge_osmid_to_key_lookup, str((from_way[0].ref, to_way[0].ref)))
                    except KeyError:
                        continue
                    except (IndexError, Exception) as e:
                        print(f'Error occurred while processing restriction {data}: {e}')
                        continue

                    try:
                        graph.remove_edge(*restricted_edge)
                    except nx.NetworkXError:
                        continue
                case _:
                    continue

        return graph
