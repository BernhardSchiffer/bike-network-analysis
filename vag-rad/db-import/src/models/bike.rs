use serde::Deserialize;

#[derive(Deserialize, Debug)]
pub struct Bike {
    pub number: String,
    pub bike_type: i64,
    pub lock_types: Vec<String>,
    pub active: bool,
    pub state: String,
    pub electric_lock: bool,
    pub boardcomputer: u64,
}