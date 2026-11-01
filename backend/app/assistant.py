"""Authenticated ElevenLabs session support for the WORLDOS assistant."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env.local")


class AssistantUnavailable(RuntimeError):
    """The configured ElevenLabs assistant cannot create a session."""


def create_elevenlabs_conversation_token() -> str:
    """Mint a short-lived WebRTC token without exposing the project key to the browser."""
    agent_id = os.getenv("WORLDOS_ELEVENLABS_AGENT_ID", "").strip()
    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not agent_id or not api_key:
        raise AssistantUnavailable("ElevenLabs agent credentials are not configured")
    try:
        from elevenlabs import ElevenLabs

        token = ElevenLabs(api_key=api_key).conversational_ai.conversations.get_webrtc_token(agent_id=agent_id)
        value = getattr(token, "token", None)
        if not isinstance(value, str) or not value:
            raise RuntimeError("ElevenLabs returned an empty conversation token")
        return value
    except ImportError as exc:
        raise AssistantUnavailable("The ElevenLabs SDK is not installed") from exc
    except Exception as exc:
        raise AssistantUnavailable("ElevenLabs could not create a conversation session") from exc
