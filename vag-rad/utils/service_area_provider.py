import geopandas as gpd
import shapely
from tqdm import tqdm
import osmnx as ox
import networkx as nx
from utils.utils import get_network_coverage, get_unique_lines

class ServiceAreaProvider():
    def __init__(self, coverage_distance: float, buffer_value: float, routing_graph: nx.MultiDiGraph):
        self.coverage_distance = coverage_distance
        self.buffer_value = buffer_value
        self.cache_file_name: str = 'service_areas.gpkg'
        self.cache_layer_name: str = f'distance-{self.coverage_distance}_buffer-{self.buffer_value}'
        self.routing_graph = routing_graph
        try:
            self.service_areas = gpd.read_file(self.cache_file_name, layer=self.cache_layer_name, driver='GPKG').set_index('osmid')
            self.service_areas['service_area'] = self.service_areas['service_area'].apply(lambda x: shapely.from_wkt(x))
        except:
            self.service_areas = self.calculate_service_areas()
            self.service_areas.to_file(self.cache_file_name, layer=self.cache_layer_name, driver='GPKG')
        finally:
            self.service_areas.index = self.service_areas.index.map(int)
    
    def calculate_service_areas(self) -> gpd.GeoDataFrame:
        print(f'calculate the coverage of {len(self.routing_graph.nodes)} nodes')
        reachable_edges = get_network_coverage(self.routing_graph, self.routing_graph, travel_cost=self.coverage_distance)
        reachable_edges.set_index('osmid', inplace=True)
        service_areas = []
        for r in tqdm(reachable_edges['geometry'].values, desc='calculating service areas', unit='node'):
            u = get_unique_lines([r])
            t = gpd.GeoDataFrame(geometry=u, crs=4326).to_crs(25832).buffer(self.buffer_value, cap_style='square').to_crs(4326).union_all()
            service_areas.append(t)

        reachable_edges['service_area'] = service_areas
        return reachable_edges
    
    def get_service_area(self, gap: list[int]) -> tuple[shapely.Polygon, list[shapely.LineString]]:
        reachable_edges = []
        areas = []

        for node in gap:
            try:
                reachable_edges.append(self.service_areas.loc[node]['geometry'])
                areas.append(self.service_areas.loc[node]['service_area'])
            except KeyError:
                raise KeyError(f'node {node} not found in service areas')
        gap_polygon = ox.graph_to_gdfs(self.routing_graph.subgraph(gap), nodes=False, edges=True).to_crs(25832).buffer(self.buffer_value, cap_style='square').to_crs(4326).union_all()
        areas.append(gap_polygon)
        gap_coverage_polygon = shapely.union_all(areas)

        unique_lines = get_unique_lines(reachable_edges)

        return gap_coverage_polygon, unique_lines