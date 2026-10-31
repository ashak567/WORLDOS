from __future__ import annotations

import json
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from app.assistant import (
    AssistantInputError,
    AssistantUnavailable,
    OllamaEvidenceBoundReasoner,
    transcribe_local_audio,
    validated_layer_action,
    validate_audio,
)
from app.main import AssistantTravelPreferences
from pydantic import ValidationError


class AssistantTests(unittest.TestCase):
    def test_local_reasoner_sends_deterministic_result_to_ollama(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps({
            "message": {"content": json.dumps({"answer": "Two sourced events are visible.", "evidence_ids": ["evidence-1"]})}
        }).encode()

        with patch("app.assistant.urlopen", return_value=response) as urlopen:
            result = OllamaEvidenceBoundReasoner("http://localhost:11434", "test-model").answer(
                "Summarize this map", {"events": [{"id": "event-1"}]}, ["evidence-1"]
            )

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(payload["format"], "json")
        self.assertIn("event-1", payload["messages"][1]["content"])
        self.assertEqual(result["answer"], "Two sourced events are visible.")
        self.assertEqual(result["evidence_ids"], ["evidence-1"])

    def test_reasoner_rejects_unknown_evidence_ids(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps({
            "message": {"content": json.dumps({"answer": "Unsupported claim.", "evidence_ids": ["fake-id"]})}
        }).encode()
        with patch("app.assistant.urlopen", return_value=response):
            with self.assertRaises(AssistantUnavailable):
                OllamaEvidenceBoundReasoner("http://localhost:11434").answer("question", {}, ["real-id"])

    def test_remote_ollama_host_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            OllamaEvidenceBoundReasoner("https://example.com")

    def test_unreachable_ollama_has_no_cloud_fallback(self) -> None:
        with patch("app.assistant.urlopen", side_effect=URLError("offline")) as urlopen:
            with self.assertRaises(AssistantUnavailable):
                OllamaEvidenceBoundReasoner("http://localhost:11434").answer("question", {}, [])
        self.assertEqual(urlopen.call_count, 1)
        self.assertTrue(urlopen.call_args.args[0].full_url.startswith("http://localhost:11434/"))

    def test_layer_action_only_allows_known_layer_ids(self) -> None:
        self.assertEqual(
            validated_layer_action("show the satellites"),
            {"type": "set_layer_visibility", "layer_id": "space-satellites", "visible": True},
        )
        self.assertIsNone(validated_layer_action("show the imaginary layer"))
        self.assertIsNone(validated_layer_action("tell me about satellites"))

    def test_audio_content_type_and_size_are_validated(self) -> None:
        validate_audio(b"audio", "audio/webm;codecs=opus")
        with self.assertRaises(AssistantInputError):
            validate_audio(b"audio", "text/plain")
        with self.assertRaises(AssistantInputError):
            validate_audio(b"", "audio/webm")
        with self.assertRaises(AssistantInputError):
            validate_audio(b"x" * (5 * 1024 * 1024 + 1), "audio/webm")

    def test_transcription_uses_local_model_and_returns_language(self) -> None:
        class FakeModel:
            def transcribe(self, audio, **kwargs):
                self.audio = audio.read()
                self.kwargs = kwargs
                return iter([SimpleNamespace(text=" WORLDOS assistant ")]), SimpleNamespace(language="en")

        model = FakeModel()
        with patch("app.assistant._transcriber", model):
            result = transcribe_local_audio(b"local test audio", "audio/wav")

        self.assertEqual(result, {"text": "WORLDOS assistant", "language": "en"})
        self.assertEqual(model.audio, b"local test audio")
        self.assertTrue(model.kwargs["vad_filter"])

    def test_travel_preferences_are_allowlisted_and_bounded(self) -> None:
        saved = AssistantTravelPreferences(pace="relaxed", photo_interest="architecture")
        self.assertEqual(saved.model_dump(exclude_none=True), {"pace": "relaxed", "photo_interest": "architecture"})
        with self.assertRaises(ValidationError):
            AssistantTravelPreferences(pace="luxury")
        with self.assertRaises(ValidationError):
            AssistantTravelPreferences(photo_interest="x" * 121)
        with self.assertRaises(ValidationError):
            AssistantTravelPreferences(home_address="secret")


if __name__ == "__main__":
    unittest.main()
