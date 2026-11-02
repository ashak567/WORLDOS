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
            with urlopen(req, timeout=8) as resp:
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
_cached_aircraft_states: tuple[list[AircraftStateRecord], float] | None = None


def get_cached_aircraft_states(max_age_seconds: float = 30.0) -> list[AircraftStateRecord] | None:
    global _cached_aircraft_states
    if _cached_aircraft_states is None:
        return None
    records, cached_at = _cached_aircraft_states
    if time.time() - cached_at <= max_age_seconds:
        return records
    return None


def set_cached_aircraft_states(records: list[AircraftStateRecord]) -> None:
    global _cached_aircraft_states
    _cached_aircraft_states = (records, time.time())


SAMPLE_AIRCRAFT_DATA: list[dict[str, Any]] = [
    # North Atlantic Corridors (Eastbound & Westbound)
    {"icao24": "4006c3", "callsign": "BAW178", "country": "United Kingdom", "lat": 52.34, "lon": -35.21, "alt": 11277, "track": 260.0, "vel": 235.0},
    {"icao24": "a0211a", "callsign": "UAL854", "country": "United States", "lat": 48.12, "lon": -42.84, "alt": 10668, "track": 255.0, "vel": 242.0},
    {"icao24": "3c65c2", "callsign": "DLH400", "country": "Germany", "lat": 55.40, "lon": -28.65, "alt": 10972, "track": 270.0, "vel": 230.0},
    {"icao24": "3949ee", "callsign": "AFR006", "country": "France", "lat": 51.05, "lon": -38.50, "alt": 11582, "track": 265.0, "vel": 238.0},
    {"icao24": "4009a1", "callsign": "VIR10", "country": "United Kingdom", "lat": 53.15, "lon": -22.40, "alt": 11887, "track": 85.0, "vel": 260.0},
    {"icao24": "a10b42", "callsign": "AAL106", "country": "United States", "lat": 50.80, "lon": -18.90, "alt": 11277, "track": 80.0, "vel": 255.0},
    {"icao24": "484501", "callsign": "KLM641", "country": "Netherlands", "lat": 56.20, "lon": -45.10, "alt": 10668, "track": 280.0, "vel": 228.0},
    {"icao24": "4ca918", "callsign": "EIN105", "country": "Ireland", "lat": 54.10, "lon": -30.50, "alt": 11582, "track": 265.0, "vel": 232.0},
    {"icao24": "3441a5", "callsign": "IBE6251", "country": "Spain", "lat": 42.50, "lon": -32.80, "alt": 11277, "track": 250.0, "vel": 240.0},
    {"icao24": "4951b2", "callsign": "TAP101", "country": "Portugal", "lat": 38.90, "lon": -28.40, "alt": 10972, "track": 260.0, "vel": 235.0},

    # North America Transcontinental & Regional
    {"icao24": "a3b102", "callsign": "AAL100", "country": "United States", "lat": 40.71, "lon": -74.00, "alt": 9144, "track": 75.0, "vel": 245.0},
    {"icao24": "a79401", "callsign": "DAL221", "country": "United States", "lat": 33.64, "lon": -84.42, "alt": 10668, "track": 285.0, "vel": 232.0},
    {"icao24": "a9314e", "callsign": "SWA421", "country": "United States", "lat": 37.61, "lon": -122.37, "alt": 10058, "track": 90.0, "vel": 228.0},
    {"icao24": "c01823", "callsign": "ACA872", "country": "Canada", "lat": 45.47, "lon": -73.74, "alt": 11277, "track": 60.0, "vel": 240.0},
    {"icao24": "a2401f", "callsign": "UAL1", "country": "United States", "lat": 37.77, "lon": -122.41, "alt": 11582, "track": 265.0, "vel": 250.0},
    {"icao24": "a5518b", "callsign": "JBU523", "country": "United States", "lat": 26.07, "lon": -80.15, "alt": 9753, "track": 185.0, "vel": 220.0},
    {"icao24": "a88c30", "callsign": "DAL445", "country": "United States", "lat": 44.88, "lon": -93.22, "alt": 10363, "track": 120.0, "vel": 230.0},
    {"icao24": "c058e1", "callsign": "WJA128", "country": "Canada", "lat": 51.11, "lon": -114.02, "alt": 10668, "track": 95.0, "vel": 235.0},
    {"icao24": "a4190c", "callsign": "ASA62", "country": "United States", "lat": 58.36, "lon": -134.58, "alt": 10972, "track": 145.0, "vel": 240.0},
    {"icao24": "a0592e", "callsign": "FFT142", "country": "United States", "lat": 39.86, "lon": -104.67, "alt": 9144, "track": 210.0, "vel": 215.0},
    {"icao24": "a7d189", "callsign": "AAL4", "country": "United States", "lat": 33.94, "lon": -118.40, "alt": 11277, "track": 65.0, "vel": 255.0},
    {"icao24": "a34fe2", "callsign": "FDX382", "country": "United States", "lat": 35.04, "lon": -89.97, "alt": 10668, "track": 330.0, "vel": 245.0},
    {"icao24": "a29b01", "callsign": "UPS102", "country": "United States", "lat": 38.17, "lon": -85.73, "alt": 9753, "track": 15.0, "vel": 238.0},

    # European Airspace
    {"icao24": "4ca255", "callsign": "RYR415", "country": "Ireland", "lat": 48.85, "lon": 2.35, "alt": 9753, "track": 140.0, "vel": 215.0},
    {"icao24": "407172", "callsign": "EZY812", "country": "United Kingdom", "lat": 51.50, "lon": -0.12, "alt": 8534, "track": 180.0, "vel": 210.0},
    {"icao24": "4b1802", "callsign": "SWR124", "country": "Switzerland", "lat": 46.81, "lon": 8.22, "alt": 10363, "track": 125.0, "vel": 220.0},
    {"icao24": "468e21", "callsign": "SAS532", "country": "Sweden", "lat": 59.32, "lon": 18.06, "alt": 10668, "track": 200.0, "vel": 225.0},
    {"icao24": "3c4b26", "callsign": "DLH102", "country": "Germany", "lat": 50.03, "lon": 8.57, "alt": 9144, "track": 350.0, "vel": 220.0},
    {"icao24": "39b891", "callsign": "AFR124", "country": "France", "lat": 43.66, "lon": 7.21, "alt": 10058, "track": 320.0, "vel": 225.0},
    {"icao24": "4bb201", "callsign": "THY198", "country": "Turkey", "lat": 41.27, "lon": 28.75, "alt": 11277, "track": 300.0, "vel": 240.0},
    {"icao24": "3002b1", "callsign": "ITY401", "country": "Italy", "lat": 41.80, "lon": 12.23, "alt": 9448, "track": 340.0, "vel": 218.0},
    {"icao24": "471f45", "callsign": "WZZ202", "country": "Hungary", "lat": 47.43, "lon": 19.25, "alt": 10363, "track": 270.0, "vel": 222.0},
    {"icao24": "4401a8", "callsign": "AUA301", "country": "Austria", "lat": 48.11, "lon": 16.56, "alt": 9753, "track": 110.0, "vel": 220.0},
    {"icao24": "461e05", "callsign": "FIN132", "country": "Finland", "lat": 60.31, "lon": 24.96, "alt": 10972, "track": 190.0, "vel": 230.0},
    {"icao24": "4840e4", "callsign": "KLM141", "country": "Netherlands", "lat": 52.31, "lon": 4.76, "alt": 8839, "track": 130.0, "vel": 212.0},
    {"icao24": "4b8294", "callsign": "LOT381", "country": "Poland", "lat": 52.16, "lon": 20.96, "alt": 10668, "track": 240.0, "vel": 228.0},
    {"icao24": "45ce21", "callsign": "BEL441", "country": "Belgium", "lat": 50.90, "lon": 4.48, "alt": 9144, "track": 175.0, "vel": 215.0},
    {"icao24": "491204", "callsign": "NOZ551", "country": "Norway", "lat": 60.19, "lon": 11.10, "alt": 10058, "track": 160.0, "vel": 225.0},
    {"icao24": "4510b2", "callsign": "AEE601", "country": "Greece", "lat": 37.93, "lon": 23.94, "alt": 10363, "track": 315.0, "vel": 228.0},

    # Middle East & Gulf Hubs
    {"icao24": "896081", "callsign": "UAE201", "country": "United Arab Emirates", "lat": 25.25, "lon": 55.36, "alt": 10972, "track": 310.0, "vel": 248.0},
    {"icao24": "06a12e", "callsign": "QTR701", "country": "Qatar", "lat": 28.50, "lon": 51.53, "alt": 11582, "track": 320.0, "vel": 245.0},
    {"icao24": "896422", "callsign": "ETD101", "country": "United Arab Emirates", "lat": 24.43, "lon": 54.65, "alt": 11277, "track": 305.0, "vel": 242.0},
    {"icao24": "70014a", "callsign": "OMA105", "country": "Oman", "lat": 23.59, "lon": 58.28, "alt": 10668, "track": 290.0, "vel": 235.0},
    {"icao24": "71c045", "callsign": "SVA124", "country": "Saudi Arabia", "lat": 21.68, "lon": 39.15, "alt": 11887, "track": 335.0, "vel": 250.0},
    {"icao24": "706012", "callsign": "KAC102", "country": "Kuwait", "lat": 29.22, "lon": 47.97, "alt": 10972, "track": 300.0, "vel": 240.0},
    {"icao24": "89619a", "callsign": "FDB512", "country": "United Arab Emirates", "lat": 27.80, "lon": 52.10, "alt": 9753, "track": 120.0, "vel": 225.0},
    {"icao24": "0101b4", "callsign": "MSR777", "country": "Egypt", "lat": 30.12, "lon": 31.40, "alt": 11277, "track": 325.0, "vel": 245.0},
    {"icao24": "73804f", "callsign": "GFA002", "country": "Bahrain", "lat": 26.27, "lon": 50.63, "alt": 10668, "track": 105.0, "vel": 238.0},
    {"icao24": "7500c8", "callsign": "RJA261", "country": "Jordan", "lat": 31.72, "lon": 35.99, "alt": 10972, "track": 295.0, "vel": 240.0},

    # Asia & Pacific
    {"icao24": "76ce81", "callsign": "SIA22", "country": "Singapore", "lat": 1.36, "lon": 103.99, "alt": 11887, "track": 335.0, "vel": 252.0},
    {"icao24": "7809a4", "callsign": "CCA981", "country": "China", "lat": 39.90, "lon": 116.40, "alt": 10668, "track": 45.0, "vel": 235.0},
    {"icao24": "8619bc", "callsign": "ANA106", "country": "Japan", "lat": 35.77, "lon": 139.77, "alt": 11277, "track": 65.0, "vel": 242.0},
    {"icao24": "710115", "callsign": "KAL081", "country": "Republic of Korea", "lat": 37.46, "lon": 126.44, "alt": 10972, "track": 55.0, "vel": 240.0},
    {"icao24": "780512", "callsign": "CPA830", "country": "Hong Kong", "lat": 22.31, "lon": 113.91, "alt": 11582, "track": 35.0, "vel": 245.0},
    {"icao24": "800311", "callsign": "AIC101", "country": "India", "lat": 28.55, "lon": 77.10, "alt": 10668, "track": 305.0, "vel": 238.0},
    {"icao24": "800bc4", "callsign": "IGO204", "country": "India", "lat": 19.09, "lon": 72.87, "alt": 9753, "track": 135.0, "vel": 225.0},
    {"icao24": "8005d2", "callsign": "SEJ312", "country": "India", "lat": 12.97, "lon": 77.59, "alt": 10058, "track": 20.0, "vel": 230.0},
    {"icao24": "7812a1", "callsign": "CES587", "country": "China", "lat": 31.14, "lon": 121.80, "alt": 11277, "track": 50.0, "vel": 248.0},
    {"icao24": "780b43", "callsign": "CSN327", "country": "China", "lat": 23.39, "lon": 113.30, "alt": 11582, "track": 60.0, "vel": 250.0},
    {"icao24": "8632f0", "callsign": "JAL004", "country": "Japan", "lat": 34.78, "lon": 135.44, "alt": 11887, "track": 70.0, "vel": 255.0},
    {"icao24": "888042", "callsign": "THA910", "country": "Thailand", "lat": 13.69, "lon": 100.75, "alt": 10972, "track": 310.0, "vel": 245.0},
    {"icao24": "750284", "callsign": "MAS001", "country": "Malaysia", "lat": 2.74, "lon": 101.70, "alt": 11277, "track": 320.0, "vel": 248.0},
    {"icao24": "8a0149", "callsign": "GIA880", "country": "Indonesia", "lat": -6.12, "lon": 106.65, "alt": 10668, "track": 45.0, "vel": 240.0},
    {"icao24": "758112", "callsign": "PAL102", "country": "Philippines", "lat": 14.51, "lon": 121.01, "alt": 11277, "track": 40.0, "vel": 242.0},
    {"icao24": "885141", "callsign": "HVN36", "country": "Viet Nam", "lat": 21.22, "lon": 105.80, "alt": 10972, "track": 305.0, "vel": 238.0},
    {"icao24": "7104b2", "callsign": "AAR202", "country": "Republic of Korea", "lat": 35.18, "lon": 128.94, "alt": 11582, "track": 85.0, "vel": 252.0},
    {"icao24": "899015", "callsign": "CAL008", "country": "Taiwan", "lat": 25.08, "lon": 121.23, "alt": 11277, "track": 60.0, "vel": 248.0},
    {"icao24": "89912a", "callsign": "EVA016", "country": "Taiwan", "lat": 24.80, "lon": 121.00, "alt": 11887, "track": 55.0, "vel": 250.0},

    # Transpacific Routes
    {"icao24": "a12c40", "callsign": "UAL837", "country": "United States", "lat": 42.50, "lon": -165.20, "alt": 11277, "track": 285.0, "vel": 240.0},
    {"icao24": "a341b5", "callsign": "DAL295", "country": "United States", "lat": 48.20, "lon": -155.80, "alt": 10972, "track": 290.0, "vel": 238.0},
    {"icao24": "8620b4", "callsign": "ANA008", "country": "Japan", "lat": 45.10, "lon": 175.40, "alt": 11887, "track": 85.0, "vel": 262.0},
    {"icao24": "863110", "callsign": "JAL062", "country": "Japan", "lat": 39.80, "lon": -170.10, "alt": 11582, "track": 90.0, "vel": 258.0},
    {"icao24": "7c4581", "callsign": "QFA11", "country": "Australia", "lat": -15.40, "lon": -160.20, "alt": 11277, "track": 60.0, "vel": 250.0},
    {"icao24": "c81d24", "callsign": "ANZ002", "country": "New Zealand", "lat": -20.10, "lon": -150.50, "alt": 10972, "track": 45.0, "vel": 245.0},
    {"icao24": "a5501e", "callsign": "HAL21", "country": "United States", "lat": 21.32, "lon": -157.92, "alt": 10668, "track": 70.0, "vel": 240.0},
    {"icao24": "a77192", "callsign": "UAL115", "country": "United States", "lat": 28.50, "lon": -140.20, "alt": 11277, "track": 245.0, "vel": 235.0},

    # Oceania & Southern Hemisphere
    {"icao24": "7c0142", "callsign": "QFA401", "country": "Australia", "lat": -33.94, "lon": 151.17, "alt": 10668, "track": 225.0, "vel": 235.0},
    {"icao24": "7c19b0", "callsign": "VOZ801", "country": "Australia", "lat": -37.67, "lon": 144.84, "alt": 9753, "track": 300.0, "vel": 225.0},
    {"icao24": "7c2841", "callsign": "JST502", "country": "Australia", "lat": -27.38, "lon": 153.11, "alt": 10363, "track": 195.0, "vel": 230.0},
    {"icao24": "7c331a", "callsign": "QFA581", "country": "Australia", "lat": -31.94, "lon": 115.96, "alt": 11277, "track": 95.0, "vel": 245.0},
    {"icao24": "c8201a", "callsign": "ANZ404", "country": "New Zealand", "lat": -41.33, "lon": 174.80, "alt": 9144, "track": 210.0, "vel": 215.0},
    {"icao24": "c80521", "callsign": "ANZ601", "country": "New Zealand", "lat": -43.48, "lon": 172.53, "alt": 8534, "track": 30.0, "vel": 210.0},

    # Latin America & Caribbean
    {"icao24": "e08422", "callsign": "LAN800", "country": "Chile", "lat": -33.39, "lon": -70.78, "alt": 10668, "track": 240.0, "vel": 235.0},
    {"icao24": "e4811a", "callsign": "GLO142", "country": "Brazil", "lat": -23.55, "lon": -46.63, "alt": 9753, "track": 15.0, "vel": 225.0},
    {"icao24": "e49052", "callsign": "TAM8060", "country": "Brazil", "lat": -22.81, "lon": -43.25, "alt": 11277, "track": 345.0, "vel": 245.0},
    {"icao24": "e01048", "callsign": "ARG1302", "country": "Argentina", "lat": -34.82, "lon": -58.53, "alt": 10972, "track": 355.0, "vel": 240.0},
    {"icao24": "0b001a", "callsign": "AVA010", "country": "Colombia", "lat": 4.70, "lon": -74.14, "alt": 11582, "track": 350.0, "vel": 245.0},
    {"icao24": "0d0491", "callsign": "AMX001", "country": "Mexico", "lat": 19.43, "lon": -99.07, "alt": 11277, "track": 50.0, "vel": 240.0},
    {"icao24": "0d0822", "callsign": "VOI502", "country": "Mexico", "lat": 20.52, "lon": -103.31, "alt": 9753, "track": 10.0, "vel": 225.0},
    {"icao24": "0e4120", "callsign": "CMP302", "country": "Panama", "lat": 9.07, "lon": -79.38, "alt": 10668, "track": 340.0, "vel": 238.0},
    {"icao24": "e80112", "callsign": "LPE212", "country": "Peru", "lat": -12.02, "lon": -77.11, "alt": 10363, "track": 330.0, "vel": 232.0},

    # Africa
    {"icao24": "00a124", "callsign": "SAA203", "country": "South Africa", "lat": -26.13, "lon": 28.24, "alt": 10363, "track": 300.0, "vel": 230.0},
    {"icao24": "040049", "callsign": "ETH500", "country": "Ethiopia", "lat": 8.98, "lon": 38.80, "alt": 11582, "track": 315.0, "vel": 248.0},
    {"icao24": "02a110", "callsign": "KQA101", "country": "Kenya", "lat": -1.32, "lon": 36.92, "alt": 11277, "track": 330.0, "vel": 245.0},
    {"icao24": "020084", "callsign": "RAM200", "country": "Morocco", "lat": 33.37, "lon": -7.59, "alt": 10972, "track": 285.0, "vel": 240.0},
    {"icao24": "06401a", "callsign": "NGR102", "country": "Nigeria", "lat": 6.58, "lon": 3.32, "alt": 10058, "track": 355.0, "vel": 230.0},
    {"icao24": "00205b", "callsign": "DAH100", "country": "Algeria", "lat": 36.69, "lon": 3.21, "alt": 10668, "track": 350.0, "vel": 235.0},

    # Central & South Asia Corridors
    {"icao24": "151a02", "callsign": "UZB101", "country": "Uzbekistan", "lat": 41.26, "lon": 69.28, "alt": 10668, "track": 280.0, "vel": 235.0},
    {"icao24": "683015", "callsign": "KZR901", "country": "Kazakhstan", "lat": 43.35, "lon": 77.04, "alt": 10972, "track": 295.0, "vel": 240.0},
    {"icao24": "760084", "callsign": "PIA785", "country": "Pakistan", "lat": 31.52, "lon": 74.40, "alt": 11277, "track": 305.0, "vel": 242.0},
    {"icao24": "708021", "callsign": "BBC001", "country": "Bangladesh", "lat": 23.84, "lon": 90.40, "alt": 10363, "track": 290.0, "vel": 232.0},
    {"icao24": "704042", "callsign": "ALK503", "country": "Sri Lanka", "lat": 7.18, "lon": 79.88, "alt": 10668, "track": 310.0, "vel": 235.0},
]


