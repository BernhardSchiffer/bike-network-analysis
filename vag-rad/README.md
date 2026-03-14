# Analysis of the Bike Network in Nuremberg

This repository contains code for the master thesis of Bernhard Schubert at the University of Bamberg. The thesis is about the analysis of the bike network in Nuremberg. The Repository is structured in multiple files that contain code for different parts of the analysis. The main files are:

- `vag-rad-data-visualization.py`: This file contains code for visualizing the data of the bike sharing system in Nuremberg.
- `vag-rad-data-preprocessing.py`: This file contains code for preprocessing the data of the bike sharing system in Nuremberg.
- `bike_network_analysis.py`: This file contains code for analyzing the bike network in Nuremberg.
- `population-data.py`: This file contains code for analyzing the differences between the population data of Nuremberg and GHSL dataset.
- `prepare_graph.py`: This file contains code for creating the graph of the street network in Nuremberg.
- `route_model_testing.py`: This file contains code for visually testing the route model.
- `routing.py`: This file contains code for calculating the shortest and most likely routes of the bike sharing trips in Nuremberg.
- `ebc_analysis.py`: This file contains code for calculating the edge betweenness centrality of the street network in Nuremberg.
- `gaps.py`: This file contains code for identifying and analyzing the gaps in the bike network in Nuremberg.

These files can be executed interactively via vs-code cells. The necessary python packages are listed in the `requirements.txt` file. For running the code you can create a virtual environment and install the packages via pip `pip install -r requirements.txt`. To fully run the code a QGIS installation is also necessary, since some of the code uses the processing toolbox of QGIS. QGIS was also used for most of the visualizations in the thesis.

## Directories

- `scraper`: This directory contains code for scraping the data of the bike sharing system in Nuremberg.
- `population_data`: This directory contains the GHSL population density data used in the project.
- `osm_data`: This directory contains the OpenStreetMap data of Nuremberg used in the project.
- `dem`: This directory contains the digital elevation model data of Nuremberg used in the project.
- `utils`: This directory contains utility functions used in the project for building the graph, wrapper classes for external tools like overpass and qgis, for visualization and other helper functions.

## Scraping

For Scraping the vag-rad api you must set the env-variables `scraping_data_location` and `log_location` in an `.env` file to locations where you would like to store the files with the scraped data and the location for the logging file.
Then just launch the docker container by running the following command in the terminal.

```Shell
docker-compose -f docker-compose.vag-rad_scraper.yml up -d
```

## DB-Setup

The Database is an PostgreSQL Database with the PostGIS Extension.
For setting up the Database you must habe an `.env` file in your folder with the variables `POSTGRES_USER` `POSTGRES_PASSWORD` `POSTGRES_DB` and `POSTGRES_PORT`.

With the following command you can spin up the db in an lokal docker container.

```Shell
docker-compose -f docker-compose.db.yml up -d
```

## DB-Import

Before starting the code to import the scraped data into the database you must create the needed tables. In the file `./sql/create-tables.sql` you find the scripts to create all necessary tables.

For Importing the scraped files into to database there is the `db_import.py` file. But first you must also set an additional `POSTGRES_HOST` env-variable in your `.env` file. For an local instance of your database you can set that variable to `localhost`.

The `db_import.py` file can be interactively executed via vs-code cells or just over the terminal.
