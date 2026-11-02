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


# Global commercial airport coordinates (lat, lon, country)
_GLOBAL_HUBS: dict[str, tuple[float, float, str]] = {
    # North America
    "JFK": (40.64, -73.78, "United States"), "EWR": (40.69, -74.17, "United States"), "LGA": (40.77, -73.87, "United States"),
    "LAX": (33.94, -118.41, "United States"), "ORD": (41.97, -87.91, "United States"), "DFW": (32.90, -97.04, "United States"),
    "ATL": (33.64, -84.43, "United States"), "SFO": (37.62, -122.38, "United States"), "MIA": (25.80, -80.29, "United States"),
    "YVR": (49.19, -123.18, "Canada"), "YYZ": (43.68, -79.63, "Canada"), "MEX": (19.44, -99.07, "Mexico"),
    "SEA": (47.45, -122.31, "United States"), "BOS": (42.36, -71.01, "United States"), "IAD": (38.95, -77.46, "United States"),
    "MCO": (28.43, -81.31, "United States"), "PHX": (33.43, -112.01, "United States"), "DEN": (39.86, -104.67, "United States"),
    "HNL": (21.32, -157.92, "United States"),
    # Europe
    "LHR": (51.47, -0.45, "United Kingdom"), "LGW": (51.15, -0.19, "United Kingdom"), "CDG": (49.01, 2.55, "France"),
    "FRA": (50.03, 8.57, "Germany"), "AMS": (52.31, 4.76, "Netherlands"), "MAD": (40.48, -3.57, "Spain"),
    "FCO": (41.80, 12.24, "Italy"), "MUC": (48.35, 11.79, "Germany"), "ZRH": (47.46, 8.55, "Switzerland"),
    "VIE": (48.11, 16.57, "Austria"), "IST": (41.28, 28.73, "Turkey"), "DUB": (53.42, -6.27, "Ireland"),
    "ARN": (59.65, 17.92, "Sweden"), "HEL": (60.32, 24.96, "Finland"), "OSL": (60.19, 11.10, "Norway"),
    "CPH": (55.62, 12.66, "Denmark"), "BCN": (41.30, 2.08, "Spain"), "ATH": (37.94, 23.94, "Greece"),
    "WAW": (52.17, 20.97, "Poland"),
    # Middle East
    "DXB": (25.25, 55.36, "United Arab Emirates"), "DOH": (25.27, 51.61, "Qatar"), "AUH": (24.43, 54.65, "United Arab Emirates"),
    "JED": (21.68, 39.16, "Saudi Arabia"), "RUH": (24.96, 46.70, "Saudi Arabia"), "KWI": (29.23, 47.98, "Kuwait"),
    # Asia
    "HND": (35.55, 139.78, "Japan"), "NRT": (35.76, 140.39, "Japan"), "KIX": (34.43, 135.23, "Japan"), "ITM": (34.78, 135.44, "Japan"),
    "ICN": (37.47, 126.44, "Republic of Korea"), "PEK": (40.08, 116.58, "China"), "PVG": (31.14, 121.81, "China"),
    "CAN": (23.39, 113.30, "China"), "HKG": (22.31, 113.91, "Hong Kong"), "TPE": (25.08, 121.23, "Taiwan"),
    "SIN": (1.36, 103.99, "Singapore"), "BKK": (13.69, 100.75, "Thailand"), "KUL": (2.75, 101.71, "Malaysia"),
    "CGK": (-6.13, 106.66, "Indonesia"), "MNL": (14.51, 121.02, "Philippines"), "DEL": (28.56, 77.10, "India"),
    "BOM": (19.09, 72.87, "India"), "BLR": (13.20, 77.71, "India"), "MAA": (12.99, 80.17, "India"),
    "HYD": (17.24, 78.43, "India"), "CCU": (22.65, 88.45, "India"), "SGN": (10.82, 106.65, "Viet Nam"),
    # Oceania
    "SYD": (-33.95, 151.18, "Australia"), "MEL": (-37.67, 144.84, "Australia"), "BNE": (-27.38, 153.12, "Australia"),
    "PER": (-31.94, 115.97, "Australia"), "AKL": (-37.01, 174.79, "New Zealand"), "CHC": (-43.49, 172.53, "New Zealand"),
    # South America
    "GRU": (-23.44, -46.47, "Brazil"), "GIG": (-22.81, -43.25, "Brazil"), "EZE": (-34.82, -58.54, "Argentina"),
    "SCL": (-33.39, -70.79, "Chile"), "BOG": (4.70, -74.15, "Colombia"), "LIM": (-12.02, -77.11, "Peru"),
    # Africa
    "JNB": (-26.14, 28.25, "South Africa"), "CPT": (-33.97, 18.60, "South Africa"), "ADD": (8.98, 38.80, "Ethiopia"),
    "NBO": (-1.32, 36.93, "Kenya"), "CAI": (30.12, 31.41, "Egypt"), "CMN": (33.37, -7.59, "Morocco"),
    "LOS": (6.58, 3.32, "Nigeria"), "ALG": (36.69, 3.22, "Algeria"),
}

