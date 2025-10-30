# %%
# imports
import pandas as pd
import geopandas as gpd
import shapely
import matplotlib.pyplot as plt
import calendar

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

# %%
# calculate straight-line distances between starting and finishing positions
distances = df_all['distance_m']

print(f'Median straight-line distance between starting and finishing positions (in meters): {distances.median():.2f}')

distances.plot.hist(bins=100, range=(100, 5000), title='Histogram of straight-line distances between starting and finishing positions', xlabel='Distance (m)', ylabel='Number of rentals')

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
# plot starting and finishing positions
gpd.GeoDataFrame(df_all['starting_position'], geometry='starting_position').to_file('vag-rad-rentals.gpkg', layer='starting_positions', driver='GPKG')

gpd.GeoDataFrame(df_all['finishing_position'], geometry='finishing_position').to_file('vag-rad-rentals.gpkg', layer='finishing_position', driver='GPKG')

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
popular_routes = station_rentals.groupby(['Rental place', 'Return place']).size().sort_values(ascending=False).head(10)
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
