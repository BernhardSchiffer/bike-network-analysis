import time

import geopandas as gpd
import networkx as nx
import osmnx as ox
import shapely
from tqdm import tqdm

from utils.qgis_utils import get_network_coverage
from utils.utils import get_unique_lines


class ServiceAreaProvider():
    def __init__(self, coverage_distance: int, buffer_value: float, routing_graph: nx.MultiDiGraph):
        self.coverage_distance = coverage_distance
        self.buffer_value = buffer_value
        self.cache_file_name: str = 'service_areas.gpkg'
        self.cache_edge_layer_name: str = f'distance-{self.coverage_distance}'
        self.cache_area_layer_name: str = f'distance-{self.coverage_distance}_buffer-{self.buffer_value}'
        self.reachable_edges_key: str = 'reachable_edges'
        self.service_area_key: str = 'service_area'
        self.routing_graph = routing_graph
        self.service_areas: gpd.GeoDataFrame = self.initialize_dataframe()
        try:
            self.service_areas = self.service_areas.merge(self.load_reachable_edges(), on='osmid', how='left')
            self.service_areas = self.service_areas.set_geometry(self.reachable_edges_key)
        except FileNotFoundError:
            self.service_areas = self.service_areas.merge(self.compute_reachable_edges(), on='osmid', how='left')
            self.service_areas = self.service_areas.set_geometry(self.reachable_edges_key)
            self.save_reachable_edges()

        try:
            self.service_areas = self.service_areas.merge(self.load_service_areas(), on='osmid', how='left')
        except FileNotFoundError:
            self.service_areas = self.service_areas.merge(self.compute_service_areas(), on='osmid', how='left')
            self.save_service_areas()

    def initialize_dataframe(self):
        osmids = []
        lat = []
        lon = []

        for node, data in self.routing_graph.nodes(data=True):
            osmids.append(node)
            lat.append(data['y'])
            lon.append(data['x'])
        return gpd.GeoDataFrame({'osmid': osmids, 'lat': lat, 'lon': lon}).set_index('osmid')

    def load_reachable_edges(self) -> gpd.GeoSeries:
        try:
            reachable_edges = gpd.read_file(self.cache_file_name, layer=self.cache_edge_layer_name, driver='GPKG').set_index('osmid').rename_geometry(self.reachable_edges_key)
            return reachable_edges[self.reachable_edges_key]
        except:
            raise FileNotFoundError(f'File {self.cache_file_name} with layer distance-{self.coverage_distance} not found.')
        
    def save_reachable_edges(self):
        df = self.service_areas[['lat','lon',self.reachable_edges_key]]
        df.set_geometry(self.reachable_edges_key).to_file(filename=self.cache_file_name, layer=self.cache_edge_layer_name, driver='GPKG')

    def load_service_areas(self) -> gpd.GeoSeries:
        try:
            service_areas = gpd.read_file(self.cache_file_name, layer=self.cache_area_layer_name, driver='GPKG').set_index('osmid').rename_geometry(self.service_area_key)
            return service_areas[self.service_area_key]
        except:
            raise FileNotFoundError(f'File {self.cache_file_name} with layer buffer-{self.coverage_distance} not found.')

    def save_service_areas(self):
        df = self.service_areas[['lat','lon',self.service_area_key]]
        df.set_geometry(self.service_area_key).to_file(filename=self.cache_file_name, layer=self.cache_area_layer_name, driver='GPKG')
    
    def compute_reachable_edges(self) -> gpd.GeoSeries:
        print(f'calculate the coverage of {len(self.routing_graph.nodes)} nodes')
        start_time = time.time()
        reachable_edges = get_network_coverage(self.routing_graph, self.routing_graph, travel_cost=self.coverage_distance)
        print(f'calculation took {time.time() - start_time:.2f} seconds')
        reachable_edges = reachable_edges.set_index('osmid').rename_geometry(self.reachable_edges_key)
        
        return reachable_edges[self.reachable_edges_key]
    
    def compute_service_areas(self) -> gpd.GeoSeries:
        service_areas = []
        for r in tqdm(self.service_areas[self.reachable_edges_key].values, desc='calculating service areas', unit='node'):
            u = get_unique_lines([r])
            t = gpd.GeoDataFrame(geometry=u, crs=4326).to_crs(25832).buffer(self.buffer_value, cap_style='square').to_crs(4326).union_all()
            service_areas.append(t)

        return gpd.GeoSeries(service_areas, index=self.service_areas.index, crs=4326, name=self.service_area_key)
    
    def get_service_area(self, gap: list[int]) -> tuple[shapely.Polygon, list[shapely.LineString]]:
        reachable_edges = []
        areas = []

        for node in gap:
            try:
                reachable_edges.append(self.service_areas.loc[node][self.reachable_edges_key])
                areas.append(self.service_areas.loc[node][self.service_area_key])
            except KeyError:
                raise KeyError(f'node {node} not found in service areas')
        gap_polygon = ox.graph_to_gdfs(self.routing_graph.subgraph(gap), nodes=False, edges=True).to_crs(25832).buffer(self.buffer_value, cap_style='square').to_crs(4326).union_all()
        areas.append(gap_polygon)
        gap_coverage_polygon = shapely.union_all(areas)

        unique_lines = get_unique_lines(reachable_edges)

        return gap_coverage_polygon, unique_lines