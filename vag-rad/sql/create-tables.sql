CREATE TABLE Bikes_Tmp (
    id text not null,
    vehicle_type_id int,
    time timestamp not null,
    position geography(POINT,4326) not null,
    station_id int,
    primary key (id, time)
);

CREATE TABLE Stations (
    id int primary key,
    name text,
    short_name text,
    position geography(POINT,4326) not null,
    bike_racks int not null,
    special_racks int not null
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
    id text not null,
    vehicle_type_id int,
    primary key (id),
    foreign key (vehicle_type_id) 
        references bike_types (id)
        on delete set null
);

CREATE TABLE Rides (
    id serial not null,
    bike_id text,
    starting_time timestamp not null,
    finishing_time timestamp not null,
    starting_position geography(POINT,4326) not null,
    finishing_position geography(POINT,4326) not null,
    starting_station_id int,
    finishing_station_id int,
    primary key (id),
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
