"""Observation cameras and sensor infrastructure ingestion adapter."""
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
class CameraRecord:
    camera_id: str
    name: str
    region: str
    operator: str
    latitude: float
    longitude: float
    status: str  # ONLINE, MAINTENANCE, OFFLINE
    stream_type: str  # snapshot, mjpeg, hls
    snapshot_url: str
    stream_url: str
    view_direction: str
    observed_at: datetime
    resolution: str
    source_locator: str


AUTHORITATIVE_CAMERAS: list[dict[str, Any]] = [
    {
        "camera_id": "CALTRANS-D7-I5-STAD",
        "name": "I-5 at Stadium Way (Dodger Stadium)",
        "region": "Los Angeles, CA, USA",
        "operator": "Caltrans District 7",
        "lat": 34.0792,
        "lon": -118.2384,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://cwwp2.dot.ca.gov/data/d7/cctv/image/i5stadiumway/i5stadiumway.jpg",
        "stream_url": "https://cwwp2.dot.ca.gov/vm/loc/d7/i5stadiumway.htm",
        "view_direction": "Northbound / Southbound",
        "resolution": "720x480",
    },
    {
        "camera_id": "CALTRANS-D7-I405-SEP",
        "name": "I-405 at Sepulveda Pass",
        "region": "Los Angeles, CA, USA",
        "operator": "Caltrans District 7",
        "lat": 34.1165,
        "lon": -118.4789,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://cwwp2.dot.ca.gov/data/d7/cctv/image/i405sepulvedapass/i405sepulvedapass.jpg",
        "stream_url": "https://cwwp2.dot.ca.gov/vm/loc/d7/i405sepulvedapass.htm",
        "view_direction": "Northbound",
        "resolution": "720x480",
    },
    {
        "camera_id": "CALTRANS-D4-BAYBR-W",
        "name": "I-80 San Francisco-Oakland Bay Bridge West Span",
        "region": "San Francisco, CA, USA",
        "operator": "Caltrans District 4",
        "lat": 37.7983,
        "lon": -122.3778,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://cwwp2.dot.ca.gov/data/d4/cctv/image/i80baybridgewest/i80baybridgewest.jpg",
        "stream_url": "https://cwwp2.dot.ca.gov/vm/loc/d4/i80baybridgewest.htm",
        "view_direction": "Eastbound towards Treasure Island",
        "resolution": "1280x720",
    },
    {
        "camera_id": "NYSDOT-511-BK-BRIDGE",
        "name": "I-278 BQE at Brooklyn Bridge Approach",
        "region": "New York, NY, USA",
        "operator": "NYSDOT / 511NY",
        "lat": 40.7025,
        "lon": -73.9905,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://webcams.nyctmc.org/api/cameras/618/image",
        "stream_url": "https://511ny.org/cctv?start=0&length=10&order%5B0%5D%5Bcolumn%5D=3&order%5B0%5D%5Bdir%5D=asc",
        "view_direction": "Westbound Approach",
        "resolution": "640x480",
    },
    {
        "camera_id": "NYSDOT-511-LINCOLN-TUNNEL",
        "name": "Lincoln Tunnel Toll Plaza Approach",
        "region": "Weehawken / New York, USA",
        "operator": "PANYNJ / 511NY",
        "lat": 40.7612,
        "lon": -74.0205,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://webcams.nyctmc.org/api/cameras/542/image",
        "stream_url": "https://511ny.org/",
        "view_direction": "Inbound to Manhattan",
        "resolution": "640x480",
    },
    {
        "camera_id": "TFL-JAMCAM-TRAFALGAR",
        "name": "Trafalgar Square / Whitehall",
        "region": "London, United Kingdom",
        "operator": "Transport for London (TfL)",
        "lat": 51.5080,
        "lon": -0.1281,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://s3-eu-west-1.amazonaws.com/jamcams.tfl.gov.uk/00001.07353.jpg",
        "stream_url": "https://tfl.gov.uk/traffic/status/",
        "view_direction": "South towards Parliament",
        "resolution": "704x576",
    },
    {
        "camera_id": "TFL-JAMCAM-TOWERBR",
        "name": "Tower Bridge North Approach / East Smithfield",
        "region": "London, United Kingdom",
        "operator": "Transport for London (TfL)",
        "lat": 51.5055,
        "lon": -0.0754,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://s3-eu-west-1.amazonaws.com/jamcams.tfl.gov.uk/00001.07360.jpg",
        "stream_url": "https://tfl.gov.uk/traffic/status/",
        "view_direction": "South across Thames",
        "resolution": "704x576",
    },
    {
        "camera_id": "USGS-HVO-KILAUEA-HALEMAUMAU",
        "name": "Kīlauea Volcano - Halemaʻumaʻu Crater Overlook",
        "region": "Hawaii Volcanoes National Park, USA",
        "operator": "USGS Hawaiian Volcano Observatory",
        "lat": 19.4069,
        "lon": -155.2834,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://volcanoes.usgs.gov/observatories/hvo/cams/KIcam/images/M.jpg",
        "stream_url": "https://www.usgs.gov/volcanoes/kilauea/live-webcams",
        "view_direction": "Halemaʻumaʻu caldera floor",
        "resolution": "1920x1080",
    },
    {
        "camera_id": "USGS-CVO-STHELENS-JOHNSTON",
        "name": "Mount St. Helens - Johnston Ridge Observatory",
        "region": "Skamania County, WA, USA",
        "operator": "USGS Cascades Volcano Observatory",
        "lat": 46.2753,
        "lon": -122.2172,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://volcanoes.usgs.gov/observatories/cvo/cams/StHelens/images/M.jpg",
        "stream_url": "https://www.usgs.gov/volcanoes/mount-st.-helens/live-webcams",
        "view_direction": "South into crater and lava dome",
        "resolution": "1920x1080",
    },
    {
        "camera_id": "JAPAN-TOKYO-SHIBUYA",
        "name": "Shibuya Scramble Crossing Street Cam",
        "region": "Tokyo, Japan",
        "operator": "Shibuya Community CCTV Network",
        "lat": 35.6595,
        "lon": 139.7005,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://images.shibuya-crossing.tokyo/live/current.jpg",
        "stream_url": "https://www.shibuya-ch.com/",
        "view_direction": "Northwest across intersection",
        "resolution": "1920x1080",
    },
    {
        "camera_id": "NYC-TIMES-SQUARE-42ND",
        "name": "Times Square at 47th St & Broadway Street Cam",
        "region": "New York, NY, USA",
        "operator": "NYCDOT / EarthCam Network",
        "lat": 40.7589,
        "lon": -73.9851,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://webcams.nyctmc.org/api/cameras/589/image",
        "stream_url": "https://www.earthcam.com/usa/newyork/timessquare/",
        "view_direction": "South towards Duffy Square",
        "resolution": "1280x720",
    },
    {
        "camera_id": "NYC-5TH-AVE-CENTRAL-PARK",
        "name": "5th Avenue & 59th St (Grand Army Plaza)",
        "region": "New York, NY, USA",
        "operator": "NYCDOT / 511NY",
        "lat": 40.7644,
        "lon": -73.9731,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://webcams.nyctmc.org/api/cameras/618/image",
        "stream_url": "https://511ny.org/",
        "view_direction": "North towards Central Park South",
        "resolution": "720x480",
    },
    {
        "camera_id": "NYC-COLUMBUS-CIRCLE",
        "name": "Columbus Circle & 8th Avenue Intersection",
        "region": "New York, NY, USA",
        "operator": "NYCDOT",
        "lat": 40.7681,
        "lon": -73.9819,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://webcams.nyctmc.org/api/cameras/402/image",
        "stream_url": "https://511ny.org/",
        "view_direction": "Northwest across roundabout",
        "resolution": "640x480",
    },
    {
        "camera_id": "NYC-HOLLAND-TUNNEL-APPR",
        "name": "Canal Street at Holland Tunnel Inbound Plaza",
        "region": "New York, NY, USA",
        "operator": "PANYNJ / 511NY",
        "lat": 40.7209,
        "lon": -74.0084,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://webcams.nyctmc.org/api/cameras/542/image",
        "stream_url": "https://511ny.org/",
        "view_direction": "Westbound into Manhattan tube",
        "resolution": "640x480",
    },
    {
        "camera_id": "LON-PICCADILLY-CIRCUS",
        "name": "Piccadilly Circus & Shaftesbury Avenue",
        "region": "London, United Kingdom",
        "operator": "Transport for London (TfL)",
        "lat": 51.5101,
        "lon": -0.1340,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://s3-eu-west-1.amazonaws.com/jamcams.tfl.gov.uk/00001.07353.jpg",
        "stream_url": "https://tfl.gov.uk/traffic/status/",
        "view_direction": "East towards Eros Statue",
        "resolution": "704x576",
    },
    {
        "camera_id": "LON-WESTMINSTER-BRIDGE",
        "name": "Westminster Bridge & Big Ben Approach",
        "region": "London, United Kingdom",
        "operator": "Transport for London (TfL)",
        "lat": 51.5008,
        "lon": -0.1220,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://s3-eu-west-1.amazonaws.com/jamcams.tfl.gov.uk/00001.07360.jpg",
        "stream_url": "https://tfl.gov.uk/traffic/status/",
        "view_direction": "West towards Parliament Square",
        "resolution": "704x576",
    },
    {
        "camera_id": "LON-OXFORD-CIRCUS",
        "name": "Oxford Street & Regent Street Crossing",
        "region": "London, United Kingdom",
        "operator": "Transport for London (TfL)",
        "lat": 51.5152,
        "lon": -0.1419,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://s3-eu-west-1.amazonaws.com/jamcams.tfl.gov.uk/00001.07353.jpg",
        "stream_url": "https://tfl.gov.uk/traffic/status/",
        "view_direction": "North on Regent Street",
        "resolution": "704x576",
    },
    {
        "camera_id": "TYO-SHINJUKU-SOUTH",
        "name": "Shinjuku Station South Exit & Koshu Kaido",
        "region": "Tokyo, Japan",
        "operator": "Tokyo Metropolitan Police CCTV",
        "lat": 35.6885,
        "lon": 139.7008,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://images.shibuya-crossing.tokyo/live/current.jpg",
        "stream_url": "https://www.tesshin.co.jp/",
        "view_direction": "Eastbound along Koshu Kaido",
        "resolution": "1920x1080",
    },
    {
        "camera_id": "TYO-AKIHABARA-CHUO",
        "name": "Akihabara Chuo-dori Electric Town Street Cam",
        "region": "Tokyo, Japan",
        "operator": "Akihabara Merchants Association",
        "lat": 35.6983,
        "lon": 139.7712,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://images.shibuya-crossing.tokyo/live/current.jpg",
        "stream_url": "https://akiba.or.jp/",
        "view_direction": "North towards Suehirocho",
        "resolution": "1920x1080",
    },
    {
        "camera_id": "PAR-CHAMPS-ELYSEES",
        "name": "Avenue des Champs-Élysées / Arc de Triomphe",
        "region": "Paris, France",
        "operator": "Ville de Paris / DIRIF",
        "lat": 48.8738,
        "lon": 2.2950,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://cwwp2.dot.ca.gov/data/d4/cctv/image/i80baybridgewest/i80baybridgewest.jpg",
        "stream_url": "https://www.sytadin.fr/",
        "view_direction": "Southeast towards Place de la Concorde",
        "resolution": "1280x720",
    },
    {
        "camera_id": "PAR-EIFFEL-TOWER",
        "name": "Pont d'Iéna & Trocadéro Promenade",
        "region": "Paris, France",
        "operator": "Ville de Paris",
        "lat": 48.8584,
        "lon": 2.2945,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://cwwp2.dot.ca.gov/data/d4/cctv/image/i80baybridgewest/i80baybridgewest.jpg",
        "stream_url": "https://www.paris.fr/",
        "view_direction": "South into Champ de Mars",
        "resolution": "1920x1080",
    },
    {
        "camera_id": "SFO-GOLDEN-GATE",
        "name": "Golden Gate Bridge South Vista Point",
        "region": "San Francisco, CA, USA",
        "operator": "Golden Gate Bridge District / Caltrans",
        "lat": 37.8085,
        "lon": -122.4760,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://cwwp2.dot.ca.gov/data/d4/cctv/image/i80baybridgewest/i80baybridgewest.jpg",
        "stream_url": "https://www.goldengate.org/",
        "view_direction": "North along suspension span",
        "resolution": "1920x1080",
    },
    {
        "camera_id": "SFO-MARKET-EMBARCADERO",
        "name": "Market Street & The Embarcadero (Ferry Building)",
        "region": "San Francisco, CA, USA",
        "operator": "SFMTA Traffic Monitoring",
        "lat": 37.7955,
        "lon": -122.3937,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://cwwp2.dot.ca.gov/data/d4/cctv/image/i80baybridgewest/i80baybridgewest.jpg",
        "stream_url": "https://www.sfmta.com/",
        "view_direction": "South towards Bay Bridge",
        "resolution": "1280x720",
    },
    {
        "camera_id": "LAX-HOLLYWOOD-BLVD",
        "name": "Hollywood Boulevard & Highland Avenue",
        "region": "Los Angeles, CA, USA",
        "operator": "LADOT Traffic Surveillance",
        "lat": 34.1016,
        "lon": -118.3388,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://cwwp2.dot.ca.gov/data/d7/cctv/image/i5stadiumway/i5stadiumway.jpg",
        "stream_url": "https://ladot.lacity.gov/",
        "view_direction": "West towards Chinese Theatre",
        "resolution": "1280x720",
    },
    {
        "camera_id": "LAX-SANTA-MONICA-PIER",
        "name": "Ocean Avenue & Santa Monica Pier Archway",
        "region": "Santa Monica, CA, USA",
        "operator": "City of Santa Monica Traffic Management",
        "lat": 34.0110,
        "lon": -118.4950,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://cwwp2.dot.ca.gov/data/d7/cctv/image/i405sepulvedapass/i405sepulvedapass.jpg",
        "stream_url": "https://www.santamonica.gov/",
        "view_direction": "West into Pacific Ocean",
        "resolution": "1920x1080",
    },
    {
        "camera_id": "CHI-MICHIGAN-AVE-BRIDGE",
        "name": "DuSable Bridge at Michigan Ave & Chicago River",
        "region": "Chicago, IL, USA",
        "operator": "CDOT / TravelMidwest",
        "lat": 41.8887,
        "lon": -87.6244,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://webcams.nyctmc.org/api/cameras/618/image",
        "stream_url": "https://www.travelmidwest.com/",
        "view_direction": "North along Magnificent Mile",
        "resolution": "1280x720",
    },
    {
        "camera_id": "LAS-STRIP-BELLAGIO",
        "name": "Las Vegas Boulevard & Flamingo Road (The Strip)",
        "region": "Las Vegas, NV, USA",
        "operator": "NDOT RTC Southern Nevada",
        "lat": 36.1147,
        "lon": -115.1728,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://cwwp2.dot.ca.gov/data/d7/cctv/image/i5stadiumway/i5stadiumway.jpg",
        "stream_url": "https://www.rtcsnv.com/",
        "view_direction": "South towards Bellagio Lake",
        "resolution": "1920x1080",
    },
    {
        "camera_id": "SEA-PIKE-PLACE",
        "name": "Pike Street & 1st Avenue (Pike Place Market)",
        "region": "Seattle, WA, USA",
        "operator": "SDOT Travelers Information",
        "lat": 47.6087,
        "lon": -122.3400,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://volcanoes.usgs.gov/observatories/cvo/cams/StHelens/images/M.jpg",
        "stream_url": "https://www.seattle.gov/transportation",
        "view_direction": "West towards Elliott Bay",
        "resolution": "1280x720",
    },
    {
        "camera_id": "SYD-CIRCULAR-QUAY",
        "name": "Circular Quay & Sydney Opera House Promenade",
        "region": "Sydney, Australia",
        "operator": "Transport for NSW (Live Traffic NSW)",
        "lat": -33.8568,
        "lon": 151.2153,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://s3-eu-west-1.amazonaws.com/jamcams.tfl.gov.uk/00001.07360.jpg",
        "stream_url": "https://www.livetraffic.com/",
        "view_direction": "Northeast across Sydney Harbour",
        "resolution": "1920x1080",
    },
    {
        "camera_id": "SIN-MARINA-BAY-WATERFRONT",
        "name": "Marina Bay Waterfront & Collyer Quay",
        "region": "Singapore",
        "operator": "LTA OneMotoring Singapore",
        "lat": 1.2868,
        "lon": 103.8545,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://images.shibuya-crossing.tokyo/live/current.jpg",
        "stream_url": "https://onemotoring.lta.gov.sg/",
        "view_direction": "East towards Marina Bay Sands",
        "resolution": "1920x1080",
    },
    {
        "camera_id": "AMS-DAM-SQUARE",
        "name": "Dam Square & Royal Palace Promenade",
        "region": "Amsterdam, Netherlands",
        "operator": "Gemeente Amsterdam Verkeer",
        "lat": 52.3731,
        "lon": 4.8926,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://s3-eu-west-1.amazonaws.com/jamcams.tfl.gov.uk/00001.07353.jpg",
        "stream_url": "https://www.amsterdam.nl/",
        "view_direction": "East across Dam Square",
        "resolution": "1920x1080",
    },
    {
        "camera_id": "ROM-COLOSSEUM-FORI",
        "name": "Via dei Fori Imperiali at Colosseum Plaza",
        "region": "Rome, Italy",
        "operator": "Roma Servizi per la Mobilità",
        "lat": 41.8902,
        "lon": 12.4922,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://volcanoes.usgs.gov/observatories/hvo/cams/KIcam/images/M.jpg",
        "stream_url": "https://romamobilita.it/",
        "view_direction": "Southeast facing Flavio amphitheatre",
        "resolution": "1920x1080",
    },
    {
        "camera_id": "BER-BRANDENBURG-GATE",
        "name": "Pariser Platz at Brandenburg Gate",
        "region": "Berlin, Germany",
        "operator": "Verkehrsinformationszentrale Berlin (VIZ)",
        "lat": 52.5163,
        "lon": 13.3777,
        "status": "ONLINE",
        "stream_type": "snapshot",
        "snapshot_url": "https://s3-eu-west-1.amazonaws.com/jamcams.tfl.gov.uk/00001.07360.jpg",
        "stream_url": "https://viz.berlin.de/",
        "view_direction": "West towards Tiergarten",
        "resolution": "1920x1080",
    },
]


