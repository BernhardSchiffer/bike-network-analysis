# %%
# imports
import calendar

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import shapely

# %%
# merge all years into a single dataframe
df_all = pd.read_csv('vag-rad-data/processed/All_Ausleihen_Kundendetails.csv')

df_all['starting_position'] = shapely.from_wkt(df_all['starting_position'])
df_all['finishing_position'] = shapely.from_wkt(df_all['finishing_position'])

df_all['Start time'] = pd.to_datetime(df_all['Start time'])
df_all['End time'] = pd.to_datetime(df_all['End time'])

df_all

# %%
print(f'Total number of rentals from 2019 to 2024: {len(df_all)}')
median_duration = pd.to_timedelta(df_all["Duration"].median(), unit='s')
minutes, seconds = divmod(median_duration.total_seconds(), 60)
print(f'Median rental duration: {int(minutes)} minutes and {int(seconds)} seconds')

minutes, seconds = divmod(df_all["Duration"].max(), 60)
print(f'Maximum rental duration: {int(minutes)} minutes and {int(seconds)} seconds')

minutes, seconds = divmod(df_all["Duration"].min(), 60)
print(f'Minimum rental duration: {int(minutes)} minutes and {int(seconds)} seconds')

# 50 percentiles
p50 = pd.to_timedelta(df_all["Duration"].quantile(0.5), unit='s')
p75 = pd.to_timedelta(df_all["Duration"].quantile(0.75), unit='s')
p90 = pd.to_timedelta(df_all["Duration"].quantile(0.9), unit='s')
p95 = pd.to_timedelta(df_all["Duration"].quantile(0.95), unit='s')
p99 = pd.to_timedelta(df_all["Duration"].quantile(0.99), unit='s')
print(f'50th percentile rental duration: {int(p50.total_seconds() // 60)} minutes and {int(p50.total_seconds() % 60)} seconds')
print(f'75th percentile rental duration: {int(p75.total_seconds() // 60)} minutes and {int(p75.total_seconds() % 60)} seconds')
print(f'90th percentile rental duration: {int(p90.total_seconds() // 60)} minutes and {int(p90.total_seconds() % 60)} seconds')
print(f'95th percentile rental duration: {int(p95.total_seconds() // 60)} minutes and {int(p95.total_seconds() % 60)} seconds')
print(f'99th percentile rental duration: {int(p99.total_seconds() // 60)} minutes and {int(p99.total_seconds() % 60)} seconds')

durations = df_all['Duration']
durations = np.divide(durations, 60)  # convert to minutes
plt.figure(figsize=(9, 6))
plt.hist(durations, bins=100, range=(0, 100), color='#1f78b4')
plt.title('Histogram of Rental Durations', fontsize=16)
plt.xlabel('Duration (minutes)', fontsize=12)
plt.xticks(range(0, 101, 5), fontsize=11)
plt.yticks(fontsize=11)
plt.ylabel('Number of Rentals', fontsize=12)
plt.grid()
plt.tight_layout()
plt.savefig('vag_rad_rental_durations.png', dpi=300)

# %%
# calculate straight-line distances between starting and finishing positions
distances = df_all['distance_m']

plt.figure(figsize=(10, 6))
plt.hist(distances, bins=100, range=(0, 5000), color='#0072B2')
plt.title('Histogram of straight-line distances between starting and finishing positions')
plt.xlabel('Distance (m)')
plt.xticks(range(0, 5001, 250), rotation=45)
plt.ylabel('Number of rentals')
plt.grid()
plt.savefig('vag_rad_rental_distances.png', dpi=300)

# get distances above 50 meters
distances = distances[distances > 50]

print(f'Median straight-line distance between starting and finishing positions (in meters): {distances.median():.2f}')

print(f'Maximum straight-line distance between starting and finishing positions (in meters): {distances.max():.2f}')
print(f'Minimum straight-line distance between starting and finishing positions (in meters): {distances.min():.2f}')

# percentiles
p50 = distances.quantile(0.5)
p75 = distances.quantile(0.75)
p90 = distances.quantile(0.9)
p95 = distances.quantile(0.95)
p99 = distances.quantile(0.99)
print(f'50th percentile straight-line distance (m): {p50:.2f}')
print(f'75th percentile straight-line distance (m): {p75:.2f}')
print(f'90th percentile straight-line distance (m): {p90:.2f}')
print(f'95th percentile straight-line distance (m): {p95:.2f}')
print(f'99th percentile straight-line distance (m): {p99:.2f}')

