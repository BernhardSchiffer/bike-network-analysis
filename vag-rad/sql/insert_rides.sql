insert into Rides (
    bike_id, 
    starting_time, 
    finishing_time, 
    starting_position, 
    finishing_position, 
    starting_station_id,
    finishing_station_id)
values (%s, %s, %s, ST_GeomFromText(%s), ST_GeomFromText(%s), %s, %s);