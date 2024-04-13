use serde::Deserialize;

#[derive(Deserialize, Debug)]
pub struct Coordinate {
    pub lat: f64,
    pub lng: f64,
}