"""Critical infrastructure ingestion adapter (Airports, Seaports, Spaceports)."""
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
class InfrastructureRecord:
    node_id: str
    name: str
    node_type: str  # airport, port, spaceport
    country: str
    latitude: float
    longitude: float
    elevation_m: float
    operator: str
    status: str
    primary_code: str  # IATA/ICAO for airports, UN/LOCODE for ports, Spaceport code
    secondary_code: str | None
    capabilities: list[str]
    source_locator: str


AUTHORITATIVE_INFRASTRUCTURE: list[dict[str, Any]] = [
    # Strategic Hub Airports
    {
        "node_id": "AIRPORT-HND",
        "name": "Tokyo Haneda International Airport",
        "node_type": "airport",
        "country": "Japan",
        "lat": 35.5494,
        "lon": 139.7798,
        "elevation_m": 6.4,
        "operator": "Japan Civil Aviation Bureau",
        "status": "OPERATIONAL",
        "primary_code": "HND",
        "secondary_code": "RJTT",
        "capabilities": ["4 Runways (Cat IIIb)", "International Hub", "B777/A350/A380 Capable"],
    },
    {
        "node_id": "AIRPORT-LHR",
        "name": "London Heathrow Airport",
        "node_type": "airport",
        "country": "United Kingdom",
        "lat": 51.4700,
        "lon": -0.4543,
        "elevation_m": 25.3,
        "operator": "Heathrow Airport Holdings",
        "status": "OPERATIONAL",
        "primary_code": "LHR",
        "secondary_code": "EGLL",
        "capabilities": ["2 Parallel Runways", "Global Transatlantic Hub", "5 Passenger Terminals"],
    },
    {
        "node_id": "AIRPORT-JFK",
        "name": "John F. Kennedy International Airport",
        "node_type": "airport",
        "country": "United States",
        "lat": 40.6413,
        "lon": -73.7781,
        "elevation_m": 4.0,
        "operator": "Port Authority of NY & NJ",
        "status": "OPERATIONAL",
        "primary_code": "JFK",
        "secondary_code": "KJFK",
        "capabilities": ["4 Runways", "Major North American International Gateway"],
    },
    {
        "node_id": "AIRPORT-DXB",
        "name": "Dubai International Airport",
        "node_type": "airport",
        "country": "United Arab Emirates",
        "lat": 25.2532,
        "lon": 55.3657,
        "elevation_m": 19.0,
        "operator": "Dubai Airports Company",
        "status": "OPERATIONAL",
        "primary_code": "DXB",
        "secondary_code": "OMDB",
        "capabilities": ["2 Runways", "Highest International Passenger Volume", "A380 Mega-Hub"],
    },
    {
        "node_id": "AIRPORT-SIN",
        "name": "Singapore Changi Airport",
        "node_type": "airport",
        "country": "Singapore",
        "lat": 1.3644,
        "lon": 103.9915,
        "elevation_m": 7.0,
        "operator": "Changi Airport Group",
        "status": "OPERATIONAL",
        "primary_code": "SIN",
        "secondary_code": "WSSS",
        "capabilities": ["3 Parallel Runways", "Southeast Asian Mega-Hub", "Cargo Logistics Hub"],
    },
    {
        "node_id": "AIRPORT-FRA",
        "name": "Frankfurt am Main Airport",
        "node_type": "airport",
        "country": "Germany",
        "lat": 50.0379,
        "lon": 8.5622,
        "elevation_m": 111.0,
        "operator": "Fraport AG",
        "status": "OPERATIONAL",
        "primary_code": "FRA",
        "secondary_code": "EDDF",
        "capabilities": ["4 Runways", "European Cargo & Star Alliance Hub"],
    },
    # Deep-Water Seaports
    {
        "node_id": "PORT-SGSIN",
        "name": "Port of Singapore (Jurong & Tuas Mega Port)",
        "node_type": "port",
        "country": "Singapore",
        "lat": 1.2644,
        "lon": 103.7485,
        "elevation_m": 2.0,
        "operator": "PSA International / MPA Singapore",
        "status": "OPERATIONAL",
        "primary_code": "SGSIN",
        "secondary_code": None,
        "capabilities": ["67 Container Berths", "Premier Global Bunkering Hub", "37M+ TEU Annual Capacity"],
    },
    {
        "node_id": "PORT-NLRTM",
        "name": "Port of Rotterdam (Maasvlakte 2)",
        "node_type": "port",
        "country": "Netherlands",
        "lat": 51.9540,
        "lon": 4.1450,
        "elevation_m": 3.0,
        "operator": "Port of Rotterdam Authority",
        "status": "OPERATIONAL",
        "primary_code": "NLRTM",
        "secondary_code": None,
        "capabilities": ["Deep-water draft up to 24m", "Largest Port in Europe", "Petrochemical Gateway"],
    },
    {
        "node_id": "PORT-CNSHA",
        "name": "Port of Shanghai (Yangshan Deep-Water Port)",
        "node_type": "port",
        "country": "China",
        "lat": 30.6120,
        "lon": 122.0640,
        "elevation_m": 5.0,
        "operator": "Shanghai International Port Group (SIPG)",
        "status": "OPERATIONAL",
        "primary_code": "CNSHA",
        "secondary_code": None,
        "capabilities": ["World's Busiest Container Port (47M+ TEU)", "Automated Guided Vehicle Terminal"],
    },
    {
        "node_id": "PORT-USLAX",
        "name": "Port of Los Angeles (San Pedro Bay)",
        "node_type": "port",
        "country": "United States",
        "lat": 33.7432,
        "lon": -118.2673,
        "elevation_m": 2.5,
        "operator": "City of Los Angeles Harbor Department",
        "status": "OPERATIONAL",
        "primary_code": "USLAX",
        "secondary_code": None,
        "capabilities": ["Leading Seaport in Western Hemisphere", "25 Cargo Terminals", "Trans-Pacific Gateway"],
    },
    # Global Spaceports / Launch Sites
    {
        "node_id": "SPACEPORT-KSC",
        "name": "Kennedy Space Center & Cape Canaveral Space Force Station",
        "node_type": "spaceport",
        "country": "United States",
        "lat": 28.5729,
        "lon": -80.6490,
        "elevation_m": 3.0,
        "operator": "NASA / US Space Force 45th Space Wing",
        "status": "OPERATIONAL",
        "primary_code": "KSC",
        "secondary_code": "CCSFS",
        "capabilities": ["LC-39A (Falcon Heavy/Crew Dragon)", "LC-39B (SLS/Artemis)", "SLC-40/41 (Orbital Launch)"],
    },
    {
        "node_id": "SPACEPORT-VSFB",
        "name": "Vandenberg Space Force Base (Space Launch Complex 4)",
        "node_type": "spaceport",
        "country": "United States",
        "lat": 34.6321,
        "lon": -120.6106,
        "elevation_m": 112.0,
        "operator": "US Space Force Space Launch Delta 30",
        "status": "OPERATIONAL",
        "primary_code": "VSFB",
        "secondary_code": "SLC-4E",
        "capabilities": ["Polar & Retrograde Orbit Launches", "Falcon 9 West Coast Pad", "NRO/DoD Payloads"],
    },
    {
        "node_id": "SPACEPORT-CSG",
        "name": "Guiana Space Centre (Centre Spatial Guyanais)",
        "node_type": "spaceport",
        "country": "France (French Guiana)",
        "lat": 5.2390,
        "lon": -52.7680,
        "elevation_m": 15.0,
        "operator": "CNES / ESA / Arianespace",
        "status": "OPERATIONAL",
        "primary_code": "CSG",
        "secondary_code": "ELA-4",
        "capabilities": ["Ariane 6 Pad (ELA-4)", "Vega-C Pad", "Near-Equatorial Launch Trajectory (5.2° N)"],
    },
    {
        "node_id": "SPACEPORT-BAIKONUR",
        "name": "Baikonur Cosmodrome (Site 31/6)",
        "node_type": "spaceport",
        "country": "Kazakhstan",
        "lat": 45.9646,
        "lon": 63.3052,
        "elevation_m": 100.0,
        "operator": "Roscosmos",
        "status": "OPERATIONAL",
        "primary_code": "BAIKONUR",
        "secondary_code": "Site-31",
        "capabilities": ["Soyuz-2 Human Spaceflight Pad", "ISS Crew Rotations", "Historic Spaceport Node"],
    },
    {
        "node_id": "SPACEPORT-SDSC",
        "name": "Satish Dhawan Space Centre (SDSC SHAR)",
        "node_type": "spaceport",
        "country": "India",
        "lat": 13.7200,
        "lon": 80.2300,
        "elevation_m": 1.0,
        "operator": "ISRO",
        "status": "OPERATIONAL",
        "primary_code": "SDSC",
        "secondary_code": "SHAR",
        "capabilities": ["First & Second Launch Pads (FLP/SLP)", "PSLV / GSLV / LVM3", "Chandrayaan/Gaganyaan Hub"],
    },
    {
        "node_id": "SPACEPORT-TNSC",
        "name": "Tanegashima Space Center (Yoshinobu Launch Complex)",
        "node_type": "spaceport",
        "country": "Japan",
        "lat": 30.3995,
        "lon": 130.9680,
        "elevation_m": 60.0,
        "operator": "JAXA",
        "status": "OPERATIONAL",
        "primary_code": "TNSC",
        "secondary_code": "YLP-1",
        "capabilities": ["H3 Rocket Launch Pad", "HTV Cargo Missions", "Pacific Ocean Clearance Arc"],
    },
]


