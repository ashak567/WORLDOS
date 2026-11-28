from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.main import geocode_endpoint
from app.navigation import _fallback_road_route, geocode_location, resolve_location_coordinates
from app.places import _convert_price_level, _generate_fallback_places


class Nov28RegressionTests(unittest.TestCase):
    @patch("urllib.request.urlopen", side_effect=OSError("offline"))
    def test_unknown_geocode_raises_value_error_and_http_404(self, _mock_urlopen) -> None:
        with self.assertRaises(ValueError):
            geocode_location("ZzzUnknownPlace99999")

        with self.assertRaises(HTTPException) as ctx:
            geocode_endpoint(query="ZzzUnknownPlace99999")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_country_resolution_does_not_collide_with_airport_substrings(self) -> None:
        india = resolve_location_coordinates("India")
        self.assertIsNotNone(india)
        lat_in, lon_in, name_in = india  # type: ignore[misc]
        self.assertIn("India", name_in)
        self.assertNotIn("Indianapolis", name_in)
        self.assertTrue(6.0 < lat_in < 38.0 and 68.0 < lon_in < 98.0)

        france = resolve_location_coordinates("France")
        self.assertIsNotNone(france)
        lat_fr, lon_fr, name_fr = france  # type: ignore[misc]
        self.assertIn("France", name_fr)
        self.assertTrue(41.0 < lat_fr < 52.0 and -5.0 < lon_fr < 10.0)

        japan = resolve_location_coordinates("Japan")
        self.assertIsNotNone(japan)
        lat_jp, lon_jp, name_jp = japan  # type: ignore[misc]
        self.assertIn("Japan", name_jp)
        self.assertTrue(24.0 < lat_jp < 46.0 and 122.0 < lon_jp < 146.0)

    def test_fallback_road_route_is_explicitly_estimated(self) -> None:
        route = _fallback_road_route(35.68, 139.75, 35.71, 139.79, "Origin A", "Dest B")
        self.assertTrue(route.is_estimated)
        self.assertEqual(route.routing_provider, "unavailable_straight_line_estimate")
        self.assertTrue(
            (route.external_directions_url or "").startswith("https://www.openstreetmap.org/directions")
        )
        self.assertTrue(bool(route.limitation_note))

    def test_fallback_places_are_unverified_and_unknown_price_is_none(self) -> None:
        fallback = _generate_fallback_places(35.68, 139.75, "stays", 3)
        self.assertGreater(len(fallback), 0)
        for item in fallback:
            self.assertFalse(item.get("verified"))

        self.assertEqual(_convert_price_level(None), (None, None))
        self.assertEqual(_convert_price_level("PRICE_LEVEL_UNKNOWN"), (None, None))


if __name__ == "__main__":
    unittest.main()
