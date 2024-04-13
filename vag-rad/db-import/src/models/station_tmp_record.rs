use chrono::{DateTime, Utc};
use postgis::twkb::Point;

#[derive(Debug)]
pub struct StationTmpRecord {
    pub station_id: i64,
    pub name: String,
    pub short_name: String,
    pub position: Point,
    pub bike_racks: i64,
    pub special_racks: i64,
    pub time: DateTime<Utc>,
}