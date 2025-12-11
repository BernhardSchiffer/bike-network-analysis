# %%
# imports
import matplotlib.pyplot as plt
import numpy as np
import osmnx as ox
import shapely

from utils.utils import parse_junction_osmid, parse_old_edge_key

# %%
# load weighted graph from file
graph = ox.load_graphml('simplified_bicycle_graph.graphml', node_dtypes={'osmid': str}, edge_dtypes={'weight': float, 'shifted_geometry': lambda x: shapely.from_wkt(x), 'osmid': parse_junction_osmid, 'penalty': float, 'slope_percentage': float, 'length': float, 'old_edge_key': parse_old_edge_key})

# %%
# get statistics for turning angles
turning_angles = []
for u, v, key, data in graph.edges(data=True, keys=True):
    if 'turning_angle' in data:
        turning_angles.append(float(data['turning_angle']))
# %%
import matplotlib.pyplot as plt

plt.hist(turning_angles, bins=36, range=(-180, 180), edgecolor='black')
plt.title('Histogram of Turning Angles in Bicycle Graph')
plt.xlabel('Turning Angle (degrees)')
plt.ylabel('Frequency')
plt.show()

# %%
# polar plot of turning angles in 5 degree bins, with 0° at top
angle_bins = np.arange(-180, 180, 5)
hist, _ = np.histogram(turning_angles, bins=angle_bins)
# bin centers in degrees mapped into [-180, 180)
bin_centers_deg = (angle_bins[:-1] + angle_bins[1:]) / 2
angles_rad = np.deg2rad(bin_centers_deg)
fig = plt.figure()
ax = fig.add_subplot(111, polar=True)
# set 0° to top (North). Uncomment the next line to make angles increase clockwise.
ax.set_theta_zero_location('N')
#ax.set_theta_direction(-1)

ax.bar(angles_rad, hist, width=np.deg2rad(5), bottom=30000, edgecolor='black', alpha=0.8)
# radial labels starting from 30000
ax.set_yticks([30000, 40000, 50000, 60000, 70000])
ax.set_yticklabels(['', '10.000', '20.000', '30.000', '40.000'])

ax.set_ylim(0, 75000)
# move yticks to the bottom
ax.set_rlabel_position(45)
# make yticks smaller
ax.tick_params(axis='y', labelsize=8)
# move ylabels down
for label in ax.get_yticklabels():
    label.set_verticalalignment('bottom')

# xticks from -180° to 180°
ax.set_xticks(np.deg2rad([0, 60, 90, 180, 270, 300]))
ax.set_xticklabels(['0°', '-60°', '-90°', '+/-180°', '90°', '60°'])

# define colors for certain angle ranges
angle_colors = {
    'straight': '#a6cee3',
    'left': '#b2df8a',
    'right': '#fb9a99'
}
# color bars based on angle ranges
for bar, turn_angle in zip(ax.patches, bin_centers_deg):
    if turn_angle < -60:
        bar.set_color(angle_colors['left'])
    elif turn_angle > 60 :
        bar.set_color(angle_colors['right'])
    else:
        bar.set_color(angle_colors['straight'])
    bar.set_edgecolor('black')

#plt.legend(['Straight (-60° to 60°)', 'Left Turn (< -60°)', 'Right Turn (> 60°)'], loc='upper right', bbox_to_anchor=(1.1, 1.1))

#plt.show()
plt.savefig('turning_angles_polar_plot.png', dpi=300)

# %%
# plot pie chart to represent the distribution of turning angles
turning_angle_categories = {
    'straight': 0,
    'left': 0,
    'right': 0,
    'u_turn': 0
}
for angle in turning_angles:
    if angle < -170:
        turning_angle_categories['u_turn'] += 1
    elif angle >= -170 and angle < -60:
        turning_angle_categories['left'] += 1
    elif angle >= -60 and angle <= 60:
        turning_angle_categories['straight'] += 1
    elif angle > 60 and angle <= 170:
        turning_angle_categories['right'] += 1
    elif angle > 170:
        turning_angle_categories['u_turn'] += 1
labels = turning_angle_categories.keys()
sizes = turning_angle_categories.values()
colors = ['green', 'red', 'blue', 'purple'] # colors for straight, left, right, u-turn
plt.figure(figsize=(8, 8))
plt.pie(sizes, labels=labels, colors=colors, autopct='%1.2f%%', startangle=140)
plt.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.
plt.show()
# %%
