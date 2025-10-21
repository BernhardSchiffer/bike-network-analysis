# %%
# imports
from utils.population_provider import GHSLPopulationProvider, NurenbergDistrictPopulationProvider
from IPython.display import display
import pandas as pd

# %%
# initialize population providers
nbg_population_provider = NurenbergDistrictPopulationProvider()
ghsl_population_provider = GHSLPopulationProvider()

# %%
# total population comparison
print(f'official population of nurnberg: {nbg_population_provider.population_gdf["population"].sum()}')
print(f'ghsl population of nurnberg: {ghsl_population_provider.get_population_in_polygon(nbg_population_provider.nuremberg_area)}')

# %%
# compare population data per district
districts = nbg_population_provider.population_gdf[['district', 'population']].copy()
districts = districts.rename(columns={'population': 'official_population'})

for idx, row in nbg_population_provider.population_gdf.iterrows():
    district_polygon = row['district_areas']
    if district_polygon:
        ghsl_population_district = ghsl_population_provider.get_population_in_polygon(row['district_areas'])
    else:
        ghsl_population_district = pd.NA
    residential_polygon = row['residential_areas']
    if residential_polygon:
        ghsl_population_residental = ghsl_population_provider.get_population_in_polygon(row['residential_areas'])
    else:
        ghsl_population_residental = pd.NA

    districts.at[idx, 'ghsl_population_district'] = ghsl_population_district
    districts.at[idx, 'ghsl_population_residental'] = ghsl_population_residental

ghsl_population_sum = districts['ghsl_population_district'].sum()
nbg_population_sum = districts['official_population'].sum()
for idx, row in districts.iterrows():
    districts.at[idx, 'ghsl_district_proportion'] = (row['ghsl_population_district'] / ghsl_population_sum) * 100
    districts.at[idx, 'nbg_district_proportion'] = (row['official_population'] / nbg_population_sum) * 100

    districts.at[idx, 'nbg_ghsl_diff_proportion'] = (districts.at[idx, 'nbg_district_proportion'] - districts.at[idx, 'ghsl_district_proportion']) / districts.at[idx, 'nbg_district_proportion'] * 100

assert districts['ghsl_district_proportion'].sum().round() == 100.0
assert districts['nbg_district_proportion'].sum() == 100.0

with pd.option_context('display.max_rows', None, 'display.max_columns', None):
    display(districts)

# %%
# show median proportional difference
print(f'Median proportional difference between official Nuremberg population and GHSL population per district: {abs(districts['nbg_ghsl_diff_proportion']).median():.2f}%')

# %%
# show top 10 biggest differences
print('The biggest differences between official Nuremberg population and GHSL population per district area are:')
top_differences = districts.sort_values(by='nbg_ghsl_diff_proportion', key=abs, ascending=False).head(10)
display(top_differences)

# %%
