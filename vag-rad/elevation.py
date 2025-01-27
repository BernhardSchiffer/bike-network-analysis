# %%
from pyproj import Transformer
osm_to_geotiff = Transformer.from_crs("EPSG:4326", "EPSG:25832")
geotiff_to_osm = Transformer.from_crs("EPSG:25832", "EPSG:4326")

# %%

import rasterio
dat = rasterio.open('/Users/bernie/Downloads/DEM/nuernberg.tif')
# read all the data from the first band
z = dat.read()[0]

# check the crs of the data
print(dat.crs)
# >>> CRS.from_epsg(4326)

# check the bounding-box of the data
print(dat.bounds)
# >>> Out[49]: BoundingBox(left=-120.0, bottom=45.0, right=-117.0, top=48.0)

# since the raster is in regular lon/lat grid (4326) we can use 
# `dat.index()` to identify the index of a given lon/lat pair
# (e.g. it expects coordinates in the native crs of the data)

def getval(lon, lat):
    idx = dat.index(lon, lat, precision=1E-6)    
    return dat.xy(*idx), z[idx]

# %%
lat = 49.459123
lon = 11.0735755
x, y = osm_to_geotiff.transform(lat, lon)
getval(x, y)

# %%
geotiff_to_osm.transform(x, y)

# %%
import leafmap.foliumap as leafmap
import folium

map = leafmap.Map(location=[49.451900, 11.076608], zoom_start=12, crs='EPSG3857')
folium.Marker((lat, lon), 'osm').add_to(map)
x, y = osm_to_geotiff.transform(lat, lon)
folium.Marker(geotiff_to_osm.transform(x, y), 'geotiff').add_to(map)

map

# %%
from numpy import unravel_index
x, y = unravel_index(z.argmax(), z.shape)

print(f'max hight {z[x][y]} meters')
print(f'found at {dat.xy(x, y)}')
lat, lng = dat.xy(x, y)
print(f'osm coordinates {geotiff_to_osm.transform(lat, lng)}')

map = leafmap.Map(location=[49.451900, 11.076608], zoom_start=12, crs='EPSG3857')
folium.Marker(geotiff_to_osm.transform(lat, lng), z[x][y]).add_to(map)

map
# %%
