insert into Stations_Tmp (station_id, name, short_name, position, bike_racks, special_racks, created_at)
values (%s, %s, %s, ST_GeomFromText(%s), %s, %s, %s);