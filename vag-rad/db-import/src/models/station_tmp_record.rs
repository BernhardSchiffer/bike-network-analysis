use chrono::{DateTime, Utc};

#[derive(Debug)]
pub struct StationTmpRecord {
    pub station_id: i64,
    pub name: String,
    pub short_name: String,
    pub position: geo_types::Point,
    pub bike_racks: i64,
    pub special_racks: i64,
    pub time: DateTime<Utc>,
}

impl From<SelectStationTmpRecord> for StationTmpRecord {
    fn from(record: SelectStationTmpRecord) -> Self {
        StationTmpRecord{
            station_id: record.station_id,
            name: record.name,
            short_name: record.short_name,
            position: wkt::TryFromWkt::try_from_wkt_str(&record.position).unwrap(),
            bike_racks: record.bike_racks,
            special_racks: record.special_racks,
            time: record.time,
        }
    }
}

#[derive(sqlx::FromRow)]
pub struct SelectStationTmpRecord {
    pub station_id: i64,
    pub name: String,
    pub short_name: String,
    pub position: String,
    pub bike_racks: i64,
    pub special_racks: i64,
    pub time: DateTime<Utc>,
}