# Major global route templates (origin, dest, airline_code, base_flight_number, country, speed_mps, altitude_m)
_GLOBAL_ROUTE_TEMPLATES: list[tuple[str, str, str, int, str, float, float]] = [
    # North Atlantic Trunk Corridors
    ("JFK", "LHR", "BAW", 178, "United Kingdom", 245.0, 11277),
    ("LHR", "JFK", "VIR", 10, "United Kingdom", 235.0, 11582),
    ("JFK", "CDG", "AFR", 7, "France", 240.0, 10972),
    ("CDG", "JFK", "AFR", 6, "France", 232.0, 11277),
    ("BOS", "LHR", "BAW", 212, "United Kingdom", 242.0, 11887),
    ("ORD", "FRA", "DLH", 431, "Germany", 238.0, 10668),
    ("FRA", "ORD", "UAL", 907, "United States", 230.0, 10972),
    ("EWR", "AMS", "KLM", 642, "Netherlands", 240.0, 11277),
    ("IAD", "LHR", "UAL", 918, "United States", 242.0, 11582),
    ("MIA", "MAD", "IBE", 6124, "Spain", 238.0, 11277),
    ("MAD", "MIA", "AAL", 68, "United States", 235.0, 10972),
    ("YYZ", "LHR", "ACA", 856, "Canada", 245.0, 11582),
    ("LAX", "LHR", "BAW", 268, "United Kingdom", 248.0, 11887),
    ("SFO", "FRA", "DLH", 455, "Germany", 246.0, 11582),
    ("JFK", "MAD", "IBE", 6251, "Spain", 240.0, 11277),
    ("MCO", "LGW", "VIR", 16, "United Kingdom", 242.0, 10972),
    ("ATL", "AMS", "DAL", 72, "United States", 240.0, 11277),
    ("DFW", "LHR", "AAL", 50, "United States", 245.0, 11582),
    ("SEA", "LHR", "BAW", 48, "United Kingdom", 244.0, 11887),
    ("PHX", "LHR", "AAL", 194, "United States", 246.0, 11582),

    # North America Transcontinental & Regional Corridors
    ("JFK", "LAX", "AAL", 1, "United States", 235.0, 10668),
    ("LAX", "JFK", "DAL", 4, "United States", 255.0, 11277),
    ("BOS", "SFO", "UAL", 312, "United States", 230.0, 10972),
    ("SFO", "BOS", "JBU", 634, "United States", 252.0, 11582),
    ("JFK", "SFO", "DAL", 412, "United States", 232.0, 10668),
    ("EWR", "LAX", "UAL", 112, "United States", 234.0, 10972),
    ("ORD", "LAX", "AAL", 215, "United States", 228.0, 9753),
    ("LAX", "ORD", "UAL", 480, "United States", 245.0, 10363),
    ("ATL", "DFW", "DAL", 891, "United States", 225.0, 9144),
    ("DFW", "ATL", "AAL", 124, "United States", 230.0, 9753),
    ("MIA", "JFK", "AAL", 1102, "United States", 240.0, 10058),
    ("JFK", "MIA", "DAL", 305, "United States", 225.0, 9753),
    ("SEA", "LAX", "ASA", 412, "United States", 220.0, 9448),
    ("LAX", "SEA", "DAL", 502, "United States", 222.0, 9753),
    ("DEN", "ORD", "UAL", 610, "United States", 235.0, 10058),
    ("ORD", "DEN", "SWA", 114, "United States", 220.0, 9144),
    ("ATL", "MCO", "DAL", 182, "United States", 215.0, 8534),
    ("DFW", "ORD", "AAL", 404, "United States", 225.0, 9753),
    ("LAX", "HNL", "HAL", 2, "United States", 240.0, 11277),
    ("HNL", "LAX", "UAL", 115, "United States", 250.0, 11582),

    # Europe High-Density Corridors
    ("LHR", "CDG", "BAW", 304, "United Kingdom", 210.0, 7620),
    ("CDG", "LHR", "AFR", 1680, "France", 212.0, 7620),
    ("LHR", "AMS", "KLM", 1000, "Netherlands", 205.0, 7315),
    ("AMS", "LHR", "BAW", 428, "United Kingdom", 208.0, 7315),
    ("LHR", "FRA", "DLH", 901, "Germany", 220.0, 8534),
    ("FRA", "LHR", "BAW", 902, "United Kingdom", 218.0, 8534),
    ("FRA", "CDG", "AFR", 1819, "France", 210.0, 7924),
    ("CDG", "FRA", "DLH", 1029, "Germany", 212.0, 7924),
    ("CDG", "MAD", "IBE", 3401, "Spain", 225.0, 10058),
    ("MAD", "CDG", "AFR", 1400, "France", 228.0, 10363),
    ("LHR", "MAD", "BAW", 460, "United Kingdom", 230.0, 10668),
    ("MAD", "LHR", "IBE", 3164, "Spain", 232.0, 10972),
    ("AMS", "CDG", "AFR", 1141, "France", 208.0, 7620),
    ("FRA", "MAD", "DLH", 1112, "Germany", 228.0, 10363),
    ("MUC", "FCO", "DLH", 1842, "Germany", 220.0, 9144),
    ("FCO", "MUC", "ITY", 102, "Italy", 222.0, 9448),
    ("ZRH", "LHR", "SWR", 316, "Switzerland", 220.0, 8839),
    ("LHR", "ZRH", "BAW", 712, "United Kingdom", 218.0, 8839),
    ("VIE", "FRA", "AUA", 111, "Austria", 215.0, 8534),
    ("DUB", "LHR", "EIN", 152, "Ireland", 205.0, 7315),
    ("CPH", "OSL", "SAS", 452, "Sweden", 210.0, 8229),
    ("ARN", "CPH", "SAS", 1419, "Sweden", 212.0, 8534),
    ("HEL", "ARN", "FIN", 801, "Finland", 205.0, 7620),
    ("WAW", "FRA", "LOT", 379, "Poland", 222.0, 9448),
    ("IST", "FRA", "THY", 1587, "Turkey", 235.0, 10668),
    ("FRA", "IST", "DLH", 1300, "Germany", 238.0, 10972),
    ("ATH", "LHR", "AEE", 600, "Greece", 235.0, 10668),
    ("LHR", "ATH", "BAW", 632, "United Kingdom", 238.0, 10972),

    # Europe - Middle East - Asia Corridors
    ("LHR", "DXB", "UAE", 2, "United Arab Emirates", 252.0, 11887),
    ("DXB", "LHR", "UAE", 1, "United Arab Emirates", 242.0, 11277),
    ("CDG", "DXB", "AFR", 662, "France", 250.0, 11582),
    ("FRA", "DXB", "DLH", 630, "Germany", 248.0, 11582),
    ("LHR", "DOH", "QTR", 4, "Qatar", 250.0, 11887),
    ("DOH", "LHR", "BAW", 122, "United Kingdom", 242.0, 11277),
    ("FRA", "DOH", "QTR", 70, "Qatar", 246.0, 11582),
    ("LHR", "SIN", "SIA", 305, "Singapore", 255.0, 11887),
    ("SIN", "LHR", "SIA", 306, "Singapore", 245.0, 11277),
    ("LHR", "HKG", "CPA", 250, "Hong Kong", 250.0, 11582),
    ("HKG", "LHR", "BAW", 28, "United Kingdom", 244.0, 11277),
    ("CDG", "HND", "AFR", 274, "France", 252.0, 11887),
    ("HND", "CDG", "ANA", 215, "Japan", 248.0, 11582),
    ("LHR", "HND", "BAW", 5, "United Kingdom", 252.0, 11887),
    ("FRA", "HND", "DLH", 716, "Germany", 250.0, 11582),
    ("LHR", "DEL", "AIC", 162, "India", 248.0, 11277),
    ("DEL", "LHR", "AIC", 161, "India", 242.0, 10972),
    ("FRA", "DEL", "DLH", 760, "Germany", 246.0, 11277),
    ("LHR", "BOM", "BAW", 199, "United Kingdom", 246.0, 11277),
    ("CDG", "BKK", "AFR", 166, "France", 250.0, 11582),

    # Middle East Hub Corridors
    ("DXB", "DEL", "UAE", 510, "United Arab Emirates", 240.0, 10668),
    ("DEL", "DXB", "AIC", 995, "India", 238.0, 10363),
    ("DXB", "BOM", "UAE", 500, "United Arab Emirates", 238.0, 10363),
    ("BOM", "DXB", "IGO", 21, "India", 236.0, 10058),
    ("DXB", "SIN", "UAE", 354, "United Arab Emirates", 250.0, 11582),
    ("SIN", "DXB", "SIA", 494, "Singapore", 246.0, 11277),
    ("DXB", "BKK", "UAE", 384, "United Arab Emirates", 248.0, 11277),
    ("DXB", "SYD", "UAE", 414, "United Arab Emirates", 255.0, 11887),
    ("DOH", "SIN", "QTR", 942, "Qatar", 250.0, 11582),
    ("DOH", "DEL", "QTR", 678, "Qatar", 240.0, 10668),
    ("DOH", "SYD", "QTR", 906, "Qatar", 255.0, 11887),
    ("AUH", "LHR", "ETD", 19, "United Arab Emirates", 245.0, 11582),
    ("JED", "CAI", "SVA", 301, "Saudi Arabia", 230.0, 9753),
    ("RUH", "DXB", "FDB", 872, "United Arab Emirates", 225.0, 9448),
    ("KWI", "DXB", "KAC", 107, "Kuwait", 228.0, 9753),

    # Asia & Pacific Corridors
    ("HND", "ITM", "ANA", 15, "Japan", 210.0, 7315),
    ("NRT", "ICN", "KAL", 702, "Republic of Korea", 228.0, 9753),
    ("ICN", "NRT", "AAR", 102, "Republic of Korea", 230.0, 10058),
    ("HND", "PEK", "CCA", 182, "China", 238.0, 10668),
    ("PEK", "HND", "ANA", 962, "Japan", 242.0, 10972),
    ("PVG", "HND", "CES", 537, "China", 235.0, 10363),
    ("HKG", "TPE", "CPA", 468, "Hong Kong", 220.0, 8534),
    ("TPE", "HKG", "CAL", 919, "Taiwan", 222.0, 8839),
    ("HKG", "SIN", "CPA", 711, "Hong Kong", 242.0, 10972),
    ("SIN", "HKG", "SIA", 856, "Singapore", 245.0, 11277),
    ("SIN", "KUL", "MAS", 606, "Malaysia", 200.0, 6096),
    ("KUL", "SIN", "SIA", 119, "Singapore", 202.0, 6096),
    ("SIN", "CGK", "GIA", 823, "Indonesia", 215.0, 8534),
    ("BKK", "SIN", "THA", 403, "Thailand", 230.0, 9753),
    ("SIN", "BKK", "SIA", 710, "Singapore", 232.0, 10058),
    ("HKG", "BKK", "THA", 601, "Thailand", 235.0, 10363),
    ("PEK", "PVG", "CCA", 1501, "China", 230.0, 9753),
    ("PVG", "PEK", "CES", 5102, "China", 232.0, 10058),
    ("CAN", "PEK", "CSN", 3101, "China", 236.0, 10363),
    ("HKG", "MNL", "PAL", 301, "Philippines", 225.0, 9144),
    ("TPE", "NRT", "EVA", 198, "Taiwan", 238.0, 10668),
    ("ICN", "HKG", "KAL", 607, "Republic of Korea", 236.0, 10668),

    # Transpacific Corridors
    ("LAX", "HND", "ANA", 105, "Japan", 248.0, 11277),
    ("HND", "LAX", "JAL", 62, "Japan", 260.0, 11887),
    ("SFO", "HND", "UAL", 875, "United States", 246.0, 11277),
    ("HND", "SFO", "ANA", 108, "Japan", 258.0, 11887),
    ("LAX", "ICN", "KAL", 12, "Republic of Korea", 248.0, 11277),
    ("ICN", "LAX", "AAR", 202, "Republic of Korea", 262.0, 11887),
    ("SFO", "TPE", "EVA", 27, "Taiwan", 246.0, 11277),
    ("TPE", "SFO", "CAL", 4, "Taiwan", 260.0, 11887),
    ("LAX", "SYD", "QFA", 12, "Australia", 250.0, 11582),
    ("SYD", "LAX", "QFA", 11, "Australia", 255.0, 11887),
    ("SFO", "SYD", "UAL", 863, "United States", 250.0, 11582),
    ("LAX", "AKL", "ANZ", 5, "New Zealand", 250.0, 11582),
    ("AKL", "LAX", "ANZ", 6, "New Zealand", 255.0, 11887),
    ("YVR", "HKG", "CPA", 889, "Hong Kong", 248.0, 11277),

    # India Domestic & Regional
    ("DEL", "BOM", "IGO", 204, "India", 230.0, 9753),
    ("BOM", "DEL", "AIC", 887, "India", 232.0, 10058),
    ("DEL", "BLR", "IGO", 512, "India", 236.0, 10363),
    ("BLR", "DEL", "AIC", 505, "India", 238.0, 10668),
    ("BOM", "BLR", "IGO", 314, "India", 220.0, 8839),
    ("DEL", "HYD", "AIC", 542, "India", 232.0, 10058),
    ("DEL", "CCU", "IGO", 251, "India", 234.0, 10363),
    ("MAA", "DEL", "AIC", 430, "India", 238.0, 10668),

    # Australia & Oceania Domestic
    ("SYD", "MEL", "QFA", 401, "Australia", 225.0, 9144),
    ("MEL", "SYD", "VOZ", 811, "Australia", 228.0, 9448),
    ("SYD", "BNE", "QFA", 502, "Australia", 226.0, 9144),
    ("BNE", "SYD", "JST", 511, "Australia", 228.0, 9448),
    ("MEL", "PER", "QFA", 775, "Australia", 242.0, 11277),
    ("PER", "MEL", "VOZ", 682, "Australia", 250.0, 11582),
    ("SYD", "PER", "QFA", 581, "Australia", 240.0, 11277),
    ("AKL", "CHC", "ANZ", 509, "New Zealand", 215.0, 8534),
    ("CHC", "AKL", "ANZ", 534, "New Zealand", 218.0, 8839),

    # Latin America
    ("GRU", "EZE", "TAM", 8010, "Brazil", 232.0, 10363),
    ("EZE", "GRU", "ARG", 1240, "Argentina", 235.0, 10668),
    ("SCL", "EZE", "LAN", 445, "Chile", 220.0, 9753),
    ("GRU", "GIG", "GLO", 1024, "Brazil", 205.0, 6705),
    ("BOG", "MIA", "AVA", 6, "Colombia", 238.0, 10668),
    ("MIA", "BOG", "AAL", 916, "United States", 235.0, 10363),
    ("MEX", "LAX", "AMX", 648, "Mexico", 230.0, 10058),
    ("LIM", "SCL", "LAN", 531, "Chile", 236.0, 10668),

    # Africa
    ("JNB", "CPT", "SAA", 317, "South Africa", 235.0, 10363),
    ("CPT", "JNB", "SAA", 322, "South Africa", 238.0, 10668),
    ("ADD", "NBO", "ETH", 801, "Ethiopia", 220.0, 9144),
    ("NBO", "JNB", "KQA", 760, "Kenya", 240.0, 10972),
    ("CAI", "DXB", "MSR", 912, "Egypt", 242.0, 11277),
    ("CMN", "CDG", "RAM", 750, "Morocco", 236.0, 10668),
    ("LOS", "LHR", "BAW", 75, "United Kingdom", 246.0, 11582),
    ("ALG", "CDG", "DAH", 1004, "Algeria", 228.0, 10058),
]