def load_sample_aircraft(now: datetime | None = None) -> list[AircraftStateRecord]:
    """Provide realistic worldwide commercial flight states with dynamic flight motion."""
    epoch = now or datetime.now(UTC)
    records: list[AircraftStateRecord] = []

    # 4-hour cycle for global route progression
    cycle_seconds = 14400.0
    elapsed = epoch.timestamp() % cycle_seconds
    earth_radius_m = 6371000.0

    for item in SAMPLE_AIRCRAFT_DATA:
        callsign = item["callsign"]
        speed_mps = float(item["vel"])
        track_deg = float(item["track"])

        # Dead-reckoning position projection along track bearing
        dist_m = speed_mps * elapsed
        bearing_rad = math.radians(track_deg)
        lat_rad = math.radians(item["lat"])
        lon_rad = math.radians(item["lon"])
        angular_dist = dist_m / earth_radius_m

        cur_lat_rad = math.asin(
            math.sin(lat_rad) * math.cos(angular_dist)
            + math.cos(lat_rad) * math.sin(angular_dist) * math.cos(bearing_rad)
        )
        cur_lon_rad = lon_rad + math.atan2(
            math.sin(bearing_rad) * math.sin(angular_dist) * math.cos(lat_rad),
            math.cos(angular_dist) - math.sin(lat_rad) * math.sin(cur_lat_rad),
        )
        cur_lat = math.degrees(cur_lat_rad)
        cur_lon = (math.degrees(cur_lon_rad) + 540.0) % 360.0 - 180.0

        content_hash = hashlib.sha256(f"{item['icao24']}:{callsign}:{epoch.isoformat()}".encode("utf-8")).hexdigest()
        records.append(
            AircraftStateRecord(
                icao24=item["icao24"],
                callsign=callsign,
                origin_country=item["country"],
                time_position=epoch,
                last_contact=epoch,
                longitude=round(cur_lon, 4),
                latitude=round(cur_lat, 4),
                baro_altitude=float(item["alt"]),
                on_ground=False,
                velocity=speed_mps,
                true_track=track_deg,
                vertical_rate=0.0,
                geo_altitude=float(item["alt"]),
                squawk="1000",
                position_source=0,
                category=1,
                locator="worldos://simulated-flight-corridor",
                content_hash=content_hash,
            )
        )
    return records


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
    if lamin is None and lomin is None and lamax is None and lomax is None:
        cached = get_cached_aircraft_states(max_age_seconds=30.0)
        if cached is not None:
            return cached

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
        with urlopen(req, timeout=60) as resp:
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
    if lamin is None and lomin is None and lamax is None and lomax is None and records:
        set_cached_aircraft_states(records)
    return records
