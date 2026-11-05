"""Unit tests for Live Internet Travel Intelligence & Itinerary Engine."""
from __future__ import annotations

import unittest

from app.travel_intelligence import (
    generate_travel_plan,
    resolve_destination_from_coords,
    fetch_wikipedia_summary,
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
        plan = generate_travel_plan("Tokyo", days=3, pace="balanced")
        self.assertEqual(plan["status"], "success")
        self.assertEqual(plan["destination"], "Tokyo")
        self.assertGreaterEqual(len(plan["days"]), 3)
        self.assertTrue(len(plan["famous_attractions"]) > 0)
        self.assertTrue(len(plan["local_food_recommendations"]) > 0)
        self.assertIn("Sensō-ji", [a["name"] for a in plan["famous_attractions"]] + [plan["days"][0]["activities"][0]["title"]])
        self.assertTrue(len(plan["spoken_summary"]) > 50)
        self.assertEqual(len(plan["center"]), 2)

    def test_generate_travel_plan_dynamic_city(self) -> None:
        plan = generate_travel_plan("Rome", days=2)
        self.assertEqual(plan["status"], "success")
        self.assertEqual(plan["destination"], "Rome")
        self.assertEqual(len(plan["days"]), 2)
        self.assertTrue(len(plan["famous_attractions"]) > 0)

    def test_wikipedia_summary_fallback(self) -> None:
        summary = fetch_wikipedia_summary("Kyoto")
        if summary:
            self.assertIn("Kyoto", summary["title"])
            self.assertTrue(len(summary["summary"]) > 10)


if __name__ == "__main__":
    unittest.main()

