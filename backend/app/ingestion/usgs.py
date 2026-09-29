"""USGS Earthquake Hazards Program public event ingestion contract."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.request import urlopen

USGS_EVENT_API = "https://earthquake.usgs.gov/fdsnws/event/1/query"


@dataclass(frozen=True)
class EarthquakeRecord:
    event_id: str
    title: str
    place: str
    mag: float
    time: datetime
    longitude: float
    latitude: float
    depth_km: float
    locator: str
    content_hash: str


def parse_earthquake_feature(feature: dict, locator: str, payload_hash: str) -> EarthquakeRecord:
    if not isinstance(feature, dict) or feature.get("type") != "Feature":
        raise ValueError("unexpected USGS GeoJSON feature")
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") or []
    if len(coordinates) < 2:
        raise ValueError("USGS earthquake feature missing coordinates")

    event_id = feature.get("id") or properties.get("code")
    if not event_id:
        raise ValueError("USGS earthquake feature missing event ID")

    epoch_ms = properties.get("time")
    if epoch_ms is None:
        raise ValueError("USGS earthquake feature missing timestamp")
    event_time = datetime.fromtimestamp(epoch_ms / 1000.0, tz=UTC)

    depth_km = float(coordinates[2]) if len(coordinates) > 2 else 0.0

    return EarthquakeRecord(
        event_id=str(event_id),
        title=properties.get("title") or f"M {properties.get('mag', 0)} Earthquake",
        place=properties.get("place") or "Unknown location",
        mag=float(properties.get("mag", 0.0)),
        time=event_time,
        longitude=float(coordinates[0]),
        latitude=float(coordinates[1]),
        depth_km=depth_km,
        locator=locator,
        content_hash=payload_hash,
    )


def fetch_earthquake(event_id: str) -> EarthquakeRecord:
    locator = f"{USGS_EVENT_API}?eventid={event_id}&format=geojson"
    with urlopen(locator, timeout=30) as response:  # nosec B310: fixed HTTPS host
        payload = json.loads(response.read())
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return parse_earthquake_feature(payload, locator, payload_hash)
