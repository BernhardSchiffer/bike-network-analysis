# define abstract class for population providers
from abc import ABC, abstractmethod
import shapely
import rasterio
import geopandas as gpd
import overpy
from tqdm import tqdm
from utils.overpass_utils import get_polygon_from_result, fetch_city_polygon
from utils.demand_provider import DemandProvider

class PopulationProvider(ABC):
    @abstractmethod
    def get_population_in_polygon(self, polygon: shapely.Polygon | shapely.MultiPolygon) -> float:
        pass

    @abstractmethod
    def get_population_at_point(self, point: shapely.Point) -> float:
        pass

class GHSLPopulationProvider(PopulationProvider, DemandProvider):
    def __init__(self):
        self.population_src: rasterio.DatasetReader = rasterio.open('population_data/GHS_POP_E2025_GLOBE_R2023A_4326_3ss_V1_0_R4_C20.tif')
        # read all the data from the first band
        self.population_data = self.population_src.read()[0]

    def get_population_in_polygon(self, polygon: shapely.Polygon | shapely.MultiPolygon) -> float:
        # calculate population in added area polygon
        bbox_west = polygon.bounds[0]
        bbox_north = polygon.bounds[3]
        bbox_east = polygon.bounds[2]
        bbox_south = polygon.bounds[1]

        row_start ,col_start = self.population_src.index(bbox_west, bbox_north)
        row_end ,col_end = self.population_src.index(bbox_east, bbox_south)

        added_population = 0

        for row in range(row_start, row_end + 1):
            for col in range(col_start, col_end + 1):
                tile = shapely.Polygon([
                    self.population_src.transform * (col, row),
                    self.population_src.transform * (col, row + 1),
                    self.population_src.transform * (col + 1, row + 1),
                    self.population_src.transform * (col + 1, row)
                ])
                intersection = tile.intersection(polygon)
                if not intersection.is_empty:
                    added_population += intersection.area / tile.area * self.population_data[row, col]
        
        return added_population
    
    def get_population_at_point(self, point: shapely.Point) -> float:
        row, col = self.population_src.index(point.x, point.y)
        return self.population_data[row, col]
    
    def get_demand_at_point(self, point: shapely.Point) -> float:
        # for GHSL, we assume demand is proportional to the population
        return self.get_population_at_point(point)

