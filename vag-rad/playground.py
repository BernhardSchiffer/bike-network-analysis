# %%
# imports
import matplotlib.pyplot as plt
import networkx as nx
import shapely
import shapely.ops

# %%
# calculate the cutting point of two lines that have the same direction
node1 = shapely.Point(1, 2)
node2 = shapely.Point(2, 2)
node3 = shapely.Point(3, 2)
node4 = shapely.Point(3, 3)

graph = nx.MultiDiGraph([
    (1, 2, 0, {'geometry': shapely.LineString([node1, node2])}),
    (2, 5, 0),
    (2, 9, 0),
    (3, 4, 0, {'geometry': shapely.LineString([node2, node1])}),
    (5, 6, 0, {'geometry': shapely.LineString([node2, node3])}),
    (7, 8, 0, {'geometry': shapely.LineString([node3, node2])}),
    (8, 9, 0),
    (8, 3, 0),
    (9, 10, 0, {'geometry': shapely.LineString([node2, node4])}),
    (11, 12, 0, {'geometry': shapely.LineString([node4, node2])}),
    (12, 5, 0),
    (12, 3, 0),
])

# set coordinates for nodes
for edge in graph.edges(data=True, keys=True):
    u, v, key, data = edge
    if 'geometry' in data:
        line: shapely.LineString = data['geometry']
        x, y = line.xy
        graph.nodes[u]['x'] = x[0]
        graph.nodes[u]['y'] = y[0]
        graph.nodes[v]['x'] = x[-1]
        graph.nodes[v]['y'] = y[-1]

# plot original and offsetted edges
for edge in graph.edges(data=True, keys=True):
    u, v, key, data = edge
    if 'geometry' not in data:
        continue
    line: shapely.LineString = data['geometry']
    # shift line 1 unit to the left
    shifted_line = line.parallel_offset(0.2, 'left', join_style=2)
    # plot the original and shifted line
    plt.plot(*shifted_line.xy, label=f'Edge {u}->{v} shifted', linestyle='--')
    plt.plot(*line.xy, label=f'Edge {u}->{v} original')

for node in graph.nodes:
    x = graph.nodes[node].get('x', None)
    y = graph.nodes[node].get('y', None)
    if x is not None and y is not None:
        plt.plot(x, y, 'ro')
plt.show()

