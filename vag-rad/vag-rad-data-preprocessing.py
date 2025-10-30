# %%
# imports
import pandas as pd
import geopandas as gpd
import shapely.geometry
import numpy as np
from utils.overpass_utils import fetch_city_polygon
from utils.vag_rad_utils import get_vag_rad_flexzone, vag_rad_city_ids
import time

# %%
# Ausleihen 2019 und 2020
df = pd.read_excel('vag-rad-data/raw/2019_2020_Archiv_Ausleihen_Kundendetails.xlsx')

# convert lat and lng to points
df['starting_position'] = gpd.points_from_xy(df['Start lng'], df['Start lat'], crs='EPSG:4326')
df['finishing_position'] = gpd.points_from_xy(df['End lng'], df['End lat'], crs='EPSG:4326')

# drop unnecessary data
df.drop(columns=['Start lat', 'Start lng', 'End lat', 'End lng', 'Monat', 'Bike id'], inplace=True)

# drop rows with empty starting or finishing position
indices_to_drop = df[df['starting_position'] == shapely.geometry.Point()].index
df.drop(indices_to_drop, inplace=True)

indices_to_drop = df[df['finishing_position'] == shapely.geometry.Point()].index
df.drop(indices_to_drop, inplace=True)

# show if dataframe has missing values
assert df.isna().sum().sum() == 0, f'dataframe has missing values {df.isna().sum()}'
assert all(not point.is_empty for point in df['starting_position'].values), "There are empty geometries in 'starting_position'"
assert all(not point.is_empty for point in df['finishing_position'].values), "There are empty geometries in 'finishing_position'"
assert all(type(v) is np.datetime64 for v in df['Start time'].values), "There are non-datetime values in 'Start time'"

# convert Start time and End time to ISO format
df['Start time'] = pd.to_datetime(df['Start time'])
df['End time'] = pd.to_datetime(df['End time'])
df['Start time'] = df['Start time'].dt.strftime('%Y-%m-%dT%H:%M:%S')
df['End time'] = df['End time'].dt.strftime('%Y-%m-%dT%H:%M:%S')

# save cleaned data to file
df.to_csv('vag-rad-data/processed/2019_2020_Ausleihen_Kundendetails.csv', index=False)

# %%
# Ausleihen 2021
df = pd.read_excel('vag-rad-data/raw/2021_Ausleihe_Kundendetails.xlsx')

# convert lat and lng to points
df['starting_position'] = gpd.points_from_xy(df['Start lng'], df['Start lat'], crs='EPSG:4326')
df['finishing_position'] = gpd.points_from_xy(df['End lng'], df['End lat'], crs='EPSG:4326')

# drop unnecessary data
df.drop(columns=['Start lat', 'Start lng', 'End lat', 'End lng', 'Monat', 'Bike id'], inplace=True)

# show if dataframe has missing values
assert df.isna().sum().sum() == 0, f'dataframe has missing values {df.isna().sum()}'
assert all(not point.is_empty for point in df['starting_position'].values), "There are empty geometries in 'starting_position'"
assert all(not point.is_empty for point in df['finishing_position'].values), "There are empty geometries in 'finishing_position'"
assert all(type(v) is np.datetime64 for v in df['Start time'].values), "There are non-datetime values in 'Start time'"

# convert Start time and End time to ISO format
df['Start time'] = pd.to_datetime(df['Start time'])
df['End time'] = pd.to_datetime(df['End time'])
df['Start time'] = df['Start time'].dt.strftime('%Y-%m-%dT%H:%M:%S')
df['End time'] = df['End time'].dt.strftime('%Y-%m-%dT%H:%M:%S')

# save cleaned data to file
df.to_csv('vag-rad-data/processed/2021_Ausleihen_Kundendetails.csv', index=False)

# %%
# Ausleihen 2022
df = pd.read_excel('vag-rad-data/raw/2022_Ausleihen_Kundendetails.xlsx')

# convert lat and lng to points
df['starting_position'] = gpd.points_from_xy(df['Start lng'], df['Start lat'], crs='EPSG:4326')
df['finishing_position'] = gpd.points_from_xy(df['End lng'], df['End lat'], crs='EPSG:4326')

# drop unnecessary data
df.drop(columns=['Start lat', 'Start lng', 'End lat', 'End lng', 'First name', 'Last name', 'Phone number', 'Email', 'Bike id'], inplace=True)

# show if dataframe has missing values
assert df.isna().sum().sum() == 0, f'dataframe has missing values {df.isna().sum()}'
assert all(not point.is_empty for point in df['starting_position'].values), "There are empty geometries in 'starting_position'"
assert all(not point.is_empty for point in df['finishing_position'].values), "There are empty geometries in 'finishing_position'"
assert all(type(v) is np.datetime64 for v in df['Start time'].values), "There are non-datetime values in 'Start time'"

# convert Start time and End time to ISO format
df['Start time'] = pd.to_datetime(df['Start time'])
df['End time'] = pd.to_datetime(df['End time'])
df['Start time'] = df['Start time'].dt.strftime('%Y-%m-%dT%H:%M:%S')
df['End time'] = df['End time'].dt.strftime('%Y-%m-%dT%H:%M:%S')

