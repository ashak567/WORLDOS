"""Natural Earth admin-0 country boundaries, matched only by ISO alpha-3."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from urllib.request import urlopen

NATURAL_EARTH_COUNTRIES_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
    "ne_110m_admin_0_countries.geojson"
)


@dataclass(frozen=True)
class CountryBoundary:
    iso3: str
    name: str
    geometry: dict
    locator: str
    content_hash: str


def parse_country_boundary(payload: object, iso3: str, locator: str) -> CountryBoundary:
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ValueError("unexpected Natural Earth GeoJSON")
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    for feature in payload.get("features", []):
        properties = feature.get("properties", {})
        if properties.get("ISO_A3") == iso3:
            geometry = feature.get("geometry")
            if not geometry or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
                raise ValueError(f"Natural Earth feature {iso3} has no country polygon")
            return CountryBoundary(
                iso3=iso3,
                name=properties.get("NAME") or iso3,
                geometry=geometry,
                locator=locator,
                content_hash=payload_hash,
            )
    raise LookupError(f"Natural Earth has no ISO alpha-3 country {iso3}")


def fetch_country_boundary(iso3: str) -> CountryBoundary:
    with urlopen(NATURAL_EARTH_COUNTRIES_URL, timeout=60) as response:  # nosec B310: fixed HTTPS host
        payload = json.loads(response.read())
    return parse_country_boundary(payload, iso3.upper(), NATURAL_EARTH_COUNTRIES_URL)
