# VAG-Rad

## Scraping

For Scraping the vag-rad api you must set the env-variables `scraping_data_location` and `log_location` in an `.env` file to locations where you would like to store the files with the scraped data and the location for the logging file.
Then just launch the docker container by running the following command in the terminal.

``` Shell
docker-compose -f docker-compose.vag-rad_scraper.yml up -d
```

## DB-Setup

The Database is an PostgreSQL Database with the PostGIS Extension.
For setting up the Database you must habe an `.env` file in your folder with the variables `POSTGRES_USER` `POSTGRES_PASSWORD` `POSTGRES_DB` and `POSTGRES_PORT`.

With the following command you can spin up the db in an lokal docker container.

``` Shell
docker-compose -f docker-compose.db.yml up -d
```

## DB-Import

Before starting the code to import the scraped data into the database you must create the needed tables. In the file `./sql/create-tables.sql` you find the scripts to create all necessary tables.

For Importing the scraped files into to database there is the `db_import.py` file. But first you must also set an additional `POSTGRES_HOST` env-variable in your `.env` file. For an local instance of your database you can set that variable to `localhost`.

The `db_import.py` file can be interactively executed via vs-code cells or just over the terminal.
