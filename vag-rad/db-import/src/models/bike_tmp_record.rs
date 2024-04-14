use chrono::{DateTime, Utc};

#[derive(Debug)]
pub struct BikeTmpRecord {
    pub id: String,
    pub vehicle_type_id: i64,
    pub time: DateTime<Utc>,
    pub position: geo_types::Point,
    pub station_id: Option<i64>,
}