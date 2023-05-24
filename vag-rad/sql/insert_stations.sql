insert into Stations (id, name, short_name, position, bike_racks, special_racks)
values (%s, %s, %s, ST_GeomFromText(%s), %s, %s);