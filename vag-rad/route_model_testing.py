# %%
import ipyleaflet as ipy
import osmnx as ox
from IPython.display import display
from utils.utils import correct_routes, route_to_edge_ids

# Load the graph from a file or create it as needed
graph = ox.io.load_graphml('expanded_bicycle_graph.graphml', node_dtypes={'osmid': str}, edge_dtypes={'weight': float})

# %%
start_marker = None
end_marker = None
route = None

def handle_observe(value):
    global start_marker
    global end_marker
    global route

    if route is not None:
        m.remove_layer(route)

    if start_marker is not None and end_marker is not None:
        x = start_marker.location[1]
        y = start_marker.location[0]
        starting_node_id = ox.distance.nearest_nodes(graph, [x], [y])
        
        x = end_marker.location[1]
        y = end_marker.location[0]
        finishing_node_id = ox.distance.nearest_nodes(graph, [x], [y])

        r = ox.routing.shortest_path(graph, starting_node_id, finishing_node_id, weight='weight')[0]

        if correct_routes(r):
            positions = []
            edges = route_to_edge_ids(r)
            for idx, edge in enumerate(edges):
                s, d, key = edge
                positions.extend(graph.edges[s, d, key]['geometry'].coords)
            positions = [(lat, lon) for lon, lat in positions]
            print(positions)
            
            route = ipy.Polyline(locations=positions, fill=False)
            m.add(route)

def add_marker_to_map(lat, lon):
    global start_marker
    global end_marker
    if start_marker is None:
        marker = ipy.Marker(location=[lat, lon], draggable=True, icon=ipy.AwesomeIcon(marker_color='green'))
        marker.observe(handle_observe, 'location')
        start_marker = marker
        m.add_layer(marker)
    elif end_marker is None:
        marker = ipy.Marker(location=[lat, lon], draggable=True, icon=ipy.AwesomeIcon(marker_color='red'))
        marker.observe(handle_observe, 'location')
        end_marker = marker
        m.add_layer(marker)
    
    if start_marker is not None and end_marker is not None:
        handle_observe(None)

def handle_map_interaction(**kwargs):
    if kwargs.get('type') == 'click':
        # get the coordinates of the clicked point
        lat = kwargs.get('coordinates')[0]
        lon = kwargs.get('coordinates')[1]
        # add a marker to the map
        add_marker_to_map(lat, lon)

m = ipy.Map(center=(49.451900, 11.076608), zoom=15)

m.on_interaction(handle_map_interaction)

display(m)
# %%
graph.edges