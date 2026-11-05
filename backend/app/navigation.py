"""Navigation, Road Routing & Inbound Flight Plans Engine for WORLDOS.

Provides:
1. Turn-by-turn road route navigation (via OSRM driving engine with deterministic fallback).
2. Global inbound flight plans by country and airline for any world destination,
   including 3D geodesic flight corridors for Cesium globe visualization.
"""
from __future__ import annotations

import json
import logging
import math
import urllib.parse
import urllib.request
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .ingestion.flight_routes import (
    WORLD_AIRPORTS,
    Airport,
    haversine_distance_km,
)

logger = logging.getLogger("worldos.navigation")

# -----------------------------------------------------------------------------
# Pydantic Response Models
# -----------------------------------------------------------------------------

class RoadRouteStep(BaseModel):
    step_number: int
    instruction: str
    maneuver_type: str  # 'depart', 'turn_right', 'turn_left', 'slight_right', 'slight_left', 'continue', 'merge', 'ramp', 'roundabout', 'arrive'
    street_name: str
    distance_m: float
    distance_formatted: str
    duration_s: float
    duration_formatted: str
    coordinates: list[float]  # [lon, lat]


class RoadRouteResponse(BaseModel):
    route_id: str
    origin_name: str
    origin_coords: list[float]  # [lon, lat]
    destination_name: str
    destination_coords: list[float]  # [lon, lat]
    total_distance_km: float
    total_distance_formatted: str
    total_duration_min: float
    total_duration_formatted: str
    primary_roads: list[str]
    summary: str
    steps: list[RoadRouteStep]
    polyline: list[list[float]]  # [[lon, lat], ...]


class AirportSummary(BaseModel):
    icao: str
    iata: str
    name: str
    city: str
    country: str
    latitude: float
    longitude: float


class InboundFlightPlan(BaseModel):
    flight_id: str
    airline: str
    airline_code: str
    flight_number: str
    origin_country: str
    origin_country_code: str
    origin_city: str
    origin_airport: AirportSummary
    destination_city: str
    destination_airport: AirportSummary
    aircraft_type: str
    departure_time_schedule: str
    duration_hours: float
    duration_formatted: str
    distance_km: float
    frequency: str
    is_direct: bool = True
    waypoints_3d: list[list[float]]  # [[lon, lat, alt_m], ...]


class FlightPlansResponse(BaseModel):
    destination: str
    destination_city: str
    destination_airport: AirportSummary
    total_inbound_flights: int
    origin_countries: list[str]
    flights: list[InboundFlightPlan]


# -----------------------------------------------------------------------------
# Curated Flagship Inbound Flights per Destination Hub
# -----------------------------------------------------------------------------

