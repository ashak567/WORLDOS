"""Small, keyless public news and climate context feeds."""
from __future__ import annotations

import csv
import json
import logging
import math
import threading
from datetime import UTC, datetime
from io import StringIO
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from typing import Any

logger = logging.getLogger(__name__)
NEWS_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
CLIMATE_URL = "https://data.giss.nasa.gov/gistemp/tabledata_v4/GLB.Ts+dSST.csv"
_CACHE_SECONDS = {"news": 300, "climate": 86400}
_cache_lock = threading.Lock()
_cache: dict[str, tuple[Any, datetime]] = {}


class LiveContextFeedError(RuntimeError):
    """Raised when a public context feed fails without a cached response."""


def _download(name: str, url: str, now: datetime, limit: int) -> tuple[bytes, datetime, str]:
    with _cache_lock:
        cached = _cache.get(name)
        if cached and (now - cached[1]).total_seconds() < _CACHE_SECONDS[name]:
            return cached[0], cached[1], "fresh"
        request = Request(url, headers={"Accept": "application/json, text/csv", "User-Agent": "WORLDOS/0.1 (open-data dashboard)"})
        try:
            with urlopen(request, timeout=15) as response:  # nosec B310: fixed HTTPS provider URLs
                raw = response.read(limit + 1)
            if len(raw) > limit:
                raise LiveContextFeedError(f"{name} feed exceeded its response size limit")
            _cache[name] = (raw, now)
            return raw, now, "fresh"
        except (URLError, TimeoutError, UnicodeError, LiveContextFeedError) as exc:
            if cached:
                logger.warning("%s feed unavailable; serving cached response: %s", name, exc)
                return cached[0], cached[1], "stale"
            raise LiveContextFeedError(f"{name} feed is unavailable: {exc}") from exc


def fetch_global_news(now: datetime | None = None) -> tuple[list[dict[str, str]], datetime, str]:
    retrieved_at = now or datetime.now(UTC)
    query = urlencode({
        "query": '(earthquake OR tsunami OR cyclone OR flood OR wildfire OR volcano OR landslide OR conflict OR election OR protest)',
        "mode": "artlist",
        "format": "json",
        "timespan": "24h",
        "maxrecords": "30",
        "sort": "datedesc",
    })
    raw, retrieved_at, status = _download("news", f"{NEWS_URL}?{query}", retrieved_at, 2_000_000)
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise LiveContextFeedError(f"news feed returned invalid JSON: {exc}") from exc
    articles = payload.get("articles") if isinstance(payload, dict) else None
    if not isinstance(articles, list):
        raise LiveContextFeedError("news feed returned an unexpected response structure")
    clean = []
    for article in articles:
        if not isinstance(article, dict) or not article.get("url") or not article.get("title"):
            continue
        clean.append({
            "title": str(article["title"])[:500],
            "url": str(article["url"])[:2000],
            "domain": str(article.get("domain") or "")[:200],
            "published_at": str(article.get("seendate") or ""),
            "language": str(article.get("language") or ""),
            "source_country": str(article.get("sourcecountry") or ""),
        })
    return clean, retrieved_at, status


def fetch_global_climate(now: datetime | None = None) -> tuple[dict[str, Any], datetime, str]:
    retrieved_at = now or datetime.now(UTC)
    raw, retrieved_at, status = _download("climate", CLIMATE_URL, retrieved_at, 1_000_000)
    try:
        rows = csv.DictReader(StringIO(raw.decode("utf-8-sig")))
        months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
        latest = None
        for row in rows:
            year = row.get("Year")
            if not year or not year.isdigit():
                continue
            for month_number, month in enumerate(months, start=1):
                value = row.get(month, "").strip()
                if value and value != "***":
                    parsed = float(value)
                    if math.isfinite(parsed):
                        latest = (int(year), month_number, parsed)
        if latest is None:
            raise ValueError("no monthly values found")
    except (UnicodeError, ValueError, TypeError) as exc:
        raise LiveContextFeedError(f"climate feed returned invalid CSV data: {exc}") from exc
    year, month, anomaly = latest
    return {
        "period": f"{year:04d}-{month:02d}",
        "global_temperature_anomaly_c": anomaly,
        "unit": "°C",
        "baseline": "1951–1980",
        "measure": "Monthly global land-ocean temperature anomaly",
        "source": "NASA GISS GISTEMP v4",
        "source_url": "https://data.giss.nasa.gov/gistemp/",
        "truth_class": "OBSERVED",
        "cadence": "Monthly; generally updated around the 10th",
    }, retrieved_at, status


