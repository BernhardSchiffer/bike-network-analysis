#!/bin/bash

d=$(date --date="yesterday" +%Y-%m-%d)

if [ -f $d.tar.gz ]; then
    echo "Oops! backup file for the $d was already here."
    exit
fi

tar -czvf $d.tar.gz $d*.json --remove-files