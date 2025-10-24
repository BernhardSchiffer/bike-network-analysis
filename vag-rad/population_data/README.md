# Population Data

This folder contains population density data used in the project to analyze and visualize population distribution in the area of interest. The data is typically in raster format (GeoTIFF) where each pixel represents the population count or density for that specific area.

## Data Source

The population data used in this project is sourced from the [Global Human Settlement Layer (GHSL)](https://human-settlement.emergency.copernicus.eu/download.php?ds=pop). The GHSL provides high-resolution population density maps derived from satellite imagery and census data.

### Download

The population density data can be downloaded from the GHSL website. The data is available in various resolutions and formats. For this project, GeoTIFF files for 2025 were used with a resolution of 3 arcsec by 3 arcsec and the tile id R4_C20.

## Use

The population data can be queried through the `population_provider` class located in `utils/population_provider.py`. This class provides methods to get population density values for given coordinates or areas.
