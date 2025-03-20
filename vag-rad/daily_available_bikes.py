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
import pytz
import shutil

# %%
# get unique bikes per day
def get_bikes_from_file(filename):
    #print(f'get bikes from: {filename}')
    f = open(f'{filename}', 'r')
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

def get_available_bikes_per_date(date, directory):
    #print(f'getting bikes for {date.date()}')
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

def get_unique_bikes_in_date_range(dict, date_start, date_end):
    unique_bikes = []

    dates = pd.date_range(date_start, date_end)
    for date in dates:
        try:
            unique_bikes.append(len(dict[date.date().isoformat()]))
        except:
            pass
            
    return unique_bikes

cities = {
    'Nürnberg': {
        'directory': './scraper/scraping_data/nuernberg/',
        'available_bikes_filename': './stats/available_bikes_per_day_nuernberg.csv',
        'monthly_stats_filename': './stats/monthly_stats_nuernberg.csv',
        'daily_stats_filename': './stats/daily_stats_nuernberg.csv'
    },
    'Fürth': {
        'directory': './scraper/scraping_data/fuerth/',
        'available_bikes_filename': './stats/available_bikes_per_day_fuerth.csv',
        'monthly_stats_filename': './stats/monthly_stats_fuerth.csv',
        'daily_stats_filename': './stats/daily_stats_fuerth.csv'
    },
    'Erlangen': {
        'directory': './scraper/scraping_data/erlangen/',
        'available_bikes_filename': './stats/available_bikes_per_day_erlangen.csv',
        'monthly_stats_filename': './stats/monthly_stats_erlangen.csv',
        'daily_stats_filename': './stats/daily_stats_erlangen.csv'
    },
    'Schwabach': {
        'directory': './scraper/scraping_data/schwabach/',
        'available_bikes_filename': './stats/available_bikes_per_day_schwabach.csv',
        'monthly_stats_filename': './stats/monthly_stats_schwabach.csv',
        'daily_stats_filename': './stats/daily_stats_schwabach.csv'
    }
}

