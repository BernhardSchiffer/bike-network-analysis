import networkx as nx
import osmnx as ox
from shapely.geometry import LineString
from tqdm import tqdm

def get_angle_between_edges(e1: LineString, e2: LineString):
    # calculate bearing of edges
    e1_start = e1.coords[0]
    e1_dest = e1.coords[1]
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
    if turn_angle < -135:
        return TurnDirection.U_TURN
    elif turn_angle >= -135 and turn_angle < -45:
        return TurnDirection.LEFT
    elif turn_angle >= -45 and turn_angle < 45:
        return TurnDirection.STRAIGHT
    elif turn_angle >= 45 and turn_angle < 135:
        return TurnDirection.RIGHT
    elif turn_angle >= 135:
        return TurnDirection.U_TURN

def get_turn_penalty(turn_angle: float) -> float:
    turn_direction = get_turn_direction(turn_angle)
    if turn_direction == TurnDirection.STRAIGHT:
        return 1.0001
    elif turn_direction == TurnDirection.LEFT:
        return 1.04
    elif turn_direction == TurnDirection.RIGHT:
        return 1.04
    elif turn_direction == TurnDirection.U_TURN:
        return 1.0001

def split_nodes(graph: nx.DiGraph) -> nx.DiGraph:
    edge_lookup = ox.graph_to_gdfs(nx.MultiDiGraph(graph), nodes=False, edges=True)

    # save old edge keys
    old_edge_keys: dict[tuple[int, int], dict[str, float]] = {}
    for u, v in graph.edges():
        old_edge_keys[u, v] = {'old_edge_key': (u, v)}
    nx.set_edge_attributes(graph, old_edge_keys)

    for node_id, node_data in tqdm([x for x in graph.nodes(data=True)], desc='splitting crossing nodes', total=len(graph.nodes), unit='nodes'):
        in_edges = graph.in_edges(node_id, data=True)
        out_edges = graph.out_edges(node_id, data=True)

        in_osm_ids = [e[2].get("osmid") for e in in_edges]
        out_osm_ids = [e[2].get("osmid") for e in out_edges]
        osmids = set()
        osmids.update(out_osm_ids)
        osmids.update(in_osm_ids)

        # only split nodes with more than one in and out edge and only if they are not the same street
        if len(in_edges) <= 0 or len(out_edges) <= 0 or (len(osmids) == 1):
            continue

        # create new nodes for each out edge
        out_nodes = []
        for o_s, o_d, o_data in out_edges:
            graph.add_nodes_from([((o_s, o_d), node_data)])
            out_nodes.append((o_s, o_d))
            graph.add_edges_from([((o_s, o_d), (o_s, o_d)[1], o_data)])

        # create new edges for each in edge and connect them to the out nodes
        for in_edge_start, in_edge_dest, in_edge_data in in_edges:
            # create new node for each in edge
            graph.add_nodes_from([((in_edge_start, in_edge_dest), node_data)])
            # create new edges to each out edge
            for out_node, out_edge in zip(out_nodes, out_edges):
                out_edge_data = out_edge[2]
                # TODO calculate turn angle and set attribute if street is the same or changes
                e1 = edge_lookup.loc[in_edge_data['old_edge_key'][0], in_edge_data['old_edge_key'][1], 0]
                e2 = edge_lookup.loc[out_edge_data['old_edge_key'][0], out_edge_data['old_edge_key'][1], 0]
                turning_angle = get_angle_between_edges(e1['geometry'], e2['geometry'])
                weight = get_turn_penalty(turning_angle) - 1.0
                length = float(e1['length'] * weight)
                graph.add_edge((in_edge_start, in_edge_dest), out_node, length=length, turning_angle=turning_angle)
            # add edge from previous node to new in node
            graph.add_edges_from([((in_edge_start, in_edge_dest)[0], (in_edge_start, in_edge_dest), in_edge_data)])
        # remove old node
        graph.remove_node(node_id)

    return graph