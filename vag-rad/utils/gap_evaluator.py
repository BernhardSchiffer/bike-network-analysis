import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pyproj
import shapely
from shapely.ops import transform
from tqdm import tqdm

from utils.population_provider import PopulationProvider
from utils.service_area_provider import ServiceAreaProvider

type GapPath = list[int]

class Gap:
    def __init__(self, paths: list[GapPath]):
        self.paths: list[GapPath] = paths

    def get_geometry(self, routing_graph: nx.MultiDiGraph) -> shapely.MultiLineString:
        geometry: shapely.MultiLineString = shapely.MultiLineString()
        for path in self.paths:
            lines = []
            g = routing_graph.subgraph(path)
            for u, v, data in g.edges(data=True):
                line = data.get('geometry', None)
                if line is not None:
                    lines.append(line)
            geometry = shapely.union_all([geometry, shapely.MultiLineString(lines)])
        return geometry
    
    def get_graph(self, routing_graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
        gap_graph = routing_graph.subgraph(self.paths[0]).copy()
        for path in self.paths[1:]:
            other_gap_graph = routing_graph.subgraph(path).copy()
            gap_graph = nx.compose(gap_graph, other_gap_graph)
        return gap_graph
    
def merge_gaps(gaps: list[Gap]) -> Gap:
    merged_paths: list[GapPath] = []
    for gap in gaps:
        merged_paths.extend(gap.paths)
    return Gap(merged_paths)

class GapEvaluator:
    def __init__(self, population_provider: PopulationProvider, service_area_provider: ServiceAreaProvider, osmids_with_bike_infra: set[int], osmids_with_protected_bike_infra: set[int]):
        self.populationProvider = population_provider
        self.service_area_provider = service_area_provider
        self.osmids_with_bike_infra = osmids_with_bike_infra
        self.protected_bike_infra_polygon = self.calculate_protected_bike_infra_polygon(osmids_with_protected_bike_infra)
    
    def calculate_protected_bike_infra_polygon(self, osmids_with_protected_bike_infra: set[int]) -> shapely.MultiPolygon | shapely.Polygon:
        protected_bike_infra_graph = self.service_area_provider.routing_graph.copy()

        edges_to_remove = []
        for u, v, key, data in protected_bike_infra_graph.edges(data=True, keys=True):
            osmid = data.get('osmid', None)
            if osmid is None or osmid not in osmids_with_protected_bike_infra:
                edges_to_remove.append((u, v, key))

        protected_bike_infra_graph.remove_edges_from(edges_to_remove)

        protected_bike_infra_graph.remove_nodes_from(list(nx.isolates(protected_bike_infra_graph)))

        reachable_area, _ = self.service_area_provider.get_service_area(protected_bike_infra_graph)

        bike_way_polygon = ox.graph_to_gdfs(protected_bike_infra_graph, nodes=False, edges=True).to_crs(25832).buffer(self.service_area_provider.buffer_value, cap_style='square').to_crs(4326).union_all()

        return shapely.union_all([reachable_area, bike_way_polygon])

    def with_connectedness_metrics(self, value: bool = True) -> None:
        self.should_calculate_connectedness_metrics = value

    def with_population_metrics(self, value: bool = True) -> None:
        self.should_calculate_population_metrics = value

    def with_area_coverage_metrics(self, value: bool = True) -> None:
        self.should_calculate_area_coverage_metrics = value

    # calculate area coverage
    def get_added_area_coverage(self, gap_polygon: shapely.Polygon) -> float:
        epsg_4326 = pyproj.CRS('EPSG:4326')
        epsg_25832 = pyproj.CRS('EPSG:25832')

        project = pyproj.Transformer.from_crs(epsg_4326, epsg_25832, always_xy=True).transform

        added_area: shapely.MultiPolygon | shapely.Polygon = shapely.difference(gap_polygon, self.protected_bike_infra_polygon)
        added_area = transform(project, added_area)

        return added_area.area
    
    def get_added_population(self, gap_polygon: shapely.Polygon) -> float:
        # calculating the population in the difference polygon of gap_polygon and protected_bike_infra_polygon
        added_area: shapely.MultiPolygon | shapely.Polygon = shapely.difference(gap_polygon, self.protected_bike_infra_polygon)

        return self.populationProvider.get_population_in_polygon(added_area)

    def is_connecting_bike_infra(self, gap: nx.MultiDiGraph, bike_infra_graph: nx.MultiDiGraph) -> bool:
        number_of_clusters_before = nx.number_connected_components(bike_infra_graph.to_undirected())
        # add gap graph to bike infra graph
        combined_graph = nx.compose(bike_infra_graph, gap)
        number_of_clusters_after = nx.number_connected_components(combined_graph.to_undirected())
        return number_of_clusters_after < number_of_clusters_before
    
    def get_cc_lengths(self, bike_infra_graph: nx.MultiDiGraph) -> list[float]:
        cc_lengths = []
        for cc in nx.connected_components(bike_infra_graph.to_undirected()):
            cc_length = []
            for edge in bike_infra_graph.subgraph(cc).edges(data=True, keys=True):
                u, v, key, data = edge
                cc_length.append(data.get('length', 0))
            cc_lengths.append(sum(cc_length))
        return cc_lengths
    
    def avg_size_of_connected_component(self, gap: nx.MultiDiGraph, bike_infra_graph: nx.MultiDiGraph):
        combined_graph = nx.compose(bike_infra_graph, gap)
        cc_length_after = self.get_cc_lengths(combined_graph)
        return np.mean(cc_length_after)

    def calculate_gap_metrics(self, gaps: list[Gap], routing_graph_with_ebc: nx.MultiDiGraph) -> gpd.GeoDataFrame:
        # calculate different metrics for every gap
        gaps_df_values = {'gap': [], 'gap_geometry': [], 'additional_coverage': [], 'additional_population_coverage': [], 'length': [], 'benefit': [], 'mean_ebc': [], 'max_ebc': [], 'min_ebc': [], 'vag_rad_usage': [], 'is_connecting_bike_infra': [], 'gap_polygon': [], 'reachable_edges': [], 'mean_cc_size': []}

        bike_infra_graph = routing_graph_with_ebc.copy()
        for edge in routing_graph_with_ebc.edges(data=True, keys=True):
            u, v, key, data = edge
            osmid = data.get('osmid', None)
            if osmid is None or osmid not in self.osmids_with_bike_infra:
                bike_infra_graph.remove_edge(u, v, key)
        # remove isolated nodes
        isolated_nodes = list(nx.isolates(bike_infra_graph))
        bike_infra_graph.remove_nodes_from(isolated_nodes)

        #ox.graph_to_gdfs(bike_infra_graph, nodes=False, edges=True).to_file('graph.gpkg', layer='bike_infra_graph', driver='GPKG')

        for g in tqdm(gaps, desc='calculating gap metrics', unit='gap'):
            gap = g.get_graph(routing_graph_with_ebc)
            length = 0
            lines = []
            ebc_values = []

            for edge in gap.edges(data=True, keys=True):
                u, v, key, data = edge
                length += data.get('length', 0)
                ebc_values.append(data.get('count', 0))
                line = data.get('geometry', None)
                if line is not None:
                    lines.append(line)
            gap_geometry = shapely.MultiLineString(lines)
            max_ebc = max(ebc_values)
            min_ebc = min(ebc_values)
            mean_ebc = sum(ebc_values) / len(ebc_values)

            gaps_df_values['gap'].append(g)
            gaps_df_values['gap_geometry'].append(gap_geometry)
            if self.should_calculate_area_coverage_metrics or self.should_calculate_population_metrics:
                gap_polygon, reachable_edges = self.service_area_provider.get_service_area(gap)
                gaps_df_values['gap_polygon'].append(gap_polygon)
                gaps_df_values['reachable_edges'].append(shapely.MultiLineString(reachable_edges))
            if self.should_calculate_area_coverage_metrics:
                gaps_df_values['additional_coverage'].append(self.get_added_area_coverage(gap_polygon))
            if self.should_calculate_population_metrics:
                gaps_df_values['additional_population_coverage'].append(self.get_added_population(gap_polygon))
            gaps_df_values['length'].append(length)
            gaps_df_values['benefit'].append(length * mean_ebc)
            gaps_df_values['mean_ebc'].append(mean_ebc)
            gaps_df_values['max_ebc'].append(max_ebc)
            gaps_df_values['min_ebc'].append(min_ebc)
            gaps_df_values['vag_rad_usage'].append(None)
            if self.should_calculate_connectedness_metrics:
                gaps_df_values['is_connecting_bike_infra'].append(self.is_connecting_bike_infra(gap, bike_infra_graph))
                gaps_df_values['mean_cc_size'].append(self.avg_size_of_connected_component(gap, bike_infra_graph))

        if not self.should_calculate_connectedness_metrics:
            gaps_df_values.pop('is_connecting_bike_infra')
            gaps_df_values.pop('mean_cc_size')
        if not self.should_calculate_population_metrics:
            gaps_df_values.pop('additional_population_coverage')
        if not self.should_calculate_area_coverage_metrics:
            gaps_df_values.pop('additional_coverage')
        if not self.should_calculate_area_coverage_metrics and not self.should_calculate_population_metrics:
            gaps_df_values.pop('gap_polygon')
            gaps_df_values.pop('reachable_edges')

        gaps_df = gpd.GeoDataFrame(gaps_df_values, geometry='gap_geometry', crs='EPSG:4326')
        return gaps_df
