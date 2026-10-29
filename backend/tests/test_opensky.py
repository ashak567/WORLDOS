"""Tests for OpenSky ADS-B state vector ingestion, OAuth2 token caching, and normalization."""
from __future__ import annotations

import json
import time
import unittest
from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from pydantic import SecretStr

from app.config import OpenSkySettings
from app.ingestion.opensky import (
    AircraftStateRecord,
    OpenSkyAuthError,
    OpenSkyRateLimitError,
    OpenSkyTokenManager,
    fetch_aircraft_states,
    parse_state_vector,
)


class TestOpenSkyTokenManager(unittest.TestCase):
    """Test OAuth2 token retrieval, caching, and error handling."""

    def test_unconfigured_raises_auth_error(self) -> None:
        mgr = OpenSkyTokenManager(OpenSkySettings(client_id=None, client_secret=None))
        self.assertFalse(mgr.is_configured)
        with self.assertRaises(OpenSkyAuthError) as ctx:
            mgr.get_token()
        self.assertIn("not configured", str(ctx.exception))

    @patch("app.ingestion.opensky.urlopen")
    def test_token_exchange_and_caching(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "access_token": "test-mock-token-xyz",
            "expires_in": 1800,
            "token_type": "Bearer",
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        settings = OpenSkySettings(client_id="test-id", client_secret=SecretStr("test-secret"))
        mgr = OpenSkyTokenManager(settings)

        # First retrieval performs exchange
        token1 = mgr.get_token()
        self.assertEqual(token1, "test-mock-token-xyz")
        self.assertEqual(mock_urlopen.call_count, 1)

        # Second retrieval within expiry reuses cached token without urlopen call
        token2 = mgr.get_token()
        self.assertEqual(token2, "test-mock-token-xyz")
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("app.ingestion.opensky.urlopen")
    def test_token_exchange_http_401_sanitized(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = HTTPError(
            url="https://auth.opensky-network.org/...",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=BytesIO(b'{"error": "invalid_client"}'),
        )
        settings = OpenSkySettings(client_id="bad-id", client_secret=SecretStr("bad-secret"))
        mgr = OpenSkyTokenManager(settings)

        with self.assertRaises(OpenSkyAuthError) as ctx:
            mgr.get_token()
        err_msg = str(ctx.exception)
        self.assertIn("HTTP 401", err_msg)
        self.assertNotIn("bad-secret", err_msg)


class TestOpenSkyParsing(unittest.TestCase):
    """Test parsing and validation of OpenSky state vector arrays."""

    def setUp(self) -> None:
        # Standard OpenSky state vector array: 17 elements
        self.sample_vector = [
            "80033c",          # 0: icao24
            "AIC101  ",        # 1: callsign
            "India",           # 2: origin_country
            1729999998,        # 3: time_position
            1729999999,        # 4: last_contact
            77.1025,           # 5: longitude
            28.5562,           # 6: latitude
            10668.0,           # 7: baro_altitude
            False,             # 8: on_ground
            230.5,             # 9: velocity
            110.2,             # 10: true_track
            0.0,               # 11: vertical_rate
            None,              # 12: sensors
            10972.8,           # 13: geo_altitude
            "1234",            # 14: squawk
            False,             # 15: spi
            0,                 # 16: position_source
            4,                 # 17: category (large)
        ]

    def test_parse_valid_state_vector(self) -> None:
        record = parse_state_vector(self.sample_vector, "https://opensky-network.org/test", "hash123")
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.icao24, "80033c")
        self.assertEqual(record.callsign, "AIC101")  # Stripped trailing spaces
        self.assertEqual(record.origin_country, "India")
        self.assertEqual(record.longitude, 77.1025)
        self.assertEqual(record.latitude, 28.5562)
        self.assertEqual(record.baro_altitude, 10668.0)
        self.assertEqual(record.velocity, 230.5)
        self.assertEqual(record.true_track, 110.2)
        self.assertFalse(record.on_ground)
        self.assertEqual(record.squawk, "1234")
        self.assertEqual(record.category, 4)
        self.assertEqual(record.locator, "https://opensky-network.org/test")
        self.assertEqual(record.content_hash, "hash123")

    def test_parse_null_coordinates_skipped(self) -> None:
        vec = list(self.sample_vector)
        vec[5] = None  # longitude null
        self.assertIsNone(parse_state_vector(vec, "loc", "hash"))

        vec[5] = 77.0
        vec[6] = None  # latitude null
        self.assertIsNone(parse_state_vector(vec, "loc", "hash"))

    def test_parse_out_of_range_coordinates_skipped(self) -> None:
        vec = list(self.sample_vector)
        vec[5] = 195.0  # Invalid longitude > 180
        self.assertIsNone(parse_state_vector(vec, "loc", "hash"))

    def test_parse_empty_callsign_becomes_none(self) -> None:
        vec = list(self.sample_vector)
        vec[1] = "   "  # whitespace callsign
        record = parse_state_vector(vec, "loc", "hash")
        self.assertIsNotNone(record)
        assert record is not None
        self.assertIsNone(record.callsign)


class TestFetchAircraftStates(unittest.TestCase):
    """Test fetch_aircraft_states querying and bounding box handling."""

    @patch("app.ingestion.opensky.urlopen")
    def test_fetch_with_bbox(self, mock_urlopen: MagicMock) -> None:
        mock_mgr = MagicMock()
        mock_mgr.get_token.return_value = "mock-token"

        mock_payload = {
            "time": 1729999999,
            "states": [
                [
                    "80033c", "AIC101", "India", 1729999998, 1729999999,
                    77.1025, 28.5562, 10668.0, False, 230.5, 110.2, 0.0,
                    None, 10972.8, "1234", False, 0,
                ],
                [
                    "80044d", None, "India", None, 1729999999,
                    None, None, None, True, None, None, None,
                    None, None, None, False, 0,  # Missing coordinates -> should be filtered out
                ],
            ],
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        records = fetch_aircraft_states(
            lamin=26.0,
            lomin=75.0,
            lamax=30.0,
            lomax=79.0,
            token_manager=mock_mgr,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].icao24, "80033c")
        self.assertEqual(records[0].callsign, "AIC101")
        self.assertIn("lamin=26.0000", records[0].locator)
        self.assertIn("lomax=79.0000", records[0].locator)


if __name__ == "__main__":
    unittest.main()
