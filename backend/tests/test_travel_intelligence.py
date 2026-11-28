"""Unit tests for Live Internet Travel Intelligence & Itinerary Engine."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.travel_intelligence import (
    fetch_wikipedia_summary,
    generate_travel_plan,
    resolve_destination_from_coords,
)


class TravelIntelligenceTests(unittest.TestCase):
    def test_resolve_destination_from_coords(self) -> None:
        # Near Tokyo
        tokyo = resolve_destination_from_coords(35.68, 139.75)
        self.assertEqual(tokyo, "Tokyo")

        # Near Paris
        paris = resolve_destination_from_coords(48.86, 2.34)
        self.assertEqual(paris, "Paris")

        # Near New York
        nyc = resolve_destination_from_coords(40.71, -74.01)
        self.assertEqual(nyc, "New York")

    def test_generate_travel_plan_curated_and_live(self) -> None:
        with (
            patch("app.travel_intelligence.fetch_google_places_internet", return_value=[]),
            patch("app.travel_intelligence.fetch_wikipedia_summary", return_value=None),
            patch("app.travel_intelligence.search_web_intelligence", return_value=[]),
            patch("app.travel_intelligence.search_reddit_intelligence", return_value=[]),
        ):
            plan = generate_travel_plan("Tokyo", days=3, pace="balanced")
        self.assertEqual(plan["status"], "success")
        self.assertEqual(plan["destination"], "Tokyo")
        self.assertGreaterEqual(len(plan["days"]), 3)
        self.assertTrue(len(plan["famous_attractions"]) > 0)
        self.assertTrue(len(plan["local_food_recommendations"]) > 0)
        self.assertTrue(
            any("Sensō-ji" in a["name"] for a in plan["famous_attractions"]),
            f"Expected Sensō-ji in attractions: {plan['famous_attractions']}",
        )
        self.assertFalse(plan.get("has_verified_places", True))
        self.assertTrue(len(plan["spoken_summary"]) > 50)
        self.assertEqual(len(plan["center"]), 2)

    def test_generate_travel_plan_dynamic_city(self) -> None:
        rome_sights = [
            {
                "name": "Colosseum",
                "summary": "Ancient Roman amphitheatre",
                "lat": 41.8902,
                "lon": 12.4922,
                "rating": 4.7,
                "user_rating_count": 300000,
                "address": "Piazza del Colosseo, Rome",
                "photos": [],
            }
        ]
        with (
            patch("app.travel_intelligence.fetch_google_places_internet", side_effect=[rome_sights, []]),
            patch("app.travel_intelligence.fetch_wikipedia_summary", return_value=None),
            patch("app.travel_intelligence.search_web_intelligence", return_value=[]),
            patch("app.travel_intelligence.search_reddit_intelligence", return_value=[]),
        ):
            plan = generate_travel_plan("Rome", days=2)
        self.assertEqual(plan["status"], "success")
        self.assertEqual(plan["destination"], "Rome")
        self.assertEqual(len(plan["days"]), 2)
        self.assertTrue(plan.get("has_verified_places"))
        self.assertTrue(len(plan["famous_attractions"]) > 0)

    def test_wikipedia_summary_fallback(self) -> None:
        summary = fetch_wikipedia_summary("Kyoto")
        if summary:
            self.assertIn("Kyoto", summary["title"])
            self.assertTrue(len(summary["summary"]) > 10)

    def test_generate_travel_plan_does_not_fabricate_ratings_when_offline_or_unrated(self) -> None:
        with (
            patch("app.travel_intelligence._get_api_key", return_value=None),
            patch("app.travel_intelligence.fetch_google_places_internet", return_value=[]),
            patch("app.travel_intelligence.fetch_wikipedia_summary", return_value=None),
            patch("app.travel_intelligence.search_web_intelligence", return_value=[]),
            patch("app.travel_intelligence.search_reddit_intelligence", return_value=[]),
        ):
            offline_plan = generate_travel_plan("Reykjavik", days=2)

        self.assertFalse(offline_plan.get("has_verified_places", True))
        self.assertEqual(offline_plan.get("famous_attractions"), [])
        for day in offline_plan.get("days", []):
            for act in day.get("activities", []):
                self.assertIsNone(act.get("rating"))

        unrated_places = [
            {
                "name": "Hallgrimskirkja Area",
                "summary": "Landmark district",
                "lat": 64.1417,
                "lon": -21.9266,
                "rating": None,
                "user_rating_count": None,
                "address": "Reykjavik",
                "photos": [],
            }
        ]
        with (
            patch("app.travel_intelligence._get_api_key", return_value=None),
            patch("app.travel_intelligence.fetch_google_places_internet", side_effect=[unrated_places, []]),
            patch("app.travel_intelligence.fetch_wikipedia_summary", return_value=None),
            patch("app.travel_intelligence.search_web_intelligence", return_value=[]),
            patch("app.travel_intelligence.search_reddit_intelligence", return_value=[]),
        ):
            unrated_plan = generate_travel_plan("Reykjavik", days=2)

        self.assertTrue(unrated_plan.get("has_verified_places"))
        for item in unrated_plan.get("famous_attractions", []):
            self.assertIsNone(item.get("rating"))
        for item in unrated_plan.get("local_food_recommendations", []):
            self.assertIsNone(item.get("rating"))
        for day in unrated_plan.get("days", []):
            for act in day.get("activities", []):
                self.assertIsNone(act.get("rating"))


if __name__ == "__main__":
    unittest.main()

