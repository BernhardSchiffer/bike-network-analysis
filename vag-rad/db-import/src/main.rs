use std::{fs::{self, File}, io::{BufReader, Error}, path::{Path, PathBuf}, sync::Arc, thread, time::Duration};

use chrono::{DateTime, Utc};
use dotenv::dotenv;
use futures::stream::FuturesUnordered;
use models::{bike_tmp_record::BikeTmpRecord, station_tmp_record::StationTmpRecord};
use postgis::twkb::Point;
use tokio::sync::Semaphore;
use zip_extensions::zip_extract;
use threadpool::ThreadPool;
use sqlx::{postgres::{PgConnectOptions, PgPoolOptions}, Pool, Postgres};

use crate::models::scraping_file::VagScrapingFile;
mod models;

#[tokio::main]
async fn main() {

    use std::time::Instant;
    let now = Instant::now();

    // Code block to measure.
    {
        let count = thread::available_parallelism().unwrap().get();
        println!("running process on {} cores", count);
        let pool = ThreadPool::new(count);
        
        let paths = fs::read_dir("../scraping_data").unwrap();
        let working_dir = "../scraping_data/tmp";
        
        println!("extract files");
        for path in paths {
            pool.execute(|| {
                decompress_files(path.unwrap().path(), Path::new(working_dir).to_path_buf());
            })
        }
        pool.join();

        let db_pool = connect().await.unwrap();
        // let insert_bike_tmp_sql = fs::read_to_string("../sql/insert_bike_records.sql").unwrap();
        // let insert_station_tmp_sql = fs::read_to_string("../sql/insert_stations_records.sql").unwrap();

        let paths = fs::read_dir(working_dir).unwrap();
        let sem = Arc::new(Semaphore::new(100));
        let tasks = FuturesUnordered::new();

        for path in paths {
            let pool_clone = db_pool.clone();
            let permit = Arc::clone(&sem).acquire_owned().await;
            tasks.push(tokio::spawn(async move {
                let _permit = permit;
                let path = &path.unwrap();
                //println!("read file {}", path.path().display());
                let scraping_file = read_scraping_file(path.path());
                let tmp = path.path().clone();
                let filename = tmp.as_path().file_stem().unwrap().to_str().unwrap();
                //println!("{}", filename);
                let time: DateTime<Utc> = DateTime::parse_from_rfc3339(&filename).unwrap().with_timezone(&Utc);
                let bikes = get_bikes(scraping_file.as_ref().unwrap(), time).await;
                let _stations = get_stations(scraping_file.as_ref().unwrap(), time);
                //println!("found {} bikes", bikes.len());
                insert_bike_records(bikes, pool_clone).await;
            }));
        }
        db_pool.close().await;
    }

    let elapsed = now.elapsed();
    println!("Elapsed: {:.2?}", elapsed);
}

fn decompress_files(archive: PathBuf, target_dir: PathBuf) {
    //println!("decompress {:?}", archive);
    zip_extract(&archive, &target_dir).unwrap();
}

fn read_scraping_file<P: AsRef<Path>>(path: P) -> Result<VagScrapingFile, Error> {
    let file = File::open(path).unwrap();
    let reader = BufReader::new(file);

    let scraping_file: VagScrapingFile = serde_json::from_reader(reader).unwrap();
    Ok(scraping_file)
}

async fn get_bikes(scraping_file: &VagScrapingFile, time: DateTime<Utc>) -> Vec<BikeTmpRecord> {
    let mut bikes: Vec<BikeTmpRecord> = Vec::new();
    for country in &scraping_file.countries {
        for city in &country.cities {
            for place in &city.places {
                if place.spot && !place.bike {
                    for bike in &place.bike_list {
                        let station_id: Option<i64> = Option::Some(place.uid); 
                        let bike_tmp_record = BikeTmpRecord{
                            id: bike.number.clone(),
                            vehicle_type_id: bike.bike_type,
                            time: time,
                            position: Point{x: place.lat, y: place.lng},
                            station_id: station_id,
                        };
                        bikes.push(bike_tmp_record)
                    }
                } else if !place.spot && place.bike {
                    for bike in &place.bike_list {
                        let station_id: Option<i64> = Option::None; 
                        let bike_tmp_record = BikeTmpRecord{
                            id: bike.number.clone(),
                            vehicle_type_id: bike.bike_type,
                            time: time,
                            position: Point{x: place.lat, y: place.lng},
                            station_id: station_id,
                        };
                        bikes.push(bike_tmp_record)
                    }
                }
            }
        }
    }
    return bikes;
}

fn get_stations(scraping_file: &VagScrapingFile, time: DateTime<Utc>) -> Vec<StationTmpRecord> {
    let mut stations: Vec<StationTmpRecord> = Vec::new();
    for country in &scraping_file.countries {
        for city in &country.cities {
            for place in &city.places {
                if place.spot && !place.bike {
                    let station_tmp_record = StationTmpRecord{
                        station_id: place.uid,
                        name: place.name.clone(),
                        short_name: place.number.to_string(),
                        position: Point{x: place.lat, y: place.lng},
                        bike_racks: place.bike_racks,
                        special_racks: place.special_racks,
                        time: time,
                    };
                    stations.push(station_tmp_record)
                }
            }
        }
    }
    return stations;
}

pub async fn connect() -> Result<Pool<Postgres>, sqlx::Error> {
    dotenv().ok();
    let postgres_user: String = std::env::var("TEST_POSTGRES_USER").expect("POSTGRES_USER must be set.");
    let postgres_password: String = std::env::var("TEST_POSTGRES_PASSWORD").expect("POSTGRES_PASSWORD must be set.");
    let postgres_db: String = std::env::var("TEST_POSTGRES_DB").expect("POSTGRES_DB must be set.");
    let postgres_host: String = std::env::var("TEST_POSTGRES_HOST").expect("POSTGRES_HOST must be set.");
    let postgres_port: String = std::env::var("TEST_POSTGRES_PORT").expect("POSTGRES_PORT must be set.");
    
    let connection_options = PgConnectOptions::new()
        .host(&postgres_host)
        .port(postgres_port.parse::<u16>().unwrap())
        .username(&postgres_user)
        .password(&postgres_password)
        .database(&postgres_db);
    let pool = PgPoolOptions::new().test_before_acquire(true).max_connections(500).acquire_timeout(Duration::from_secs(60)).connect_with(connection_options).await;
    return pool;
}

pub async fn insert_bike_records(bikes: Vec<BikeTmpRecord>, connection_pool: Pool<Postgres>) {
    match bikes.get(0) {
        Some(bike) => println!("import bikes for {}", bike.time.to_rfc3339()),
        None => println!("ERROR on {:?}", bikes),
    };
    
    // let transaction = connection_pool.begin().await.unwrap();
    for bike in bikes {
        match sqlx::query(r#"insert into Bikes_Tmp (id, vehicle_type_id, time, position, station_id) values ($1, $2, $3, ST_GeomFromText($4), $5)"#)
            .bind(bike.id)
            .bind(bike.vehicle_type_id)
            .bind(bike.time)
            .bind(format!("POINT({} {})", bike.position.y, bike.position.x))
            .bind(bike.station_id)
            .execute(&connection_pool)
            .await {
                Ok(_) => (),
                Err(e) => (),
            }
    }
    // transaction.commit().await.unwrap();
}