def load_sample_aircraft(now: datetime | None = None) -> list[AircraftStateRecord]:
    """Provide realistic worldwide commercial flight states (850+ flights) with real-time forward flight motion."""
    epoch = now or datetime.now(UTC)
    elapsed = epoch.timestamp()
    records: list[AircraftStateRecord] = []
    flight_idx = 0

    for orig, dest, airline, base_num, country, speed, alt in _GLOBAL_ROUTE_TEMPLATES:
        if orig not in _GLOBAL_HUBS or dest not in _GLOBAL_HUBS:
            continue
        orig_lat, orig_lon, _ = _GLOBAL_HUBS[orig]
        dest_lat, dest_lon, _ = _GLOBAL_HUBS[dest]

        # Calculate great-circle distance
        dlat = math.radians(dest_lat - orig_lat)
        dlon = math.radians(dest_lon - orig_lon)
        a = (
            math.sin(dlat / 2.0) ** 2
            + math.cos(math.radians(orig_lat)) * math.cos(math.radians(dest_lat)) * math.sin(dlon / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(max(0.0, a)), math.sqrt(max(0.0, 1.0 - a)))
        dist_m = max(50000.0, 6371000.0 * c)
        duration_sec = max(1800.0, dist_m / speed)

        # Bearing from origin to destination
        y = math.sin(dlon) * math.cos(math.radians(dest_lat))
        x = (
            math.cos(math.radians(orig_lat)) * math.sin(math.radians(dest_lat))
            - math.sin(math.radians(orig_lat)) * math.cos(math.radians(dest_lat)) * math.cos(dlon)
        )
        track_deg = round((math.degrees(math.atan2(y, x)) + 360.0) % 360.0, 1)

        # 5 staggered flights along this route leg
        for offset_ratio in [0.08, 0.28, 0.48, 0.68, 0.88]:
            flight_idx += 1
            progress = (elapsed / duration_sec + offset_ratio) % 1.0
            cur_lat = round(orig_lat + (dest_lat - orig_lat) * progress, 4)
            cur_lon = round(orig_lon + (dest_lon - orig_lon) * progress, 4)

            # Unique non-duplicated ICAO24 and callsign
            icao24 = f"a{flight_idx:05x}"
            fnum = base_num + (int(offset_ratio * 100) % 70)
            callsign = f"{airline}{fnum}"
            content_hash = hashlib.sha256(f"{icao24}:{callsign}:{epoch.isoformat()}".encode("utf-8")).hexdigest()

            records.append(
                AircraftStateRecord(
                    icao24=icao24,
                    callsign=callsign,
                    origin_country=country,
                    time_position=epoch,
                    last_contact=epoch,
                    longitude=cur_lon,
                    latitude=cur_lat,
                    baro_altitude=float(alt),
                    on_ground=False,
                    velocity=float(speed),
                    true_track=track_deg,
                    vertical_rate=0.0,
                    geo_altitude=float(alt),
                    squawk="1000",
                    position_source=0,
                    category=1,
                    locator="worldos://simulated-flight-corridor",
                    content_hash=content_hash,
                )
            )

    return records


SAMPLE_AIRCRAFT_DATA: list[dict[str, Any]] = [
    {
        "icao24": r.icao24,
        "callsign": r.callsign,
        "country": r.origin_country,
        "lat": r.latitude,
        "lon": r.longitude,
        "alt": r.baro_altitude,
        "track": r.true_track,
        "vel": r.velocity,
    }
    for r in load_sample_aircraft()[:100]
]


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
    """Query OpenSky Network /states/all with OAuth2 authentication and smart memory-cached bounding box scoping."""
    has_bbox = lamin is not None and lomin is not None and lamax is not None and lomax is not None

    # 1. Check in-memory global cache first (valid for 30s)
    cached = get_cached_aircraft_states(max_age_seconds=30.0)
    if cached is not None:
        if has_bbox:
            return [
                r for r in cached
                if lamin <= r.latitude <= lamax and lomin <= r.longitude <= lomax
            ]
        return cached

    # 2. Fetch fresh global states from OpenSky /states/all
    mgr = token_manager or get_token_manager()
    token = mgr.get_token()

    # Always query global /states/all so we populate the in-memory cache for all viewport queries
    locator = OPENSKY_STATES_URL
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
    if records:
        set_cached_aircraft_states(records)

    if has_bbox:
        return [
            r for r in records
            if lamin <= r.latitude <= lamax and lomin <= r.longitude <= lomax
        ]
    return records
