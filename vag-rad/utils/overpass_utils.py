import overpy
import shapely

def get_line_from_way(way: overpy.Way) -> shapely.LineString:
    line_nodes = []
    for node in way.nodes:
        line_nodes.append((node.lon, node.lat))
    return shapely.LineString(line_nodes)

def get_line_from_ways(ways: list[overpy.Way]) -> shapely.MultiLineString:
    border_lines = []
    for way in ways:
        border_lines.append(get_line_from_way(way))
    return shapely.MultiLineString(border_lines)

def get_polygon_from_relation(relation: overpy.Relation, result_ways: list[overpy.Way]) -> shapely.Polygon:
    ways: dict[int, overpy.Way] = {w.id: w for w in result_ways}
    relations: dict[int, overpy.RelationWay] = {}
    members = relation.members
    if type(members) is list and len(members) > 0:
        for member in members:
            relations[member.ref] = member
    else:
        raise ValueError('relation members is not a list')

    shell_way_ids = [w.ref for w in relations.values() if w.role == 'outer' or w.role == None]
    hole_way_ids = [w.ref for w in relations.values() if w.role == 'inner']

    shell_ways = [ways[w_id] for w_id in shell_way_ids if w_id in ways]
    hole_ways = [ways[w_id] for w_id in hole_way_ids if w_id in ways]

    shell = get_line_from_ways(shell_ways)
    holes = get_line_from_ways(hole_ways)

    outer_polygon = shapely.polygonize([shell])
    inner_polygon = shapely.polygonize([holes])

    return shapely.difference(shapely.MultiPolygon(outer_polygon), shapely.MultiPolygon(inner_polygon))

def get_polygon_from_result(result: overpy.Result) -> shapely.MultiPolygon:
    ways: dict[int, overpy.Way] = {w.id: w for w in result.ways}

    polygons = []
    for relation in result.relations:
        try:
            polygon = get_polygon_from_relation(relation, result.ways)
            polygons.append(polygon)
        except Exception as e:
            print(f'error processing relation {relation.id}: {e}')

    # remove ways that are part of a relation
    for relation in result.relations:
        members = relation.members
        if type(members) is list and len(members) > 0:
            for member in members:
                if member.role == 'outer' or member.role == None or member.role == 'inner':
                    ways.pop(member.ref, None)

    # the remaining ways are polygons without holes
    for way in ways.values():
        border = get_line_from_way(way)
        polygons.append(shapely.Polygon(border))
    
    return shapely.union_all(polygons)

def fetch_city_polygon(city_name: str, api: overpy.Overpass = overpy.Overpass(url='https://maps.mail.ru/osm/tools/overpass/api/interpreter')) -> shapely.MultiPolygon:
    result = api.query(f"""
                        (
                            relation[place="city"][name="{city_name}"];
                        );
                        out body;
                        >;
                        out skel qt;
                    """)
    if result.ways is None or len(result.ways) == 0:
        raise ValueError(f'No area found for {city_name}')
    else:
        return get_polygon_from_result(result)