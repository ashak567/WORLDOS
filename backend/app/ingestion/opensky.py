"""OpenSky Network live ADS-B state-vector ingestion adapter with OAuth2 authentication and credit safeguards."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..config import OpenSkySettings, get_opensky_settings

logger = logging.getLogger(__name__)

OPENSKY_TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
OPENSKY_STATES_URL = "https://opensky-network.org/api/states/all"


class OpenSkyError(Exception):
    """Base exception for OpenSky operations."""


class OpenSkyAuthError(OpenSkyError):
    """Authentication or token exchange failure."""


class OpenSkyConnectionError(OpenSkyError):
    """OpenSky could not be reached or returned a server-side failure."""


class OpenSkyRateLimitError(OpenSkyError):
    """Rate limit or credit quota exhaustion."""


class OpenSkyTokenManager:
    """Manages OAuth2 Client Credentials token exchange and caching for OpenSky Network."""

    def __init__(self, settings: OpenSkySettings | None = None) -> None:
        self._settings = settings or get_opensky_settings()
        self._access_token: str | None = None
        self._expires_at: float = 0.0

    @property
    def is_configured(self) -> bool:
        return self._settings.is_configured

    def get_token(self) -> str:
        """Retrieve a valid cached bearer token or exchange credentials for a new token."""
        if not self.is_configured:
            raise OpenSkyAuthError("OpenSky credentials not configured in backend environment")

        # Reuse cached token if more than 60 seconds of validity remain
        now = time.time()
        if self._access_token and now < (self._expires_at - 60):
            return self._access_token

        return self._exchange_token()

    def _exchange_token(self) -> str:
        """Perform OAuth2 Client Credentials exchange at the OpenSky token endpoint."""
        client_id = self._settings.client_id
        client_secret = self._settings.client_secret.get_secret_value() if self._settings.client_secret else ""

        payload = urlencode({
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }).encode("utf-8")

        req = Request(
            OPENSKY_TOKEN_URL,
            data=payload,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "User-Agent": "WORLDOS-Global-Intelligence-OS/0.1.0",
            },
            method="POST",
        )

        try:
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            status = e.code
            logger.error("OpenSky token exchange failed with HTTP %d", status)
            if status in (400, 401):
                raise OpenSkyAuthError(f"OpenSky authentication failed: HTTP {status} (invalid client credentials)") from None
            elif status == 429:
                raise OpenSkyRateLimitError("OpenSky token endpoint rate limit exceeded") from None
            elif status >= 500:
                raise OpenSkyConnectionError(f"OpenSky token endpoint returned HTTP {status}") from None
            raise OpenSkyAuthError(f"OpenSky token exchange failed: HTTP {status}") from None
        except (URLError, TimeoutError, OSError) as e:
            reason = getattr(e, "reason", e)
            logger.error("OpenSky token endpoint unreachable: %s", reason)
            raise OpenSkyConnectionError(f"OpenSky token endpoint unreachable: {reason}") from None

        token = data.get("access_token")
        expires_in = data.get("expires_in", 1800)

        if not token:
            raise OpenSkyAuthError("OpenSky token response missing access_token field")

        self._access_token = str(token)
        self._expires_at = time.time() + float(expires_in)
        logger.info("Successfully obtained OpenSky access token (expires in %ds)", expires_in)
        return self._access_token


@dataclass(frozen=True)
class AircraftStateRecord:
    """Normalized representation of an OpenSky aircraft state vector."""
    icao24: str
    callsign: str | None
    origin_country: str
    time_position: datetime | None
    last_contact: datetime
    longitude: float
    latitude: float
    baro_altitude: float | None
    on_ground: bool | None
    velocity: float | None
    true_track: float | None
    vertical_rate: float | None
    geo_altitude: float | None
    squawk: str | None
    position_source: int
    category: int | None
    locator: str
    content_hash: str

    @property
    def observation_time(self) -> datetime:
        return self.time_position or self.last_contact


# Global token manager singleton
_token_manager: OpenSkyTokenManager | None = None


def get_token_manager() -> OpenSkyTokenManager:
    global _token_manager
    if _token_manager is None:
        _token_manager = OpenSkyTokenManager()
    return _token_manager


def parse_state_vector(raw: list[Any], locator: str, payload_hash: str) -> AircraftStateRecord | None:
    """Parse and validate a single 17-or-18-element raw state vector from OpenSky."""
    if not isinstance(raw, list) or len(raw) < 17:
        return None

    icao24 = str(raw[0]).strip().lower() if raw[0] else None
    if not icao24:
        return None

    raw_callsign = raw[1]
    callsign = str(raw_callsign).strip() if raw_callsign else None
    if callsign == "":
        callsign = None

    origin_country = str(raw[2]).strip() if raw[2] else "Unknown"

    lon_raw = raw[5]
    lat_raw = raw[6]
    if lon_raw is None or lat_raw is None:
        return None

    try:
        lon = float(lon_raw)
        lat = float(lat_raw)
    except (ValueError, TypeError):
        return None

    if not (math.isfinite(lon) and math.isfinite(lat) and -180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        return None

    time_pos_raw = raw[3]
    time_position = None
    if time_pos_raw is not None:
        try:
            time_position = datetime.fromtimestamp(float(time_pos_raw), tz=UTC)
        except (ValueError, TypeError, OSError):
            time_position = None

    last_contact_raw = raw[4]
    try:
        last_contact = datetime.fromtimestamp(float(last_contact_raw), tz=UTC) if last_contact_raw else datetime.now(UTC)
    except (ValueError, TypeError, OSError):
        last_contact = datetime.now(UTC)

    try:
        numeric = [float(raw[i]) if raw[i] is not None else None for i in (7, 9, 10, 11, 13)]
        baro_alt, velocity, true_track, vertical_rate, geo_alt = [
            value if value is None or math.isfinite(value) else None for value in numeric
        ]
        on_ground = bool(raw[8]) if raw[8] is not None else None
        squawk = str(raw[14]).strip() if raw[14] is not None else None
        position_source = int(raw[16]) if raw[16] is not None else 0
        category = int(raw[17]) if len(raw) > 17 and raw[17] is not None else None
    except (ValueError, TypeError, OverflowError):
        return None

    return AircraftStateRecord(
        icao24=icao24,
        callsign=callsign,
        origin_country=origin_country,
        time_position=time_position,
        last_contact=last_contact,
        longitude=lon,
        latitude=lat,
        baro_altitude=baro_alt,
        on_ground=on_ground,
        velocity=velocity,
        true_track=true_track,
        vertical_rate=vertical_rate,
        geo_altitude=geo_alt,
        squawk=squawk,
        position_source=position_source,
        category=category,
        locator=locator,
        content_hash=payload_hash,
    )


def fetch_aircraft_states(
    *,
    lamin: float | None = None,
    lomin: float | None = None,
    lamax: float | None = None,
    lomax: float | None = None,
    token_manager: OpenSkyTokenManager | None = None,
) -> list[AircraftStateRecord]:
    """Query OpenSky Network /states/all with OAuth2 authentication and bounding box scoping."""
    mgr = token_manager or get_token_manager()
    token = mgr.get_token()

    params: dict[str, str] = {}
    if lamin is not None and lomin is not None and lamax is not None and lomax is not None:
        params["lamin"] = f"{lamin:.4f}"
        params["lomin"] = f"{lomin:.4f}"
        params["lamax"] = f"{lamax:.4f}"
        params["lomax"] = f"{lomax:.4f}"

    query_str = f"?{urlencode(params)}" if params else ""
    locator = f"{OPENSKY_STATES_URL}{query_str}"

    req = Request(
        locator,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "WORLDOS-Global-Intelligence-OS/0.1.0",
        },
        method="GET",
    )

    try:
        with urlopen(req, timeout=30) as resp:
            raw_body = resp.read()
            payload = json.loads(raw_body.decode("utf-8"))
    except HTTPError as e:
        status = e.code
        logger.error("OpenSky /states/all failed with HTTP %d", status)
        if status == 429:
            retry_after = e.headers.get("Retry-After", "unknown")
            raise OpenSkyRateLimitError(f"OpenSky rate limit exceeded (HTTP 429). Retry-After: {retry_after}") from None
        elif status == 401:
            raise OpenSkyAuthError("OpenSky rejected bearer token (HTTP 401 Unauthorized)") from None
        raise OpenSkyError(f"OpenSky API error: HTTP {status}") from None
    except (URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        logger.error("OpenSky API connection error: %s", reason)
        raise OpenSkyConnectionError(f"OpenSky API connection error: {reason}") from None

    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    raw_states = payload.get("states") or []

    records: list[AircraftStateRecord] = []
    for item in raw_states:
        record = parse_state_vector(item, locator, payload_hash)
        if record is not None:
            records.append(record)

    logger.info("Parsed %d valid aircraft state vectors from OpenSky (total states: %d)", len(records), len(raw_states))
    return records
