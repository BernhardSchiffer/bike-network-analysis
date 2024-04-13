use std::{fs::{self, File}, io::BufReader, path::{Path, PathBuf}, sync::Arc, thread, time::Duration};

use chrono::{DateTime, Utc};
use crossbeam::channel::unbounded;
use dotenv::dotenv;
use indicatif::{MultiProgress, ProgressBar, ProgressStyle};
use models::{bike_tmp_record::BikeTmpRecord, station_tmp_record::StationTmpRecord};
use postgis::twkb::Point;
use tokio::{join, sync::Semaphore};
use zip_extensions::zip_extract;
use threadpool::ThreadPool;
use sqlx::{postgres::{PgConnectOptions, PgPoolOptions}, Pool, Postgres};

use crate::models::scraping_file::VagScrapingFile;
mod models;

#[tokio::main]
async fn main() {
    use std::time::Instant;
    let now = Instant::now();
    // Code block to measure runtime.
    {
        let core_count = thread::available_parallelism().unwrap().get();
        println!("running process on {} cores", core_count);
        
        let paths = fs::read_dir("./scraping_data").unwrap();
        let working_dir = "./scraping_data/tmp";

        // setup progressbars
        let progress_bars = MultiProgress::new();
        let sty = ProgressStyle::with_template(
            "[{elapsed_precise}] {bar:60.white/blue} {pos:>7}/{len:7} {msg}",
        )
        .unwrap();

        let num_of_archives = fs::read_dir("./scraping_data").unwrap().count();
        let extract_files_pb = progress_bars.add(ProgressBar::new(num_of_archives as u64));
        extract_files_pb.set_style(sty.clone());
        extract_files_pb.set_message("extract files");

        let pool = ThreadPool::new(core_count);
        for _path in paths {
            let extract_files_pb = extract_files_pb.clone();
            pool.execute(move || {
                // decompress_files(path.unwrap().path(), Path::new(working_dir).to_path_buf());
                extract_files_pb.inc(1);
            })
        }
        pool.join();
        extract_files_pb.finish_with_message("✅ successfully extracted files");

        let num_of_files = fs::read_dir(working_dir).unwrap().count();
        
        let file_read_pb = progress_bars.add(ProgressBar::new(num_of_files as u64));
        file_read_pb.set_style(sty.clone());
        file_read_pb.set_message("read files");

        let bike_import_pb = progress_bars.add(ProgressBar::new(num_of_files as u64));
        bike_import_pb.set_style(sty.clone());
        bike_import_pb.set_message("import temporary bike records");

        let station_import_pb = progress_bars.add(ProgressBar::new(num_of_files as u64));
        station_import_pb.set_style(sty.clone());
        station_import_pb.set_message("import temporary station records");

        // setup producer and receivers
        let (bikes_producer, bikes_receiver) = unbounded();
        let (stations_producer, stations_receiver) = unbounded();
        let paths = fs::read_dir(working_dir).unwrap();
    
        let producer_thread = thread::spawn(move || {
            let producer_thread_pool = ThreadPool::new(core_count);
            for path in paths {
                let bp = bikes_producer.clone();
                let sp = stations_producer.clone();
                let file_read_pb = file_read_pb.clone();
                producer_thread_pool.execute(move || {
                    let path = &path.unwrap().path();
                    let scraping_file = read_scraping_file(path);
                    let time = get_timestamp_from_filename(path);
                    let bikes = get_bikes(&scraping_file, time);
                    // println!("send {} bike records", bikes.len());
                    bp.send(bikes).unwrap();
                    let stations = get_stations(&scraping_file, time);
                    // println!("send {} station records", stations.len());
                    sp.send(stations).unwrap();
                    file_read_pb.inc(1);
                });
            }
            producer_thread_pool.join();
            file_read_pb.finish_with_message("✅ read all files");
        });

        let db_pool = connect().await.unwrap();

        // let db_pool = db_pool.clone();
        let bike_receiver_thread = tokio::spawn(async move {
            // let bike_receiver_thread_pool = ThreadPool::new(core_count);
            let sem = Arc::new(Semaphore::new(10));
            for bikes in bikes_receiver {
                let bike_import_pb = bike_import_pb.clone();
                let db_pool = db_pool.clone();
                let permit = Arc::clone(&sem).acquire_owned().await;
                // bike_receiver_thread_pool.execute(move || {
                tokio::spawn(async move {
                    let _permit = permit;
                    insert_bike_records(bikes, &db_pool).await;
                    bike_import_pb.inc(1);
                });
            }
            // bike_receiver_thread_pool.join();
            db_pool.close().await;
            bike_import_pb.finish_with_message("✅ finished bike records db import");
        });

        let station_receiver_thread = thread::spawn(move || {
            let station_receiver_thread_pool = ThreadPool::new(core_count);
            
            for _stations in stations_receiver {
                let station_import_pb = station_import_pb.clone();
                station_receiver_thread_pool.execute(move || {
                    // println!("import {} station records", stations.len());
                    station_import_pb.inc(1);
                });
            }
            station_receiver_thread_pool.join();
            station_import_pb.finish_with_message("✅ finished station records db import");
        });
        
        producer_thread.join().unwrap();
        // bike_receiver_thread.join().unwrap();
        join!(bike_receiver_thread);
        station_receiver_thread.join().unwrap();
        // db_pool.close().await;
    }

    let elapsed = now.elapsed();
    println!("Elapsed: {:.2?}", elapsed);
}

