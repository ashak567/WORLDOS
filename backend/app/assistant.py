"""Authenticated ElevenLabs session support for the WORLDOS assistant."""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger("worldos.assistant")
load_dotenv(Path(__file__).resolve().parents[2] / ".env.local")


class AssistantUnavailable(RuntimeError):
    """The configured ElevenLabs assistant cannot create a session."""


def create_elevenlabs_signed_url() -> str:
    """Mint a short-lived authenticated WebSocket URL for the ElevenLabs conversational AI agent."""
    agent_id = os.getenv("WORLDOS_ELEVENLABS_AGENT_ID", "").strip()
    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not agent_id or not api_key:
        raise AssistantUnavailable("ElevenLabs agent credentials are not configured")

    # First attempt: standard REST endpoint to avoid heavy external SDK dependency issues
    url = f"https://api.elevenlabs.io/v1/convai/conversation/get_signed_url?agent_id={agent_id}"
    req = urllib.request.Request(url, headers={"xi-api-key": api_key, "User-Agent": "WORLDOS-API/0.1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            signed_url = data.get("signed_url")
            if isinstance(signed_url, str) and signed_url.strip():
                return signed_url.strip()
            raise RuntimeError("ElevenLabs returned an empty signed URL")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.error("ElevenLabs HTTPError %s: %s", exc.code, body)
        raise AssistantUnavailable(f"ElevenLabs rejected the request: HTTP {exc.code}") from exc
    except Exception as exc:
        logger.warning("REST request to ElevenLabs failed (%s); trying SDK fallback", exc)

    # Optional SDK fallback if available
    try:
        from elevenlabs import ElevenLabs

        client = ElevenLabs(api_key=api_key)
        # Check for get_signed_url or get_webrtc_token on client
        conv = client.conversational_ai.conversations
        if hasattr(conv, "get_signed_url"):
            resp = conv.get_signed_url(agent_id=agent_id)
            val = getattr(resp, "signed_url", None) or getattr(resp, "token", None) or str(resp)
            if val:
                return val
        elif hasattr(conv, "get_webrtc_token"):
            token = conv.get_webrtc_token(agent_id=agent_id)
            val = getattr(token, "token", None)
            if val:
                return val
    except Exception:
        pass

    raise AssistantUnavailable("ElevenLabs could not create a conversation session")


# Backward-compatible alias
create_elevenlabs_conversation_token = create_elevenlabs_signed_url

