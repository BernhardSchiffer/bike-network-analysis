# Digital Elevation Model

An Digital Elevation Model (DEM) is a 3D representation of a terrain's surface created from terrain elevation data. In this project DEM data is utilized to compute the elevation profiles of streets to calculate the weights of edges in the bicycle routing graph. This allows the routing algorithm to consider elevation changes when determining optimal routes for cyclists.

## Data Source

The dem used in this project is from the [Opendata Plattform of the Bavarian Land Survey Office](https://geodaten.bayern.de/opengeodata/OpenDataDetail.html?pn=dgm1)

The accuracy of the DEM is 1 meter, meaning that each pixel in the raster data represents a 1 meter by 1 meter area on the ground. The elevation values are given in meters above sea level (NN - Normalnull).

### Download

The DEM data can be downloaded per tile, administrative district, the whole of Bavaria, or for self defined polygons.

The download is provided via an meta file in XML format which contains links to the actual DEM data files in GeoTIFF format. Use the commandline tool aria2c to download or the files.

[Instructions to download metalink data](https://www.geodaten.bayern.de/odd/m/3/pdf/informationen_metalink.pdf)

### Processing

To process the DEM data for use in the project, the tiff files need to be merged into a single raster file covering the area of interest. This can be done using GIS software like QGIS.

[Instructions to merge GeoTIFF files](https://geodaten.bayern.de/odd/m/3/pdf/geotiff-kacheln_zusammenfuegen.pdf)

## Use

Due to the accuracy of 1 meter the elevation data is directly usable for routing purposes without further processing steps like interpolation. The elevation values can be directly queried for specific coordinates to determine the elevation at those points.

In the project the DEM data can be queried by using the `elevation_provider` class located in `utils/elevation_provider.py`. This class provides methods to get elevation values for given coordinates.