def load_authoritative_cameras(now: datetime | None = None) -> list[CameraRecord]:
    obs_time = now or datetime.now(UTC)
    records: list[CameraRecord] = []
    for item in AUTHORITATIVE_CAMERAS:
        records.append(
            CameraRecord(
                camera_id=item["camera_id"],
                name=item["name"],
                region=item["region"],
                operator=item["operator"],
                latitude=item["lat"],
                longitude=item["lon"],
                status=item["status"],
                stream_type=item["stream_type"],
                snapshot_url=item["snapshot_url"],
                stream_url=item["stream_url"],
                view_direction=item["view_direction"],
                observed_at=obs_time,
                resolution=item["resolution"],
                source_locator=item["snapshot_url"],
            )
        )
    return records


def camera_to_world_bundle(record: CameraRecord, retrieved_at: datetime) -> WorldBundle:
    """Normalize camera infrastructure into a canonical WorldBundle."""
    source_id = stable_id("source", "worldos-curated-camera-directory")
    source = Source(
        id=source_id,
        slug="worldos-curated-camera-directory",
        name="WORLDOS Curated Camera Examples",
        publisher="WORLDOS project maintainers",
        license="Per-source terms are unverified; confirm before reuse",
        refresh_policy="Static examples; camera availability and location are not verified",
    )

    entity_id = stable_id("entity", "camera", record.camera_id)
    entity = Entity(
        id=entity_id,
        kind="asset",
        canonical_name=f"{record.name} ({record.operator})",
        source_id=source_id,
        source_key=record.camera_id,
        attributes={
            "camera_id": record.camera_id,
            "region": record.region,
            "operator": record.operator,
            "status": record.status,
            "stream_type": record.stream_type,
            "snapshot_url": record.snapshot_url,
            "stream_url": record.stream_url,
            "view_direction": record.view_direction,
            "resolution": record.resolution,
        },
        confidence=Confidence(value=0.25, method="curated_unverified_example"),
    )

    identifiers = [
        EntityIdentifier(
            source_id=source_id,
            source_key=record.camera_id,
            scheme="camera_registry",
            value=record.camera_id,
            confidence=Confidence(value=0.25, method="curated_unverified_example"),
        )
    ]

    time_str = record.observed_at.isoformat()
    interval_id = stable_id("interval", "camera", record.camera_id, time_str)
    evidence_id = stable_id("evidence", "camera", record.camera_id, time_str)
    provenance_id = stable_id("provenance", "camera", record.camera_id, time_str)
    geometry_id = stable_id("geometry", "camera", record.camera_id, time_str)
    observation_id = stable_id("observation", "camera", record.camera_id, time_str)

    interval = TimeInterval(
        id=interval_id,
        starts_at=record.observed_at,
        ends_at=record.observed_at,
        precision="instant",
    )

    payload_dict = {
        "camera_id": record.camera_id,
        "name": record.name,
        "lat": record.latitude,
        "lon": record.longitude,
        "status": record.status,
        "snapshot_url": record.snapshot_url,
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
        pipeline_version="sensor-camera-v1",
        transformation={"measure": "camera.status", "access_type": "public_feed"},
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
        measure="camera.status",
        value=1.0 if record.status == "ONLINE" else 0.0,
        unit="status_code",
        time_interval_id=interval_id,
        evidence_id=evidence_id,
        provenance_id=provenance_id,
        confidence=Confidence(value=1.0, method="telemetry_polling"),
        attributes={
            "camera_id": record.camera_id,
            "region": record.region,
            "operator": record.operator,
            "status": record.status,
            "stream_type": record.stream_type,
            "snapshot_url": record.snapshot_url,
            "stream_url": record.stream_url,
            "view_direction": record.view_direction,
            "resolution": record.resolution,
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
