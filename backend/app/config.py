"""Configuration and secure credential management for WORLDOS."""
from __future__ import annotations

import os
from pydantic import BaseModel, ConfigDict, SecretStr


class OpenSkySettings(BaseModel):
    """Secure configuration container for OpenSky Network OAuth2 credentials."""

    model_config = ConfigDict(frozen=True)

    client_id: str | None = None
    client_secret: SecretStr | None = None

    @property
    def is_configured(self) -> bool:
        """Return True if both client_id and client_secret are configured."""
        return bool(
            self.client_id
            and self.client_secret
            and self.client_secret.get_secret_value()
        )

    @classmethod
    def from_env(cls) -> OpenSkySettings:
        """Load OpenSky settings from the process environment."""
        client_id = os.environ.get("OPENSKY_CLIENT_ID", "").strip() or None
        raw_secret = os.environ.get("OPENSKY_CLIENT_SECRET", "").strip() or None
        return cls(
            client_id=client_id,
            client_secret=SecretStr(raw_secret) if raw_secret else None,
        )


def get_opensky_settings() -> OpenSkySettings:
    """Factory function returning the active OpenSkySettings instance."""
    return OpenSkySettings.from_env()

