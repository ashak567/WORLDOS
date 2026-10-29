"""Explicit ingestion adapters; each maps a public source to the world contract."""
from .cameras import camera_to_world_bundle, load_authoritative_cameras
from .fires import load_authoritative_thermal_anomalies, thermal_anomaly_to_world_bundle
from .infrastructure import infrastructure_to_world_bundle, load_authoritative_infrastructure
from .maritime import fetch_maritime_vessels, load_sample_vessels, maritime_vessel_bundle
from .natural_earth import fetch_country_boundary, parse_country_boundary
from .opensky import fetch_aircraft_states
from .satellites import load_authoritative_satellites, satellite_to_world_bundle
from .usgs import EarthquakeRecord, fetch_earthquake
from .world_bank import fetch_country_point, fetch_population

__all__ = [
    "EarthquakeRecord",
    "camera_to_world_bundle",
    "fetch_aircraft_states",
    "fetch_country_boundary",
    "fetch_country_point",
    "fetch_earthquake",
    "fetch_maritime_vessels",
    "fetch_population",
    "infrastructure_to_world_bundle",
    "load_authoritative_cameras",
    "load_authoritative_infrastructure",
    "load_authoritative_satellites",
    "load_authoritative_thermal_anomalies",
    "load_sample_vessels",
    "maritime_vessel_bundle",
    "parse_country_boundary",
    "satellite_to_world_bundle",
    "thermal_anomaly_to_world_bundle",
]
