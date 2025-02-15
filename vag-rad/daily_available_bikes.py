#%%
import os
import json
import pandas as pd
import shutil
import csv
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.dates import DayLocator, MonthLocator, WeekdayLocator
from utils.utils import get_files_in_daterange, extract_archive_to_dir, handler

# %%
# get unique bikes per day
def get_bikes_from_file(filename):
    #print(f"get bikes from: {filename}")
    f = open(f"{filename}", "r")
    try:
        data = json.load(f)
    except json.JSONDecodeError as e:
        print(f'Exception {e} while parsing {filename}')
        return
    
    bike_records = set()

    try:
        places = data['countries'][0]['cities'][0]['places']
    except Exception as e:
        print(f'Error {e} with {filename}. No places found')
        return

    for place in places:
        # bikes parked at stations
        if place['spot'] == True and place['bike'] == False:
            for bike in place['bike_list']:
                bike_records.add(bike['number'])
        # bikes not parked at stations e.g. parked in the free floating area  
        if place['spot'] == False and place['bike'] == True:
            bike_records.add(place['bike_list'][0]['number'])

    return bike_records

def get_available_bikes_per_date(date):
    print(f'getting bikes for {date.date()}')
    path = f'{directory}{date.date()}'
    date_string = str(date.date())
    file = get_files_in_daterange(directory, date_start=date_string, date_end=date_string)
    if len(file) <= 0:
        print(f'file for {date.date()} not found')
        return None
    else:
        extract_archive_to_dir(file[0], path)

    filenames = []
    for root, dirs, files in os.walk(path):
        for file in files:
            filenames.append(os.path.join(root, file))

    unique_bikes = set()

    for filename in filenames:
        bikes = get_bikes_from_file(filename)
        if bikes is not None:
            unique_bikes.update(bikes)

    shutil.rmtree(path, onerror=handler)

    return (date, unique_bikes)

overwrite = False

fieldnames = ['date', 'bikes']

cities = {
    'nuernberg': {
        'directory': './scraper/scraping_data/nuernberg/',
        'available_bikes_filename': 'available_bikes_per_day_nuernberg.csv',
    },
    'fuerth': {
        'directory': './scraper/scraping_data/fuerth/',
        'available_bikes_filename': 'available_bikes_per_day_fuerth.csv',
    },
    'erlangen': {
        'directory': './scraper/scraping_data/erlangen/',
        'available_bikes_filename': 'available_bikes_per_day_erlangen.csv',
    },
    'schwabach': {
        'directory': './scraper/scraping_data/schwabach/',
        'available_bikes_filename': 'available_bikes_per_day_schwabach.csv',
    }
}

