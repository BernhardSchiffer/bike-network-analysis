from abc import ABC, abstractmethod

import geopandas as gpd
import pandas as pd
import shapely

from utils.utils import buffer_in_meters


class DemandProvider(ABC):
    @abstractmethod
    def get_demand_at_point(self, point: shapely.Point) -> float:
        pass

class VagRadDemandProvider(DemandProvider):
    def __init__(self):
        self.load_rental_data()

    def load_rental_data(self):
        rental_data_filename = 'vag-rad-data/processed/All_Ausleihen_Kundendetails.csv'
        # Load and process rental data as needed
        self.rental_data = pd.read_csv(rental_data_filename)

        self.rental_data['starting_position'] = shapely.from_wkt(self.rental_data['starting_position'])
        self.rental_data['finishing_position'] = shapely.from_wkt(self.rental_data['finishing_position'])

        self.rental_data['Start time'] = pd.to_datetime(self.rental_data['Start time'])
        self.rental_data['End time'] = pd.to_datetime(self.rental_data['End time'])

        self.rental_data_starting = gpd.GeoDataFrame(self.rental_data, geometry='starting_position')
        self.rental_data_finishing = gpd.GeoDataFrame(self.rental_data, geometry='finishing_position')

        self.rental_data_starting.drop(columns=['finishing_position'], inplace=True)
        self.rental_data_finishing.drop(columns=['starting_position'], inplace=True)

    def get_demand_at_point(self, point: shapely.Point) -> tuple[float, float]:
        area_of_interest = buffer_in_meters(point, 50)
        rental_starts = self.rental_data_starting.sindex.query(area_of_interest, predicate='contains')
        rental_endings = self.rental_data_finishing.sindex.query(area_of_interest, predicate='contains')
        return (len(rental_starts), len(rental_endings))
    
    def get_demand_in_polygon(self, polygon: shapely.Polygon) -> tuple[float, float]:
        rental_starts = self.rental_data_starting.sindex.query(polygon, predicate='contains')
        rental_endings = self.rental_data_finishing.sindex.query(polygon, predicate='contains')
        return (len(rental_starts), len(rental_endings))