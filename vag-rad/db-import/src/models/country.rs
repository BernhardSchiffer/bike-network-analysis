use serde::Deserialize;

use super::city::City;

#[derive(Deserialize, Debug)]
pub struct Country {
    pub lat: f64,
    pub lng: f64,
    pub zoom: u64,
    pub name: String,
    pub hotline: String,
    pub domain: String,
    pub language: String,
    pub email: String,
    pub timezone: String,
    pub currency: String,
    pub country_calling_code: String,
    pub system_operator_address: String,
    pub country: String,
    pub country_name: String,
    pub terms: String,
    pub policy: String,
    pub website: String,
    pub show_bike_types: bool,
    pub show_bike_type_groups: bool,
    pub show_free_racks: bool,
    pub booked_bikes: u64,
    pub set_point_bikes: u64,
    pub available_bikes: u64,
    pub capped_available_bikes: bool,
    pub no_registration: bool,
    pub pricing: String,
    pub vat: String,
    pub faq_url: String,
    pub store_uri_android: String,
    pub store_uri_ios: String,
    pub cities: Vec<City>
}