"""Tests for OpenSky configuration and secret masking."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.config import OpenSkySettings, get_opensky_settings


class TestOpenSkySettings(unittest.TestCase):
    """Verify OpenSkySettings behavior, env loading, and SecretStr redaction."""

    def test_empty_settings_not_configured(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = OpenSkySettings.from_env()
            self.assertFalse(settings.is_configured)
            self.assertIsNone(settings.client_id)
            self.assertIsNone(settings.client_secret)

    def test_configured_settings_with_mock_values(self) -> None:
        mock_env = {
            "OPENSKY_CLIENT_ID": "mock-client-id",
            "OPENSKY_CLIENT_SECRET": "mock-client-secret",
        }
        with patch.dict(os.environ, mock_env, clear=True):
            settings = get_opensky_settings()
            self.assertTrue(settings.is_configured)
            self.assertEqual(settings.client_id, "mock-client-id")

            # Verify SecretStr masking in string representation
            self.assertEqual(str(settings.client_secret), "**********")
            self.assertIn("**********", repr(settings))
            self.assertNotIn("mock-client-secret", str(settings))
            self.assertNotIn("mock-client-secret", repr(settings))

            # Verify secret retrieval via get_secret_value()
            self.assertIsNotNone(settings.client_secret)
            self.assertEqual(
                settings.client_secret.get_secret_value(), "mock-client-secret"
            )


if __name__ == "__main__":
    unittest.main()

