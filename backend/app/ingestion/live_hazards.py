"""Free, keyless live earthquake and natural-hazard event adapters."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

USGS_DAY_FEED = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"
EONET_EVENTS_FEED = "https://eonet.gsfc.nasa.gov/api/v3/events/geojson?status=open&days=30&limit=500"
GDACS_EVENTS_FEED = "https://www.gdacs.org/gdacsapi/api/Events/geteventlist/EVENTS4APP"
MAX_FEED_BYTES = 8_000_000
_CACHE_SECONDS = {"usgs": 60, "eonet": 600, "gdacs": 600}
_cache_lock = threading.Lock()
_cache: dict[str, tuple[list[dict[str, Any]], datetime]] = {}


class LiveHazardFeedError(RuntimeError):
    """Raised when a public live feed fails and no cached response is available."""


def _get_feed(name: str, url: str, now: datetime) -> tuple[list[dict[str, Any]], datetime, str]:
    with _cache_lock:
        cached = _cache.get(name)
        if cached and (now - cached[1]).total_seconds() < _CACHE_SECONDS[name]:
            return cached[0], cached[1], "fresh"

        request = Request(url, headers={"Accept": "application/geo+json, application/json", "User-Agent": "WORLDOS/0.1 (open-data map)"})
        try:
            with urlopen(request, timeout=20) as response:  # nosec B310: fixed HTTPS provider URLs
                raw = response.read(MAX_FEED_BYTES + 1)
            if len(raw) > MAX_FEED_BYTES:
                raise LiveHazardFeedError(f"{name} feed exceeded the 8 MB response limit")
            payload = json.loads(raw.decode("utf-8"))
            features = payload.get("features") if isinstance(payload, dict) else None
            if not isinstance(features, list):
                raise LiveHazardFeedError(f"{name} feed returned an unexpected GeoJSON structure")
            records = [row for row in features if isinstance(row, dict)]
            _cache[name] = (records, now)
            return records, now, "fresh"
        except (URLError, TimeoutError, UnicodeError, json.JSONDecodeError, LiveHazardFeedError) as exc:
            if cached:
                logger.warning("%s feed unavailable; serving cached events: %s", name, exc)
                return cached[0], cached[1], "stale"
            raise LiveHazardFeedError(f"{name} feed is unavailable: {exc}") from exc


def _payload_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _iso_time(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(UTC).isoformat()
    except ValueError:
        return None


def _millis_iso(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=UTC).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def fetch_recent_earthquakes(now: datetime | None = None) -> tuple[list[dict[str, Any]], datetime, str]:
    """Return USGS earthquakes of magnitude 2.5+ from the past day."""
    retrieved_at = now or datetime.now(UTC)
    features, retrieved_at, status = _get_feed("usgs", USGS_DAY_FEED, retrieved_at)
    result: list[dict[str, Any]] = []
    for feature in features:
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or []
        if not isinstance(coords, list) or len(coords) < 2:
            continue
        try:
            lon, lat = float(coords[0]), float(coords[1])
            if not math.isfinite(lon) or not math.isfinite(lat) or not (-180 <= lon <= 180 and -90 <= lat <= 90):
                continue
            event_time = _millis_iso(props.get("time"))
            depth_km = float(coords[2]) if len(coords) > 2 and coords[2] is not None else None
            mag = float(props["mag"]) if props.get("mag") is not None else None
            event_id = str(feature["id"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if event_time is None or (depth_km is not None and not math.isfinite(depth_km)):
            continue

        result.append({
            "id": f"usgs:{event_id}",
            "event_id": event_id,
            "canonical_name": props.get("title") or f"Earthquake {event_id}",
            "title": props.get("title") or f"Earthquake {event_id}",
            "event_type": "earthquake",
            "category": "Seismic event",
            "starts_at": event_time,
            "occurred_at": event_time,
            "magnitude": mag,
            "truth_class": "OBSERVED",
            "evidence_locator": props.get("url") or f"https://earthquake.usgs.gov/earthquakes/eventpage/{event_id}",
            "evidence_content_hash": _payload_hash(feature),
            "coordinates": [lon, lat],
            "point": [lon, lat],
            "source_slug": "usgs-earthquakes",
            "source_name": "USGS Earthquake Hazards Program",
            "attributes": {
                "place": props.get("place"),
                "depth_km": depth_km,
                "tsunami": bool(props["tsunami"]) if "tsunami" in props else None,
                "alert": props.get("alert"),
                "mag_type": props.get("magType"),
                "status": props.get("status"),
                "updated_at": _millis_iso(props.get("updated")),
                "feed_status": status,
                "feed_retrieved_at": retrieved_at.isoformat(),
            },
        })
    return result, retrieved_at, status


def fetch_open_natural_events(now: datetime | None = None) -> tuple[list[dict[str, Any]], datetime, str]:
    """Return NASA EONET open events with a publisher-provided point geometry."""
    retrieved_at = now or datetime.now(UTC)
    features, retrieved_at, status = _get_feed("eonet", EONET_EVENTS_FEED, retrieved_at)
    result: list[dict[str, Any]] = []
    for feature in features:
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or []
        geometry_type = geometry.get("type")
        geometry_dates = props.get("geometryDates") if isinstance(props.get("geometryDates"), list) else []
        if geometry_type == "LineString" and isinstance(coords, list) and coords:
            coords = coords[-1]
            event_date = geometry_dates[-1] if geometry_dates else props.get("date")
        else:
            event_date = props.get("date")
        if geometry_type not in ("Point", "LineString") or not isinstance(coords, list) or len(coords) < 2:
            continue
        try:
            lon, lat = float(coords[0]), float(coords[1])
            if not math.isfinite(lon) or not math.isfinite(lat) or not (-180 <= lon <= 180 and -90 <= lat <= 90):
                continue
        except (TypeError, ValueError):
            continue

        event_id = str(props.get("id") or feature.get("id") or "")
        if not event_id:
            continue
        category_rows = props.get("categories") if isinstance(props.get("categories"), list) else []
        source_rows = props.get("sources") if isinstance(props.get("sources"), list) else []
        categories = [str(row.get("title")) for row in category_rows if isinstance(row, dict) and row.get("title")]
        if any("earthquake" in category.lower() for category in categories):
            continue
        source_links = [row.get("url") for row in source_rows if isinstance(row, dict) and row.get("url")]
        event_time = _iso_time(event_date)
        result.append({
            "id": f"eonet:{event_id}",
            "event_id": event_id,
            "canonical_name": props.get("title") or event_id,
            "title": props.get("title") or event_id,
            "event_type": "natural_hazard",
            "category": ", ".join(categories) or "Natural event",
            "starts_at": event_time,
            "occurred_at": event_time,
            "truth_class": "OBSERVED",
            "evidence_locator": props.get("link") or "https://eonet.gsfc.nasa.gov/",
            "evidence_content_hash": _payload_hash(feature),
            "coordinates": [lon, lat],
            "point": [lon, lat],
            "source_slug": "nasa-eonet",
            "source_name": "NASA Earth Observatory Natural Event Tracker",
            "attributes": {
                "categories": categories,
                "source_links": source_links,
                "description": props.get("description"),
                "geometry_type": geometry_type,
                "track_point_count": len(geometry.get("coordinates", [])) if geometry_type == "LineString" else None,
                "feed_status": status,
                "feed_retrieved_at": retrieved_at.isoformat(),
            },
        })
    return result, retrieved_at, status


def fetch_gdacs_alerts(now: datetime | None = None) -> tuple[list[dict[str, Any]], datetime, str]:
    """Return current GDACS disaster alerts, including tropical cyclone and tsunami alerts."""
    retrieved_at = now or datetime.now(UTC)
    features, retrieved_at, status = _get_feed("gdacs", GDACS_EVENTS_FEED, retrieved_at)
    names = {"EQ": "Earthquake", "TC": "Tropical Cyclone", "TS": "Tsunami", "FL": "Flood", "VO": "Volcano", "DR": "Drought", "WF": "Wildfire"}
    result: list[dict[str, Any]] = []
    for feature in features:
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or []
        geometry_type = geometry.get("type")
        if geometry_type == "LineString" and isinstance(coords, list) and coords:
            coords = coords[-1]
        elif geometry_type != "Point":
            continue
        if not isinstance(coords, list) or len(coords) < 2:
            continue
        try:
            lon, lat = float(coords[0]), float(coords[1])
            if not math.isfinite(lon) or not math.isfinite(lat) or not (-180 <= lon <= 180 and -90 <= lat <= 90):
                continue
        except (TypeError, ValueError):
            continue

        event_id = str(props.get("eventid") or props.get("id") or "")
        event_type = str(props.get("eventtype") or props.get("eventType") or "").upper()
        name = str(props.get("eventname") or props.get("name") or props.get("title") or "").strip()
        if not event_id or not event_type:
            continue
        is_tsunami_alert = event_type == "TS" or "tsunami" in name.lower()
        if event_type == "EQ" and not is_tsunami_alert:
            continue
        current = props.get("iscurrent")
        if str(current).lower() == "false":
            continue

        severity = props.get("severitydata") if isinstance(props.get("severitydata"), dict) else {}
        start_time = _iso_time(props.get("fromdate") or props.get("fromDate"))
        alert_level = props.get("episodealertlevel") or props.get("alertlevel") or props.get("alertLevel")
        locator = props.get("htmldescription") or props.get("url") or "https://www.gdacs.org/"
        result.append({
            "id": f"gdacs:{event_type}:{event_id}:{props.get('episodeid', '')}",
            "event_id": event_id,
            "canonical_name": name or f"{names.get(event_type, event_type)} event {event_id}",
            "title": name or f"{names.get(event_type, event_type)} event {event_id}",
            "event_type": "natural_hazard",
            "category": "Tsunami" if is_tsunami_alert else names.get(event_type, event_type),
            "starts_at": start_time,
            "occurred_at": start_time,
            "truth_class": "OBSERVED",
            "evidence_locator": locator,
            "evidence_content_hash": _payload_hash(feature),
            "coordinates": [lon, lat],
            "point": [lon, lat],
            "source_slug": "gdacs",
            "source_name": "Global Disaster Alert and Coordination System (GDACS)",
            "attributes": {
                "gdacs_event_type": event_type,
                "episode_id": props.get("episodeid"),
                "country": props.get("country"),
                "alert_level": alert_level,
                "alert_score": props.get("alertscore"),
                "severity": severity.get("severity"),
                "severity_unit": severity.get("severityunit"),
                "severity_text": severity.get("severitytext"),
                "tsunami_alert": is_tsunami_alert,
                "current": props.get("iscurrent"),
                "feed_status": status,
                "feed_retrieved_at": retrieved_at.isoformat(),
            },
        })
    return result, retrieved_at, status