fn get_timestamp_from_filename(path: &Path) -> DateTime<Utc> {
    let filename = path.file_stem().unwrap().to_str().unwrap();
    let time = match DateTime::parse_from_rfc3339(&filename) {
        Ok(time) => time.with_timezone(&Utc),
        Err(e) => panic!("error occured while parsing {}. ({})", filename, e),
    };
    return time;
}

fn _decompress_files(archive: PathBuf, target_dir: PathBuf) {
    //println!("decompress {:?}", archive);
    zip_extract(&archive, &target_dir).unwrap();
}

fn read_scraping_file(path: &Path) -> VagScrapingFile {
    let file = File::open(path).unwrap();
    let reader = BufReader::new(file);
    let scraping_file: VagScrapingFile = serde_json::from_reader(reader).unwrap();
    return scraping_file;
}

fn get_bikes(scraping_file: &VagScrapingFile, time: DateTime<Utc>) -> Vec<BikeTmpRecord> {
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
    let pool = PgPoolOptions::new().test_before_acquire(true).max_connections(3000).acquire_timeout(Duration::from_secs(120)).connect_with(connection_options).await;
    return pool;
}

pub async fn insert_bike_records(bikes: Vec<BikeTmpRecord>, connection_pool: &Pool<Postgres>) {
    // match bikes.get(0) {
    //     Some(bike) => println!("import bikes for {}", bike.time.to_rfc3339()),
    //     None => println!("ERROR on {:?}", bikes),
    // };
    
    // let transaction = connection_pool.begin().await.unwrap();
    let sem = Arc::new(Semaphore::new(300));
    for bike in bikes {
        let permit = Arc::clone(&sem).acquire_owned().await;
        let connection_pool = connection_pool.clone();
        tokio::spawn(async move {
            let _permit = permit;
            match sqlx::query(r#"insert into Bikes_Tmp (id, vehicle_type_id, time, position, station_id) values ($1, $2, $3, ST_GeomFromText($4), $5)"#)
                .bind(bike.id)
                .bind(bike.vehicle_type_id)
                .bind(bike.time.with_timezone(&Utc))
                .bind(format!("POINT({} {})", bike.position.y, bike.position.x))
                .bind(bike.station_id)
                .execute(&connection_pool)
                .await {
                    Ok(_) => (),
                    Err(_e) => (),
                }
        });
    }
    // transaction.commit().await.unwrap();
}
