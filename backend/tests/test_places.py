"""Unit tests for Places, Aerial View, and YouTube Tour services."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.places import (
    PlaceItem,
    YouTubeTour,
    _convert_price_level,
    _generate_fallback_places,
    _generate_fallback_youtube,
    search_places_nearby,
    search_youtube_tours,
    search_youtube_live_cam,
    get_aerial_view_video,
)
from app.main import list_cameras, get_camera_live_stream_endpoint


class PlacesServiceTests(unittest.TestCase):
    def test_convert_price_level(self) -> None:
        p4, label4 = _convert_price_level("PRICE_LEVEL_VERY_EXPENSIVE")
        self.assertEqual(p4, "$$$$")
        self.assertEqual(label4, "Ultra-Luxury")

        p3, label3 = _convert_price_level(3)
        self.assertEqual(p3, "$$$")
        self.assertEqual(label3, "Upscale")

        p2, label2 = _convert_price_level("2")
        self.assertEqual(p2, "$$")
        self.assertEqual(label2, "Moderate")

        p1, label1 = _convert_price_level(1)
        self.assertEqual(p1, "$")
        self.assertEqual(label1, "Budget")

    def test_fallback_places_generation(self) -> None:
        for cat in ["stays", "food", "scenery", "nightlife"]:
            places = _generate_fallback_places(35.6762, 139.6503, category=cat, limit=3)
            self.assertEqual(len(places), 3)
            self.assertEqual(places[0]["category"], cat)
            self.assertIn("name", places[0])
            self.assertIn("rating", places[0])
            self.assertIn("photos", places[0])
            self.assertTrue(len(places[0]["photos"]) > 0)
            self.assertIn("latitude", places[0])
            self.assertIn("longitude", places[0])

    def test_fallback_youtube_generation(self) -> None:
        tours = _generate_fallback_youtube("Aman Tokyo")
        self.assertTrue(len(tours) >= 2)
        self.assertIn("Aman Tokyo", tours[0]["title"])
        self.assertIn("https://www.youtube.com/watch?v=", tours[0]["video_url"])

    def test_search_places_with_mocked_network(self) -> None:
        # Test fallback / live query without crashing
        results = search_places_nearby(35.6762, 139.6503, category="stays", limit=2)
        self.assertTrue(len(results) >= 2)
        self.assertIn("name", results[0])
        self.assertIn("rating", results[0])

    def test_search_youtube_tours(self) -> None:
        tours = search_youtube_tours("Park Hyatt Tokyo", limit=2)
        self.assertTrue(len(tours) >= 1)
        self.assertIn("title", tours[0])
        self.assertIn("video_url", tours[0])

    def test_search_youtube_live_cam(self) -> None:
        live = search_youtube_live_cam("Shibuya Scramble Crossing Tokyo")
        self.assertIn("video_id", live)
        self.assertIn("embed_url", live)
        self.assertIn("title", live)
        self.assertTrue(live["embed_url"].startswith("https://www.youtube.com/embed/"))

    def test_list_cameras_fallback(self) -> None:
        cams = list_cameras(limit=50)
        self.assertGreaterEqual(len(cams), 20)
        self.assertIn("canonical_name", cams[0])
        self.assertIn("longitude", cams[0])
        self.assertIn("latitude", cams[0])
        self.assertIn("attributes", cams[0])
        self.assertEqual(cams[0]["truth_class"], "OBSERVED")


if __name__ == "__main__":
    unittest.main()