CURATED_INBOUND_FLIGHTS: dict[str, list[dict[str, Any]]] = {
    # Tokyo Haneda & Narita (HND / NRT)
    "tokyo": [
        {
            "flight_number": "NH109",
            "airline": "All Nippon Airways",
            "airline_code": "ANA",
            "origin_country": "United States",
            "origin_country_code": "US",
            "origin_city": "New York",
            "origin_icao": "KJFK",
            "dest_icao": "RJTT",
            "aircraft": "Boeing 787-9 Dreamliner",
            "schedule": "Daily 11:30 EDT -> Next Day 15:00 JST",
            "frequency": "Daily Direct",
        },
        {
            "flight_number": "UA881",
            "airline": "United Airlines",
            "airline_code": "UAL",
            "origin_country": "United States",
            "origin_country_code": "US",
            "origin_city": "Chicago",
            "origin_icao": "KORD",
            "dest_icao": "RJTT",
            "aircraft": "Boeing 777-300ER",
            "schedule": "Daily 12:45 CDT -> Next Day 16:15 JST",
            "frequency": "Daily Direct",
        },
        {
            "flight_number": "JL001",
            "airline": "Japan Airlines",
            "airline_code": "JAL",
            "origin_country": "United States",
            "origin_country_code": "US",
            "origin_city": "San Francisco",
            "origin_icao": "KSFO",
            "dest_icao": "RJTT",
            "aircraft": "Airbus A350-1000",
            "schedule": "Daily 16:45 PDT -> Next Day 19:55 JST",
            "frequency": "Daily Direct",
        },
        {
            "flight_number": "BA007",
            "airline": "British Airways",
            "airline_code": "BAW",
            "origin_country": "United Kingdom",
            "origin_country_code": "GB",
            "origin_city": "London",
            "origin_icao": "EGLL",
            "dest_icao": "RJTT",
            "aircraft": "Boeing 787-9 Dreamliner",
            "schedule": "Daily 09:10 GMT -> Next Day 07:35 JST",
            "frequency": "Daily Direct",
        },
        {
            "flight_number": "AF276",
            "airline": "Air France",
            "airline_code": "AFR",
            "origin_country": "France",
            "origin_country_code": "FR",
            "origin_city": "Paris",
            "origin_icao": "LFPG",
            "dest_icao": "RJTT",
            "aircraft": "Airbus A350-900",
            "schedule": "Daily 13:20 CET -> Next Day 09:40 JST",
            "frequency": "Daily Direct",
        },
        {
            "flight_number": "LH716",
            "airline": "Lufthansa",
            "airline_code": "DLH",
            "origin_country": "Germany",
            "origin_country_code": "DE",
            "origin_city": "Frankfurt",
            "origin_icao": "EDDF",
            "dest_icao": "RJTT",
            "aircraft": "Boeing 747-8 Intercontinental",
            "schedule": "Daily 14:15 CET -> Next Day 09:50 JST",
            "frequency": "Daily Direct",
        },
        {
            "flight_number": "EK318",
            "airline": "Emirates",
            "airline_code": "UAE",
            "origin_country": "United Arab Emirates",
            "origin_country_code": "AE",
            "origin_city": "Dubai",
            "origin_icao": "OMDB",
            "dest_icao": "RJAA",
            "aircraft": "Airbus A380-800",
            "schedule": "Daily 02:40 GST -> 17:25 JST",
            "frequency": "Daily Direct",
        },
        {
            "flight_number": "QF025",
            "airline": "Qantas",
            "airline_code": "QFA",
            "origin_country": "Australia",
            "origin_country_code": "AU",
            "origin_city": "Sydney",
            "origin_icao": "YSSY",
            "dest_icao": "RJTT",
            "aircraft": "Airbus A330-300",
            "schedule": "Daily 20:55 AEST -> Next Day 05:35 JST",
            "frequency": "Daily Direct",
        },
        {
            "flight_number": "SQ638",
            "airline": "Singapore Airlines",
            "airline_code": "SIA",
            "origin_country": "Singapore",
            "origin_country_code": "SG",
            "origin_city": "Singapore",
            "origin_icao": "WSSS",
            "dest_icao": "RJAA",
            "aircraft": "Boeing 787-10 Dreamliner",
            "schedule": "Daily 23:55 SGT -> Next Day 08:00 JST",
            "frequency": "3x Daily",
        },
        {
            "flight_number": "AI306",
            "airline": "Air India",
            "airline_code": "AIC",
            "origin_country": "India",
            "origin_country_code": "IN",
            "origin_city": "Delhi",
            "origin_icao": "VIDP",
            "dest_icao": "RJTT",
            "aircraft": "Boeing 787-8 Dreamliner",
            "schedule": "Daily 21:15 IST -> Next Day 08:45 JST",
            "frequency": "Daily Direct",
        },
        {
            "flight_number": "AC001",
            "airline": "Air Canada",
            "airline_code": "ACA",
            "origin_country": "Canada",
            "origin_country_code": "CA",
            "origin_city": "Toronto",
            "origin_icao": "CYYZ",
            "dest_icao": "RJTT",
            "aircraft": "Boeing 777-200LR",
            "schedule": "Daily 13:40 EDT -> Next Day 16:30 JST",
            "frequency": "Daily Direct",
        },
        {
            "flight_number": "KE705",
            "airline": "Korean Air",
            "airline_code": "KAL",
            "origin_country": "South Korea",
            "origin_country_code": "KR",
            "origin_city": "Seoul",
            "origin_icao": "RKSI",
            "dest_icao": "RJTT",
            "aircraft": "Airbus A330-300",
            "schedule": "Daily 09:00 KST -> 11:20 JST",
            "frequency": "4x Daily",
        },
    ],
    # Paris Charles de Gaulle (CDG)
    "paris": [
        {
            "flight_number": "AF007",
            "airline": "Air France",
            "airline_code": "AFR",
            "origin_country": "United States",
            "origin_country_code": "US",
            "origin_city": "New York",
            "origin_icao": "KJFK",
            "dest_icao": "LFPG",
            "aircraft": "Boeing 777-300ER",
            "schedule": "Daily 19:30 EDT -> Next Day 08:50 CET",
            "frequency": "4x Daily Direct",
        },
        {
            "flight_number": "BA304",
            "airline": "British Airways",
            "airline_code": "BAW",
            "origin_country": "United Kingdom",
            "origin_country_code": "GB",
            "origin_city": "London",
            "origin_icao": "EGLL",
            "dest_icao": "LFPG",
            "aircraft": "Airbus A320neo",
            "schedule": "Daily 07:15 GMT -> 09:40 CET",
            "frequency": "7x Daily Direct",
        },
        {
            "flight_number": "EK073",
            "airline": "Emirates",
            "airline_code": "UAE",
            "origin_country": "United Arab Emirates",
            "origin_country_code": "AE",
            "origin_city": "Dubai",
            "origin_icao": "OMDB",
            "dest_icao": "LFPG",
            "aircraft": "Airbus A380-800",
            "schedule": "Daily 08:20 GST -> 13:30 CET",
            "frequency": "3x Daily Direct",
        },
        {
            "flight_number": "JL045",
            "airline": "Japan Airlines",
            "airline_code": "JAL",
            "origin_country": "Japan",
            "origin_country_code": "JP",
            "origin_city": "Tokyo",
            "origin_icao": "RJTT",
            "dest_icao": "LFPG",
            "aircraft": "Boeing 777-300ER",
            "schedule": "Daily 10:40 JST -> 16:30 CET",
            "frequency": "Daily Direct",
        },
        {
            "flight_number": "AC870",
            "airline": "Air Canada",
            "airline_code": "ACA",
            "origin_country": "Canada",
            "origin_country_code": "CA",
            "origin_city": "Montreal",
            "origin_icao": "CYUL",
            "dest_icao": "LFPG",
            "aircraft": "Boeing 777-300ER",
            "schedule": "Daily 20:00 EDT -> Next Day 09:10 CET",
            "frequency": "2x Daily Direct",
        },
        {
            "flight_number": "SQ336",
            "airline": "Singapore Airlines",
            "airline_code": "SIA",
            "origin_country": "Singapore",
            "origin_country_code": "SG",
            "origin_city": "Singapore",
            "origin_icao": "WSSS",
            "dest_icao": "LFPG",
            "aircraft": "Airbus A350-900",
            "schedule": "Daily 00:15 SGT -> 07:15 CET",
            "frequency": "Daily Direct",
        },
        {
            "flight_number": "AI143",
            "airline": "Air India",
            "airline_code": "AIC",
            "origin_country": "India",
            "origin_country_code": "IN",
            "origin_city": "Delhi",
            "origin_icao": "VIDP",
            "dest_icao": "LFPG",
            "aircraft": "Boeing 787-8 Dreamliner",
            "schedule": "Daily 13:10 IST -> 18:40 CET",
            "frequency": "Daily Direct",
        },
        {
            "flight_number": "QF033",
            "airline": "Qantas",
            "airline_code": "QFA",
            "origin_country": "Australia",
            "origin_country_code": "AU",
            "origin_city": "Perth",
            "origin_icao": "YPPH",
            "dest_icao": "LFPG",
            "aircraft": "Boeing 787-9 Dreamliner",
            "schedule": "4x Weekly 19:35 AWST -> Next Day 06:55 CET",
            "frequency": "Direct Non-Stop",
        },
    ],
    # Rome Fiumicino (FCO)
    "rome": [
        {
            "flight_number": "AZ609",
            "airline": "ITA Airways",
            "airline_code": "AZA",
            "origin_country": "United States",
            "origin_country_code": "US",
            "origin_city": "New York",
            "origin_icao": "KJFK",
            "dest_icao": "LIRF",
            "aircraft": "Airbus A350-900",
            "schedule": "Daily 17:10 EDT -> Next Day 07:45 CET",
            "frequency": "Daily Direct",
        },
        {
            "flight_number": "BA548",
            "airline": "British Airways",
            "airline_code": "BAW",
            "origin_country": "United Kingdom",
            "origin_country_code": "GB",
            "origin_city": "London",
            "origin_icao": "EGLL",
            "dest_icao": "LIRF",
            "aircraft": "Airbus A320neo",
            "schedule": "Daily 08:50 GMT -> 12:20 CET",
            "frequency": "5x Daily Direct",
        },
        {
            "flight_number": "EK097",
            "airline": "Emirates",
            "airline_code": "UAE",
            "origin_country": "United Arab Emirates",
            "origin_country_code": "AE",
            "origin_city": "Dubai",
            "origin_icao": "OMDB",
            "dest_icao": "LIRF",
            "aircraft": "Boeing 777-300ER",
            "schedule": "Daily 09:10 GST -> 13:15 CET",
            "frequency": "2x Daily Direct",
        },
        {
            "flight_number": "LH232",
            "airline": "Lufthansa",
            "airline_code": "DLH",
            "origin_country": "Germany",
            "origin_country_code": "DE",
            "origin_city": "Frankfurt",
            "origin_icao": "EDDF",
            "dest_icao": "LIRF",
            "aircraft": "Airbus A321neo",
            "schedule": "Daily 12:25 CET -> 14:15 CET",
            "frequency": "4x Daily Direct",
        },
        {
            "flight_number": "AF1204",
            "airline": "Air France",
            "airline_code": "AFR",
            "origin_country": "France",
            "origin_country_code": "FR",
            "origin_city": "Paris",
            "origin_icao": "LFPG",
            "dest_icao": "LIRF",
            "aircraft": "Airbus A320",
            "schedule": "Daily 09:35 CET -> 11:40 CET",
            "frequency": "6x Daily Direct",
        },
        {
            "flight_number": "QF005",
            "airline": "Qantas",
            "airline_code": "QFA",
            "origin_country": "Australia",
            "origin_country_code": "AU",
            "origin_city": "Perth",
            "origin_icao": "YPPH",
            "dest_icao": "LIRF",
            "aircraft": "Boeing 787-9 Dreamliner",
            "schedule": "3x Weekly 22:05 AWST -> Next Day 08:45 CET",
            "frequency": "Seasonal Direct",
        },
        {
            "flight_number": "AI123",
            "airline": "Air India",
            "airline_code": "AIC",
            "origin_country": "India",
            "origin_country_code": "IN",
            "origin_city": "Delhi",
            "origin_icao": "VIDP",
            "dest_icao": "LIRF",
            "aircraft": "Boeing 787-8 Dreamliner",
            "schedule": "4x Weekly 14:20 IST -> 18:55 CET",
            "frequency": "Direct Flight",
        },
    ],
    # New York (JFK / EWR)
    "new york": [
        {
            "flight_number": "BA117",
            "airline": "British Airways",
            "airline_code": "BAW",
            "origin_country": "United Kingdom",
            "origin_country_code": "GB",
            "origin_city": "London",
            "origin_icao": "EGLL",
            "dest_icao": "KJFK",
            "aircraft": "Boeing 777-300ER",
            "schedule": "Daily 08:25 GMT -> 11:20 EDT",
            "frequency": "8x Daily Direct",
        },
        {
            "flight_number": "AF006",
            "airline": "Air France",
            "airline_code": "AFR",
            "origin_country": "France",
            "origin_country_code": "FR",
            "origin_city": "Paris",
            "origin_icao": "LFPG",
            "dest_icao": "KJFK",
            "aircraft": "Boeing 777-300ER",
            "schedule": "Daily 14:00 CET -> 16:30 EDT",
            "frequency": "5x Daily Direct",
        },
        {
            "flight_number": "DLH400",
            "airline": "Lufthansa",
            "airline_code": "DLH",
            "origin_country": "Germany",
            "origin_country_code": "DE",
            "origin_city": "Frankfurt",
            "origin_icao": "EDDF",
            "dest_icao": "KJFK",
            "aircraft": "Boeing 747-8 Intercontinental",
            "schedule": "Daily 11:00 CET -> 13:45 EDT",
            "frequency": "Daily Direct",
        },
        {
            "flight_number": "EK201",
            "airline": "Emirates",
            "airline_code": "UAE",
            "origin_country": "United Arab Emirates",
            "origin_country_code": "AE",
            "origin_city": "Dubai",
            "origin_icao": "OMDB",
            "dest_icao": "KJFK",
            "aircraft": "Airbus A380-800",
            "schedule": "Daily 08:30 GST -> 14:25 EDT",
            "frequency": "2x Daily Direct",
        },
        {
            "flight_number": "JL006",
            "airline": "Japan Airlines",
            "airline_code": "JAL",
            "origin_country": "Japan",
            "origin_country_code": "JP",
            "origin_city": "Tokyo",
            "origin_icao": "RJTT",
            "dest_icao": "KJFK",
            "aircraft": "Airbus A350-1000",
            "schedule": "Daily 11:05 JST -> 11:00 EDT",
            "frequency": "Daily Direct",
        },
        {
            "flight_number": "AIC101",
            "airline": "Air India",
            "airline_code": "AIC",
            "origin_country": "India",
            "origin_country_code": "IN",
            "origin_city": "Delhi",
            "origin_icao": "VIDP",
            "dest_icao": "KJFK",
            "aircraft": "Boeing 777-300ER",
            "schedule": "Daily 02:00 IST -> 07:35 EDT",
            "frequency": "Daily Non-Stop",
        },
        {
            "flight_number": "SQ024",
            "airline": "Singapore Airlines",
            "airline_code": "SIA",
            "origin_country": "Singapore",
            "origin_country_code": "SG",
            "origin_city": "Singapore",
            "origin_icao": "WSSS",
            "dest_icao": "KJFK",
            "aircraft": "Airbus A350-900ULR",
            "schedule": "Daily 12:35 SGT -> 19:15 EDT",
            "frequency": "World's Longest Non-Stop",
        },
        {
            "flight_number": "QF003",
            "airline": "Qantas",
            "airline_code": "QFA",
            "origin_country": "Australia",
            "origin_country_code": "AU",
            "origin_city": "Sydney",
            "origin_icao": "YSSY",
            "dest_icao": "KJFK",
            "aircraft": "Boeing 787-9 Dreamliner",
            "schedule": "4x Weekly 09:45 AEST -> 16:30 EDT (via AKL)",
            "frequency": "Direct Service",
        },
    ],
    # London Heathrow (LHR)
    "london": [
        {
            "flight_number": "BA178",
            "airline": "British Airways",
            "airline_code": "BAW",
            "origin_country": "United States",
            "origin_country_code": "US",
            "origin_city": "New York",
            "origin_icao": "KJFK",
            "dest_icao": "EGLL",
            "aircraft": "Boeing 777-200ER",
            "schedule": "Daily 08:00 EDT -> 19:45 GMT",
            "frequency": "8x Daily Direct",
        },
        {
            "flight_number": "UA901",
            "airline": "United Airlines",
            "airline_code": "UAL",
            "origin_country": "United States",
            "origin_country_code": "US",
            "origin_city": "San Francisco",
            "origin_icao": "KSFO",
            "dest_icao": "EGLL",
            "aircraft": "Boeing 777-200ER",
            "schedule": "Daily 13:00 PDT -> Next Day 07:15 GMT",
            "frequency": "2x Daily Direct",
        },
        {
            "flight_number": "EK001",
            "airline": "Emirates",
            "airline_code": "UAE",
            "origin_country": "United Arab Emirates",
            "origin_country_code": "AE",
            "origin_city": "Dubai",
            "origin_icao": "OMDB",
            "dest_icao": "EGLL",
            "aircraft": "Airbus A380-800",
            "schedule": "Daily 07:45 GST -> 11:40 GMT",
            "frequency": "6x Daily Direct",
        },
        {
            "flight_number": "SQ308",
            "airline": "Singapore Airlines",
            "airline_code": "SIA",
            "origin_country": "Singapore",
            "origin_country_code": "SG",
            "origin_city": "Singapore",
            "origin_icao": "WSSS",
            "dest_icao": "EGLL",
            "aircraft": "Airbus A380-800",
            "schedule": "Daily 09:05 SGT -> 15:40 GMT",
            "frequency": "4x Daily Direct",
        },
        {
            "flight_number": "JL043",
            "airline": "Japan Airlines",
            "airline_code": "JAL",
            "origin_country": "Japan",
            "origin_country_code": "JP",
            "origin_city": "Tokyo",
            "origin_icao": "RJTT",
            "dest_icao": "EGLL",
            "aircraft": "Boeing 777-300ER",
            "schedule": "Daily 09:55 JST -> 16:30 GMT",
            "frequency": "Daily Direct",
        },
        {
            "flight_number": "AI161",
            "airline": "Air India",
            "airline_code": "AIC",
            "origin_country": "India",
            "origin_country_code": "IN",
            "origin_city": "Delhi",
            "origin_icao": "VIDP",
            "dest_icao": "EGLL",
            "aircraft": "Boeing 787-8 Dreamliner",
            "schedule": "Daily 02:45 IST -> 07:30 GMT",
            "frequency": "3x Daily Direct",
        },
        {
            "flight_number": "QF009",
            "airline": "Qantas",
            "airline_code": "QFA",
            "origin_country": "Australia",
            "origin_country_code": "AU",
            "origin_city": "Perth",
            "origin_icao": "YPPH",
            "dest_icao": "EGLL",
            "aircraft": "Boeing 787-9 Dreamliner",
            "schedule": "Daily 18:45 AWST -> Next Day 05:05 GMT",
            "frequency": "Direct Non-Stop",
        },
    ],
    # Dubai (DXB)
    "dubai": [
        {
            "flight_number": "EK202",
            "airline": "Emirates",
            "airline_code": "UAE",
            "origin_country": "United States",
            "origin_country_code": "US",
            "origin_city": "New York",
            "origin_icao": "KJFK",
            "dest_icao": "OMDB",
            "aircraft": "Airbus A380-800",
            "schedule": "Daily 23:00 EDT -> Next Day 19:45 GST",
            "frequency": "2x Daily Direct",
        },
        {
            "flight_number": "EK002",
            "airline": "Emirates",
            "airline_code": "UAE",
            "origin_country": "United Kingdom",
            "origin_country_code": "GB",
            "origin_city": "London",
            "origin_icao": "EGLL",
            "dest_icao": "OMDB",
            "aircraft": "Airbus A380-800",
            "schedule": "Daily 14:15 GMT -> Next Day 00:35 GST",
            "frequency": "6x Daily Direct",
        },
        {
            "flight_number": "EK319",
            "airline": "Emirates",
            "airline_code": "UAE",
            "origin_country": "Japan",
            "origin_country_code": "JP",
            "origin_city": "Tokyo",
            "origin_icao": "RJAA",
            "dest_icao": "OMDB",
            "aircraft": "Airbus A380-800",
            "schedule": "Daily 22:30 JST -> Next Day 04:50 GST",
            "frequency": "Daily Direct",
        },
        {
            "flight_number": "EK511",
            "airline": "Emirates",
            "airline_code": "UAE",
            "origin_country": "India",
            "origin_country_code": "IN",
            "origin_city": "Delhi",
            "origin_icao": "VIDP",
            "dest_icao": "OMDB",
            "aircraft": "Boeing 777-300ER",
            "schedule": "Daily 10:35 IST -> 13:00 GST",
            "frequency": "4x Daily Direct",
        },
        {
            "flight_number": "EK415",
            "airline": "Emirates",
            "airline_code": "UAE",
            "origin_country": "Australia",
            "origin_country_code": "AU",
            "origin_city": "Sydney",
            "origin_icao": "YSSY",
            "dest_icao": "OMDB",
            "aircraft": "Airbus A380-800",
            "schedule": "Daily 21:45 AEST -> Next Day 05:15 GST",
            "frequency": "3x Daily Direct",
        },
    ],
}


