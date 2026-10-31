"""Local-only reasoning and speech transcription for the WORLDOS assistant."""
from __future__ import annotations

import io
import json
import os
import threading
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .interfaces import EvidenceBoundReasoner
from .config import get_local_assistant_settings

MAX_AUDIO_BYTES = 5 * 1024 * 1024
SUPPORTED_AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/wav", "audio/mp4"}
SAFE_LAYER_IDS = {
    "country-boundaries",
    "population-observations",
    "aircraft-states",
    "maritime-vessels",
    "space-satellites",
    "surveillance-cameras",
    "earthquake-events",
    "natural-hazards",
    "thermal-fires",
    "critical-infrastructure",
    "anomalies",
    "system-alerts",
}
_transcriber_lock = threading.Lock()
_transcriber: Any = None


class AssistantUnavailable(RuntimeError):
    """A local assistant service is not installed or not reachable."""


class AssistantInputError(ValueError):
    """The user-provided question or audio input is invalid."""


class OllamaEvidenceBoundReasoner(EvidenceBoundReasoner):
    """Explain deterministic WORLDOS results with a local Ollama model."""

    def __init__(self, base_url: str | None = None, model: str | None = None, timeout: float = 120) -> None:
        settings = get_local_assistant_settings()
        self.base_url = (base_url or settings.ollama_url).rstrip("/")
        self.model = model or settings.ollama_model
        self.timeout = timeout
        parsed = urlparse(self.base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "host.docker.internal"}:
            raise ValueError("Ollama must use a local HTTP host")

    def answer(self, question: str, deterministic_result: dict, evidence_ids: list[str]) -> dict:
        system = (
            "You are WORLDOS, a warm and concise map assistant. Use only facts present in the supplied WORLDOS data; user_preferences are preferences, never facts. "
            "Do not invent locations, values, source status, or freshness. If the data does not answer the question, say what is missing. "
            "Keep humor occasional and understated; never joke about disasters, emergencies, or casualties. "
            "Do not claim human feelings or experiences. Do not ask to run commands or external actions. "
            "Return JSON with an answer string and evidence_ids array. Cite only supplied IDs that support the answer."
        )
        user_payload = {
            "question": question,
            "worldos_data": deterministic_result,
            "available_evidence_ids": evidence_ids,
        }
        body = json.dumps({
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "format": "json",
            "options": {"temperature": 0.25, "num_predict": 320, "num_ctx": 8192},
        }).encode("utf-8")
        request = Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read(1_000_001).decode("utf-8"))
        except (URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise AssistantUnavailable("Local Ollama is unavailable or timed out") from exc
        content = payload.get("message", {}).get("content") if isinstance(payload, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise AssistantUnavailable("Local Ollama returned an empty answer")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AssistantUnavailable("Local Ollama returned an unstructured answer") from exc
        answer = parsed.get("answer") if isinstance(parsed, dict) else None
        cited = parsed.get("evidence_ids") if isinstance(parsed, dict) else None
        if not isinstance(answer, str) or not answer.strip() or not isinstance(cited, list):
            raise AssistantUnavailable("Local Ollama returned an invalid answer structure")
        allowed = set(evidence_ids)
        valid_ids = [item for item in cited if isinstance(item, str) and item in allowed]
        if evidence_ids and not valid_ids:
            raise AssistantUnavailable("Local Ollama did not cite available WORLDOS evidence")
        return {"answer": answer.strip(), "evidence_ids": valid_ids}


def validated_layer_action(question: str) -> dict[str, Any] | None:
    """Convert a direct show/hide request into one allowlisted map view action."""
    text = question.casefold()
    visible: bool | None = None
    if any(phrase in text for phrase in ("show ", "display ", "turn on ", "enable ")):
        visible = True
    elif any(phrase in text for phrase in ("hide ", "turn off ", "disable ")):
        visible = False
    if visible is None:
        return None

    aliases = {
        "space-satellites": ("satellite", "satellites", "space layer"),
        "aircraft-states": ("aircraft", "planes", "aviation layer"),
        "maritime-vessels": ("ships", "vessels", "marine layer"),
        "surveillance-cameras": ("cameras", "camera layer"),
        "earthquake-events": ("earthquakes", "earthquake layer"),
        "natural-hazards": ("hazards", "cyclones", "tsunami", "natural hazard layer"),
        "thermal-fires": ("fires", "wildfires", "fire layer"),
        "critical-infrastructure": ("infrastructure", "infrastructure layer"),
        "population-observations": ("population", "population layer"),
        "system-alerts": ("alerts", "alert layer"),
        "anomalies": ("anomalies", "anomaly layer"),
        "country-boundaries": ("country boundaries", "boundaries"),
    }
    for layer_id, layer_aliases in aliases.items():
        if layer_id in SAFE_LAYER_IDS and any(alias in text for alias in layer_aliases):
            return {"type": "set_layer_visibility", "layer_id": layer_id, "visible": visible}
    return None


def validate_audio(audio: bytes, media_type: str) -> None:
    if media_type.split(";", 1)[0].strip().lower() not in SUPPORTED_AUDIO_TYPES:
        raise AssistantInputError("Use a WebM, Ogg, WAV, or MP4 audio recording")
    if not audio:
        raise AssistantInputError("The audio recording is empty")
    if len(audio) > MAX_AUDIO_BYTES:
        raise AssistantInputError("The audio recording exceeds the 5 MB limit")


def transcribe_local_audio(audio: bytes, media_type: str) -> dict[str, str | None]:
    """Transcribe locally with a cached, CPU-friendly Whisper tiny model."""
    validate_audio(audio, media_type)
    global _transcriber
    # ponytail: one model-wide lock bounds CPU and RAM use; use worker-local models if throughput matters.
    with _transcriber_lock:
        if _transcriber is None:
            try:
                from faster_whisper import WhisperModel
                from huggingface_hub import snapshot_download
            except ImportError as exc:
                raise AssistantUnavailable("Local speech recognition is not installed") from exc
            try:
                model_path = Path(os.getenv("WORLDOS_WHISPER_MODEL_DIR", "/models/whisper-tiny"))
                if not (model_path / "model.bin").is_file():
                    snapshot_download("Systran/faster-whisper-tiny", local_dir=str(model_path))
                _transcriber = WhisperModel(str(model_path), device="cpu", compute_type="int8")
            except Exception as exc:
                raise AssistantUnavailable("The local Whisper model could not be loaded") from exc
        try:
            segments, info = _transcriber.transcribe(io.BytesIO(audio), beam_size=1, vad_filter=True)
            text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
        except Exception as exc:
            raise AssistantInputError("The audio could not be decoded; try recording again") from exc
    if not text:
        raise AssistantInputError("No speech was detected")
    return {"text": text, "language": getattr(info, "language", None)}
