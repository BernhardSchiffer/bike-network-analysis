use std::{fs::{self, DirEntry, File, ReadDir}, io::BufReader, path::{Path, PathBuf}, str::FromStr, sync::Arc, thread, time::Duration};

use chrono::{DateTime, NaiveDate, NaiveDateTime, Utc};
use crossbeam::channel::unbounded;
use dotenv::dotenv;
use futures;
use indicatif::{MultiProgress, ProgressBar, ProgressStyle};
use models::{bike_tmp_record::BikeTmpRecord, station_tmp_record::StationTmpRecord};
use postgis::twkb::Point;
use tokio::{join, sync::Semaphore};
use threadpool::ThreadPool;
use sqlx::{postgres::{PgConnectOptions, PgPoolOptions}, Pool, Postgres};
use flate2::read::GzDecoder;
use tar::Archive;

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
        let data_dir = "./scraping_data";
        
        let paths = fs::read_dir(data_dir).unwrap();
        let start_date = NaiveDate::from_ymd_opt(2024, 1, 1);
        let end_date = NaiveDate::from_ymd_opt(2024, 3, 31);
        // let start_date = Some(convert_Naive_to_DateTime(start_date));
        // let end_date = Some(convert_Naive_to_DateTime(end_date));

        let archives_to_unpack = get_files_in_date_range(paths, start_date, end_date);
        let working_dir = "./scraping_data/tmp1";

        // setup progressbars
        let progress_bars = MultiProgress::new();
        let sty = ProgressStyle::with_template(
            "[{elapsed_precise}] {bar:60.white/blue} {pos:>7}/{len:7} {msg}",
        )
        .unwrap();

        let num_of_archives = archives_to_unpack.len();
        let extract_files_pb = progress_bars.add(ProgressBar::new(num_of_archives as u64));
        extract_files_pb.set_style(sty.clone());
        extract_files_pb.set_message("extract files");

        let pool = ThreadPool::new(core_count);
        for path in archives_to_unpack {
            let extract_files_pb = extract_files_pb.clone();
            pool.execute(move || {
                println!("{}", path.path().as_path().to_str().unwrap());
                decompress_files(path.path(), Path::new(working_dir).to_path_buf()).unwrap();
                extract_files_pb.inc(1);
            })
        }
        pool.join();
        extract_files_pb.finish_with_message("✅ successfully extracted files");
        return;

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

        let db_pool = db_pool.clone();
        let bike_receiver_thread = tokio::spawn(async move {
            let sem = Arc::new(Semaphore::new(10));
            let mut threads = Vec::new();

            for bikes in bikes_receiver {
                let bike_import_pb = bike_import_pb.clone();
                let db_pool = db_pool.clone();
                let permit = Arc::clone(&sem).acquire_owned().await;
                threads.push(tokio::spawn(async move {
                    let _permit = permit;
                    match insert_bike_records(bikes, &db_pool).await {
                        Ok(_) => bike_import_pb.inc(1),
                        Err(_e) => {
                            // println!("{}", e);
                            bike_import_pb.inc(1);
                        },
                    };
                }));
            }
            futures::future::join_all(threads).await;
            db_pool.close().await;
            bike_import_pb.finish_with_message("✅ finished bike records db import");
        });

        let db_pool = connect().await.unwrap();
        let station_receiver_thread = tokio::spawn(async move {
            let sem = Arc::new(Semaphore::new(10));
            let mut threads = Vec::new();
            
            for stations in stations_receiver {
                let station_import_pb = station_import_pb.clone();
                let db_pool = db_pool.clone();
                let permit = Arc::clone(&sem).acquire_owned().await;
                threads.push(tokio::spawn(async move {
                    let _permit = permit;
                    match insert_station_records(stations, &db_pool).await {
                        Ok(_) => station_import_pb.inc(1),
                        Err(_e) => {
                            // println!("{}", e);
                            station_import_pb.inc(1);
                        },
                    };
                }));
            }
            futures::future::join_all(threads).await;
            db_pool.close().await;
            station_import_pb.finish_with_message("✅ finished station records db import");
        });
        
        producer_thread.join().unwrap();
        // bike_receiver_thread.join().unwrap();
        join!(bike_receiver_thread);
        join!(station_receiver_thread);
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

fn get_timestamp_from_archive(path: &Path) -> NaiveDate {
    let filename = path.file_name().unwrap().to_str().unwrap();
    let filename = filename.split_terminator(".").next().unwrap();
    let time = match NaiveDate::from_str(&filename) {
        Ok(time) => time,
        Err(e) => panic!("error occured while parsing {}. ({})", filename, e),
    };
    return time;
}

