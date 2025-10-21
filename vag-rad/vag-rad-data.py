# %%
# imports
import pandas as pd
import geopandas as gpd
import shapely.geometry

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

# show if dataframe has missing values
assert df_1.isna().sum().sum() == 0, f'dataframe has missing values {df_1.isna().sum()}'
assert all(not point.is_empty for point in df_1['starting_position'].values), "There are empty geometries in 'starting_position'"
assert all(not point.is_empty for point in df_1['finishing_position'].values), "There are empty geometries in 'finishing_position'"

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

# show if dataframe has missing values
assert df_2.isna().sum().sum() == 0, f'dataframe has missing values {df_2.isna().sum()}'
assert all(not point.is_empty for point in df_2['starting_position'].values), "There are empty geometries in 'starting_position'"
assert all(not point.is_empty for point in df_2['finishing_position'].values), "There are empty geometries in 'finishing_position'"

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

df_all = pd.concat([df_2019_2020, df_2021, df_2022, df_2023, df_2024], ignore_index=True)

print(f'Total number of rentals from 2019 to 2024: {len(df_all)}')
print(f'Median rental duration (in minutes): {df_all["Duration"].median()/60:.2f}')

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
# plot starting and finishing positions
gpd.GeoDataFrame(df_all['starting_position'], geometry='starting_position').to_file('vag-rad-rentals.gpkg', layer='starting_positions', driver='GPKG')

gpd.GeoDataFrame(df_all['finishing_position'], geometry='finishing_position').to_file('vag-rad-rentals.gpkg', layer='finishing_position', driver='GPKG')
# %%
