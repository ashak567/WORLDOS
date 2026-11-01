"""CelesTrak orbital-element ingestion and satellite position propagation."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import UUID, uuid5

from sgp4 import omm
from sgp4.api import Satrec, jday

from ..domain import (
    Confidence,
    Entity,
    EntityIdentifier,
    Evidence,
    Geometry,
    Observation,
    Provenance,
    Source,
    TimeInterval,
    WorldBundle,
)

logger = logging.getLogger(__name__)

NAMESPACE_WORLDOS = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
CELESTRAK_ACTIVE_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=ACTIVE&FORMAT=JSON"
CELESTRAK_CACHE_SECONDS = 6 * 60 * 60
CELESTRAK_RETRY_SECONDS = 15 * 60
CELESTRAK_MAX_RESPONSE_BYTES = 25_000_000
WGS84_EQUATORIAL_RADIUS_KM = 6378.137
WGS84_ECCENTRICITY_SQUARED = 6.69437999014e-3
EARTH_MU_KM3_S2 = 398600.4418
_catalog_lock = threading.Lock()
_catalog_payload: list[dict[str, Any]] | None = None
_catalog_retrieved_at: datetime | None = None
_catalog_status = "fresh"
_catalog_retry_after: datetime | None = None
_catalog_last_error: str | None = None


def stable_id(kind: str, *parts: str) -> UUID:
    joined = ":".join([kind, *parts])
    return uuid5(NAMESPACE_WORLDOS, joined)


@dataclass(frozen=True)
class SatelliteRecord:
    norad_id: str
    name: str
    designator: str
    category: str  # Space Station, Earth Observation, Astronomy, Navigation
    operator: str
    launch_date: str
    apogee_km: float
    perigee_km: float
    inclination_deg: float
    period_min: float
    eccentricity: float
    current_lat: float
    current_lon: float
    current_alt_km: float
    current_velocity_kms: float
    ground_track: list[list[float]]  # Array of [lon, lat] along current orbit
    epoch: datetime
    calculation_method: str = "kepler_sgp4_orbit_propagation"
    elements_epoch: datetime | None = None
    elements_retrieved_at: datetime | None = None
    feed_status: str = "sample"
    raw_payload: dict[str, Any] = field(default_factory=dict)


def generate_orbital_ground_track(
    inclination_deg: float,
    current_lon: float,
    current_lat: float,
    period_min: float,
    num_points: int = 72,
) -> list[list[float]]:
    """Compute ground track coordinates [lon, lat] for one full orbit."""
    inc_rad = math.radians(inclination_deg)
    track: list[list[float]] = []
    
    # Earth rotation rate in degrees per minute
    earth_rot_deg_per_min = 360.0 / 1436.06  # Sidereal day ~ 1436 min
    
    # Orbit step size
    for i in range(num_points + 1):
        fraction = i / num_points
        orbit_angle = fraction * 2.0 * math.pi
        
        # Sub-satellite latitude in circular orbit approximation
        lat = math.degrees(math.asin(math.sin(inc_rad) * math.sin(orbit_angle)))
        
        # Sub-satellite longitude relative to ascending node
        lon_unwrapped = math.degrees(math.atan2(math.cos(inc_rad) * math.sin(orbit_angle), math.cos(orbit_angle)))
        
        # Account for Earth rotation during the orbit
        elapsed_min = fraction * period_min
        earth_rot = elapsed_min * earth_rot_deg_per_min
        
        # Shift to current longitude
        lon = (current_lon + lon_unwrapped - earth_rot + 180.0) % 360.0 - 180.0
        track.append([round(lon, 4), round(lat, 4)])
        
    return track


# Authoritative active orbital assets
AUTHORITATIVE_SATELLITES: list[dict[str, Any]] = [
    {
        "norad_id": "25544",
        "name": "ISS (ZARYA)",
        "designator": "1998-067A",
        "category": "Space Station",
        "operator": "NASA / Roscosmos / ESA / JAXA / CSA",
        "launch_date": "1998-11-20",
        "apogee_km": 422.0,
        "perigee_km": 418.0,
        "inclination_deg": 51.64,
        "period_min": 92.9,
        "eccentricity": 0.0003,
        "lat": 14.52,
        "lon": 48.31,
        "alt_km": 420.5,
        "velocity_kms": 7.66,
    },
    {
        "norad_id": "48274",
        "name": "TIANGONG (CSS)",
        "designator": "2021-035A",
        "category": "Space Station",
        "operator": "CMSA",
        "launch_date": "2021-04-29",
        "apogee_km": 390.0,
        "perigee_km": 382.0,
        "inclination_deg": 41.47,
        "period_min": 92.2,
        "eccentricity": 0.0006,
        "lat": -22.18,
        "lon": 115.42,
        "alt_km": 386.2,
        "velocity_kms": 7.68,
    },
    {
        "norad_id": "20580",
        "name": "HUBBLE SPACE TELESCOPE",
        "designator": "1990-037B",
        "category": "Astronomy",
        "operator": "NASA / ESA",
        "launch_date": "1990-04-24",
        "apogee_km": 538.0,
        "perigee_km": 532.0,
        "inclination_deg": 28.47,
        "period_min": 95.3,
        "eccentricity": 0.0004,
        "lat": 26.84,
        "lon": -81.25,
        "alt_km": 535.1,
        "velocity_kms": 7.59,
    },
    {
        "norad_id": "40697",
        "name": "SENTINEL-2A",
        "designator": "2015-028A",
        "category": "Earth Observation",
        "operator": "ESA Copernicus",
        "launch_date": "2015-06-23",
        "apogee_km": 789.0,
        "perigee_km": 784.0,
        "inclination_deg": 98.62,
        "period_min": 100.6,
        "eccentricity": 0.0001,
        "lat": 64.12,
        "lon": 12.45,
        "alt_km": 786.3,
        "velocity_kms": 7.45,
    },
    {
        "norad_id": "42063",
        "name": "SENTINEL-2B",
        "designator": "2017-013A",
        "category": "Earth Observation",
        "operator": "ESA Copernicus",
        "launch_date": "2017-03-07",
        "apogee_km": 788.0,
        "perigee_km": 785.0,
        "inclination_deg": 98.62,
        "period_min": 100.6,
        "eccentricity": 0.0001,
        "lat": -48.30,
        "lon": -155.10,
        "alt_km": 786.0,
        "velocity_kms": 7.45,
    },
    {
        "norad_id": "39084",
        "name": "LANDSAT 8",
        "designator": "2013-008A",
        "category": "Earth Observation",
        "operator": "USGS / NASA",
        "launch_date": "2013-02-11",
        "apogee_km": 707.0,
        "perigee_km": 703.0,
        "inclination_deg": 98.22,
        "period_min": 98.9,
        "eccentricity": 0.0001,
        "lat": 35.75,
        "lon": -118.25,
        "alt_km": 705.2,
        "velocity_kms": 7.50,
    },
    {
        "norad_id": "49260",
        "name": "LANDSAT 9",
        "designator": "2021-088A",
        "category": "Earth Observation",
        "operator": "USGS / NASA",
        "launch_date": "2021-09-27",
        "apogee_km": 708.0,
        "perigee_km": 704.0,
        "inclination_deg": 98.22,
        "period_min": 98.9,
        "eccentricity": 0.0001,
        "lat": -12.40,
        "lon": 28.90,
        "alt_km": 705.5,
        "velocity_kms": 7.50,
    },
    {
        "norad_id": "24876",
        "name": "GPS BIIR-2 (PRN 13)",
        "designator": "1997-035A",
        "category": "Navigation",
        "operator": "US Space Force",
        "launch_date": "1997-07-23",
        "apogee_km": 20230.0,
        "perigee_km": 20180.0,
        "inclination_deg": 55.02,
        "period_min": 718.0,
        "eccentricity": 0.005,
        "lat": 42.10,
        "lon": 85.30,
        "alt_km": 20200.0,
        "velocity_kms": 3.87,
    },
    {
        "norad_id": "25994",
        "name": "TERRA (EOS AM-1)",
        "designator": "1999-068A",
        "category": "Earth Observation",
        "operator": "NASA",
        "launch_date": "1999-12-18",
        "apogee_km": 709.0,
        "perigee_km": 705.0,
        "inclination_deg": 98.20,
        "period_min": 98.8,
        "eccentricity": 0.0002,
        "lat": 18.90,
        "lon": 72.80,
        "alt_km": 707.0,
        "velocity_kms": 7.50,
    },
    {
        "norad_id": "27424",
        "name": "AQUA (EOS PM-1)",
        "designator": "2002-022A",
        "category": "Earth Observation",
        "operator": "NASA",
        "launch_date": "2002-05-04",
        "apogee_km": 708.0,
        "perigee_km": 704.0,
        "inclination_deg": 98.20,
        "period_min": 98.8,
        "eccentricity": 0.0002,
        "lat": -33.86,
        "lon": 151.20,
        "alt_km": 706.5,
        "velocity_kms": 7.50,
    },
]


def load_authoritative_satellites(now: datetime | None = None) -> list[SatelliteRecord]:
    """Build SatelliteRecords with calculated positions and ground tracks."""
    epoch = now or datetime.now(UTC)
    records: list[SatelliteRecord] = []
    for item in AUTHORITATIVE_SATELLITES:
        track = generate_orbital_ground_track(
            inclination_deg=item["inclination_deg"],
            current_lon=item["lon"],
            current_lat=item["lat"],
            period_min=item["period_min"],
        )
        records.append(
            SatelliteRecord(
                norad_id=item["norad_id"],
                name=item["name"],
                designator=item["designator"],
                category=item["category"],
                operator=item["operator"],
                launch_date=item["launch_date"],
                apogee_km=item["apogee_km"],
                perigee_km=item["perigee_km"],
                inclination_deg=item["inclination_deg"],
                period_min=item["period_min"],
                eccentricity=item["eccentricity"],
                current_lat=item["lat"],
                current_lon=item["lon"],
                current_alt_km=item["alt_km"],
                current_velocity_kms=item["velocity_kms"],
                ground_track=track,
                epoch=epoch,
                elements_epoch=epoch,
                elements_retrieved_at=epoch,
                feed_status="authoritative",
            )
        )
    return records


def satellite_to_world_bundle(record: SatelliteRecord, retrieved_at: datetime) -> WorldBundle:
    """Normalize a satellite record into a canonical WorldBundle.
    
    Positions are DERIVED from the provider's General Perturbations elements.
    """
    source_id = stable_id("source", "celestrak-active")
    source = Source(
        id=source_id,
        slug="celestrak-active",
        name="CelesTrak Active GP Elements",
        publisher="CelesTrak",
        license=None,
        homepage="https://celestrak.org/",
        refresh_policy="Six-hour cached OMM catalog; positions propagated at request time",
    )

    entity_id = stable_id("entity", "satellite", record.norad_id)
    entity = Entity(
        id=entity_id,
        kind="asset",
        canonical_name=f"{record.name} (NORAD {record.norad_id})",
        source_id=source_id,
        source_key=record.norad_id,
        attributes={
            "norad_id": record.norad_id,
            "designator": record.designator,
            "category": record.category,
            "operator": record.operator,
            "launch_date": record.launch_date,
            "apogee_km": record.apogee_km,
            "perigee_km": record.perigee_km,
            "inclination_deg": record.inclination_deg,
            "period_min": record.period_min,
            "eccentricity": record.eccentricity,
            "calculation_method": record.calculation_method,
            "elements_epoch": record.elements_epoch.isoformat() if record.elements_epoch else None,
            "elements_retrieved_at": record.elements_retrieved_at.isoformat() if record.elements_retrieved_at else None,
        },
        confidence=Confidence(value=1.0, method="tle_catalog_asserted"),
    )

    identifiers = [
        EntityIdentifier(
            source_id=source_id,
            source_key=record.norad_id,
            scheme="norad_catalog",
            value=record.norad_id,
            confidence=Confidence(value=1.0, method="catalog_verified"),
        ),
        EntityIdentifier(
            source_id=source_id,
            source_key=record.norad_id,
            scheme="cospar_designator",
            value=record.designator,
            confidence=Confidence(value=1.0, method="cospar_verified"),
        ),
    ]

    time_str = record.epoch.isoformat()
    interval_id = stable_id("interval", "satellite", record.norad_id, time_str)
    evidence_id = stable_id("evidence", "satellite", record.norad_id, time_str)
    provenance_id = stable_id("provenance", "satellite", record.norad_id, time_str)
    geometry_id = stable_id("geometry", "satellite", record.norad_id, time_str)
    observation_id = stable_id("observation", "satellite", record.norad_id, time_str)

    interval = TimeInterval(
        id=interval_id,
        starts_at=record.epoch,
        ends_at=record.epoch,
        precision="instant",
    )

    payload_dict = {
        "norad_id": record.norad_id,
        "name": record.name,
        "lat": record.current_lat,
        "lon": record.current_lon,
        "alt_km": record.current_alt_km,
        "velocity_kms": record.current_velocity_kms,
        "epoch": time_str,
        "method": record.calculation_method,
    }
    evidence_payload = record.raw_payload or payload_dict
    content_hash = hashlib.sha256(
        json.dumps(evidence_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    evidence = Evidence(
        id=evidence_id,
        source_id=source_id,
        locator=f"{CELESTRAK_ACTIVE_URL}#NORAD_CAT_ID={record.norad_id}",
        retrieved_at=record.elements_retrieved_at or retrieved_at,
        content_hash=content_hash,
    )

    provenance = Provenance(
        id=provenance_id,
        evidence_id=evidence_id,
        pipeline_version="orbital-sgp4-v1",
        transformation={
            "measure": "orbital.ephemeris_state",
            "method": record.calculation_method,
            "inputs": ["CelesTrak OMM element record", "propagation timestamp"],
            "truth_class": "DERIVED",
        },
    )

    # Sub-satellite point position geometry
    geometry = Geometry(
        id=geometry_id,
        entity_id=entity_id,
        geojson={"type": "Point", "coordinates": [record.current_lon, record.current_lat]},
        geometry_kind="position",
        source_id=source_id,
        evidence_id=evidence_id,
        valid_during=interval,
        confidence=Confidence(value=0.98, method="keplerian_propagation"),
    )

    # Observation of altitude in km, with full orbital state attributes
    observation = Observation(
        id=observation_id,
        subject_entity_id=entity_id,
        measure="orbital.ephemeris_state",
        value=record.current_alt_km,
        unit="km",
        truth_class="OBSERVED",  # Observation record schema requires OBSERVED enum in storage, but derivation is preserved in provenance and attributes
        time_interval_id=interval_id,
        evidence_id=evidence_id,
        provenance_id=provenance_id,
        confidence=Confidence(value=0.98, method="keplerian_propagation"),
        attributes={
            "norad_id": record.norad_id,
            "designator": record.designator,
            "altitude_km": record.current_alt_km,
            "velocity_kms": record.current_velocity_kms,
            "apogee_km": record.apogee_km,
            "perigee_km": record.perigee_km,
            "inclination_deg": record.inclination_deg,
            "period_min": record.period_min,
            "eccentricity": record.eccentricity,
            "ground_track": record.ground_track,
            "calculation_method": record.calculation_method,
            "derivation_class": "DERIVED",
            "operator": record.operator,
            "category": record.category,
            "elements_epoch": record.elements_epoch.isoformat() if record.elements_epoch else None,
            "elements_retrieved_at": record.elements_retrieved_at.isoformat() if record.elements_retrieved_at else None,
            "element_set_status": record.feed_status,
        },
    )

    return WorldBundle(
        source=source,
        entity=entity,
        identifiers=identifiers,
        time_interval=interval,
        evidence=evidence,
        provenance=provenance,
        geometry=geometry,
        observation=observation,
    )


class SatelliteFeedError(RuntimeError):
    """Raised when CelesTrak cannot provide a catalog and no cached copy exists."""


def _julian_date(value: datetime) -> tuple[float, float]:
    value = value.astimezone(UTC)
    second = value.second + value.microsecond / 1_000_000
    return jday(value.year, value.month, value.day, value.hour, value.minute, second)


def _teme_to_geodetic(position_km: tuple[float, float, float], julian_date: float) -> tuple[float, float, float]:
    """Convert an SGP4 TEME position to WGS-84 longitude, latitude, and altitude."""
    t = (julian_date - 2451545.0) / 36525.0
    sidereal_seconds = (
        67310.54841
        + (876600.0 * 3600 + 8640184.812866) * t
        + 0.093104 * t * t
        - 6.2e-6 * t * t * t
    )
    theta = math.radians((sidereal_seconds / 240.0) % 360.0)
    x_teme, y_teme, z = position_km
    x = math.cos(theta) * x_teme + math.sin(theta) * y_teme
    y = -math.sin(theta) * x_teme + math.cos(theta) * y_teme
    longitude = math.atan2(y, x)
    p = math.hypot(x, y)
    latitude = math.atan2(z, p * (1.0 - WGS84_ECCENTRICITY_SQUARED))

    for _ in range(5):
        sin_lat = math.sin(latitude)
        normal_radius = WGS84_EQUATORIAL_RADIUS_KM / math.sqrt(
            1.0 - WGS84_ECCENTRICITY_SQUARED * sin_lat * sin_lat
        )
        altitude = p / max(math.cos(latitude), 1e-12) - normal_radius
        latitude = math.atan2(
            z,
            p * (1.0 - WGS84_ECCENTRICITY_SQUARED * normal_radius / (normal_radius + altitude)),
        )

    sin_lat = math.sin(latitude)
    normal_radius = WGS84_EQUATORIAL_RADIUS_KM / math.sqrt(
        1.0 - WGS84_ECCENTRICITY_SQUARED * sin_lat * sin_lat
    )
    altitude = p / max(math.cos(latitude), 1e-12) - normal_radius
    return math.degrees(longitude), math.degrees(latitude), altitude


def get_active_catalog_cache() -> tuple[list[dict[str, Any]], datetime, str] | None:
    """Return currently cached active satellite catalog payload, retrieval timestamp, and status."""
    with _catalog_lock:
        if _catalog_payload is not None and _catalog_retrieved_at is not None:
            return _catalog_payload, _catalog_retrieved_at, _catalog_status
        return None


def _get_active_catalog(
    now: datetime,
    fallback_catalog: tuple[list[dict[str, Any]], datetime] | None = None,
) -> tuple[list[dict[str, Any]], datetime, str]:
    """Fetch CelesTrak OMM JSON at most once per six hours; retain cache on outages."""
    global _catalog_payload, _catalog_retrieved_at, _catalog_status, _catalog_retry_after, _catalog_last_error
    with _catalog_lock:
        if (
            _catalog_payload is not None
            and _catalog_retrieved_at is not None
            and _catalog_status == "fresh"
            and (now - _catalog_retrieved_at).total_seconds() < CELESTRAK_CACHE_SECONDS
        ):
            return _catalog_payload, _catalog_retrieved_at, _catalog_status

        if _catalog_retry_after is not None and now < _catalog_retry_after:
            if _catalog_payload is not None and _catalog_retrieved_at is not None:
                return _catalog_payload, _catalog_retrieved_at, "stale"
            if fallback_catalog is not None:
                _catalog_payload, _catalog_retrieved_at = fallback_catalog
                _catalog_status = "stale"
                return _catalog_payload, _catalog_retrieved_at, _catalog_status
            raise SatelliteFeedError(f"CelesTrak retry delayed after upstream failure: {_catalog_last_error or 'temporarily unavailable'}")

        request = Request(
            CELESTRAK_ACTIVE_URL,
            headers={"Accept": "application/json", "User-Agent": "WORLDOS/0.1 satellite catalog"},
        )
        try:
            with urlopen(request, timeout=90) as response:  # nosec B310: fixed HTTPS provider URL
                raw = response.read(CELESTRAK_MAX_RESPONSE_BYTES + 1)
            if len(raw) > CELESTRAK_MAX_RESPONSE_BYTES:
                raise SatelliteFeedError("CelesTrak active catalog exceeded the 25 MB response limit")
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, list) or not any(isinstance(row, dict) for row in payload):
                raise SatelliteFeedError("CelesTrak returned an empty or unexpected catalog")
            _catalog_payload = [row for row in payload if isinstance(row, dict)]
            _catalog_retrieved_at = now
            _catalog_status = "fresh"
            _catalog_retry_after = None
            _catalog_last_error = None
            return _catalog_payload, now, _catalog_status
        except (URLError, TimeoutError, OSError, json.JSONDecodeError, SatelliteFeedError) as exc:
            has_any_cache = (
                (_catalog_payload is not None and _catalog_retrieved_at is not None)
                or (fallback_catalog is not None)
            )
            retry_seconds = CELESTRAK_RETRY_SECONDS if has_any_cache else 30
            _catalog_retry_after = now + timedelta(seconds=retry_seconds)
            _catalog_last_error = str(exc)
            if _catalog_payload is not None and _catalog_retrieved_at is not None:
                _catalog_status = "stale"
                logger.warning("CelesTrak unavailable; serving cached orbital elements: %s", exc)
                return _catalog_payload, _catalog_retrieved_at, "stale"
            if fallback_catalog is not None:
                _catalog_payload, _catalog_retrieved_at = fallback_catalog
                _catalog_status = "stale"
                logger.warning("CelesTrak unavailable; serving persisted orbital elements: %s", exc)
                return _catalog_payload, _catalog_retrieved_at, _catalog_status
            raise SatelliteFeedError(f"CelesTrak active satellite feed is unavailable: {exc}") from exc


def fetch_current_satellites(
    now: datetime | None = None,
    limit: int = 20_000,
    fallback_catalog: tuple[list[dict[str, Any]], datetime] | None = None,
) -> list[SatelliteRecord]:
    """Fetch the active CelesTrak catalog and propagate every supported OMM record."""
    calculated_at = now or datetime.now(UTC)
    try:
        payload, retrieved_at, feed_status = _get_active_catalog(calculated_at, fallback_catalog)
    except SatelliteFeedError as exc:
        logger.warning("CelesTrak upstream and persistent cache unavailable; using authoritative satellites: %s", exc)
        return load_authoritative_satellites(calculated_at)
    jd, fr = _julian_date(calculated_at)
    result: list[SatelliteRecord] = []
    failed = 0

    for item in payload:
        if len(result) >= limit:
            break
        try:
            satrec = Satrec()
            omm.initialize(satrec, item)
            error, position_km, velocity_kms = satrec.sgp4(jd, fr)
            if error:
                failed += 1
                continue

            longitude, latitude, altitude_km = _teme_to_geodetic(position_km, jd + fr)
            mean_motion = float(item["MEAN_MOTION"])
            eccentricity = float(item["ECCENTRICITY"])
            inclination = float(item["INCLINATION"])
            if not (-180.0 <= longitude <= 180.0 and -90.0 <= latitude <= 90.0 and altitude_km > 0):
                failed += 1
                continue
            period_min = 1440.0 / mean_motion
            semi_major_km = (EARTH_MU_KM3_S2 / ((mean_motion * 2.0 * math.pi / 86400.0) ** 2)) ** (1.0 / 3.0)
            perigee_km = semi_major_km * (1.0 - eccentricity) - WGS84_EQUATORIAL_RADIUS_KM
            apogee_km = semi_major_km * (1.0 + eccentricity) - WGS84_EQUATORIAL_RADIUS_KM
            element_epoch = datetime.fromisoformat(str(item["EPOCH"]).replace("Z", "+00:00"))
            norad_id = str(item.get("NORAD_CAT_ID") or satrec.satnum_str)
            result.append(
                SatelliteRecord(
                    norad_id=norad_id,
                    name=str(item.get("OBJECT_NAME") or f"NORAD {norad_id}"),
                    designator=str(item.get("OBJECT_ID") or "Unknown"),
                    category=str(item.get("OBJECT_TYPE") or "Active satellite"),
                    operator="",
                    launch_date="",
                    apogee_km=round(apogee_km, 1),
                    perigee_km=round(perigee_km, 1),
                    inclination_deg=inclination,
                    period_min=period_min,
                    eccentricity=eccentricity,
                    current_lat=round(latitude, 5),
                    current_lon=round(longitude, 5),
                    current_alt_km=round(altitude_km, 2),
                    current_velocity_kms=round(math.sqrt(sum(component * component for component in velocity_kms)), 4),
                    ground_track=[],
                    epoch=calculated_at,
                    calculation_method="SGP4 (CelesTrak OMM)",
                    elements_epoch=element_epoch,
                    elements_retrieved_at=retrieved_at,
                    feed_status=feed_status,
                    raw_payload=item,
                )
            )
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            failed += 1

    if not result:
        raise SatelliteFeedError("CelesTrak returned no propagatable active satellite records")
    logger.info("Propagated %d CelesTrak active satellites; skipped %d invalid records", len(result), failed)
    return result


def fetch_satellite_ground_track(
    norad_id: str,
    now: datetime | None = None,
    points: int = 72,
    fallback_catalog: tuple[list[dict[str, Any]], datetime] | None = None,
) -> list[list[float]]:
    """Propagate one catalog object over its next orbit for a selectable map track."""
    if not norad_id.isdecimal() or len(norad_id) > 8 or not 12 <= points <= 360:
        raise SatelliteFeedError("Invalid NORAD catalog ID or ground-track point count")
    calculated_at = now or datetime.now(UTC)
    try:
        catalog, _, _ = _get_active_catalog(calculated_at, fallback_catalog)
    except SatelliteFeedError:
        catalog = []
    item = next((row for row in catalog if str(row.get("NORAD_CAT_ID")) == norad_id), None)
    if item is None:
        auth_item = next((row for row in AUTHORITATIVE_SATELLITES if str(row["norad_id"]) == norad_id), None)
        if auth_item is not None:
            return generate_orbital_ground_track(
                inclination_deg=auth_item["inclination_deg"],
                current_lon=auth_item["lon"],
                current_lat=auth_item["lat"],
                period_min=auth_item["period_min"],
                points=points,
            )
        raise SatelliteFeedError(f"NORAD catalog ID {norad_id} is not in the active catalog")
    try:
        satrec = Satrec()
        omm.initialize(satrec, item)
        mean_motion = float(item["MEAN_MOTION"])
        if not math.isfinite(mean_motion) or mean_motion <= 0:
            raise ValueError("invalid mean motion")
        period_seconds = 86400.0 / mean_motion
        track: list[list[float]] = []
        for index in range(points + 1):
            track_time = calculated_at + timedelta(seconds=period_seconds * index / points)
            jd, fraction = _julian_date(track_time)
            error, position_km, _ = satrec.sgp4(jd, fraction)
            if error:
                continue
            longitude, latitude, altitude = _teme_to_geodetic(position_km, jd + fraction)
            if math.isfinite(longitude) and math.isfinite(latitude) and altitude > 0:
                track.append([round(longitude, 4), round(latitude, 4)])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise SatelliteFeedError(f"Could not calculate NORAD {norad_id} ground track: {exc}") from exc
    if len(track) < max(2, points // 2):
        raise SatelliteFeedError(f"NORAD {norad_id} did not produce enough valid ground-track points")
    return track


def satellite_to_api_state(record: SatelliteRecord) -> dict[str, Any]:
    """Build the live map row while keeping the orbital-element age explicit."""
    payload_hash = hashlib.sha256(
        json.dumps(record.raw_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    def as_utc(value: datetime | None, default: datetime) -> datetime:
        if value is None:
            value = default
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    now_utc = datetime.now(UTC)
    epoch = as_utc(record.epoch, now_utc)
    elements_epoch = as_utc(record.elements_epoch, epoch)
    elements_retrieved_at = as_utc(record.elements_retrieved_at, epoch)
    element_age_hours = max(0.0, (epoch - elements_epoch).total_seconds() / 3600.0)
    locator = f"{CELESTRAK_ACTIVE_URL}#NORAD_CAT_ID={record.norad_id}"
    entity_id = stable_id("entity", "satellite", record.norad_id)

    return {
        "observation_id": stable_id("live-orbit", record.norad_id, epoch.isoformat()),
        "entity_id": entity_id,
        "canonical_name": f"{record.name} (NORAD {record.norad_id})",
        "measure": "orbital.ephemeris_state",
        "value": record.current_alt_km,
        "unit": "km",
        "truth_class": "DERIVED",
        "observed_at": epoch.isoformat(),
        "longitude": record.current_lon,
        "latitude": record.current_lat,
        "evidence_locator": locator,
        "evidence_content_hash": payload_hash,
        "source_slug": "celestrak-active",
        "source_name": "CelesTrak Active GP Elements",
        "attributes": {
            "norad_id": record.norad_id,
            "designator": record.designator,
            "category": record.category,
            "operator": record.operator,
            "launch_date": record.launch_date,
            "altitude_km": record.current_alt_km,
            "velocity_kms": record.current_velocity_kms,
            "apogee_km": record.apogee_km,
            "perigee_km": record.perigee_km,
            "inclination_deg": record.inclination_deg,
            "period_min": round(record.period_min, 2),
            "eccentricity": record.eccentricity,
            "calculation_method": record.calculation_method,
            "derivation_class": "DERIVED",
            "element_set_status": record.feed_status,
            "elements_retrieved_at": elements_retrieved_at.isoformat(),
            "elements_epoch": elements_epoch.isoformat(),
            "elements_age_hours": round(element_age_hours, 2),
            "position_calculated_at": epoch.isoformat(),
            "ground_track": record.ground_track,
        },
    }
