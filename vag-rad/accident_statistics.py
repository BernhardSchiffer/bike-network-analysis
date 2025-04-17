# %%
# imports
import geopandas as gpd
import pandas as pd
import shapely
import osmnx as ox
import matplotlib.pyplot as plt
import numpy as np

# %%
# load every file in directory
import os
directory = 'accident_statistics'
files = []
for filename in os.listdir(directory):
    if filename.endswith('.csv'):
        filepath = os.path.join(directory, filename)
        files.append(filepath)
files

accidents = []
for file in files:
    accidents.append(pd.read_csv(file, sep=';'))

accidents = pd.concat(accidents, copy=False)
accidents
# %%
# load accident statistics
accidents_2023 = pd.read_csv('accident_statistics/Unfallorte2023_LinRef.csv', sep=';')
accidents_2023
# %%
wgs84_coords = [shapely.Point(x.replace(',','.'), y.replace(',','.')) for x, y in zip(accidents['XGCSWGS84'], accidents['YGCSWGS84'])]

etrs89_32n_coords = [shapely.Point(x.replace(',','.'), y.replace(',','.')) for x, y in zip(accidents['LINREFX'], accidents['LINREFY'])]
# %%
accidents['WSG84'] = wgs84_coords
accidents['ETRS89'] = etrs89_32n_coords
# %%
accidents_bavaria = accidents[accidents['ULAND'] == 9]
accidents_bavaria

# %%
nuernberg_polygon = ox.geocode_to_gdf('Nürnberg').geometry[0]
# %%
def point_is_in_polygon(point: shapely.Point, polygon: shapely.Polygon) -> bool:
    return polygon.contains(point)
# %%
accidents_nuernberg = accidents_bavaria[point_is_in_polygon(accidents_bavaria['WSG84'], nuernberg_polygon)]
# %%
accidents_nuernberg_bike = accidents_nuernberg[accidents_nuernberg['IstRad'] == 1]
# %%
# mapping functions for accident attributes
def map_accident_type(n: int) -> str:
    accident_types = {
        1: 'Zusammenstoß mit anfahrendem/anhaltendem/ruhendem Fahrzeug',
        2: 'Zusammenstoß mit vorausfahrendem/wartendem Fahrzeug',
        3: 'Zusammenstoß mit seitlich in gleicher Richtung fahrendem Fahrzeug',
        4: 'Zusammenstoß mit entgegenkommendem Fahrzeug',
        5: 'Zusammenstoß mit einbiegendem/kreuzendem Fahrzeug',
        6: 'Zusammenstoß zwischen Fahrzeug und Fußgänger',
        7: 'Aufprall auf Fahrbahnhindernis',
        8: 'Abkommen von Fahrbahn nach rechts',
        9: 'Abkommen von Fahrbahn nach links',
        0: 'Unfall anderer Art'
    }
    return accident_types.get(n, 'Unbekannte Unfallart')

def map_day_of_week(n: int) -> str:
    days_of_week = {
        1: 'Sonntag',
        2: 'Montag',
        3: 'Dienstag',
        4: 'Mittwoch',
        5: 'Donnerstag',
        6: 'Freitag',
        7: 'Samstag'
    }
    return days_of_week.get(n, 'Unbekannter Wochentag')

def map_month(n: int) -> str:
    months = {
        1: 'Januar',
        2: 'Februar',
        3: 'März',
        4: 'April',
        5: 'Mai',
        6: 'Juni',
        7: 'Juli',
        8: 'August',
        9: 'September',
        10: 'Oktober',
        11: 'November',
        12: 'Dezember'
    }
    return months.get(n, 'Unbekannter Monat')
def map_hour(n: int) -> str:
    hours = {
        0: '00:00 - 01:00',
        1: '01:00 - 02:00',
        2: '02:00 - 03:00',
        3: '03:00 - 04:00',
        4: '04:00 - 05:00',
        5: '05:00 - 06:00',
        6: '06:00 - 07:00',
        7: '07:00 - 08:00',
        8: '08:00 - 09:00',
        9: '09:00 - 10:00',
        10: '10:00 - 11:00',
        11: '11:00 - 12:00',
        12: '12:00 - 13:00',
        13: '13:00 - 14:00',
        14: '14:00 - 15:00',
        15: '15:00 - 16:00',
        16: '16:00 - 17:00',
        17: '17:00 - 18:00',
        18: '18:00 - 19:00',
        19: '19.00 - 20.00',
        20: '20.00 - 21.00',
        21: '21.00 - 22.00',
        22: '22.00 - 23.00',
        23: '23.00 - 24.00'
    }
    return hours.get(n, 'Unbekannte Uhrzeit')

def map_accident_category(n: int) -> str:
    categories = {
        1: 'Unfall mit Getöteten',
        2: 'Unfall mit Schwerverletzten',
        3: 'Unfall mit Leichtverletzten',
    }
    return categories.get(n, 'Unbekannte Unfallkategorie')

def map_accident_type1(n: int) -> str:
    accident_types = {
        1: 'Fahrunfall',
        2: 'Abbiegeunfall',
        3: 'Einbiegen / Kreuzen-Unfall',
        4: 'Überscheiten-Unfall',
        5: 'Unfall durch ruhenden Verkehr',
        6: 'Unfall im Längsverkehr',
        7: 'sonstiger Unfall',
    }
    return accident_types.get(n, 'Unbekannte Unfallart')