# save cleaned data to file
df.to_csv('vag-rad-data/processed/2022_Ausleihen_Kundendetails.csv', index=False)

# %%
# Ausleihen 2023
df = pd.read_excel('vag-rad-data/raw/2023_Ausleihen_Kundendetails.xlsx')

# convert lat and lng to points
df['starting_position'] = gpd.points_from_xy(df['Start lng'], df['Start lat'], crs='EPSG:4326')
df['finishing_position'] = gpd.points_from_xy(df['End lng'], df['End lat'], crs='EPSG:4326')

df.drop(columns=['Start lat', 'Start lng', 'End lat', 'End lng'], inplace=True)

# compute start time where missing
for idx, row in df.iterrows():
    if pd.isna(row['Start time']):
        df.at[idx, 'Start time'] = row['End time'] - pd.Timedelta(seconds=row['Duration'])

assert df.isna().sum().sum() == 0, f'dataframe has missing values {df.isna().sum()}'
assert all(not point.is_empty for point in df['starting_position'].values), "There are empty geometries in 'starting_position'"
assert all(not point.is_empty for point in df['finishing_position'].values), "There are empty geometries in 'finishing_position'"
assert all(type(v) is np.datetime64 for v in df['Start time'].values), "There are non-datetime values in 'Start time'"

# convert Start time and End time to ISO format
df['Start time'] = pd.to_datetime(df['Start time'])
df['End time'] = pd.to_datetime(df['End time'])
df['Start time'] = df['Start time'].dt.strftime('%Y-%m-%dT%H:%M:%S')
df['End time'] = df['End time'].dt.strftime('%Y-%m-%dT%H:%M:%S')

# save cleaned data to file
df.to_csv('vag-rad-data/processed/2023_Ausleihen_Kundendetails.csv', index=False)

# %%
# Ausleihen 2024
df_1 = pd.read_csv('vag-rad-data/raw/VAG Kddetails 01_24-08_24.csv', sep=';')

# replace comma with dot in start_lat, start_lng, end_lat, end_lng columns
df_1['start_lat'] = df_1['start_lat'].str.replace(',', '.').astype(float)
df_1['start_lng'] = df_1['start_lng'].str.replace(',', '.').astype(float)
df_1['end_lat'] = df_1['end_lat'].str.replace(',', '.').astype(float)
df_1['end_lng'] = df_1['end_lng'].str.replace(',', '.').astype(float)

# convert lat and lng to points
df_1['starting_position'] = gpd.points_from_xy(df_1['start_lng'], df_1['start_lat'], crs='EPSG:4326')
df_1['finishing_position'] = gpd.points_from_xy(df_1['end_lng'], df_1['end_lat'], crs='EPSG:4326')

# drop unnecessary data
df_1.drop(columns=['start_lat', 'start_lng', 'end_lat', 'end_lng', 'Unnamed: 9', 'Unnamed: 10', 'Unnamed: 11'], inplace=True)

df_1.rename(columns={'start_time':'Start time', 'end_time':'End time', 'duration':'Duration', 'start_place_id':'Rental place', 'end_place_id':'Return place'}, inplace=True)

# parse start and end times to datetime
df_1['Start time'] = pd.to_datetime(df_1['Start time'], format='%d.%m.%Y %H:%M')
df_1['End time'] = pd.to_datetime(df_1['End time'], format='%d.%m.%Y %H:%M')

# show if dataframe has missing values
assert df_1.isna().sum().sum() == 0, f'dataframe has missing values {df_1.isna().sum()}'
assert all(not point.is_empty for point in df_1['starting_position'].values), "There are empty geometries in 'starting_position'"
assert all(not point.is_empty for point in df_1['finishing_position'].values), "There are empty geometries in 'finishing_position'"
assert all(type(v) is np.datetime64 for v in df_1['Start time'].values), "There are non-datetime values in 'Start time'"

# convert Start time and End time to ISO format
df_1['Start time'] = pd.to_datetime(df_1['Start time'])
df_1['End time'] = pd.to_datetime(df_1['End time'])
df_1['Start time'] = df_1['Start time'].dt.strftime('%Y-%m-%dT%H:%M:%S')
df_1['End time'] = df_1['End time'].dt.strftime('%Y-%m-%dT%H:%M:%S')

df_2 = pd.read_csv('vag-rad-data/raw/VAG Kddetails 08_24-12_24.csv', sep=';')

# replace comma with dot in start_lat, start_lng, end_lat, end_lng columns
df_2['start_lat'] = df_2['start_lat'].str.replace(',', '.').astype(float)
df_2['start_lng'] = df_2['start_lng'].str.replace(',', '.').astype(float)
df_2['end_lat'] = df_2['end_lat'].str.replace(',', '.').astype(float)
df_2['end_lng'] = df_2['end_lng'].str.replace(',', '.').astype(float)