# %%
# time per distance
rentals = df_all[df_all['distance_m'] > 100]
speeds_m_per_s = rentals['distance_m'] / rentals['Duration']
speeds_km_per_h = speeds_m_per_s * 3.6

print(f'Median speed (km/h): {speeds_km_per_h.median():.2f}')
speeds_km_per_h.plot.hist(bins=100, range=(0, 25), title='Histogram of average speeds', xlabel='Speed (km/h)', ylabel='Number of rentals')

# %%
# plot rentals per year use groupby
df_all['year'] = df_all['Start time'].dt.year
rentals_per_year = df_all.groupby('year').size()
rentals_per_year.plot.bar(title='Number of rentals per year', xlabel='Year', ylabel='Number of rentals')

# %%
# plot the typical rental start times per day. group the rentals by year, month, day, hour
daily_rentals = pd.DataFrame()
daily_rentals['year'] = df_all['Start time'].dt.year
daily_rentals['month'] = df_all['Start time'].dt.month
daily_rentals['day'] = df_all['Start time'].dt.day
daily_rentals['hour'] = df_all['Start time'].dt.hour

daily_rentals = daily_rentals.groupby(['year', 'month', 'day', 'hour']).size().reset_index(name='rentals')

# plot rentals per hour of day
hourly_rentals = daily_rentals.groupby('hour')['rentals'].mean()
plt.bar(hourly_rentals.index, hourly_rentals.values)
plt.title('Average number of rentals per hour of day')
plt.xlabel('Hour of day')
plt.xticks(range(0, 24, 2), rotation=0)
plt.ylabel('Average number of rentals')
plt.show()

# %%
daily_rentals = pd.DataFrame()
daily_rentals['year'] = df_all['Start time'].dt.year
daily_rentals['month'] = df_all['Start time'].dt.month
daily_rentals['day_of_week'] = df_all['Start time'].dt.day_of_week
daily_rentals['hour'] = df_all['Start time'].dt.hour

daily_rentals = daily_rentals.groupby(['year', 'month', 'day_of_week', 'hour']).size().reset_index(name='rentals')

# plot rentals in subplots for each day of the week
plt.figure(figsize=(8, 12))

for day in range(7):
    # plot rentals per hour of day
    daily_rentals_day = daily_rentals[daily_rentals['day_of_week'] == day]
    rentals_per_hour = daily_rentals_day.groupby('hour')['rentals'].mean()

    plt.subplot(4, 2, day + 1)

    plt.bar(rentals_per_hour.index, rentals_per_hour.values, label=f'Day {day}')
    day_name = calendar.day_name[day]
    plt.title(f'{day_name}')
    plt.xlabel('Hour of day')
    plt.xticks(range(0, 24, 2), rotation=0)
    plt.ylabel('Average number of rentals')
    plt.ylim(0, 1100)

plt.tight_layout()
plt.suptitle('Average number of rentals per hour of day for each day of the week', y=1.02)
plt.show()
# %%
# show in which city the rentals start and end
print('Number of rentals starting in each city:')
nuremberg_to_fuerth = df_all[df_all['starting_in_nbg'] & df_all['finishing_in_fuerth']]
nuremberg_to_erlangen = df_all[df_all['starting_in_nbg'] & df_all['finishing_in_erlangen']]
nuremberg_to_schwabach = df_all[df_all['starting_in_nbg'] & df_all['finishing_in_schwabach']]
nuremberg_to_nuremberg = df_all[df_all['starting_in_nbg'] & df_all['finishing_in_nbg']]

fuerth_to_nuremberg = df_all[df_all['starting_in_fuerth'] & df_all['finishing_in_nbg']]
fuerth_to_fuerth = df_all[df_all['starting_in_fuerth'] & df_all['finishing_in_fuerth']]
fuerth_to_erlangen = df_all[df_all['starting_in_fuerth'] & df_all['finishing_in_erlangen']]
fuerth_to_schwabach = df_all[df_all['starting_in_fuerth'] & df_all['finishing_in_schwabach']]

