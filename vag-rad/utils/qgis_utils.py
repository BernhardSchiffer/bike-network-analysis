import os
import subprocess

import geopandas as gpd
import networkx as nx
import osmnx as ox


# call QGIS processing algorithm for network analysis
def get_network_coverage(routing_graph: nx.MultiDiGraph, coverage_graph: nx.MultiDiGraph, travel_cost: int) -> gpd.GeoDataFrame:
    path_to_qgis_processing = '/Applications/QGIS.app/Contents/MacOS/bin/qgis_process'
    geopackage_file = 'tmp.gpkg'
    result_file = 'qgis_result.gpkg'

    ox.graph_to_gdfs(routing_graph, nodes=False, edges=True).to_file(geopackage_file, layer='routing_graph', driver='GPKG')
    ox.graph_to_gdfs(coverage_graph, nodes=True, edges=False).drop(columns=['osmid']).to_file(geopackage_file, layer='starting_points', driver='GPKG')

    # call QGIS processing algorithm over terminal
    result = subprocess.run([path_to_qgis_processing, 'run', 'qgis:serviceareafromlayer', 'PROJECT_PATH=/Users/bernie/Documents/mittelfranken_fahrradwege.qgz', f'INPUT={geopackage_file}|layername=routing_graph', f'START_POINTS={geopackage_file}|layername=starting_points', f'STRATEGY={0}', f'TRAVEL_COST={travel_cost}', f'OUTPUT_LINES={result_file}'], capture_output=True)

    if result.returncode != 0:
        raise RuntimeError(f"Error occurred: {result.stderr.decode()} - {result}")

    reachable_edges = gpd.read_file(result_file)

    #remove temporary files
    os.remove(geopackage_file)
    os.remove(result_file)

    return reachable_edges