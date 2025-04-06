# %%
# imports
import geopandas as gpd
import pandas as pd
import shapely
import osmnx as ox
import matplotlib.pyplot as plt
import numpy as np

# %%
# load accident statistics
accidents_2023 = pd.read_csv('accident_statistics/Unfallorte2023_LinRef.csv', sep=';')
accidents_2023
# %%
wgs84_coords = [shapely.Point(x.replace(',','.'), y.replace(',','.')) for x, y in zip(accidents_2023['XGCSWGS84'], accidents_2023['YGCSWGS84'])]

etrs89_32n_coords = [shapely.Point(x.replace(',','.'), y.replace(',','.')) for x, y in zip(accidents_2023['LINREFX'], accidents_2023['LINREFY'])]
# %%
accidents_2023['WSG84'] = wgs84_coords
accidents_2023['ETRS89'] = etrs89_32n_coords
# %%
accidents_2023_bavaria = accidents_2023[accidents_2023['ULAND'] == 9]
accidents_2023_bavaria

# %%
nuernberg_polygon = ox.geocode_to_gdf('Nürnberg').geometry[0]
# %%
def point_is_in_polygon(point: shapely.Point, polygon: shapely.Polygon) -> bool:
    return polygon.contains(point)
# %%
accidents_2023_nuernberg = accidents_2023_bavaria[point_is_in_polygon(accidents_2023_bavaria['WSG84'], nuernberg_polygon)]
# %%
accidents_2023_nuernberg_bike = accidents_2023_nuernberg[accidents_2023_nuernberg['IstRad'] == 1]
# %%

gpd.GeoDataFrame(accidents_2023_nuernberg_bike, geometry='WSG84').to_file(filename='accidents_2023.gpkg', layer='nuernberg_bike', driver='GPKG')
# %%
# plot accidents by month
month, count = np.unique(accidents_2023_nuernberg_bike['UMONAT'], return_counts=True)
plt.bar(month, count)
month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
plt.xticks(month, month_names)
plt.title('Accidents per Month')
plt.xlabel('Month')
plt.ylabel('Number of Accidents')
plt.grid(False)
# %%
# plot accidents by day of week
day_of_week, count = np.unique(accidents_2023_nuernberg_bike['UWOCHENTAG'], return_counts=True)
plt.bar(day_of_week, count)
day_names = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
plt.xticks(day_of_week, day_names)
plt.title('Accidents per Day of Week')
plt.xlabel('Day of Week')
plt.ylabel('Number of Accidents')
plt.grid(False)
# %%
# plot accidents by hour of day
hour_of_day, count = np.unique(accidents_2023_nuernberg_bike['USTUNDE'], return_counts=True)
plt.bar(hour_of_day, count)
hour_names = [f'{hour}:00' for hour in hour_of_day]
plt.xticks(hour_of_day, hour_names)
plt.xticks(rotation=45)
plt.title('Accidents per Hour of Day')
plt.xlabel('Hour of Day')
plt.ylabel('Number of Accidents')
plt.grid(False)
# %%
# plot accidents by light condition
light_condition, count = np.unique(accidents_2023_nuernberg_bike['ULICHTVERH'], return_counts=True)
plt.bar(light_condition, count)
light_condition_names = ['Daylight', 'Dawn/Dusk', 'Darkness']
plt.xticks(light_condition, light_condition_names)
# plot the counts above the bars
for i, c in enumerate(count):
    plt.text(light_condition[i], c, str(c), ha='center', va='bottom')
plt.title('Accidents by Light Condition')
plt.xlabel('Light Condition')
plt.ylabel('Number of Accidents')
plt.grid(False)
plt.show()
# %%
# plot accidents by street condition
street_condition, count = np.unique(accidents_2023_nuernberg_bike['IstStrassenzustand'], return_counts=True)
plt.bar(street_condition, count)
street_condition_names = ['Dry', 'Wet', 'Snow/Ice']
plt.xticks(street_condition, street_condition_names)
# plot the counts above the bars
for i, c in enumerate(count):
    plt.text(street_condition[i], c, str(c), ha='center', va='bottom')