erlangen_to_nuremberg = df_all[df_all['starting_in_erlangen'] & df_all['finishing_in_nbg']]
erlangen_to_fuerth = df_all[df_all['starting_in_erlangen'] & df_all['finishing_in_fuerth']]
erlangen_to_erlangen = df_all[df_all['starting_in_erlangen'] & df_all['finishing_in_erlangen']]
erlangen_to_schwabach = df_all[df_all['starting_in_erlangen'] & df_all['finishing_in_schwabach']]

schwabach_to_nuremberg = df_all[df_all['starting_in_schwabach'] & df_all['finishing_in_nbg']]
schwabach_to_fuerth = df_all[df_all['starting_in_schwabach'] & df_all['finishing_in_fuerth']]
schwabach_to_erlangen = df_all[df_all['starting_in_schwabach'] & df_all['finishing_in_erlangen']]
schwabach_to_schwabach = df_all[df_all['starting_in_schwabach'] & df_all['finishing_in_schwabach']]

# display as confusion matrix
confusion_matrix = np.array([
    [len(nuremberg_to_nuremberg), len(nuremberg_to_fuerth), len(nuremberg_to_erlangen), len(nuremberg_to_schwabach)],
    [len(fuerth_to_nuremberg), len(fuerth_to_fuerth), len(fuerth_to_erlangen), len(fuerth_to_schwabach)],
    [len(erlangen_to_nuremberg), len(erlangen_to_fuerth), len(erlangen_to_erlangen), len(erlangen_to_schwabach)],
    [len(schwabach_to_nuremberg), len(schwabach_to_fuerth), len(schwabach_to_erlangen), len(schwabach_to_schwabach)],
])

plt.figure(figsize=(8, 6))
sns.heatmap(confusion_matrix, annot=True, fmt='d', cmap='viridis', xticklabels=['Nürnberg', 'Fürth', 'Erlangen', 'Schwabach'], yticklabels=['Nürnberg', 'Fürth', 'Erlangen', 'Schwabach'])
plt.xlabel('Finishing City')
plt.ylabel('Starting City')
plt.gca().xaxis.set_label_position('top')
plt.gca().xaxis.tick_top()

plt.title('Number of rentals starting and ending in each city')
plt.show()

# %%
# how many rentals stay within the flexzone, leave the flexzone, go into the flexzone, or stay outside the flexzone
rides_in_nuremberg = df_all[df_all['starting_in_nbg'] & df_all['finishing_in_nbg']]
stay_in_flexzone = df_all[df_all['starting_in_nbg'] & df_all['finishing_in_nbg'] & df_all['starting_in_flexzone'] & df_all['finishing_in_flexzone']]
leave_flexzone = df_all[df_all['starting_in_nbg'] & df_all['finishing_in_nbg'] & df_all['starting_in_flexzone'] & ~df_all['finishing_in_flexzone']]
going_into_flexzone = df_all[df_all['starting_in_nbg'] & df_all['finishing_in_nbg'] & ~df_all['starting_in_flexzone'] & df_all['finishing_in_flexzone']]
stay_outside_flexzone = df_all[df_all['starting_in_nbg'] & df_all['finishing_in_nbg'] & ~df_all['starting_in_flexzone'] & ~df_all['finishing_in_flexzone']]

print(f'Number of rentals that start and end within the flexzone: {len(stay_in_flexzone)} ({len(stay_in_flexzone) / len(rides_in_nuremberg):.2%})')
print(f'Number of rentals that start within the flexzone but end outside: {len(leave_flexzone)} ({len(leave_flexzone) / len(rides_in_nuremberg):.2%})')
print(f'Number of rentals that start outside the flexzone but end inside: {len(going_into_flexzone)} ({len(going_into_flexzone) / len(rides_in_nuremberg):.2%})')
print(f'Number of rentals that start and end outside the flexzone: {len(stay_outside_flexzone)} ({len(stay_outside_flexzone) / len(rides_in_nuremberg):.2%})')
print(f'Total number of rentals that start and end in Nuremberg: {len(rides_in_nuremberg)}')

ending_outside_flexzone = df_all[df_all['starting_in_nbg'] & df_all['finishing_in_nbg'] &~df_all['finishing_in_flexzone']]
ending_outside_flexzone_not_at_station = ending_outside_flexzone[ending_outside_flexzone['Return place'].str.startswith('BIKE')]
print(f'Number of rentals that end outside the flexzone and not at a station: {len(ending_outside_flexzone_not_at_station)} ({len(ending_outside_flexzone_not_at_station) / len(rides_in_nuremberg):.2%})')

