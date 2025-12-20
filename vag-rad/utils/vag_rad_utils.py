import json

import shapely.geometry

vag_rad_city_ids = {
    'Nürnberg': '626',
    'Fürth': '966',
    'Erlangen': '829',
    'Schwabach': '967'
}

# all flexzones are fetched from https://api.nextbike.net/reservation/geojson/flexzone_all.json
def get_vag_rad_flexzone(cityId: str) -> shapely.geometry.MultiPolygon:
    filename = "./vag-rad-data/flexzone_all.json"
    f = open(filename, "r")
    try:
        data = json.load(f)
    except json.JSONDecodeError as e:
        print(f'Exception {e} while parsing {filename}')

    vag_rad_flexzone_parts = []
    for feature in data['features']:
        if feature['properties']['cityId'] == cityId:
            geom = shapely.geometry.shape(feature['geometry'])
            vag_rad_flexzone_parts.append(geom)

    vag_rad_flexzone = shapely.geometry.MultiPolygon(vag_rad_flexzone_parts)
    return vag_rad_flexzone