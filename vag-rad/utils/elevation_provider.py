from abc import ABC, abstractmethod

import rasterio
from pyproj import Transformer


class ElevationProvider(ABC):
    @abstractmethod
    def get_elevation(self, lon: float, lat: float) -> float:
        pass

class DEMElevationProvider(ElevationProvider):
    def __init__(self):
        self.osm_to_geotiff = Transformer.from_crs("EPSG:4326", "EPSG:25832")
        self.geotiff_to_osm = Transformer.from_crs("EPSG:25832", "EPSG:4326")
        self.dat = rasterio.open('./DEM/dem.tif')
        # read all the data from the first band
        self.z = self.dat.read()[0]

    def get_elevation(self, lon, lat):
        x, y = self.osm_to_geotiff.transform(lat, lon)
        idx = self.dat.index(x, y, precision=1E-6)
        return self.z[idx]