starting_outside_flexzone = df_all[df_all['starting_in_nbg'] & df_all['finishing_in_nbg'] &~df_all['starting_in_flexzone']]
starting_outside_flexzone_not_at_station = starting_outside_flexzone[starting_outside_flexzone['Rental place'].str.startswith('BIKE')]
print(f'Number of bikes picked up outside the free floating area but not at a station: {len(starting_outside_flexzone_not_at_station)} ({len(starting_outside_flexzone_not_at_station) / len(rides_in_nuremberg):.2%}). {len(starting_outside_flexzone_not_at_station) / len(ending_outside_flexzone_not_at_station):.2%} are therefor picked up before rebalancing operations.')

# %%
# plot starting and finishing positions
gpd.GeoDataFrame(df_all['starting_position'], geometry='starting_position', crs='EPSG:4326').to_file('vag-rad-rentals.gpkg', layer='starting_positions', driver='GPKG')

gpd.GeoDataFrame(df_all['finishing_position'], geometry='finishing_position', crs='EPSG:4326').to_file('vag-rad-rentals.gpkg', layer='finishing_position', driver='GPKG')

# %%
# get all rentals that start and end within nuremberg city polygon
df_all = df_all[df_all['starting_in_nbg'] & df_all['finishing_in_nbg']]
#%%
# number of rentals that start or end at a station
station_starts = ~df_all['Rental place'].str.startswith('BIKE')
station_destinations = ~df_all['Return place'].str.startswith('BIKE')

print(f'Number of rentals that start at a station: {station_starts.sum()}')
print(f'Number of rentals that end at a station: {station_destinations.sum()}')

station_rentals = df_all[station_starts & station_destinations]
print(f'Number of rentals that start and end at a station: {len(station_rentals)}')
station_rentals
# %%
# most popular stations
station_starts = ~df_all['Rental place'].str.startswith('BIKE')
station_destinations = ~df_all['Return place'].str.startswith('BIKE')

# get most popular starting stations
popular_starting_stations = df_all[station_starts]['Rental place'].value_counts().head(10)
print('Most popular starting stations:')
print(popular_starting_stations)

print('---')
# get most popular destination stations
popular_destination_stations = df_all[station_destinations]['Return place'].value_counts().head(10)
print('Most popular destination stations:')
print(popular_destination_stations)
# %%
# get most popular station-to-station routes
station_starts = ~df_all['Rental place'].str.startswith('BIKE')
station_destinations = ~df_all['Return place'].str.startswith('BIKE')

station_rentals = df_all[station_starts & station_destinations]
popular_routes = station_rentals.groupby(['Rental place', 'Return place']).size().sort_values(ascending=False)
# filter out entries where start and end stations are the same
popular_routes = popular_routes[popular_routes.index.get_level_values(0) != popular_routes.index.get_level_values(1)]
popular_routes = popular_routes.head(10)
print('Most popular station-to-station routes:')
print(popular_routes)
# %%
# get rentals that start and end inside the flexzone
starting_in_flexzone = df_all['starting_in_flexzone']
ending_in_flexzone = df_all['ending_in_flexzone']
flexzone_rentals = df_all[starting_in_flexzone & ending_in_flexzone]
print(f'Number of rentals that start and end within the flexzone: {len(flexzone_rentals)}')

# get rentals that start inside the flexzone but end outside
print(f'Number of rentals that start within the flexzone but end outside: {len(df_all[starting_in_flexzone & ~ending_in_flexzone])}')

# get rentals that end inside the flexzone but start outside
print(f'Number of rentals that end within the flexzone but start outside: {len(df_all[~starting_in_flexzone & ending_in_flexzone])}')

# rentals outside of the flexzone
outside_flexzone_rentals = df_all[~starting_in_flexzone & ~ending_in_flexzone]
print(f'Number of rentals that start and end outside the flexzone: {len(outside_flexzone_rentals)}')

# get rentals that end outside the flexzone but not at a station
ending_not_at_station = df_all['Return place'].str.startswith('BIKE')
ending_outside_flexzone = df_all[starting_in_flexzone & ~ending_in_flexzone & ending_not_at_station]
print(f'Number of rentals that end outside the flexzone and not at a station: {len(ending_outside_flexzone)}')

# %%

short_rentals = df_all[df_all['distance_m'] < 50]
short_rentals