class NurenbergDistrictPopulationProvider(PopulationProvider):
    def __init__(self, from_cache: bool = True):
        self.api = overpy.Overpass(url='https://maps.mail.ru/osm/tools/overpass/api/interpreter')
        self.residential_area_cache_file = 'nuremberg_residential_areas.gpkg'
        self.district_area_cache_file = 'nuremberg_districts.gpkg'
        self.apartments_cache_file = 'nuremberg_apartments.gpkg'
        self.nuremberg_area = self.fetch_nuremberg_area()

        population_data: dict[str, int] = {
            "Ludwigsfeld": 11684,
            "Glockenhof": 19136,
            "Guntherstraße": 3820,
            "Galgenhof": 20302,
            "Hummelstein": 11410,
            "Gugelstraße": 8233,
            "Steinbühl": 13782,
            "Gibitzenhof": 5313,
            "Sandreuth": 426,
            "Schweinau": 5157,
            "St. Leonhard": 14764,
            "Sündersbühl": 7298,
            "Bärenschanze": 9573,
            "Sandberg": 11091,
            "Bielingplatz": 5532,
            "Uhlandstraße": 12088,
            "Maxfeld": 10925,
            "Veilhof": 12406,
            "Tullnau": 4167,
            "Gleißhammer": 6243,
            "Dutzendteich": 1066,
            "Rangierbahnhof-Siedlung": 4314,
            "Langwasser Nordwest": 7462,
            "Langwasser Nordost": 6977,
            "Beuthener Straße": 419,
            "Altenfurt Nord": 1326,
            "Langwasser Südost": 10529,
            "Langwasser Südwest": 8441,
            "Altenfurt, Moorenbrunn": 8377,
            "Gewerbepark Nürnberg-Feucht": 91,
            "Hasenbuck": 4070,
            "Rangierbahnhof": 381,
            "Katzwanger Straße": 242,
            "Dianastraße": 2385,
            "Trierer Straße": 5201,
            "Gartenstadt": 7454,
            "Werderau": 4705,
            "Maiach": 1717,
            "Katzwang, Reichelsdorf Ost, Reichelsdorfer Keller": 11396,
            "Kornburg, Worzeldorf": 13414,
            "Hohe Marter": 7095,
            "Röthenbach West": 9225,
            "Röthenbach Ost": 12703,
            "Eibach": 8910,
            "Reichelsdorf": 7987,
            "Krottenbach, Mühlhof": 2410,
            "Großreuth b. Schweinau": 6796,
            "Gebersdorf": 4261,
            "Gaismannshof": 6185,
            "Höfen": 3653,
            "Eberhardshof": 11143,
            "Muggenhof": 2839,
            "Westfriedhof": 3361,
            "Schniegling": 3993,
            "Wetzendorf": 9064,
            "Buch": 1976,
            "Thon": 5488,
            "Almoshof": 1153,
            "Kraftshof": 869,
            "Neunhof": 1669,
            "Boxdorf": 2897,
            "Großgründlach": 4857,
            "Schleifweg": 4556,
            "Schoppershof": 8811,
            "Schafhof": 2161,
            "Marienberg": 4333,
            "Ziegelstein": 5709,
            "Mooshof": 2190,
            "Buchenbühl": 2245,
            "Flughafen": 6,
            "St. Jobst": 10570,
            "Erlenstegen": 4335,
            "Mögeldorf": 6192,
            "Schmausenbuckstraße": 4911,
            "Laufamholz": 8615,
            "Zerzabelshof": 8336,
            "Fischbach": 5035,
            "Brunn": 993,
            "Altstadt, St. Lorenz": 5247,
            "Marienvorstadt": 1851,
            "Tafelhof": 1370,
            "Gostenhof": 9528,
            "Himpfelshof": 6040,
            "Altstadt, St. Sebald": 9705,
            "St. Johannis": 8187,
            "Pirckheimerstraße": 8204,
            "Wöhrd": 10517,
        }
        district_names = list(population_data.keys())
        populations = list(population_data.values())
        district_areas: list[shapely.MultiPolygon | None] = []
        residential_areas: list[shapely.MultiPolygon | None] = []
        apartments_areas = []
        for name in tqdm(district_names, desc='loading residential areas for districts', unit='district'):
            try:
                district_area = self.get_district_area(district_name=name, from_cache=from_cache)
                district_areas.append(district_area)
            except Exception as e:
                print(f'Error loading district area {name}: {e}')
                district_areas.append(None)
                residential_areas.append(None)
                apartments_areas.append(None)
                continue
            try:
                residential_area = self.get_residential_area(district_name=name, district_area=district_area, from_cache=from_cache)
                residential_areas.append(residential_area)
            except Exception as e:
                print(f'Error loading residential area for district {name}: {e}')
                residential_areas.append(None)
                apartments_areas.append(None)
                continue
            try:
                apartment_area = self.get_apartment_area(district_name=name, residential_area=residential_area, from_cache=from_cache)
                apartments_areas.append(apartment_area)
            except Exception as e:
                print(f'Error loading apartment area for district {name}: {e}')
                apartments_areas.append(None)
                continue

        self.population_gdf = gpd.GeoDataFrame({
            'district': district_names,
            'population': populations,
            'district_areas': district_areas,
            'residential_areas': residential_areas,
            'apartments_areas': apartments_areas
        }, crs=4326, geometry='residential_areas')

    def save(self, filename: str, district_name: str, polygon: shapely.MultiPolygon):
        gpd.GeoDataFrame({'district': district_name, 'geometry': [polygon]}, crs=4326).to_file(filename, layer=district_name, driver='GPKG')
    
    def load(self, filename: str, district_name) -> shapely.MultiPolygon:
        try:
            gdf = gpd.read_file(filename, layer=district_name, driver='GPKG').to_crs(4326)
            return gdf['geometry'].values[0]
        except:
            raise ValueError(f'No cached values found for district {filename}/{district_name}')
        
    def fetch_nuremberg_area(self) -> shapely.MultiPolygon:
        return fetch_city_polygon('Nürnberg')
        
    def fetch_district_area(self, district_name: str) -> shapely.MultiPolygon:
        result = self.api.query(f"""
                            (
                                relation['boundary'='administrative']['admin_level'='11']['name'='{district_name}'];
                            );
                            out body;
                            >;
                            out skel qt;
                        """)
        if result.ways is None or len(result.ways) == 0:
            raise ValueError(f'No district found for name: {district_name}')
        else:
            district_area = get_polygon_from_result(result)
            intersection = shapely.intersection(district_area, self.nuremberg_area)

            if isinstance(intersection, (shapely.Polygon, shapely.MultiPolygon)):
                return intersection
            else:
                polygons = [geom for geom in intersection.geoms if isinstance(geom, (shapely.Polygon, shapely.MultiPolygon))]

                return shapely.MultiPolygon(polygons)
        
    def get_district_area(self, district_name: str, from_cache) -> shapely.MultiPolygon:
        try:
            if not from_cache:
                raise ValueError('Force fetch residential area from API')
            return self.load(self.district_area_cache_file, district_name)
        except:
            polygon = self.fetch_district_area(district_name)
            self.save(self.district_area_cache_file, district_name, polygon)
            return polygon

    def fetch_residential_area(self, district_name: str, district_area: shapely.MultiPolygon) -> shapely.MultiPolygon:
        result = self.api.query(f"""
                            (
                                area['boundary'='administrative']['admin_level'='11']['name'='{district_name}']->.district;
                                nwr["landuse"="residential"](area.district);
                            );
                            out body;
                            >;
                            out skel qt;
                        """)
        if result.ways is None or len(result.ways) == 0:
            raise ValueError(f'No residential area found for district {district_name}')
        else:
            residential_area = get_polygon_from_result(result)
            intersection = shapely.intersection(residential_area, district_area)
        
            if isinstance(intersection, (shapely.Polygon, shapely.MultiPolygon)):
                return intersection
            else:
                polygons = [geom for geom in intersection.geoms if isinstance(geom, (shapely.Polygon, shapely.MultiPolygon))]

                return shapely.MultiPolygon(polygons)
            
    def get_residential_area(self, district_name: str, district_area, from_cache: bool) -> shapely.MultiPolygon:
        try:
            if not from_cache:
                raise ValueError('Force fetch residential area from API')
            return self.load(self.residential_area_cache_file, district_name)
        except:
            polygon = self.fetch_residential_area(district_name, district_area)
            self.save(self.residential_area_cache_file, district_name, polygon)
            return polygon
    
    def fetch_apartments(self, district_name: str, residential_area: shapely.MultiPolygon) -> shapely.MultiPolygon:
        result = self.api.query(f"""
                            (
                                area['boundary'='administrative']['admin_level'='11']['name'='{district_name}']->.district;
                                wr["building"~"(apartments|residential|yes|house|terrace|detached)"](area.district);
                            );
                            out body;
                            >;
                            out skel qt;
                        """)
        if result.ways is None or len(result.ways) == 0:
            raise ValueError(f'No apartments found in district {district_name}')
        else:
            apartment_area = get_polygon_from_result(result)
            intersection = shapely.intersection(apartment_area, residential_area)
        
            if isinstance(intersection, (shapely.Polygon, shapely.MultiPolygon)):
                return intersection
            else:
                polygons = [geom for geom in intersection.geoms if isinstance(geom, (shapely.Polygon, shapely.MultiPolygon))]

                return shapely.MultiPolygon(polygons)
        
    def get_apartment_area(self, district_name: str, residential_area, from_cache: bool) -> shapely.MultiPolygon:
        try:
            if not from_cache:
                raise ValueError('Force fetch apartment area from API')
            return self.load(self.apartments_cache_file, district_name)
        except:
            polygon = self.fetch_apartments(district_name, residential_area)
            self.save(self.apartments_cache_file, district_name, polygon)
            return polygon

    def get_population_in_polygon(self, polygon: shapely.Polygon | shapely.MultiPolygon) -> float:
        # calculate population in added area polygon
        total_population = 0
        for _, row in self.population_gdf.iterrows():
            if row['apartments_areas'] is None:
                continue
            intersection = row['apartments_areas'].intersection(polygon)
            if not intersection.is_empty:
                total_population += intersection.area / row['apartments_areas'].area * row['population']
        
        return total_population
    
    def get_population_at_point(self, point: shapely.Point) -> float:
        for _, row in self.population_gdf.iterrows():
            if row['geometry'].contains(point):
                return row['population']
        return 0
