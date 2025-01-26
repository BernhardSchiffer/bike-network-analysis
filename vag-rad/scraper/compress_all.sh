#!/bin/bash

date=$1 #$(date --date="yesterday" +%Y-%m-%d)

sh compress.sh $date ./scraping_data/nuernberg/ ./scraping_data/nuernberg/
sh compress.sh $date ./scraping_data/fuerth/ ./scraping_data/fuerth/
sh compress.sh $date ./scraping_data/erlangen/ ./scraping_data/erlangen/
sh compress.sh $date ./scraping_data/schwabach/ ./scraping_data/schwabach/