plt.title('Accidents by Street Condition')
plt.xlabel('Street Condition')
plt.ylabel('Number of Accidents')
plt.grid(False)
plt.show()

# %%
# plot accidents by light condition and street condition
counts, x_bins, y_bins, _ = plt.hist2d(accidents_2023_nuernberg_bike['ULICHTVERH'], accidents_2023_nuernberg_bike['IstStrassenzustand'], bins=(3, 3), cmap='Blues')

# move the ticks to the center of the bins
bin_w = (max(x_bins) - min(x_bins)) / (len(x_bins) - 1)
plt.xticks(np.arange(min(x_bins)+bin_w/2, max(x_bins), bin_w), street_condition_names)
plt.xlim(x_bins[0], x_bins[-1])

bin_h = (max(y_bins) - min(y_bins)) / (len(y_bins) - 1)
plt.yticks(np.arange(min(y_bins)+bin_h/2, max(y_bins), bin_h), light_condition_names)
plt.ylim(y_bins[0], y_bins[-1])

# plot the counts inside of the bins
for i in range(len(x_bins)-1):
    for j in range(len(y_bins)-1):
        # get text color based on the background color
        cmap = plt.get_cmap('Blues')
        norm = plt.Normalize(vmin=0, vmax=np.max(counts))
        color = cmap(norm(counts[j][i]))
        # if the background color is dark, use white text
        if np.mean(color[:3]) < 0.5:
            text_color = 'white'
        else:
            text_color = 'black'
        plt.text(x_bins[i]+bin_w/2, y_bins[j]+bin_h/2, int(counts[j][i]), ha='center', va='center', color=text_color)

plt.title('Accidents by Light Condition and Street Condition')
plt.xlabel('Street Condition')
plt.ylabel('Light Condition')
plt.colorbar(label='Number of Accidents')
plt.grid(False)
plt.show()

# %%
# plot accidents by hour of day and month
counts, x_bins, y_bins, _ = plt.hist2d(accidents_2023_nuernberg_bike['USTUNDE'], accidents_2023_nuernberg_bike['UMONAT'], bins=(24,12), cmap='Blues')
print(counts.shape)
# move the ticks to the center of the bins
bin_w = (max(x_bins) - min(x_bins)) / (len(x_bins) - 1)
plt.xticks(np.arange(min(x_bins)+bin_w/2, max(x_bins), bin_w), hour_names)
plt.xlim(x_bins[0], x_bins[-1])
bin_h = (max(y_bins) - min(y_bins)) / (len(y_bins) - 1)
plt.yticks(np.arange(min(y_bins)+bin_h/2, max(y_bins), bin_h), month_names)
plt.ylim(y_bins[0], y_bins[-1])
# plot the counts inside of the bins
for i in range(len(x_bins)-1):
    for j in range(len(y_bins)-1):
        if counts[i][j] == 0:
            continue
        # get text color based on the background color
        cmap = plt.get_cmap('Blues')
        norm = plt.Normalize(vmin=0, vmax=np.max(counts))
        color = cmap(norm(counts[i][j]))
        # if the background color is dark, use white text
        if np.mean(color[:3]) < 0.5:
            text_color = 'white'
        else:
            text_color = 'black'
        
        plt.text(x_bins[i]+bin_w/2, y_bins[j]+bin_h/2, int(counts[i][j]), ha='center', va='center', color=text_color)
plt.title('Accidents by Hour of Day and Month')
plt.xlabel('Hour of Day')
plt.xticks(rotation=45)
plt.ylabel('Month')
plt.colorbar(label='Number of Accidents')
plt.grid(False)
# resize the figure
fig = plt.gcf()
fig.set_size_inches(12, 6)
plt.show()

# %%
