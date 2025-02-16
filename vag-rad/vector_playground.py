#%%
import numpy as np
import matplotlib.pyplot as plt

#%%
def get_vector(V: tuple[tuple[int, int], tuple[int, int]]) -> tuple[int, int]:
    return (V[1][0]-V[0][0], V[1][1]-V[0][1])

def get_shifting_vector(V: tuple[tuple[int, int], tuple[int, int]], point: tuple[int, int]) -> tuple[int, int]:
    # rotate vector 35 degrees
    turning_angle = 20
    if(point == V[0]):
        angle = 360 - turning_angle
    else:
        angle = turning_angle + 180
    angle = np.radians(angle)
    x = V[1][0] - V[0][0]
    y = V[1][1] - V[0][1]
    x_new = x * np.cos(angle) - y * np.sin(angle)
    y_new = x * np.sin(angle) + y * np.cos(angle)
    v = (x_new, y_new)
    return v/np.linalg.norm(v)

V1 = ((-1, -1), (0, 0))
V2 = ((0, 0), (0, -1))
V3 = ((0, 0), (1, 0))
V4 = ((1, 0), (0, 0))

# Create the plot
fig, ax = plt.subplots()

# Add the vector V to the plot
ax.quiver(V1[0][0], V1[0][1], get_vector(V1)[0], get_vector(V1)[1], angles='xy', scale_units='xy', scale=1, color='r')
ax.quiver(V1[1][0], V1[1][1], get_shifting_vector(V1, V1[1])[0], get_shifting_vector(V1, V1[1])[1], angles='xy', scale_units='xy', scale=1, color='r')

ax.quiver(V2[0][0], V2[0][1], get_vector(V2)[0], get_vector(V2)[1], angles='xy', scale_units='xy', scale=1, color='b')
ax.quiver(V2[0][0], V2[0][1], get_shifting_vector(V2, V2[0])[0], get_shifting_vector(V2, V2[0])[1], angles='xy', scale_units='xy', scale=1, color='b')

ax.quiver(V3[0][0], V3[0][1], get_vector(V3)[0], get_vector(V3)[1], angles='xy', scale_units='xy', scale=1, color='y')
ax.quiver(V3[0][0], V3[0][1], get_shifting_vector(V3, V3[0])[0], get_shifting_vector(V3, V3[0])[1], angles='xy', scale_units='xy', scale=1, color='y')

ax.quiver(V4[0][0], V4[0][1], get_vector(V4)[0], get_vector(V4)[1], angles='xy', scale_units='xy', scale=1, color='g')
ax.quiver(V4[1][0], V4[1][1], get_shifting_vector(V4, V4[1])[0], get_shifting_vector(V4, V4[1])[1], angles='xy', scale_units='xy', scale=1, color='g')

# Set the x-limits and y-limits of the plot
ax.set_xlim([-2, 2])
ax.set_ylim([-2, 2])

# Show the plot along with the grid
ax.set_aspect('equal')
plt.grid()
plt.show()

# %%
