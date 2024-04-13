use chrono::{DateTime, Utc};
use postgis::twkb::Point;

#[derive(Debug)]
pub struct BikeTmpRecord {
    pub id: String,
    pub vehicle_type_id: i64,
    pub time: DateTime<Utc>,
    pub position: Point,
    pub station_id: Option<i64>,
}