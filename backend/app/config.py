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


class AISStreamSettings(BaseModel):
    """Secure configuration container for AISStream.io API key."""

    model_config = ConfigDict(frozen=True)

    api_key: SecretStr | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.get_secret_value())

    @classmethod
    def from_env(cls) -> AISStreamSettings:
        raw_key = os.environ.get("AISSTREAM_API_KEY", "").strip() or None
        return cls(api_key=SecretStr(raw_key) if raw_key else None)


class FirmsSettings(BaseModel):
    """Secure configuration container for NASA FIRMS map key."""

    model_config = ConfigDict(frozen=True)

    map_key: SecretStr | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.map_key and self.map_key.get_secret_value())

    @classmethod
    def from_env(cls) -> FirmsSettings:
        raw_key = os.environ.get("NASA_FIRMS_MAP_KEY", "").strip() or None
        return cls(map_key=SecretStr(raw_key) if raw_key else None)


class LocalAssistantSettings(BaseModel):
    """Local model settings; the endpoint is restricted to local hosts by the adapter."""

    model_config = ConfigDict(frozen=True)

    ollama_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "llama3.2:3b"

    @classmethod
    def from_env(cls) -> LocalAssistantSettings:
        return cls(
            ollama_url=os.environ.get("WORLDOS_OLLAMA_URL", "http://host.docker.internal:11434").strip(),
            ollama_model=os.environ.get("WORLDOS_OLLAMA_MODEL", "llama3.2:3b").strip(),
        )


def get_aisstream_settings() -> AISStreamSettings:
    """Factory function returning the active AISStreamSettings instance."""
    return AISStreamSettings.from_env()


def get_firms_settings() -> FirmsSettings:
    """Factory function returning the active FirmsSettings instance."""
    return FirmsSettings.from_env()


def get_local_assistant_settings() -> LocalAssistantSettings:
    return LocalAssistantSettings.from_env()