for city, city_data in cities.items():
    print(f'getting available bikes for {city}')
    directory = city_data['directory']
    available_bikes_filename = city_data['available_bikes_filename']
    available_bikes = {}

    if os.path.isfile(available_bikes_filename):
        with open(available_bikes_filename, 'r', newline='') as csvfile:
            reader = csv.DictReader(csvfile, fieldnames=fieldnames, delimiter=';')
            # skip header
            next(reader, None)

            for row in reader:
                bikes = row['bikes'].split(',')
                available_bikes[row['date']] = bikes

    dates = pd.date_range('2023-05-22', '2025-01-31')
    for date in dates:
        if overwrite is False and date.date().isoformat() in available_bikes:
            print(f'bikes for {date.date()} are already there')
            continue
        else:
            result = get_available_bikes_per_date(date)
            if result is not None:
                _, bikes = result
                available_bikes[date.date().isoformat()] = list(bikes)

    with open(available_bikes_filename, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        sorted_bikes = dict(sorted(available_bikes.items()))
        writer.writerows([
            {'date': date, 'bikes': ','.join(unique_bikes)} for date, unique_bikes in available_bikes.items()
        ])

# %%
# read csv of available bikes
def get_unique_bikes_in_date_range(dict, date_start, date_end):
    unique_bikes = []

    dates = pd.date_range(date_start, date_end)
    for date in dates:
        try:
            unique_bikes.append(len(dict[date.date().isoformat()]))
        except:
            pass
            
    return unique_bikes

for city, city_data in cities.items():
    available_bikes_filename = city_data['available_bikes_filename']

    with open(available_bikes_filename, 'r', newline='') as csvfile:
        fieldnames = ['date', 'bikes']
        reader = csv.DictReader(csvfile, fieldnames=fieldnames, delimiter=';')
        # skip header
        next(reader, None)

        available_bikes = {}
        for row in reader:
            bikes = row['bikes'].split(',')
            available_bikes[row['date']] = bikes

    cities[city]['available_bikes'] = available_bikes

# %%
# plot monthly available bikes
for city, city_data in cities.items():
    available_bikes = city_data['available_bikes']
    monthly_available_bikes = {}
    for month_start, month_end in zip(pd.date_range('2023-01', '2025-02', freq='MS'), pd.date_range('2023-01', '2025-02', freq='M')):
        monthly_available_bikes[f'{month_start.year} {month_start.date().strftime("%B")}'] = get_unique_bikes_in_date_range(available_bikes, month_start, month_end)

    monthly_available_bikes = dict((k, v) for k, v in monthly_available_bikes.items() if len(v) > 0)

    for k, v in monthly_available_bikes.items():
        print(f'average available bikes in {k}: {np.mean(v)}')
        print(f'median available bikes in {k}: {np.median(v)}')

    fig, ax = plt.subplots()
    ax.boxplot(monthly_available_bikes.values())
    ax.set_xticklabels(monthly_available_bikes.keys())
    plt.xticks(rotation=45)
    fig.set_size_inches(25, 10, forward=True)
    fig.set_dpi(100)
    plt.grid()
    plt.show()

# %%
# plot number of daily available bikes
fig, ax = plt.subplots(1)

x_data = [date.date().isoformat() for date in pd.date_range('2023-01', '2025-02', freq='D')]
y_max = 0

for city, city_data in cities.items():
    available_bikes = city_data['available_bikes']
    
    y_data = []
    for date in x_data:
        b = available_bikes.get(date, None)
        if b is None:
            y_data.append(None)
        else:
            y_data.append(len(b))
    
    plt.plot(x_data, y_data, label=city)

    max_temp = max([x for x in y_data if x is not None], default=0)
    if(max_temp > y_max):
        y_max = max_temp

plt.xticks(rotation=45)
ax.set_ylim(ymin=0, ymax=y_max + 200)
ax.xaxis.set_major_locator(MonthLocator(interval=1))
#ax.xaxis.set_minor_locator(WeekdayLocator())
fig.set_size_inches(25, 10, forward=True)
fig.set_dpi(100)
fig.tight_layout()
fig.legend()
plt.grid()
plt.show()

# %%
# look for dates with outliers
for city, city_data in cities.items():
    available_bikes = city_data['available_bikes']
    for k, v in available_bikes.items():
        if len(v) < 100:
            print(f'{city} {k}: available bikes {len(v)}')

# %%
# remove dates with falsy data
available_bikes_filename = 'available_bikes_per_day.csv'
fieldnames = ['date', 'bikes']
available_bikes = {}

with open(available_bikes_filename, 'r', newline='') as csvfile:
    reader = csv.DictReader(csvfile, fieldnames=fieldnames, delimiter=';')
    # skip header
    next(reader, None)

    for row in reader:
        bikes = row['bikes'].split(',')
        available_bikes[row['date']] = bikes

list_of_compromised_days = [
    '2024-02-18',
    '2024-06-08',
    '2024-08-09',
    '2024-09-07',
    '2024-09-08',
    '2024-11-16'
]

for k in list_of_compromised_days:
    print(f'{k}: available bikes {len(available_bikes[k])}')
    available_bikes.pop(k)

with open(available_bikes_filename, 'w', newline='') as csvfile:
    fieldnames = ['date', 'bikes']
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=';')
    writer.writeheader()
    sorted_bikes = dict(sorted(available_bikes.items()))
    writer.writerows([
        {'date': date, 'bikes': ','.join(unique_bikes)} for date, unique_bikes in available_bikes.items()
    ])
# %%
