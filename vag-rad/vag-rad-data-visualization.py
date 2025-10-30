# %%
# imports
import pandas as pd
import geopandas as gpd
import shapely
from utils.overpass_utils import fetch_city_polygon

# %%
# fetch city polygon for nuremberg
nbg_polygon = fetch_city_polygon('Nürnberg')

# merge all years into a single dataframe
df_2019_2020 = pd.read_csv('vag-rad-data/processed/2019_2020_Ausleihen_Kundendetails.csv')
df_2021 = pd.read_csv('vag-rad-data/processed/2021_Ausleihen_Kundendetails.csv')
df_2022 = pd.read_csv('vag-rad-data/processed/2022_Ausleihen_Kundendetails.csv')
df_2023 = pd.read_csv('vag-rad-data/processed/2023_Ausleihen_Kundendetails.csv')
df_2024 = pd.read_csv('vag-rad-data/processed/2024_Ausleihen_Kundendetails.csv')

df_all = pd.concat([df_2019_2020, df_2021, df_2022, df_2023, df_2024], ignore_index=True)

df_all['starting_position'] = shapely.from_wkt(df_all['starting_position'])
df_all['finishing_position'] = shapely.from_wkt(df_all['finishing_position'])

# %%
print(f'Total number of rentals from 2019 to 2024: {len(df_all)}')
median_duration = pd.to_timedelta(df_all["Duration"].median(), unit='s')
minutes, seconds = divmod(median_duration.total_seconds(), 60)
print(f'Median rental duration: {int(minutes)} minutes and {int(seconds)} seconds')

# %%
# map starting and finishing positions from wkt
df_all['starting_position'] = gpd.GeoSeries.from_wkt(df_all['starting_position'], crs='EPSG:4326')
df_all['finishing_position'] = gpd.GeoSeries.from_wkt(df_all['finishing_position'], crs='EPSG:4326')

#%%
# calculate straight-line distances between starting and finishing positions
distances = gpd.GeoDataFrame(df_all[['starting_position', 'finishing_position']], crs='EPSG:4326', geometry='starting_position')

# transform starting and finishing positions to epsg 25832 for distance calculation
distances['starting_position'] = distances['starting_position'].to_crs(epsg=25832)
distances['finishing_position'] = distances['finishing_position'].to_crs(epsg=25832)

# calculate distances between starting and finishing positions in meters
distances['distance_m'] = distances.apply(lambda row: row['starting_position'].distance(row['finishing_position']), axis=1)

print(f'Median straight-line distance between starting and finishing positions (in meters): {distances["distance_m"].median():.2f}')

distances['distance_m'].plot.hist(bins=100, range=(100, 5000), title='Histogram of straight-line distances between starting and finishing positions', xlabel='Distance (m)', ylabel='Number of rentals')

# %%
# time per distance
durations = df_all['Duration']  # in seconds
speeds_m_per_s = distances['distance_m'] / durations
speeds_km_per_h = speeds_m_per_s * 3.6

print(f'Median speed (km/h): {speeds_km_per_h.median():.2f}')
speeds_km_per_h.plot.hist(bins=100, range=(0, 25), title='Histogram of average speeds', xlabel='Speed (km/h)', ylabel='Number of rentals')

# %%
# plot rentals per year use groupby
df_all['Start time'] = pd.to_datetime(df_all['Start time'])
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
hourly_rentals.plot.bar(title='Average number of rentals per hour of day', xlabel='Hour of day', ylabel='Average number of rentals')

# %%
import matplotlib.pyplot as plt
import calendar

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
    plt.ylabel('Average number of rentals')
    # make the yticks from 0 to 1100
    plt.ylim(0, 1100)

plt.tight_layout()
plt.suptitle('Average number of rentals per hour of day for each day of the week', y=1.02)
plt.show()
# %%
# plot starting and finishing positions
gpd.GeoDataFrame(df_all['starting_position'], geometry='starting_position').to_file('vag-rad-rentals.gpkg', layer='starting_positions', driver='GPKG')

gpd.GeoDataFrame(df_all['finishing_position'], geometry='finishing_position').to_file('vag-rad-rentals.gpkg', layer='finishing_position', driver='GPKG')

# %%

# get all rentals that start and end within nuremberg city polygon
gpdf_start_within_nbg = gpd.GeoDataFrame(df_all, geometry='starting_position', crs='EPSG:4326')

gpdf_start_within_nbg = gpdf_start_within_nbg[gpdf_start_within_nbg['starting_position'].within(nbg_polygon)]

gpdf_end_within_nbg = gpd.GeoDataFrame(gpdf_start_within_nbg, geometry='finishing_position', crs='EPSG:4326')

gpdf_end_within_nbg = gpdf_end_within_nbg[gpdf_end_within_nbg['finishing_position'].within(nbg_polygon)]

# join both dataframes to get rentals that start and end within nuremberg
gpdf_nbg = gpd.GeoDataFrame(gpdf_end_within_nbg, geometry='starting_position', crs='EPSG:4326')

gpdf_nbg
# %%
# get number of rides that start at a station and end at a station
station_rentals = df_all[(df_all['Rental place']) & (df_all['finishing_station_id'].notnull())]

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
popular_routes = station_rentals.groupby(['Rental place', 'Return place']).size().sort_values(ascending=False).head(10)
print('Most popular station-to-station routes:')
print(popular_routes)
# %%
# get rentals that start and end inside the flexzone
from utils.vag_rad_utils import get_vag_rad_flexzone, vag_rad_city_ids
flexzone_nbg = get_vag_rad_flexzone(vag_rad_city_ids['Nürnberg'])

starting_in_flexzone = gpd.GeoSeries(df_all['starting_position'], crs='EPSG:4326').within(flexzone_nbg)
ending_in_flexzone = gpd.GeoSeries(df_all['finishing_position'], crs='EPSG:4326').within(flexzone_nbg)

flexzone_rentals = df_all[starting_in_flexzone & ending_in_flexzone]
print(f'Number of rentals that start and end within the flexzone: {len(flexzone_rentals)}')

# get rentals that start inside the flexzone but end outside
print(f'Number of rentals that start within the flexzone but end outside: {len(df_all[starting_in_flexzone & ~ending_in_flexzone])}')

# get rentals that end inside the flexzone but start outside
print(f'Number of rentals that end within the flexzone but start outside: {len(df_all[~starting_in_flexzone & ending_in_flexzone])}')

# rentals outside of the flexzone
outside_flexzone_rentals = df_all[~starting_in_flexzone & ~ending_in_flexzone]
print(f'Number of rentals that start and end outside the flexzone: {len(outside_flexzone_rentals)}')
# %%