# %%
# get available bikes per day and write it to file
overwrite = False
fieldnames = ['date', 'bikes']

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

    dates = pd.date_range('2023-05-22', '2025-03-31')
    for date in dates:
        if overwrite is False and date.date().isoformat() in available_bikes:
            print(f'bikes for {date.date()} are already there')
            continue
        else:
            result = get_available_bikes_per_date(date, directory)
            if result is not None:
                _, bikes = result
                available_bikes[date.date().isoformat()] = list(bikes)

    with open(available_bikes_filename, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        sorted_bikes = dict(sorted(available_bikes.items()))
        writer.writerows([
            {'date': date, 'bikes': ','.join(unique_bikes)} for date, unique_bikes in sorted_bikes.items()
        ])

# %%
# read csv of available bikes
for city, city_data in cities.items():
    available_bikes_filename = city_data['available_bikes_filename']

    with open(available_bikes_filename, 'r', newline='') as csvfile:
        fieldnames = ['date', 'bikes']
        reader = csv.DictReader(csvfile, fieldnames=fieldnames, delimiter=';')
        # skip header
        next(reader, None)

        available_bikes = {}
        for row in reader:
            if(len(row['bikes']) > 0):
                bikes = row['bikes'].split(',')
                available_bikes[row['date']] = bikes

    cities[city]['available_bikes'] = available_bikes

# %%
# plot monthly available bikes
for city, city_data in cities.items():
    available_bikes = city_data['available_bikes']
    monthly_available_bikes = {}
    for month_start, month_end in zip(pd.date_range('2023-01', '2025-04', freq='MS'), pd.date_range('2023-01', '2025-04', freq='ME')):
        monthly_available_bikes[f'{month_start.year} {month_start.date().strftime('%B')}'] = get_unique_bikes_in_date_range(available_bikes, month_start, month_end)

    monthly_available_bikes = dict((k, v) for k, v in monthly_available_bikes.items() if len(v) > 0)

    monthly_stats: dict[str, dict[str, float]] = {}
    for k, v in monthly_available_bikes.items():
        monthly_stats[k] = {}
        monthly_stats[k]['median_number_of_available_bikes'] = np.median(v)
        monthly_stats[k]['mean_number_of_available_bikes'] = np.mean(v)
        monthly_stats[k]['max_number_of_available_bikes'] = np.max(v)
        monthly_stats[k]['min_number_of_available_bikes'] = np.min(v)

    monthly_stats_filename = city_data['monthly_stats_filename']
    with open(monthly_stats_filename, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=['year', 'month', 'median_number_of_available_bikes', 'mean_number_of_available_bikes', 'max_number_of_available_bikes', 'min_number_of_available_bikes'], delimiter=';')
        writer.writeheader()
        writer.writerows([
            {'year': date.split(' ')[0], 'month': date.split(' ')[1]} | stats for date, stats in monthly_stats.items()
        ])

    fig, ax = plt.subplots()
    ax.boxplot(monthly_available_bikes.values())
    ax.set_xticklabels(monthly_available_bikes.keys())
    plt.xticks(rotation=45)
    plt.xlabel('Month')
    plt.ylabel('Number of available bikes')
    fig.set_size_inches(25, 10, forward=True)
    fig.set_dpi(100)
    plt.title(f'{city} - Monthly available bikes')
    plt.grid()
    plt.show()

# %%
# plot number of daily available bikes
fig, ax = plt.subplots(1)

x_data = [date.date().isoformat() for date in pd.date_range('2023-01', '2025-04', freq='D')]
y_max = 0

for city, city_data in cities.items():
    #if(city != 'Nürnberg'):
    #    continue

    available_bikes = city_data['available_bikes']
    
    y_data = []
    for date in x_data:
        b = available_bikes.get(date, None)
        if b is None:
            y_data.append(None)
        else:
            y_data.append(len(b))
    
    plt.plot(x_data, y_data, label=city)

    daily_stats_filename = city_data['daily_stats_filename']
    with open(daily_stats_filename, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=['date','number_of_available_bikes'], delimiter=';')
        writer.writeheader()
        writer.writerows([
            {'date': date, 'number_of_available_bikes': bikes} for date, bikes in zip(x_data, y_data) if bikes is not None
        ])

    max_temp = max([x for x in y_data if x is not None], default=0)
    if(max_temp > y_max):
        y_max = max_temp

plt.xticks(rotation=45)
ax.set_ylim(ymin=0, ymax=y_max + 200)
ax.xaxis.set_major_locator(MonthLocator(interval=1))
#ax.xaxis.set_minor_locator(WeekdayLocator())
plt.xlabel('Date')
plt.ylabel('Number of available bikes')
fig.set_size_inches(25, 10, forward=True)
fig.set_dpi(100)
fig.tight_layout()
fig.legend()
plt.title('Daily available bikes')
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
fieldnames = ['date', 'bikes']

list_of_compromised_days = {
    'Nürnberg': [
        '2024-02-18',
        '2024-06-08',
        '2024-08-09',
        '2024-09-07',
        '2024-09-08',
        '2024-11-16'
    ]
}

for city, compromised_days in list_of_compromised_days.items():
    available_bikes_filename = cities[city]['available_bikes_filename']
    available_bikes = {}

    with open(available_bikes_filename, 'r', newline='') as csvfile:
        reader = csv.DictReader(csvfile, fieldnames=fieldnames, delimiter=';')
        # skip header
        next(reader, None)

        for row in reader:
            bikes = row['bikes'].split(',')
            available_bikes[row['date']] = bikes

    for k in compromised_days:
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
# merge monthly and daily stats for every city into one xlsx file
cities_stats = {}
# Reading the csv file
for city, city_data in cities.items():
    daily_stats_filename = city_data['daily_stats_filename']
    monthly_stats_filename = city_data['monthly_stats_filename']

    daily_stats = pd.read_csv(daily_stats_filename, delimiter=';')
    monthly_stats = pd.read_csv(monthly_stats_filename, delimiter=';')

    cities_stats[city] = {}
    cities_stats[city]['daily_stats'] = daily_stats
    cities_stats[city]['monthly_stats'] = monthly_stats

# saving xlsx file
with pd.ExcelWriter('vag-rad_stats.xlsx', mode='w') as writer:
    for city, city_data in cities_stats.items():
        daily_stats = city_data['daily_stats']
        monthly_stats = city_data['monthly_stats']
        daily_stats.to_excel(writer, sheet_name=f'{city} - daily stats', index=False)
        monthly_stats.to_excel(writer, sheet_name=f'{city} - monthly stats', index=False)

# %%
directory = './scraper/scraping_data/nuernberg/'

for date in pd.date_range('2023-05-22', '2025-03-12'):
    path = f'{directory}{date.date()}'
    date_string = str(date.date())
    file = get_files_in_daterange(directory, date_start=date_string, date_end=date_string)
    if len(file) <= 0:
        print(f'file for {date.date()} not found')
        continue
    else:
        extract_archive_to_dir(file[0], path)

    date = date.replace(tzinfo=pytz.utc).astimezone(pytz.timezone('Europe/Berlin')).replace(hour=3, minute=0, second=0, microsecond=0)
    # get utc time stamp
    date = date.astimezone(pytz.utc)
    date_string = date.isoformat()[:14]

    # find file path that matches date_string
    first_fould_file = None
    for root, dirs, files in os.walk(path):
        for file in sorted(files):
            if date_string in file:
                first_fould_file = os.path.join(root, file)
                break

    if first_fould_file is not None:
        print(f'copying {first_fould_file}')
        shutil.copy2(first_fould_file, './tmp')

    shutil.rmtree(path, onerror=handler)

# %%
