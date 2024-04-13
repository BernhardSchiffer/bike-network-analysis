use serde::Deserialize;

use super::{coordinate::Coordinate, station::Station};

#[derive(Deserialize, Debug)]
pub struct BoundigBox {
    pub south_west: Coordinate,
    pub north_east: Coordinate,
}

#[derive(Deserialize, Debug)]
pub struct City {
    pub uid: u64,
    pub lat: f64,
    pub lng: f64,
    pub zoom: u64,
    pub maps_icon: String,
    pub alias: String,
    #[serde(rename = "break")]
    pub break_allowed: bool,
    pub name: String,
    pub num_places: u64,
    pub refresh_rate: String,
    pub bounds: BoundigBox,
    pub booked_bikes: u64,
    pub set_point_bikes: u64,
    pub available_bikes: u64,
    pub return_to_official_only: bool,
    pub website: String,
    pub places: Vec<Station>
}

