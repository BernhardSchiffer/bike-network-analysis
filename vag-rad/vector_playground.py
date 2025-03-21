#%%
import matplotlib.colors
import numpy as np
import shapely
import osmnx as ox
import shapely.geos
from utils.utils import *
import leafmap.foliumap as leafmap
from utils.graph import split_nodes
import math
from pyproj import Geod
from pyproj import Transformer
from tqdm import tqdm
import geopandas as gpd
import matplotlib

# %%
# fetch graph of all streets available by bike
place_name = 'Nürnberg'
# use specific overpass settings
ox.settings.overpass_settings = '[out:json][timeout:{timeout}][date:"2025-03-15T21:21:30Z"]{maxsize}'

bikeable_ways = (
        '["highway"]["area"!~"yes"]["access"!~"private"]'
        '["highway"!~"abandoned|bus_guideway|construction|corridor|elevator|escalator|footway|'
        'motor|no|planned|platform|proposed|raceway|razed|steps"]'
        '["bicycle"!~"no"]["service"!~"private"]'
    )

bikeable_areas = '["area"~"yes"]["bicycle"~"yes"]'

#graph = ox.graph_from_bbox(bbox=(11.112325,49.454484,11.112778,49.454985), simplify=False, retain_all=True, custom_filter=[bikeable_ways, bikeable_areas], truncate_by_edge=True)

graph = ox.graph_from_place(query=place_name, simplify=False, retain_all=True, custom_filter=[bikeable_ways, bikeable_areas], truncate_by_edge=True)

graph = split_nodes(nx.DiGraph(graph))

