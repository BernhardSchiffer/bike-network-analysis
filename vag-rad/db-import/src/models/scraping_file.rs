use serde::Deserialize;

use super::country::Country;

#[derive(Deserialize, Debug)]
pub struct VagScrapingFile {
    pub countries: Vec<Country>
}