fn get_files_in_date_range(path: ReadDir, start_date: Option<NaiveDate>, end_date: Option<NaiveDate>) -> Vec<DirEntry> {
    let mut valid_files: Vec<DirEntry> = Vec::new();
    let start_date = match start_date {
        Some(d) => d,
        None => NaiveDate::MIN
    };
    let end_date = match end_date {
        Some(d) => d,
        None => NaiveDate::MAX,
    };

    for file in path {
        let file = file.unwrap();
        let file_metadata = std::fs::metadata(file.path()).unwrap();
        if file_metadata.is_file() {
            let file_date = get_timestamp_from_archive(file.path().as_path());
            if file_date.ge(&start_date) && file_date.le(&end_date) {
                valid_files.push(file);
            }
        }
    }

    return valid_files;
}

fn decompress_files(archive: PathBuf, target_dir: PathBuf) -> Result<(), std::io::Error> {
    println!("decompress {:?}", archive);

    let tar_gz = File::open(archive)?;
    let tar = GzDecoder::new(tar_gz);
    let mut archive = Archive::new(tar);
    archive.unpack(target_dir)?;

    Ok(())
}

fn convert_Naive_to_DateTime(naive_date: NaiveDate) -> NaiveDateTime {
    return naive_date.and_hms_opt(0, 0, 0).unwrap();
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
    let pool = PgPoolOptions::new()
        .test_before_acquire(true)
        .max_connections(3000)
        .acquire_timeout(Duration::from_secs(120))
        .connect_with(connection_options).await;
    return pool;
}

pub async fn insert_bike_records(bikes: Vec<BikeTmpRecord>, connection_pool: &Pool<Postgres>) -> Result<(), sqlx::Error> {
    // match bikes.get(0) {
    //     Some(bike) => println!("import bikes for {}", bike.time.to_rfc3339()),
    //     None => println!("ERROR on {:?}", bikes),
    // };
    let mut bike_ids = Vec::new();
    let mut vehicle_types_ids = Vec::new();
    let mut dates = Vec::new();
    let mut positions = Vec::new();
    let mut stations = Vec::new();
    
    for bike in bikes {
        bike_ids.push(bike.id);
        vehicle_types_ids.push(bike.vehicle_type_id);
        dates.push(bike.time.with_timezone(&Utc));
        positions.push(format!("POINT({} {})", bike.position.y, bike.position.x));
        stations.push(bike.station_id);
    };

    match sqlx::query("
        insert into Bikes_Tmp (id, vehicle_type_id, time, position, station_id) 
        SELECT UNNEST($1), unnest($2), unnest($3), ST_GeomFromText(unnest($4)), unnest($5)
    ")
        .bind(bike_ids)
        .bind(vehicle_types_ids)
        .bind(dates)
        .bind(positions)
        .bind(stations)
        .execute(connection_pool)
        .await {
            Ok(_) => (),
            Err(e) => return Err(e),
        };
    return Ok(());
}


pub async fn insert_station_records(stations: Vec<StationTmpRecord>, connection_pool: &Pool<Postgres>) -> Result<(), sqlx::Error> {
    // match stations.get(0) {
    //     Some(station) => println!("import stations for {}", station.time.to_rfc3339()),
    //     None => println!("ERROR on {:?}", stations),
    // };
    let mut station_ids = Vec::new();
    let mut names = Vec::new();
    let mut short_names = Vec::new();
    let mut positions = Vec::new();
    let mut bike_racks = Vec::new();
    let mut special_racks = Vec::new();
    let mut dates = Vec::new();
    
    for station in stations {
        station_ids.push(station.station_id);
        names.push(station.name);
        short_names.push(station.short_name);
        positions.push(format!("POINT({} {})", station.position.y, station.position.x));
        bike_racks.push(station.bike_racks);
        special_racks.push(station.special_racks);
        dates.push(station.time.with_timezone(&Utc));
    };

    match sqlx::query("
        insert into Stations_Tmp (station_id, name, short_name, position, bike_racks, special_racks, created_at)
        select unnest($1), unnest($2), unnest($3), ST_GeomFromText(unnest($4)), unnest($5), unnest($6), unnest($7)
    ")
        .bind(station_ids)
        .bind(names)
        .bind(short_names)
        .bind(positions)
        .bind(bike_racks)
        .bind(special_racks)
        .bind(dates)
        .execute(connection_pool)
        .await {
            Ok(_) => (),
            Err(e) => return Err(e),
        };
    return Ok(());
}