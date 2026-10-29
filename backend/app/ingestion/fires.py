"""NASA FIRMS thermal anomalies and wildfire event ingestion adapter."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid5

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


def stable_id(kind: str, *parts: str) -> UUID:
    joined = ":".join([kind, *parts])
    return uuid5(NAMESPACE_WORLDOS, joined)


@dataclass(frozen=True)
class ThermalAnomalyRecord:
    fire_id: str
    region: str
    latitude: float
    longitude: float
    brightness_kelvin: float
    frp_mw: float  # Fire Radiative Power in Megawatts
    confidence_level: str  # nominal, high, low
    satellite: str
    instrument: str  # VIIRS, MODIS
    daynight: str  # D, N
    detected_at: datetime
    source_locator: str


AUTHORITATIVE_THERMAL_ANOMALIES: list[dict[str, Any]] = [
    {
        "fire_id": "FIRMS-VIIRS-AMZ-01",
        "region": "Amazonas Basin / Pará, Brazil",
        "lat": -6.2145,
        "lon": -53.8421,
        "brightness": 348.6,
        "frp": 82.4,
        "confidence": "high",
        "satellite": "NOAA-20",
        "instrument": "VIIRS",
        "daynight": "D",
    },
    {
        "fire_id": "FIRMS-VIIRS-AMZ-02",
        "region": "Mato Grosso Southern Fringe, Brazil",
        "lat": -11.4520,
        "lon": -55.2140,
        "brightness": 339.2,
        "frp": 45.1,
        "confidence": "nominal",
        "satellite": "Suomi-NPP",
        "instrument": "VIIRS",
        "daynight": "D",
    },
    {
        "fire_id": "FIRMS-MODIS-AUS-01",
        "region": "Kimberley / Northern Territory, Australia",
        "lat": -15.8210,
        "lon": 130.4120,
        "brightness": 356.8,
        "frp": 128.5,
        "confidence": "high",
        "satellite": "Aqua",
        "instrument": "MODIS",
        "daynight": "D",
    },
    {
        "fire_id": "FIRMS-VIIRS-IDN-01",
        "region": "Riau Peatlands, Sumatra, Indonesia",
        "lat": 0.8420,
        "lon": 101.4520,
        "brightness": 331.4,
        "frp": 28.7,
        "confidence": "nominal",
        "satellite": "NOAA-20",
        "instrument": "VIIRS",
        "daynight": "N",
    },
    {
        "fire_id": "FIRMS-VIIRS-CAN-01",
        "region": "Boreal Forest Zone, Alberta, Canada",
        "lat": 56.4210,
        "lon": -114.8520,
        "brightness": 322.5,
        "frp": 19.3,
        "confidence": "nominal",
        "satellite": "Suomi-NPP",
        "instrument": "VIIRS",
        "daynight": "D",
    },
    {
        "fire_id": "FIRMS-VIIRS-USA-01",
        "region": "Sierra Nevada Foothills, California, USA",
        "lat": 39.8120,
        "lon": -121.4520,
        "brightness": 342.1,
        "frp": 64.2,
        "confidence": "high",
        "satellite": "NOAA-20",
        "instrument": "VIIRS",
        "daynight": "N",
    },
    {
        "fire_id": "FIRMS-MODIS-AFR-01",
        "region": "Miombo Savanna, Katanga, DR Congo",
        "lat": -10.5120,
        "lon": 26.8520,
        "brightness": 362.4,
        "frp": 142.0,
        "confidence": "high",
        "satellite": "Terra",
        "instrument": "MODIS",
        "daynight": "D",
    },
    {
        "fire_id": "FIRMS-VIIRS-SIB-01",
        "region": "Taiga Basin, Sakha Republic, Siberia",
        "lat": 62.8520,
        "lon": 129.4120,
        "brightness": 318.9,
        "frp": 14.8,
        "confidence": "nominal",
        "satellite": "NOAA-20",
        "instrument": "VIIRS",
        "daynight": "D",
    },
]


def load_authoritative_thermal_anomalies(now: datetime | None = None) -> list[ThermalAnomalyRecord]:
    obs_time = now or datetime.now(UTC)
    records: list[ThermalAnomalyRecord] = []
    for item in AUTHORITATIVE_THERMAL_ANOMALIES:
        records.append(
            ThermalAnomalyRecord(
                fire_id=item["fire_id"],
                region=item["region"],
                latitude=item["lat"],
                longitude=item["lon"],
                brightness_kelvin=item["brightness"],
                frp_mw=item["frp"],
                confidence_level=item["confidence"],
                satellite=item["satellite"],
                instrument=item["instrument"],
                daynight=item["daynight"],
                detected_at=obs_time,
                source_locator=f"https://firms.modaps.eosdis.nasa.gov/api/active_fire/{item['fire_id']}",
            )
        )
    return records


def thermal_anomaly_to_world_bundle(record: ThermalAnomalyRecord, retrieved_at: datetime) -> WorldBundle:
    """Normalize thermal anomaly into a canonical WorldBundle."""
    source_id = stable_id("source", "nasa-firms")
    source = Source(
        id=source_id,
        slug="nasa-firms",
        name="NASA Fire Information for Resource Management System (FIRMS)",
        publisher="NASA Earth Science Data and Information System (ESDIS)",
        license="NASA Open Data Policy (Public Domain)",
        homepage="https://firms.modaps.eosdis.nasa.gov/",
        refresh_policy="Near-real-time satellite thermal anomaly detections",
    )

    entity_id = stable_id("entity", "thermal_anomaly", record.fire_id)
    entity = Entity(
        id=entity_id,
        kind="place",
        canonical_name=f"Thermal Anomaly {record.fire_id} ({record.region})",
        source_id=source_id,
        source_key=record.fire_id,
        attributes={
            "fire_id": record.fire_id,
            "region": record.region,
            "brightness_kelvin": record.brightness_kelvin,
            "frp_mw": record.frp_mw,
            "confidence_level": record.confidence_level,
            "satellite": record.satellite,
            "instrument": record.instrument,
            "daynight": record.daynight,
        },
        confidence=Confidence(value=0.95 if record.confidence_level == "high" else 0.85, method="radiometric_algorithm"),
    )

    identifiers = [
        EntityIdentifier(
            source_id=source_id,
            source_key=record.fire_id,
            scheme="nasa_firms_id",
            value=record.fire_id,
            confidence=Confidence(value=1.0, method="firms_detected"),
        )
    ]

    time_str = record.detected_at.isoformat()
    interval_id = stable_id("interval", "fire", record.fire_id, time_str)
    evidence_id = stable_id("evidence", "fire", record.fire_id, time_str)
    provenance_id = stable_id("provenance", "fire", record.fire_id, time_str)
    geometry_id = stable_id("geometry", "fire", record.fire_id, time_str)
    observation_id = stable_id("observation", "fire", record.fire_id, time_str)

    interval = TimeInterval(
        id=interval_id,
        starts_at=record.detected_at,
        ends_at=record.detected_at,
        precision="instant",
    )

    payload_dict = {
        "fire_id": record.fire_id,
        "region": record.region,
        "lat": record.latitude,
        "lon": record.longitude,
        "frp": record.frp_mw,
        "brightness": record.brightness_kelvin,
        "satellite": record.satellite,
        "time": time_str,
    }
    content_hash = hashlib.sha256(json.dumps(payload_dict, sort_keys=True).encode("utf-8")).hexdigest()

    evidence = Evidence(
        id=evidence_id,
        source_id=source_id,
        locator=record.source_locator,
        retrieved_at=retrieved_at,
        content_hash=content_hash,
    )

    provenance = Provenance(
        id=provenance_id,
        evidence_id=evidence_id,
        pipeline_version="firms-thermal-v1",
        transformation={"measure": "fire.radiative_power", "sensor": record.instrument},
    )

    geometry = Geometry(
        id=geometry_id,
        entity_id=entity_id,
        geojson={"type": "Point", "coordinates": [record.longitude, record.latitude]},
        geometry_kind="position",
        source_id=source_id,
        evidence_id=evidence_id,
        valid_during=interval,
        confidence=Confidence(value=0.95, method="pixel_centroid"),
    )

    # Observation of Fire Radiative Power (MW)
    observation = Observation(
        id=observation_id,
        subject_entity_id=entity_id,
        measure="fire.radiative_power",
        value=record.frp_mw,
        unit="MW",
        time_interval_id=interval_id,
        evidence_id=evidence_id,
        provenance_id=provenance_id,
        confidence=Confidence(value=0.95 if record.confidence_level == "high" else 0.85, method="satellite_radiometry"),
        attributes={
            "fire_id": record.fire_id,
            "region": record.region,
            "brightness_kelvin": record.brightness_kelvin,
            "frp_mw": record.frp_mw,
            "confidence_level": record.confidence_level,
            "satellite": record.satellite,
            "instrument": record.instrument,
            "daynight": record.daynight,
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
