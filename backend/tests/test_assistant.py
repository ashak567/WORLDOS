from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.assistant import AssistantUnavailable, create_elevenlabs_conversation_token
from app.main import AssistantTravelPreferences
from pydantic import ValidationError


class AssistantTests(unittest.TestCase):
    def test_session_token_uses_server_credentials(self) -> None:
        client = MagicMock()
        client.conversational_ai.conversations.get_webrtc_token.return_value = SimpleNamespace(token="ephemeral-token")
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "server-key", "WORLDOS_ELEVENLABS_AGENT_ID": "agent-id"}):
            with patch.dict(sys.modules, {"elevenlabs": SimpleNamespace(ElevenLabs=lambda **_: client)}):
                self.assertEqual(create_elevenlabs_conversation_token(), "ephemeral-token")
        client.conversational_ai.conversations.get_webrtc_token.assert_called_once_with(agent_id="agent-id")

    def test_missing_server_credentials_fail_closed(self) -> None:
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "", "WORLDOS_ELEVENLABS_AGENT_ID": ""}):
            with self.assertRaises(AssistantUnavailable):
                create_elevenlabs_conversation_token()

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