def load_authoritative_infrastructure(now: datetime | None = None) -> list[InfrastructureRecord]:
    records: list[InfrastructureRecord] = []
    for item in AUTHORITATIVE_INFRASTRUCTURE:
        records.append(
            InfrastructureRecord(
                node_id=item["node_id"],
                name=item["name"],
                node_type=item["node_type"],
                country=item["country"],
                latitude=item["lat"],
                longitude=item["lon"],
                elevation_m=item["elevation_m"],
                operator=item["operator"],
                status=item["status"],
                primary_code=item["primary_code"],
                secondary_code=item["secondary_code"],
                capabilities=item["capabilities"],
                source_locator=f"curated://worldos/infrastructure/{item['node_id']}",
            )
        )
    return records


def infrastructure_to_world_bundle(record: InfrastructureRecord, retrieved_at: datetime) -> WorldBundle:
    """Normalize critical infrastructure into a canonical WorldBundle."""
    source_id = stable_id("source", "worldos-curated-infrastructure-directory")
    source = Source(
        id=source_id,
        slug="worldos-curated-infrastructure-directory",
        name="WORLDOS Curated Infrastructure Examples",
        publisher="WORLDOS project maintainers",
        license="Per-source terms are unverified; confirm before reuse",
        refresh_policy="Static examples; facility details are not verified",
    )

    entity_id = stable_id("entity", "infrastructure", record.node_id)
    entity = Entity(
        id=entity_id,
        kind="place",
        canonical_name=f"{record.name} [{record.primary_code}]",
        source_id=source_id,
        source_key=record.node_id,
        attributes={
            "node_id": record.node_id,
            "node_type": record.node_type,
            "country": record.country,
            "elevation_m": record.elevation_m,
            "operator": record.operator,
            "status": record.status,
            "primary_code": record.primary_code,
            "secondary_code": record.secondary_code,
            "capabilities": record.capabilities,
        },
        confidence=Confidence(value=0.25, method="curated_unverified_example"),
    )

    identifiers = [
        EntityIdentifier(
            source_id=source_id,
            source_key=record.node_id,
            scheme="facility_code",
            value=record.primary_code,
            confidence=Confidence(value=0.25, method="curated_unverified_example"),
        )
    ]

    time_str = retrieved_at.isoformat()
    interval_id = stable_id("interval", "infra", record.node_id, time_str)
    evidence_id = stable_id("evidence", "infra", record.node_id, time_str)
    provenance_id = stable_id("provenance", "infra", record.node_id, time_str)
    geometry_id = stable_id("geometry", "infra", record.node_id, time_str)
    observation_id = stable_id("observation", "infra", record.node_id, time_str)

    interval = TimeInterval(
        id=interval_id,
        starts_at=retrieved_at,
        ends_at=retrieved_at,
        precision="instant",
    )

    payload_dict = {
        "node_id": record.node_id,
        "name": record.name,
        "lat": record.latitude,
        "lon": record.longitude,
        "primary_code": record.primary_code,
        "type": record.node_type,
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
        pipeline_version="infrastructure-registry-v1",
        transformation={"measure": "infrastructure.status", "facility_type": record.node_type},
    )

    geometry = Geometry(
        id=geometry_id,
        entity_id=entity_id,
        geojson={"type": "Point", "coordinates": [record.longitude, record.latitude]},
        geometry_kind="position",
        source_id=source_id,
        evidence_id=evidence_id,
        valid_during=interval,
        confidence=Confidence(value=0.25, method="curated_unverified_example"),
    )

    observation = Observation(
        id=observation_id,
        subject_entity_id=entity_id,
        measure="infrastructure.status",
        value=1.0 if record.status == "OPERATIONAL" else 0.0,
        unit="status_code",
        time_interval_id=interval_id,
        evidence_id=evidence_id,
        provenance_id=provenance_id,
        confidence=Confidence(value=1.0, method="registry_record"),
        attributes={
            "node_id": record.node_id,
            "node_type": record.node_type,
            "country": record.country,
            "elevation_m": record.elevation_m,
            "operator": record.operator,
            "status": record.status,
            "primary_code": record.primary_code,
            "secondary_code": record.secondary_code,
            "capabilities": record.capabilities,
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