def map_light_condition(n: int) -> str:
    light_conditions = {
        0: 'Tageslicht',
        1: 'Dämmerung',
        2: 'Dunkelheit'
    }
    return light_conditions.get(n, 'Unbekannte Lichtverhältnisse')

def map_street_condition(n: int) -> str:
    street_conditions = {
        0: 'trocken',
        1: 'nass/feucht/schlüpfrig',
        2: 'winterglatt',
    }
    return street_conditions.get(n, 'Unbekannte Straßenverhältnisse')

def map_plausibility(n: int) -> str:
    plausibility = {
        1: 'Erfolgreiche Plausibilisierung des Unfallortes nach regulärem Verfahren',
        1: 'Erfolgreiche Plausibilisierung des Unfallortes nach erweitertem Verfahren für Unfälle mit Fahrradbeteiligung'
    }
    return plausibility.get(n, 'Unbekannte Plausibilität')

def map_accident_participants(row) -> str:
    participants = []
    if row['IstRad'] == 1:
        participants.append('Fahrrad')
    if row['IstPKW'] == 1:
        participants.append('PKW')
    if row['IstFuss'] == 1:
        participants.append('Fußgänger')
    if row['IstGkfz'] == 1:
        participants.append('Güterkraftfahrzeug')
    if row['IstSonstige'] == 1:
        participants.append('Sonstige')
    return ', '.join(participants)
# %%
# create tooltip for accidents to show in qgis
accidents_nuernberg_bike['tooltip'] = accidents_nuernberg_bike.apply(lambda row: f"""
    Datum: {map_month(row['UMONAT'])} {row['UJAHR']} - {map_day_of_week(row['UWOCHENTAG'])} {map_hour(row['USTUNDE'])} Uhr<br>
    Unfallkategorie: {map_accident_category(row['UKATEGORIE'])}<br>
    Unfallart: {map_accident_type(row['UART'])}<br>
    Unfalltyp: {map_accident_type1(row['UTYP1'])}<br>
    Lichtverhältnisse: {map_light_condition(row['ULICHTVERH'])}<br>
    Straßenverhältnisse: {map_street_condition(row['IstStrassenzustand'])}<br>
    Beteiligte: {map_accident_participants(row)}<br>
    Plausibilität: {map_plausibility(row['PLST'])}<br>
""", axis=1)

# %%
accidents_nuernberg_bike.drop(columns=['FID'], inplace=False)
# %%
# save accidents to file
gpd.GeoDataFrame(accidents_nuernberg_bike.drop(columns=['FID'], inplace=False), geometry='WSG84').to_file(filename='accidents.gpkg', layer='nuernberg_bike', driver='GPKG')
# %%
# plot accidents by month
month, count = np.unique(accidents_nuernberg_bike['UMONAT'], return_counts=True)
plt.bar(month, count)
month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
plt.xticks(month, month_names)
plt.title('Accidents per Month')
plt.xlabel('Month')
plt.ylabel('Number of Accidents')
plt.grid(False)
# %%
# plot accidents by day of week
day_of_week, count = np.unique(accidents_nuernberg_bike['UWOCHENTAG'], return_counts=True)
plt.bar(day_of_week, count)
day_names = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
plt.xticks(day_of_week, day_names)
plt.title('Accidents per Day of Week')
plt.xlabel('Day of Week')
plt.ylabel('Number of Accidents')
plt.grid(False)
# %%
# plot accidents by hour of day
hour_of_day, count = np.unique(accidents_nuernberg_bike['USTUNDE'], return_counts=True)
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
light_condition, count = np.unique(accidents_nuernberg_bike['ULICHTVERH'].dropna(inplace=False), return_counts=True)
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
street_condition, count = np.unique(accidents_nuernberg_bike['IstStrassenzustand'].dropna(inplace=False), return_counts=True)
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
tmp = accidents_nuernberg_bike[['ULICHTVERH', 'IstStrassenzustand']].dropna(inplace=False)

counts, x_bins, y_bins, _ = plt.hist2d(tmp['ULICHTVERH'], tmp['IstStrassenzustand'], bins=(3, 3), cmap='Blues')
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
counts, x_bins, y_bins, _ = plt.hist2d(accidents_nuernberg_bike['USTUNDE'], accidents_nuernberg_bike['UMONAT'], bins=(24,12), cmap='Blues')
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
# plot accidents by hour of day and day of week
counts, x_bins, y_bins, _ = plt.hist2d(accidents_nuernberg_bike['USTUNDE'], accidents_nuernberg_bike['UWOCHENTAG'], bins=(24,7), cmap='Blues')
# move the ticks to the center of the bins
bin_w = (max(x_bins) - min(x_bins)) / (len(x_bins) - 1)
plt.xticks(np.arange(min(x_bins)+bin_w/2, max(x_bins), bin_w), hour_names)
plt.xlim(x_bins[0], x_bins[-1])
bin_h = (max(y_bins) - min(y_bins)) / (len(y_bins) - 1)
plt.yticks(np.arange(min(y_bins)+bin_h/2, max(y_bins), bin_h), day_names)
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
plt.ylabel('Weekday')
plt.colorbar(label='Number of Accidents')
plt.grid(False)
# resize the figure
fig = plt.gcf()
fig.set_size_inches(12, 6)
plt.show()
# %%
