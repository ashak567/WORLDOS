from datetime import datetime, timezone
import pytest
from app.ingestion.flight_routes import resolve_flight_route, WORLD_AIRPORTS, KNOWN_FLIGHT_ROUTES
from app.main import _enrich_aircraft_payload


def test_known_flight_routes_resolution():
    res = resolve_flight_route(
        callsign="UAL946",
        icao24="a0002a",
        current_lat=52.3,
        current_lon=4.7,
        true_track=270.0,
        velocity=230.0,
        baro_altitude=11000.0,
        on_ground=False,
    )
    assert res["departure_airport"]["iata"] == "AMS"
    assert res["destination_airport"]["iata"] == "EWR"
    assert "departure_time" in res
    assert "estimated_arrival_time" in res
    assert "UTC" in res["departure_time_formatted"]
    assert "ETA:" not in res["departure_time_formatted"]
    assert "UTC" in res["estimated_arrival_time_formatted"]
    assert res["flight_progress_pct"] >= 0
    assert res["is_international"] is True


def test_dynamic_spatial_corridor_resolution():
    # Aircraft flying eastward near Tokyo Haneda heading towards San Francisco
    res = resolve_flight_route(
        callsign="ANA8",
        icao24="86d4b1",
        current_lat=36.0,
        current_lon=142.0,
        true_track=70.0,
        velocity=250.0,
        baro_altitude=10500.0,
        on_ground=False,
    )
    assert res["departure_airport"]["iata"] == "NRT"
    assert res["destination_airport"]["iata"] == "SFO"
    assert res["distance_flown_km"] > 0
    assert res["remaining_distance_km"] > 0


def test_enrich_aircraft_payload():
    record = {
        "id": "obs-123",
        "entity_id": "ent-123",
        "canonical_name": "BAW178",
        "latitude": 45.0,
        "longitude": -50.0,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "attributes": {
            "callsign": "BAW178",
            "icao24": "40089c",
            "velocity": 240.0,
            "true_track": 65.0,
            "baro_altitude": 10600.0,
            "on_ground": False,
        },
    }
    enriched = _enrich_aircraft_payload(record)
    attr = enriched["attributes"]
    assert attr["departure_airport"]["iata"] == "JFK"
    assert attr["destination_airport"]["iata"] == "LHR"
    assert "departure_time_formatted" in attr
    assert "estimated_arrival_time_formatted" in attr
    assert attr["flight_phase"] == "EN ROUTE (CRUISE)"
