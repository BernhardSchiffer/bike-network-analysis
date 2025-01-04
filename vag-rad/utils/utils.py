import networkx as nx
import osmnx as ox
import folium
import geopandas as gpd

# calculate length of edges of a graph
def get_path_length(graph: nx.MultiGraph | nx.MultiDiGraph):
    if len(graph.edges) > 0:
        edges = ox.graph_to_gdfs(graph, nodes=False, edges=True)
        return sum(edges['length'])
    else:
        return 0
    
# plot edges of a graph on to a folium map
def plot_graph(graph: nx.MultiGraph | nx.MultiDiGraph, map=folium.Map(location=[49.451900, 11.076608], zoom_start=12, crs='EPSG3857'), color='blue'):
    if(len(graph.edges) > 0):
        df = ox.graph_to_gdfs(graph, nodes=False)
        for t in df['geometry'].values:
            coordinates = []
            for c in t.coords[:]:
                coordinates.append((c[1], c[0]))
            folium.PolyLine(coordinates, color=color).add_to(map)
    return map

def get_list_of_edges(osmids: list[str], df: gpd.GeoDataFrame):
    merged_df: gpd.GeoDataFrame = None
    for osmid in osmids:
        tmp = df.loc[df['osmid'] == osmid]
        if merged_df is not None:
            merged_df.add(tmp)
        else:
            merged_df = tmp
    return merged_df