# shift nodes
node_offset = 0.2
line_offset = 0.2
for node in graph.nodes:
    in_edges = graph.in_edges(node, keys=True, data=True, default=[])
    out_edges = graph.out_edges(node, keys=True, data=True, default=[])
    edges = [*in_edges, *out_edges]

    is_start_node = len(out_edges) <= 1
    is_end_node = len(in_edges) == 1

    if len(edges) < 1:
        continue
    if len(edges) == 1:
        u, v, key, data = edges[0]
        line: shapely.LineString = data.get('geometry', None)
        if line is None:
            continue
        # shift line 1 unit to the left
        shifted_line = line.parallel_offset(line_offset, 'right', join_style=2)
        if len(out_edges) == 1:
            graph.nodes[node]['x_shifted'] = shifted_line.xy[0][0]
            graph.nodes[node]['y_shifted'] = shifted_line.xy[1][0]
        if len(in_edges) == 1:
            graph.nodes[node]['x_shifted'] = shifted_line.xy[0][-1]
            graph.nodes[node]['y_shifted'] = shifted_line.xy[1][-1]
        continue
    if len(edges) > 1:
        in_street_edges = []
        out_street_edges = []
        for u, v, key, data in in_edges:
            if 'geometry' in data:
                in_street_edges.append((u, v, key, data))
            else:
                in_street_edges.append(*graph.in_edges(u, keys=True, data=True, default=[]))
        for u, v, key, data in out_edges:
            if 'geometry' in data:
                out_street_edges.append((u, v, key, data))
            else:
                out_street_edges.append(*graph.out_edges(v, keys=True, data=True, default=[]))

        # shift geometries of in_street_edges
        shifted_lines = []
        for u, v, key, data in in_street_edges:
            line: shapely.LineString = data.get('geometry', None)
            if line is None:
                continue
            # shift line 1 unit to the left
            shifted_line = line.parallel_offset(line_offset, 'right', join_style=2)
            shifted_lines.append(shifted_line)
        in_street_edges = shifted_lines

        shifted_lines = []
        for u, v, key, data in out_street_edges:
            line: shapely.LineString = data.get('geometry', None)
            if line is None:
                continue
            # shift line 1 unit to the left
            shifted_line = line.parallel_offset(line_offset, 'right', join_style=2)
            shifted_lines.append(shifted_line)
        out_street_edges: list[shapely.LineString] = shifted_lines
        
        if is_start_node:
            intersections = out_street_edges[0].intersection(shapely.MultiLineString(in_street_edges))
        else:
            intersections = in_street_edges[0].intersection(shapely.MultiLineString(out_street_edges))

        print(intersections)
        if intersections.is_empty:
            for u, v, key, data in edges:
                line: shapely.LineString = data.get('geometry', None)
                if line is None:
                    continue
                # shift line 1 unit to the left
                shifted_line = line.parallel_offset(line_offset, 'right', join_style=2)
                if is_start_node:
                    shifted_point = shifted_line.line_interpolate_point(node_offset)
                    graph.nodes[node]['x_shifted'] = shifted_point.x
                    graph.nodes[node]['y_shifted'] = shifted_point.y
                if is_end_node:
                    shifted_point = shifted_line.line_interpolate_point(shifted_line.length - node_offset)
                    graph.nodes[node]['x_shifted'] = shifted_point.x
                    graph.nodes[node]['y_shifted'] = shifted_point.y
                break
        else:
            if type(intersections) is shapely.Point:
                if is_start_node:
                    offset = out_street_edges[0].line_locate_point(intersections)
                    # get line segment from intersection to end of out_street_edges[0]
                    edge_length = out_street_edges[0].length
                    point = out_street_edges[0].line_interpolate_point(offset + node_offset)
                    graph.nodes[node]['x_shifted'] = point.x
                    graph.nodes[node]['y_shifted'] = point.y
                else:
                    # get line segment from start of in_street_edges[0] to intersection
                    offset = in_street_edges[0].line_locate_point(intersections)
                    edge_length = in_street_edges[0].length
                    point = in_street_edges[0].line_interpolate_point(offset - node_offset)
                    graph.nodes[node]['x_shifted'] = point.x
                    graph.nodes[node]['y_shifted'] = point.y
            else:
                # take first point
                points = list(intersections.geoms)
                if is_start_node:
                    offsets = []
                    for point in points:
                        offset = out_street_edges[0].line_locate_point(point)
                        offsets.append(offset)
                    offset = max(offsets)
                    point = out_street_edges[0].line_interpolate_point(offset + node_offset)
                    graph.nodes[node]['x_shifted'] = point.x
                    graph.nodes[node]['y_shifted'] = point.y
                else:
                    offsets = []
                    for point in points:
                        offset = in_street_edges[0].line_locate_point(point)
                        offsets.append(offset)
                    offset = min(offsets)
                    edge_length = in_street_edges[0].length
                    point = in_street_edges[0].line_interpolate_point(offset - node_offset)
                    graph.nodes[node]['x_shifted'] = point.x
                    graph.nodes[node]['y_shifted'] = point.y

# shift edges
for edge in graph.edges(data=True, keys=True):
    u, v, key, data = edge
    if 'geometry' not in data:
        origin = shapely.Point([graph.nodes[u]['x_shifted'], graph.nodes[u]['y_shifted']])
        destination = shapely.Point([graph.nodes[v]['x_shifted'], graph.nodes[v]['y_shifted']])
        line = shapely.LineString([origin, destination])
        graph.edges[u, v, key]['shifted_geometry'] = line
    else:
        line: shapely.LineString = data['geometry']
        shifted_line = line.parallel_offset(line_offset, 'right', join_style=2)
        line_coords_start = shapely.Point(graph.nodes[u]['x_shifted'], graph.nodes[u]['y_shifted'])
        line_coords_dest = shapely.Point(graph.nodes[v]['x_shifted'], graph.nodes[v]['y_shifted'])

        origin_offset = shifted_line.line_locate_point(line_coords_start)
        dest_offset = shifted_line.line_locate_point(line_coords_dest)

        # get line segment from origin_offset to dest_offset
        shifted_edge = shapely.ops.substring(shifted_line, origin_offset, dest_offset)

        graph.edges[u, v, key]['shifted_geometry'] = shifted_edge

# plot shifted edges
for edge in graph.edges(data=True, keys=True):
    u, v, key, data = edge
    shifted_line = data['shifted_geometry']
    # plot the original and shifted line
    plt.plot(*shifted_line.xy, label=f'Edge {u}->{v} shifted', linestyle='--')

# plot shifted nodes
for node in graph.nodes:
    x = graph.nodes[node].get('x_shifted', None)
    y = graph.nodes[node].get('y_shifted', None)
    if x is not None and y is not None:
        plt.plot(x, y, 'ro')
plt.show()
# %%
