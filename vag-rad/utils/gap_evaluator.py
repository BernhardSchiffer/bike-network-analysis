import rasterio
import geopandas as gpd
import networkx as nx
import osmnx as ox
import shapely
from utils.utils import get_network_coverage, get_unique_lines

class GapEvaluator:
    def __init__(self):
        self.coverage_distance = 300
        self.buffer_value = 30
        self.protected_bike_infra_polygon = gpd.read_file('protected_bike_infra_coverage.gpkg', layer='protected_bike_infra_coverage_30').to_crs(4326)['geometry'].values[0]
        self.load_bicycle_routing_graph()
        self.load_population_data()

    def load_bicycle_routing_graph(self):
        routing_graph_edges = gpd.read_file('graph.gpkg', layer='original_graph_edges').to_crs(4326)
        routing_graph_nodes = gpd.read_file('graph.gpkg', layer='original_graph_nodes').to_crs(4326)
        self.routing_graph = ox.graph_from_gdfs(routing_graph_nodes, routing_graph_edges)

    def load_population_data(self):
        self.population_src: rasterio.DatasetReader = rasterio.open('population_data/GHS_POP_E2025_GLOBE_R2023A_4326_3ss_V1_0_R4_C20.tif')
        # read all the data from the first band
        self.population_data = self.population_src.read()[0]

    def get_area_coverage(self, graph: nx.Graph) -> shapely.Polygon:
        reachable_edges = get_network_coverage(self.routing_graph, graph, distance=300)
        
        unique_lines = get_unique_lines(reachable_edges['geometry'].values)

        reachable_area = gpd.GeoSeries(unique_lines, crs=4326).to_crs(3043).buffer(self.buffer_value, cap_style='square').to_crs(4326).union_all()

        graph_polygon = ox.graph_to_gdfs(graph, nodes=False, edges=True).to_crs(3043).buffer(self.buffer_value, cap_style='square').to_crs(4326).union_all()

        graph_polygon = shapely.union_all([reachable_area, graph_polygon])

        return graph_polygon

    # calculate area coverage
    def get_added_area_coverage(self, gap: nx.Graph) -> float:
        gap_polygon = self.get_area_coverage(gap)

        added_area = shapely.difference(gap_polygon, self.protected_bike_infra_polygon)

        return added_area.area
    
    def get_added_population(self, gap: set) -> float:
        # calculating the population in the difference polygon of gap_polygon and protected_bike_infra_polygon
        gap_polygon = self.get_area_coverage(gap)

        added_area: shapely.MultiPolygon | shapely.Polygon = shapely.difference(gap_polygon, self.protected_bike_infra_polygon)

        # calculate population in added area polygon
        bbox_west = added_area.bounds[0]
        bbox_north = added_area.bounds[1]
        bbox_east = added_area.bounds[2]
        bbox_south = added_area.bounds[3]

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