def _interpolate_geodesic_3d(
    lon1: float, lat1: float, lon2: float, lat2: float, steps: int = 30
) -> list[list[float]]:
    """Generate 3D waypoints [lon, lat, alt_m] along a spherical great-circle arc."""
    phi1, lambda1 = math.radians(lat1), math.radians(lon1)
    phi2, lambda2 = math.radians(lat2), math.radians(lon2)

    # Great circle angular distance
    d = 2 * math.asin(
        math.sqrt(
            math.sin((phi2 - phi1) / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin((lambda2 - lambda1) / 2) ** 2
        )
    )

    if d < 1e-6:
        return [[lon1, lat1, 0.0], [lon2, lat2, 0.0]]

    pts: list[list[float]] = []
    max_alt_m = 11200.0  # Cruising altitude ~36,700 ft

    for i in range(steps + 1):
        f = i / float(steps)
        # Parabolic altitude curve
        alt = max_alt_m * math.sin(f * math.pi)

        a = math.sin((1 - f) * d) / math.sin(d)
        b = math.sin(f * d) / math.sin(d)
        x = a * math.cos(phi1) * math.cos(lambda1) + b * math.cos(phi2) * math.cos(lambda2)
        y = a * math.cos(phi1) * math.sin(lambda1) + b * math.cos(phi2) * math.sin(lambda2)
        z = a * math.sin(phi1) + b * math.sin(phi2)

        lat = math.degrees(math.atan2(z, math.sqrt(x**2 + y**2)))
        lon = math.degrees(math.atan2(y, x))
        pts.append([round(lon, 4), round(lat, 4), round(alt, 1)])

    return pts


def resolve_destination_airport(destination_name: str) -> Airport:
    """Find the most representative airport for a world destination name."""
    clean = destination_name.strip().lower()

    # Exact or common aliases
    alias_map = {
        "tokyo": "RJTT",
        "kyoto": "RJBB",  # Kansai serves Kyoto
        "osaka": "RJBB",
        "new york": "KJFK",
        "nyc": "KJFK",
        "london": "EGLL",
        "paris": "LFPG",
        "rome": "LIRF",
        "berlin": "EDDB",
        "frankfurt": "EDDF",
        "amsterdam": "EHAM",
        "san francisco": "KSFO",
        "los angeles": "KLAX",
        "chicago": "KORD",
        "las vegas": "KLAS",
        "seattle": "KSEA",
        "honolulu": "PHNL",
        "hawaii": "PHNL",
        "sydney": "YSSY",
        "melbourne": "YMML",
        "singapore": "WSSS",
        "hong kong": "VHHH",
        "bangkok": "VTBS",
        "seoul": "RKSI",
        "dubai": "OMDB",
        "doha": "OTHH",
        "cairo": "HECA",
        "delhi": "VIDP",
        "mumbai": "VABB",
        "bengaluru": "VOBL",
        "toronto": "CYYZ",
        "vancouver": "CYVR",
    }

    for key, icao in alias_map.items():
        if key in clean or clean in key:
            if icao in WORLD_AIRPORTS:
                return WORLD_AIRPORTS[icao]

    # Search airport names / cities in WORLD_AIRPORTS
    for code, apt in WORLD_AIRPORTS.items():
        if (
            clean in apt.city.lower()
            or clean in apt.name.lower()
            or clean == apt.iata.lower()
            or clean == apt.country.lower()
        ):
            return apt

    # Default fallback: Tokyo Haneda
    return WORLD_AIRPORTS["RJTT"]


def get_inbound_flight_plans(
    destination: str, origin_country_filter: str | None = None
) -> FlightPlansResponse:
    """Generate or retrieve inbound international flight plans for any destination worldwide.

    Groups flights by origin country and calculates full 3D geodesic flight paths.
    """
    dest_apt = resolve_destination_airport(destination)
    clean_dest_name = dest_apt.city

    # Check if curated entries exist for this city
    city_key = ""
    for k in CURATED_INBOUND_FLIGHTS:
        if k in destination.lower() or k in clean_dest_name.lower():
            city_key = k
            break

    raw_flights: list[dict[str, Any]] = []
    if city_key and city_key in CURATED_INBOUND_FLIGHTS:
        raw_flights = CURATED_INBOUND_FLIGHTS[city_key]
    else:
        # Dynamically synthesize realistic international inbound flights from major world hubs
        top_hubs = [
            ("KJFK", "United States", "US", "New York", "American Airlines", "AAL", "AA101", "Boeing 777-300ER"),
            ("KSFO", "United States", "US", "San Francisco", "United Airlines", "UAL", "UA850", "Boeing 787-9 Dreamliner"),
            ("EGLL", "United Kingdom", "GB", "London", "British Airways", "BAW", "BA45", "Airbus A350-1000"),
            ("LFPG", "France", "FR", "Paris", "Air France", "AFR", "AF180", "Boeing 777-300ER"),
            ("EDDF", "Germany", "DE", "Frankfurt", "Lufthansa", "DLH", "LH500", "Boeing 747-8"),
            ("OMDB", "United Arab Emirates", "AE", "Dubai", "Emirates", "UAE", "EK404", "Airbus A380-800"),
            ("WSSS", "Singapore", "SG", "Singapore", "Singapore Airlines", "SIA", "SQ220", "Airbus A350-900"),
            ("YSSY", "Australia", "AU", "Sydney", "Qantas", "QFA", "QF61", "Boeing 787-9 Dreamliner"),
            ("VIDP", "India", "IN", "Delhi", "Air India", "AIC", "AI202", "Boeing 787-8 Dreamliner"),
            ("RJTT", "Japan", "JP", "Tokyo", "All Nippon Airways", "ANA", "NH11", "Boeing 787-9 Dreamliner"),
            ("RKSI", "South Korea", "KR", "Seoul", "Korean Air", "KAL", "KE901", "Airbus A330-300"),
            ("CYYZ", "Canada", "CA", "Toronto", "Air Canada", "ACA", "AC85", "Boeing 787-9 Dreamliner"),
        ]

        for orig_icao, c_name, c_code, c_city, airline, a_code, flt_num, ac in top_hubs:
            if orig_icao == dest_apt.icao:
                continue
            raw_flights.append({
                "flight_number": flt_num,
                "airline": airline,
                "airline_code": a_code,
                "origin_country": c_name,
                "origin_country_code": c_code,
                "origin_city": c_city,
                "origin_icao": orig_icao,
                "dest_icao": dest_apt.icao,
                "aircraft": ac,
                "schedule": "Daily Direct Scheduled Service",
                "frequency": "Daily Direct",
            })

    # Process and build final InboundFlightPlan objects
    flight_items: list[InboundFlightPlan] = []
    seen_countries: set[str] = set()

    for item in raw_flights:
        orig_icao = item["origin_icao"]
        orig_apt = WORLD_AIRPORTS.get(orig_icao)
        if not orig_apt:
            continue

        orig_country = item["origin_country"]
        seen_countries.add(orig_country)

        # Apply country filter if specified
        if origin_country_filter and isinstance(origin_country_filter, str):
            filt = origin_country_filter.strip().lower()
            if filt not in orig_country.lower() and filt != item.get("origin_country_code", "").lower():
                continue

        # Calculate distance and flight duration
        dist_km = haversine_distance_km(
            orig_apt.latitude, orig_apt.longitude, dest_apt.latitude, dest_apt.longitude
        )
        # Average cruising speed 880 km/h + 30 mins climb/descent
        est_hours = round((dist_km / 880.0) + 0.5, 1)
        h = int(est_hours)
        m = int(round((est_hours - h) * 60))
        dur_str = f"{h}h {m}m"

        # 3D waypoints for Cesium globe
        waypoints_3d = _interpolate_geodesic_3d(
            orig_apt.longitude, orig_apt.latitude, dest_apt.longitude, dest_apt.latitude, steps=30
        )

        flight_items.append(
            InboundFlightPlan(
                flight_id=f"{item['flight_number']}-{orig_apt.iata}-{dest_apt.iata}",
                airline=item["airline"],
                airline_code=item["airline_code"],
                flight_number=item["flight_number"],
                origin_country=orig_country,
                origin_country_code=item["origin_country_code"],
                origin_city=item["origin_city"],
                origin_airport=AirportSummary(
                    icao=orig_apt.icao,
                    iata=orig_apt.iata,
                    name=orig_apt.name,
                    city=orig_apt.city,
                    country=orig_apt.country,
                    latitude=orig_apt.latitude,
                    longitude=orig_apt.longitude,
                ),
                destination_city=dest_apt.city,
                destination_airport=AirportSummary(
                    icao=dest_apt.icao,
                    iata=dest_apt.iata,
                    name=dest_apt.name,
                    city=dest_apt.city,
                    country=dest_apt.country,
                    latitude=dest_apt.latitude,
                    longitude=dest_apt.longitude,
                ),
                aircraft_type=item["aircraft"],
                departure_time_schedule=item["schedule"],
                duration_hours=est_hours,
                duration_formatted=dur_str,
                distance_km=round(dist_km, 1),
                frequency=item["frequency"],
                waypoints_3d=waypoints_3d,
            )
        )

    return FlightPlansResponse(
        destination=destination,
        destination_city=dest_apt.city,
        destination_airport=AirportSummary(
            icao=dest_apt.icao,
            iata=dest_apt.iata,
            name=dest_apt.name,
            city=dest_apt.city,
            country=dest_apt.country,
            latitude=dest_apt.latitude,
            longitude=dest_apt.longitude,
        ),
        total_inbound_flights=len(flight_items),
        origin_countries=sorted(list(seen_countries)),
        flights=flight_items,
    )


# -----------------------------------------------------------------------------
# Road Route Turn-by-Turn Navigation Engine (OSRM + Deterministic Fallback)
# -----------------------------------------------------------------------------

def _format_maneuver_instruction(
    m_type: str, modifier: str | None, street_name: str, dest_name: str
) -> tuple[str, str]:
    """Map OSRM maneuver type and modifier to a clean icon type and clear instruction."""
    norm_mod = (modifier or "").replace(" ", "_")
    m_type_norm = m_type.lower()
    road = street_name if street_name and street_name != "" else "unnamed road"

    if m_type_norm == "depart":
        return "depart", f"Depart on {road}"
    elif m_type_norm == "arrive":
        target = dest_name if dest_name else "destination"
        return "arrive", f"Arrive at {target}"
    elif m_type_norm in ("turn", "end_of_road"):
        if "right" in norm_mod:
            icon = "turn_right" if "sharp" not in norm_mod else "sharp_right"
            return icon, f"Turn right onto {road}"
        elif "left" in norm_mod:
            icon = "turn_left" if "sharp" not in norm_mod else "sharp_left"
            return icon, f"Turn left onto {road}"
        elif "straight" in norm_mod:
            return "continue", f"Continue straight onto {road}"
        return "turn_right", f"Turn onto {road}"
    elif m_type_norm == "new_name":
        return "continue", f"Continue as road becomes {road}"
    elif m_type_norm in ("merge", "on_ramp", "ramp"):
        if "right" in norm_mod:
            return "ramp", f"Take ramp on right onto {road}"
        elif "left" in norm_mod:
            return "ramp", f"Take ramp on left onto {road}"
        return "merge", f"Merge onto {road}"
    elif m_type_norm == "fork":
        if "left" in norm_mod:
            return "fork_left", f"Take the left fork onto {road}"
        return "fork_right", f"Take the right fork onto {road}"
    elif m_type_norm == "roundabout":
        return "roundabout", f"At roundabout, take exit onto {road}"
    elif m_type_norm == "off_ramp":
        return "ramp", f"Take exit toward {road}"
    else:
        return "continue", f"Follow {road}"


def _format_distance(meters: float) -> str:
    if meters >= 1000:
        return f"{meters / 1000.0:.1f} km"
    return f"{int(round(meters))} m"


def _format_duration(seconds: float) -> str:
    mins = int(round(seconds / 60.0))
    if mins < 60:
        return f"{mins} min" if mins > 0 else "< 1 min"
    hrs = mins // 60
    rem_mins = mins % 60
    return f"{hrs}h {rem_mins}m"


def _fallback_road_route(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    origin_name: str,
    dest_name: str,
) -> RoadRouteResponse:
    """Generate high-fidelity deterministic road route geometry and steps if OSRM is offline."""
    dist_km = haversine_distance_km(origin_lat, origin_lon, dest_lat, dest_lon) * 1.25
    # Average urban/suburban driving speed 42 km/h
    dur_min = max(3.0, (dist_km / 42.0) * 60.0)

    # Interpolate intermediate waypoints with slight road bends
    num_pts = max(12, min(50, int(dist_km * 3)))
    polyline: list[list[float]] = []

    for i in range(num_pts + 1):
        f = i / float(num_pts)
        lat = origin_lat + f * (dest_lat - origin_lat)
        lon = origin_lon + f * (dest_lon - origin_lon)
        # Add subtle orthogonal curvature to mimic real streets
        bend = 0.003 * math.sin(f * math.pi * 2.0)
        lat += bend
        lon += bend * 0.5
        polyline.append([round(lon, 6), round(lat, 6)])

    # Generate realistic turn steps
    p0 = polyline[0]
    p1 = polyline[len(polyline) // 4]
    p2 = polyline[len(polyline) // 2]
    p3 = polyline[(3 * len(polyline)) // 4]
    pend = polyline[-1]

    step_dist_m = (dist_km * 1000.0) / 4.0
    step_dur_s = (dur_min * 60.0) / 4.0

    orig_label = origin_name if origin_name else "Departure Point"
    dest_label = dest_name if dest_name else "Destination"

    steps = [
        RoadRouteStep(
            step_number=1,
            instruction=f"Depart from {orig_label} onto Main Arterial",
            maneuver_type="depart",
            street_name="Main Arterial",
            distance_m=round(step_dist_m, 1),
            distance_formatted=_format_distance(step_dist_m),
            duration_s=round(step_dur_s, 1),
            duration_formatted=_format_duration(step_dur_s),
            coordinates=p0,
        ),
        RoadRouteStep(
            step_number=2,
            instruction="Take ramp onto Metropolitan Expressway / Corridor",
            maneuver_type="ramp",
            street_name="Metropolitan Expressway",
            distance_m=round(step_dist_m, 1),
            distance_formatted=_format_distance(step_dist_m),
            duration_s=round(step_dur_s, 1),
            duration_formatted=_format_duration(step_dur_s),
            coordinates=p1,
        ),
        RoadRouteStep(
            step_number=3,
            instruction="Take exit toward City Center / Avenue",
            maneuver_type="turn_right",
            street_name="City Center Ave",
            distance_m=round(step_dist_m, 1),
            distance_formatted=_format_distance(step_dist_m),
            duration_s=round(step_dur_s, 1),
            duration_formatted=_format_duration(step_dur_s),
            coordinates=p2,
        ),
        RoadRouteStep(
            step_number=4,
            instruction=f"Turn left and arrive at {dest_label}",
            maneuver_type="arrive",
            street_name="Destination Access",
            distance_m=round(step_dist_m, 1),
            distance_formatted=_format_distance(step_dist_m),
            duration_s=round(step_dur_s, 1),
            duration_formatted=_format_duration(step_dur_s),
            coordinates=pend,
        ),
    ]

    return RoadRouteResponse(
        route_id=str(uuid4()),
        origin_name=orig_label,
        origin_coords=[origin_lon, origin_lat],
        destination_name=dest_label,
        destination_coords=[dest_lon, dest_lat],
        total_distance_km=round(dist_km, 1),
        total_distance_formatted=f"{dist_km:.1f} km",
        total_duration_min=round(dur_min, 1),
        total_duration_formatted=f"{int(round(dur_min))} mins",
        primary_roads=["Main Arterial", "Metropolitan Expressway", "City Center Ave"],
        summary="via Metropolitan Expressway & City Center Ave",
        steps=steps,
        polyline=polyline,
    )


def calculate_road_route(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    origin_name: str = "",
    dest_name: str = "",
) -> RoadRouteResponse:
    """Calculate driving route with turn-by-turn maneuvers and full polyline geometry.

    Uses OSRM driving engine with automatic deterministic fallback if network unavailable.
    """
    orig_label = origin_name.strip() if origin_name else "Origin"
    dest_label = dest_name.strip() if dest_name else "Destination"

    # Build OSRM query URL
    # Format: /route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson&steps=true
    url = (
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{origin_lon:.6f},{origin_lat:.6f};{dest_lon:.6f},{dest_lat:.6f}"
        f"?overview=full&geometries=geojson&steps=true"
    )

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "WORLDOS-Navigator/2.0 (Tactical Transit Engine)"},
        )
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                routes = data.get("routes", [])
                if routes:
                    route_data = routes[0]
                    total_dist_m = float(route_data.get("distance", 0.0))
                    total_dur_s = float(route_data.get("duration", 0.0))
                    geometry = route_data.get("geometry", {}).get("coordinates", [])

                    total_dist_km = total_dist_m / 1000.0
                    total_dur_min = total_dur_s / 60.0

                    # Parse legs & steps
                    steps_list: list[RoadRouteStep] = []
                    primary_roads_set: list[str] = []

                    legs = route_data.get("legs", [])
                    step_num = 1
                    for leg in legs:
                        for s in leg.get("steps", []):
                            m_obj = s.get("maneuver", {})
                            m_type = m_obj.get("type", "continue")
                            m_mod = m_obj.get("modifier")
                            s_name = s.get("name", "").strip()
                            s_dist = float(s.get("distance", 0.0))
                            s_dur = float(s.get("duration", 0.0))
                            s_loc = m_obj.get("location", [0.0, 0.0])

                            if s_name and s_name not in primary_roads_set:
                                primary_roads_set.append(s_name)

                            icon, instruction = _format_maneuver_instruction(
                                m_type, m_mod, s_name, dest_label
                            )

                            steps_list.append(
                                RoadRouteStep(
                                    step_number=step_num,
                                    instruction=instruction,
                                    maneuver_type=icon,
                                    street_name=s_name,
                                    distance_m=round(s_dist, 1),
                                    distance_formatted=_format_distance(s_dist),
                                    duration_s=round(s_dur, 1),
                                    duration_formatted=_format_duration(s_dur),
                                    coordinates=[round(s_loc[0], 6), round(s_loc[1], 6)],
                                )
                            )
                            step_num += 1

                    top_roads = primary_roads_set[:3]
                    summary_text = f"via {' & '.join(top_roads)}" if top_roads else "Direct road route"

                    return RoadRouteResponse(
                        route_id=str(uuid4()),
                        origin_name=orig_label,
                        origin_coords=[origin_lon, origin_lat],
                        destination_name=dest_label,
                        destination_coords=[dest_lon, dest_lat],
                        total_distance_km=round(total_dist_km, 1),
                        total_distance_formatted=f"{total_dist_km:.1f} km",
                        total_duration_min=round(total_dur_min, 1),
                        total_duration_formatted=f"{int(round(total_dur_min))} mins",
                        primary_roads=top_roads,
                        summary=summary_text,
                        steps=steps_list,
                        polyline=geometry,
                    )
    except Exception as exc:
        logger.warning("OSRM routing call failed (%s); serving deterministic fallback route", exc)

    return _fallback_road_route(origin_lat, origin_lon, dest_lat, dest_lon, orig_label, dest_label)
