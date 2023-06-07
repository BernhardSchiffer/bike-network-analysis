#!/bin/bash

date=$1 #$(date --date="yesterday" +%Y-%m-%d)
input_dir=$(realpath $2)
output_dir=$(realpath $3)

if [ -e "$output_dir/$date.tar.gz" ]; then
    echo "Oops! backup file for the $output_dir/$date was already here."
    exit
fi

$(cd $input_dir && tar -czvf "$output_dir/$date.tar.gz" $date*.json --remove-files)
