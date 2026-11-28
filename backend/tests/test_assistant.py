from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.assistant import AssistantUnavailable, create_elevenlabs_conversation_token
from app.main import (
    AssistantMapBounds,
    AssistantMapContextRequest,
    AssistantTravelPreferences,
    assistant_map_context,
    search_intelligence_endpoint,
)
from pydantic import ValidationError


class AssistantTests(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_session_token_uses_server_credentials(self, mock_urlopen: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"signed_url": "wss://api.elevenlabs.io/v1/convai/test"}'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "server-key", "WORLDOS_ELEVENLABS_AGENT_ID": "agent-id"}):
            self.assertEqual(create_elevenlabs_conversation_token(), "wss://api.elevenlabs.io/v1/convai/test")

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

    def test_assistant_map_bounds_antimeridian_and_lat_normalization(self) -> None:
        # Panning across the International Date Line (e.g. 170° to -160°) must not raise
        bounds = AssistantMapBounds(min_lon=170.0, min_lat=10.0, max_lon=-160.0, max_lat=20.0)
        self.assertEqual(bounds.min_lon, 170.0)
        self.assertEqual(bounds.max_lon, -160.0)

        # Inverted latitude order must be safely normalized
        inverted_lat = AssistantMapBounds(min_lon=10.0, min_lat=45.0, max_lon=20.0, max_lat=30.0)
        self.assertEqual(inverted_lat.min_lat, 30.0)
        self.assertEqual(inverted_lat.max_lat, 45.0)

    def test_assistant_map_context_request_flexible_entity_id(self) -> None:
        # Valid UUID
        uid = str(uuid4())
        req_uuid = AssistantMapContextRequest(selected_entity_id=uid)
        self.assertEqual(req_uuid.selected_entity_id, uid)

        # Non-UUID string identifier (e.g. event ID, hazard ID, camera ID) must not raise 422
        req_str = AssistantMapContextRequest(
            selected_entity_id="camera-nyc-times-square",
            map_bounds=AssistantMapBounds(min_lon=10.0, min_lat=20.0, max_lon=11.0, max_lat=21.0),
        )
        self.assertEqual(req_str.selected_entity_id, "camera-nyc-times-square")

    @patch("app.main.WorldRepository")
    def test_assistant_map_context_antimeridian_handling(self, mock_repo_class: MagicMock) -> None:
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        mock_context = MagicMock()
        mock_context.model_dump.return_value = {
            "query_scope": {},
            "entities": [],
            "observations": [],
            "events": [],
            "geometries": [],
            "relationships": [],
            "claims": [],
            "evidence": [],
            "assumptions_or_limitations": [],
        }
        mock_repo.scoped_context.return_value = mock_context

        # Call with antimeridian bounds (min_lon > max_lon)
        req = AssistantMapContextRequest(
            map_bounds=AssistantMapBounds(min_lon=175.0, min_lat=-40.0, max_lon=-175.0, max_lat=-30.0),
            selected_entity_id="non-uuid-feature-id",
        )
        res = assistant_map_context(req)
        self.assertIn("entities", res)
        # Verify scoped_context was called with normalized [-180, 180] longitude
        self.assertTrue(mock_repo.scoped_context.called)
        call_kwargs = mock_repo.scoped_context.call_args[1]
        bbox = call_kwargs["bbox"]
        self.assertIsNotNone(bbox)
        self.assertEqual(bbox.min_longitude, -180.0)
        self.assertEqual(bbox.max_longitude, 180.0)
        self.assertEqual(bbox.min_latitude, -40.0)
        self.assertEqual(bbox.max_latitude, -30.0)
        # Non-UUID entity ID safely results in None in entity_ids list
        self.assertIsNone(call_kwargs["entity_ids"])

    @patch("app.main.generate_travel_plan")
    @patch("app.main.WorldRepository")
    def test_assistant_map_context_preserves_web_intelligence_and_urls(
        self, mock_repo_class: MagicMock, mock_travel_plan: MagicMock
    ) -> None:
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        mock_context = MagicMock()
        mock_context.model_dump.return_value = {
            "query_scope": {},
            "entities": [],
            "observations": [],
            "events": [],
            "geometries": [],
            "relationships": [],
            "claims": [],
            "evidence": [],
            "assumptions_or_limitations": [],
        }
        mock_repo.scoped_context.return_value = mock_context
        mock_travel_plan.return_value = {
            "destination": "Tokyo",
            "summary": "Overview",
            "spoken_summary": "Spoken",
            "famous_attractions": [],
            "local_food_recommendations": [],
            "days": [],
            "pro_tips": [],
            "web_intelligence": [{"platform": "web", "title": "Tokyo Guide", "url": "https://example.com/tokyo"}],
            "social_intelligence": [{"platform": "reddit", "title": "r/JapanTravel", "url": "https://reddit.com/r/JapanTravel/1"}],
            "source": "Exa + Reddit",
        }

        req = AssistantMapContextRequest(
            map_bounds=AssistantMapBounds(min_lon=139.0, min_lat=35.0, max_lon=140.0, max_lat=36.0),
        )
        res = assistant_map_context(req)
        intel = res["travel_intelligence"]
        self.assertEqual(len(intel["web_intelligence"]), 1)
        self.assertEqual(len(intel["social_intelligence"]), 1)
        self.assertEqual(
            intel["source_urls"],
            ["https://example.com/tokyo", "https://reddit.com/r/JapanTravel/1"],
        )
        self.assertEqual(intel["source"], "Exa + Reddit")

    @patch("app.main.search_web_intelligence", return_value=[])
    def test_search_intelligence_empty_reports_unavailable_status(self, mock_search: MagicMock) -> None:
        res = search_intelligence_endpoint(q="tokyo coffee", platform="auto", limit=5)
        self.assertEqual(res["status"], "unavailable_or_no_results")
        self.assertEqual(res["count"], 0)
        self.assertEqual(res["results"], [])
        self.assertTrue(isinstance(res["checked_at"], str) and len(res["checked_at"]) > 10)
        mock_search.assert_called_once_with(query="tokyo coffee", limit=5, platform="auto")

    @patch(
        "app.main.search_web_intelligence",
        return_value=[{"platform": "web", "title": "Kyoto Guide", "url": "https://example.com/kyoto"}],
    )
    def test_search_intelligence_non_empty_reports_success(self, mock_search: MagicMock) -> None:
        res = search_intelligence_endpoint(q="kyoto coffee", platform="web", limit=3)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["count"], 1)
        self.assertEqual(len(res["results"]), 1)
        mock_search.assert_called_once_with(query="kyoto coffee", limit=3, platform="web")


if __name__ == "__main__":
    unittest.main()