# get the duration statistics for short rentals
print(f'Number of short rentals (less than 100 meters): {len(short_rentals)}')
median_duration = pd.to_timedelta(short_rentals["Duration"].median(), unit='s')
minutes, seconds = divmod(median_duration.total_seconds(), 60)
print(f'Median duration of short rentals: {int(minutes)} minutes and {int(seconds)} seconds')
# %%
# get number of bike-sharing starts and endings for heatmap
from tqdm import tqdm
from utils.vag_rad_demand_provider import VagRadDemandProvider

from utils.overpass_utils import fetch_city_polygon

place_name = 'Nürnberg'
nbg_area = fetch_city_polygon(place_name)
nbg_area

def move_polygon(polygon: shapely.Polygon, x_offset: float, y_offset: float) -> shapely.Polygon:
    # transform polygon from EPSG:4326 to EPSG:32633
    polygon = gpd.GeoSeries([polygon], crs='EPSG:4326').to_crs('32633').iloc[0]
    # move polygon
    moved_polygon = shapely.affinity.translate(polygon, xoff=x_offset, yoff=y_offset)
    # transform polygon back to EPSG:4326
    moved_polygon = gpd.GeoSeries([moved_polygon], crs='32633').to_crs('EPSG:4326').iloc[0]
    return moved_polygon

bike_sharing_demand_provider = VagRadDemandProvider()
# move polygon of 100 x 100 meters across the nbg area in steps of 100 meters
minx, miny, maxx, maxy = 11.014, 49.382, 11.175, 49.508
#minx, miny, maxx, maxy = nbg_area.bounds
start_point = shapely.Point(minx, miny)
# transform point to EPSG:32633
start_point = gpd.GeoSeries([start_point], crs='EPSG:4326').to_crs('32633').iloc[0]
polygon = shapely.box(start_point.x, start_point.y, start_point.x + 100, start_point.y + 100)
# transform polygon back to EPSG:4326
polygon = gpd.GeoSeries([polygon], crs='EPSG:32633').to_crs('EPSG:4326').iloc[0]

# get side length of polygon in EPSG:4326
side_length = shapely.Point(polygon.exterior.coords[0]).distance(shapely.Point(polygon.exterior.coords[1]))

max_starts = 0
max_endings = 0
min_starts = 0
min_endings = 0

for x in tqdm(range(int((maxx - minx) / side_length) + 1), desc='calculating max vag rad demand in 100x100m polygon', unit='x step'):
    for y in range(int((maxy - miny) / side_length) + 1):
        moved_polygon = move_polygon(polygon, x * 100, y * 100)
        demand = bike_sharing_demand_provider.get_demand_in_polygon(moved_polygon)
        max_starts = max(max_starts, demand[0])
        max_endings = max(max_endings, demand[1])
        min_starts = min(min_starts, demand[0])
        min_endings = min(min_endings, demand[1])

print(f'max vag rad demand starts in 100x100m polygon: {max_starts}')
print(f'max vag rad demand endings in 100x100m polygon: {max_endings}')
print(f'min vag rad demand starts in 100x100m polygon: {min_starts}')
print(f'min vag rad demand endings in 100x100m polygon: {min_endings}')

# %%
# get the number of unique bikes used in the year 2019
rentals_2019 = df_all[df_all['Start time'].dt.year == 2019]

bike_ids_start = rentals_2019[rentals_2019['Rental place'].str.startswith('BIKE')]['Rental place']
bike_ids_end = rentals_2019[rentals_2019['Return place'].str.startswith('BIKE')]['Return place']

unique_bike_ids = set()
unique_bike_ids.update(bike_ids_start.values)
unique_bike_ids.update(bike_ids_end.values)

print(f'Number of unique bikes used in 2019: {len(unique_bike_ids)}')

# %%
# get the number of unique bikes used in the year 2024
rentals_2024 = df_all[df_all['Start time'].dt.year == 2024]

bike_ids_start = rentals_2024[rentals_2024['Rental place'].str.startswith('BIKE')]['Rental place']
bike_ids_end = rentals_2024[rentals_2024['Return place'].str.startswith('BIKE')]['Return place']

unique_bike_ids = set()
unique_bike_ids.update(bike_ids_start.values)
unique_bike_ids.update(bike_ids_end.values)

print(f'Number of unique bikes used in 2024: {len(unique_bike_ids)}')
# %%
