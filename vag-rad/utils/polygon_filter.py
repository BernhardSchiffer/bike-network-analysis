# osmium filter that checks if node or one of way nodes is in polygon
import shapely


class PolygonFilter:
    def __init__(self, polygon):
        self.polygon = polygon

    def node(self, n):
        is_not_in_place = True
        if n.location.valid() and self.polygon.contains(shapely.Point(n.lon, n.lat)):
            is_not_in_place = False
        return is_not_in_place

    def way(self, w):
        is_not_in_place = True
        for n in w.nodes:
            if n.location.valid() and self.polygon.contains(shapely.Point(n.lon, n.lat)):
                is_not_in_place = False
                break
        return is_not_in_place
