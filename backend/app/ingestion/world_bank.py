"""Public, deterministic World Bank population ingestion contract."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode
from urllib.request import urlopen

WORLD_BANK_API = "https://api.worldbank.org/v2"
POPULATION_INDICATOR = "SP.POP.TOTL"


@dataclass(frozen=True)
class PopulationRecord:
    country_code: str
    country_name: str
    year: int
    population: float
    locator: str
    content_hash: str


@dataclass(frozen=True)
class CountryPoint:
    country_code: str
    longitude: float
    latitude: float


def fetch_json(path: str, params: dict[str, str]) -> tuple[object, str]:
    locator = f"{WORLD_BANK_API}{path}?{urlencode(params)}"
    with urlopen(locator, timeout=30) as response:  # nosec B310: fixed HTTPS host
        payload = response.read()
    return json.loads(payload), locator


def parse_population(payload: object, locator: str) -> list[PopulationRecord]:
    if not isinstance(payload, list) or len(payload) != 2 or not isinstance(payload[1], list):
        raise ValueError("unexpected World Bank indicator response")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    records: list[PopulationRecord] = []
    for item in payload[1]:
        if item.get("value") is None:
            continue
        records.append(
            PopulationRecord(
                country_code=item["countryiso3code"],
                country_name=item["country"]["value"],
                year=int(item["date"]),
                population=float(item["value"]),
                locator=locator,
                content_hash=digest,
            )
        )
    return records


def fetch_population(country_code: str, *, year: int | None = None) -> list[PopulationRecord]:
    params = {"format": "json", "per_page": "100"}
    if year:
        params["date"] = str(year)
    payload, locator = fetch_json(f"/country/{country_code}/indicator/{POPULATION_INDICATOR}", params)
    return parse_population(payload, locator)


def fetch_country_point(country_code: str) -> CountryPoint | None:
    payload, _ = fetch_json(f"/country/{country_code}", {"format": "json"})
    if not isinstance(payload, list) or len(payload) != 2 or not payload[1]:
        raise ValueError("unexpected World Bank country response")
    country = payload[1][0]
    if not country.get("longitude") or not country.get("latitude"):
        return None
    return CountryPoint(country_code, float(country["longitude"]), float(country["latitude"]))


def retrieved_now() -> datetime:
    return datetime.now(UTC)