# convert lat and lng to points
df_2['starting_position'] = gpd.points_from_xy(df_2['start_lng'], df_2['start_lat'], crs='EPSG:4326')
df_2['finishing_position'] = gpd.points_from_xy(df_2['end_lng'], df_2['end_lat'], crs='EPSG:4326')

# drop unnecessary data
df_2.drop(columns=['start_lat', 'start_lng', 'end_lat', 'end_lng'], inplace=True)

df_2.rename(columns={'start_time':'Start time', 'end_time':'End time', 'duration':'Duration', 'start_place_id':'Rental place', 'end_place_id':'Return place'}, inplace=True)

# parse start and end times to datetime
df_2['Start time'] = pd.to_datetime(df_2['Start time'], format='%d.%m.%Y %H:%M')
df_2['End time'] = pd.to_datetime(df_2['End time'], format='%d.%m.%Y %H:%M')

# show if dataframe has missing values
assert df_2.isna().sum().sum() == 0, f'dataframe has missing values {df_2.isna().sum()}'
assert all(not point.is_empty for point in df_2['starting_position'].values), "There are empty geometries in 'starting_position'"
assert all(not point.is_empty for point in df_2['finishing_position'].values), "There are empty geometries in 'finishing_position'"
assert all(type(v) is np.datetime64 for v in df_2['Start time'].values), "There are non-datetime values in 'Start time'"

# convert Start time and End time to ISO format
df_2['Start time'] = pd.to_datetime(df_2['Start time'])
df_2['End time'] = pd.to_datetime(df_2['End time'])
df_2['Start time'] = df_2['Start time'].dt.strftime('%Y-%m-%dT%H:%M:%S')
df_2['End time'] = df_2['End time'].dt.strftime('%Y-%m-%dT%H:%M:%S')

# merge both dataframes
df = pd.concat([df_1, df_2], ignore_index=True)

# save cleaned data to file
df.to_csv('vag-rad-data/processed/2024_Ausleihen_Kundendetails.csv', index=False)

# %%
# merge all years into a single dataframe
df_2019_2020 = pd.read_csv('vag-rad-data/processed/2019_2020_Ausleihen_Kundendetails.csv')
df_2021 = pd.read_csv('vag-rad-data/processed/2021_Ausleihen_Kundendetails.csv')
df_2022 = pd.read_csv('vag-rad-data/processed/2022_Ausleihen_Kundendetails.csv')
df_2023 = pd.read_csv('vag-rad-data/processed/2023_Ausleihen_Kundendetails.csv')
df_2024 = pd.read_csv('vag-rad-data/processed/2024_Ausleihen_Kundendetails.csv')

df = pd.concat([df_2019_2020, df_2021, df_2022, df_2023, df_2024], ignore_index=True)

df['starting_position'] = shapely.from_wkt(df['starting_position'])
df['finishing_position'] = shapely.from_wkt(df['finishing_position'])

df = gpd.GeoDataFrame(df, geometry='starting_position', crs='EPSG:4326')

print('calculating straight-line distances...')
# change crs of geoSeries to epsg 25832
starting_points = gpd.GeoSeries(df['starting_position'], crs='EPSG:4326').to_crs(epsg=25832)
finishing_points = gpd.GeoSeries(df['finishing_position'], crs='EPSG:4326').to_crs(epsg=25832)

# calculate straight-line distances between starting and finishing positions
start = time.time()
distances = starting_points.distance(finishing_points)
df['distance_m'] = distances
print(f'Calculated distances for {len(df)} rows in {time.time() - start:.2f} seconds')
print('---')

# calculate if positions are within nuremberg city polygon
print('calculating if positions are within Nürnberg city polygon...')
nbg_polygon = fetch_city_polygon('Nürnberg')

start = time.time()
starting_positions_in_nbg = gpd.GeoSeries(df['starting_position'], crs='EPSG:4326').within(nbg_polygon)
finishing_positions_in_nbg = gpd.GeoSeries(df['finishing_position'], crs='EPSG:4326').within(nbg_polygon)
df['starting_in_nbg'] = starting_positions_in_nbg
df['finishing_in_nbg'] = finishing_positions_in_nbg
print(f'Calculated if positions are within Nürnberg for {len(df)} rows in {time.time() - start:.2f} seconds')
print('---')

# calculate if positions are within nuremberg free floating zone
print('calculating if positions are within Nürnberg flexzone...')
flexzone_nbg = get_vag_rad_flexzone(vag_rad_city_ids['Nürnberg'])

start = time.time()
starting_in_flexzone = gpd.GeoSeries(df['starting_position'], crs='EPSG:4326').within(flexzone_nbg)
ending_in_flexzone = gpd.GeoSeries(df['finishing_position'], crs='EPSG:4326').within(flexzone_nbg)
df['starting_in_flexzone'] = starting_in_flexzone
df['ending_in_flexzone'] = ending_in_flexzone
print(f'Calculated if positions are within Nürnberg flexzone for {len(df)} rows in {time.time() - start:.2f} seconds')
print('---')

# saving pre-calculated columns to csv
df.to_csv('vag-rad-data/processed/All_Ausleihen_Kundendetails.csv', index=False)
# %%
