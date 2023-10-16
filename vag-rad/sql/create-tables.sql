CREATE TABLE Bikes_Tmp (
    id text not null,
    vehicle_type_id int,
    time timestamp not null,
    position geography(POINT,4326) not null,
    station_id int,
    primary key (id, time)
);

CREATE INDEX idx_bikes_tmp_id
ON Bikes_Tmp(id);

CREATE INDEX idx_bikes_tmp_time 
ON Bikes_Tmp(time ASC);

CREATE TABLE Stations_Tmp (
    station_id int not null,
    name text,
    short_name text,
    position geography(POINT,4326) not null,
    bike_racks int not null,
    special_racks int not null,
    created_at timestamp not null
);

CREATE INDEX idx_stations_tmp 
ON Stations_Tmp(station_id);

CREATE TABLE Stations (
    id serial primary key,
    station_id int not null,
    name text,
    short_name text,
    position geography(POINT,4326) not null,
    bike_racks int not null,
    special_racks int not null,
    first_seen timestamp not null,
    unique (station_id, name, short_name, position, bike_racks, special_racks)
);

CREATE TABLE Bike_Types (
    id int primary key,
    image_url text,
    name text,
    description text,
    form_factor text,
    rider_capacity text,
    propulsion_type text
);

CREATE TABLE Bikes (
    id serial primary key,
    bike_id text not null,
    vehicle_type_id int,
    first_seen timestamp not null,
    unique (bike_id, vehicle_type_id),
    foreign key (vehicle_type_id) 
        references bike_types (id)
        on delete set null
);

CREATE INDEX idx_bikes_bike_id 
ON Bikes(bike_id);

CREATE TABLE Rides (
    id serial not null,
    bike_id int not null,
    starting_time timestamp not null,
    finishing_time timestamp not null,
    starting_position geography(POINT,4326) not null,
    finishing_position geography(POINT,4326) not null,
    starting_station_id int,
    finishing_station_id int,
    primary key (id),
    unique (bike_id, starting_time),
    foreign key (bike_id) 
        references bikes (id)
        on delete set null,
    foreign key (starting_station_id) 
        references stations (id)
        on delete set null,
    foreign key (finishing_station_id)
        references stations (id)
        on delete set null
);

CREATE INDEX idx_rides_bike_id 
ON Rides(bike_id);
