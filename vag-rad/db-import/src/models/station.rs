use serde::Deserialize;

use super::bike::Bike;

#[derive(Deserialize, Debug)]
pub struct Station {
    pub uid: i64,
    pub lat: f64,
    pub lng: f64,
    pub bike: bool,
    pub name: String,
    pub spot: bool,
    pub number: u64,
    pub booked_bikes: u64,
    pub bikes: u64,
    pub bikes_available_to_rent: u64,
    pub bike_racks: i64,
    pub free_racks: i64,
    pub special_racks: i64,
    pub free_special_racks: u64,
    pub maintenance: bool,
    pub terminal_type: String,
    pub bike_list: Vec<Bike>,
    pub bike_numbers: Vec<String>,
    pub place_type: String,
    pub rack_locks: bool
}