# %%
def plot_shifted_graph(graph: nx.MultiDiGraph, debug_marker = False, plot_arrow_heads = False, plot_original_graph=False) -> leafmap.Map:
    osm_to_gk = Transformer.from_crs("EPSG:4326", "EPSG:31468")
    gk_to_osm = Transformer.from_crs("EPSG:31468", "EPSG:4326")
    
    graph = graph.copy()
    map = leafmap.Map(location=[49.454446, 11.112065], zoom_start=15, crs='EPSG4326')

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
            s_x, s_y = osm_to_gk.transform(graph.nodes[s]['x'], graph.nodes[s]['y'])
            d_x, d_y = osm_to_gk.transform(graph.nodes[d]['x'], graph.nodes[d]['y'])
            line = shapely.LineString([[s_x, s_y], [d_x, d_y]])
            shifted_line = line.parallel_offset(1, side='right')
            
            if s == node:
                shifted_coords = shifted_line.coords[0]
            else:
                shifted_coords = shifted_line.coords[1]
            
            if data['reversed']:
                reversed_coords.append((shifted_coords[0], shifted_coords[1]))
            else:
                not_reversed_coords.append((shifted_coords[0], shifted_coords[1]))

        x_reversed = np.mean([coord[0] for coord in reversed_coords])
        y_reversed = np.mean([coord[1] for coord in reversed_coords])

        x_not_reversed = np.mean([coord[0] for coord in not_reversed_coords])
        y_not_reversed = np.mean([coord[1] for coord in not_reversed_coords])

        if (len(not_reversed_coords) == 1 or len(reversed_coords) == 1) and len(street_edges) == 1:
            s, d, data = street_edges[0]
            s_x, s_y = osm_to_gk.transform(graph.nodes[s]['x'], graph.nodes[s]['y'])
            d_x, d_y = osm_to_gk.transform(graph.nodes[d]['x'], graph.nodes[d]['y'])
            line = shapely.LineString([[s_x, s_y], [d_x, d_y]])
            line = line.parallel_offset(1, side='right')
            if street_edges[0] in in_edges:
                shifted_point = line.line_interpolate_point(line.length - 2)
            else:
                shifted_point = line.line_interpolate_point(-(line.length - 2))
            
            if len(not_reversed_coords) == 1:
                x_not_reversed = shifted_point.x
                y_not_reversed = shifted_point.y
            else:
                x_reversed = shifted_point.x
                y_reversed = shifted_point.y

        if len(reversed_coords) > 0:
            x_reversed, y_reversed = gk_to_osm.transform(x_reversed, y_reversed)
            graph.nodes[node]['x_reversed'] = x_reversed
            graph.nodes[node]['y_reversed'] = y_reversed
        if len(not_reversed_coords) > 0:
            x_not_reversed, y_not_reversed = gk_to_osm.transform(x_not_reversed, y_not_reversed)
            graph.nodes[node]['x_not_reversed'] = x_not_reversed
            graph.nodes[node]['y_not_reversed'] = y_not_reversed

        if(debug_marker):
            if not math.isnan(y_reversed) and not math.isnan(x_reversed):
                map.add_marker(location=[y_reversed, x_reversed], popup=f'{node}, Reversed')
            if not math.isnan(y_not_reversed) and not math.isnan(x_not_reversed):
                map.add_marker(location=[y_not_reversed, x_not_reversed], popup=f'{node}, Not Reversed')
            map.add_marker(location=[graph.nodes[node]['y'], graph.nodes[node]['x']], popup=f'{node}, Original')

    # plot edges
    edges_df = {'geometry': [], 'color': [], 'line_width': []}
    original_edges_df = {'geometry': [], 'color': [], 'line_width': []}

    for edge in tqdm(graph.edges(data=True), desc='Plotting edges', unit='edges'):
        s, d, data = edge
        try:
            reversed = data['reversed']
        except:
            reversed = None

        if reversed == True:
            color = 'red'
            start = [graph.nodes[s]['y_reversed'], graph.nodes[s]['x_reversed']]
            dest = [graph.nodes[d]['y_reversed'], graph.nodes[d]['x_reversed']]
        if reversed == False:
            color = 'blue'
            start = [graph.nodes[s]['y_not_reversed'], graph.nodes[s]['x_not_reversed']]
            dest = [graph.nodes[d]['y_not_reversed'], graph.nodes[d]['x_not_reversed']]
        # nodes at intersections only have one of those attributes (*_reversed, *_not_reversed) because they are only traversed in one direction
        if reversed is None:
            color = 'green'
            try:
                start = [graph.nodes[s]['y_reversed'], graph.nodes[s]['x_reversed']]
            except:
                start = [graph.nodes[s]['y_not_reversed'], graph.nodes[s]['x_not_reversed']]
            try:
                dest = [graph.nodes[d]['y_reversed'], graph.nodes[d]['x_reversed']]
            except:
                dest = [graph.nodes[d]['y_not_reversed'], graph.nodes[d]['x_not_reversed']]
        
        edges_df['geometry'].append(shapely.LineString([start[::-1], dest[::-1]]))
        edges_df['color'].append(matplotlib.colors.to_hex(color))
        edges_df['line_width'].append(0.1)
        leafmap.folium.PolyLine([start, dest], color=color).add_to(map)

        # plot arrow heads to indicate direction of the edge
        if plot_arrow_heads:
            geodesic = Geod(ellps='WGS84')
            rot = geodesic.inv(dest[1], dest[0], start[1], start[0])[0]+90
            line = shapely.LineString([start, dest])
            arrow_pos = line.line_interpolate_point(line.length - 0.000001)
            arrow_pos = [arrow_pos.coords[0][0], arrow_pos.coords[0][1]]
            leafmap.folium.RegularPolygonMarker(location=arrow_pos, color=color, fill=True, fill_color=color, fill_opacity=1, number_of_sides=3, rotation=rot, radius=5).add_to(map)

        # plot original edge
        if plot_original_graph:
            start = [graph.nodes[s]['y'], graph.nodes[s]['x']]
            dest = [graph.nodes[d]['y'], graph.nodes[d]['x']]
            leafmap.folium.PolyLine([start, dest], color='black').add_to(map)
            original_edges_df['geometry'].append(shapely.LineString([start[::-1], dest[::-1]]))
            original_edges_df['color'].append(matplotlib.colors.to_hex('black'))
            original_edges_df['line_width'].append(0.1)
    
    edges_df = gpd.GeoDataFrame(edges_df, crs='EPSG:4326')
    original_edges_df = gpd.GeoDataFrame(original_edges_df, crs='EPSG:4326')

    if len(edges_df) > 0:
        edges_df.to_file('shifted_graph.gpkg', layer='shifted_edges', driver='GPKG')
    if len(original_edges_df) > 0:
        original_edges_df.to_file('shifted_graph.gpkg', layer='original_edges', driver='GPKG')

plot_shifted_graph(graph, plot_original_graph=True, plot_arrow_heads=False, debug_marker=False)#.save('shifted_graph.html')
# %%