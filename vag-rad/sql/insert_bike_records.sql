insert into Bikes_Tmp (id, vehicle_type_id, time, position, station_id)
values (%s, %s, %s, ST_GeomFromText(%s), %s);