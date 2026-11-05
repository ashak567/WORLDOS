"""Unit tests for WORLDOS Navigation, Road Routing, and Inbound Flight Plans."""
from __future__ import annotations

import unittest

from backend.app.navigation import (
    calculate_road_route,
    get_inbound_flight_plans,
    resolve_destination_airport,
    _fallback_road_route,
)
from backend.app.main import get_flight_plans_endpoint, get_road_route_endpoint


class NavigationTests(unittest.TestCase):
    def test_resolve_destination_airport(self) -> None:
        tokyo_apt = resolve_destination_airport("Tokyo")
        self.assertEqual(tokyo_apt.icao, "RJTT")

        paris_apt = resolve_destination_airport("Paris")
        self.assertEqual(paris_apt.icao, "LFPG")

        rome_apt = resolve_destination_airport("Rome")
        self.assertEqual(rome_apt.icao, "LIRF")

    def test_get_inbound_flight_plans(self) -> None:
        resp = get_inbound_flight_plans("Tokyo")
        self.assertEqual(resp.destination_city, "Tokyo")
        self.assertGreaterEqual(resp.total_inbound_flights, 1)
        self.assertIn("United States", resp.origin_countries)

        # Check first flight structure
        flight = resp.flights[0]
        self.assertTrue(flight.flight_number)
        self.assertTrue(flight.airline)
        self.assertTrue(flight.origin_country)
        self.assertGreater(flight.distance_km, 0)
        self.assertGreater(len(flight.waypoints_3d), 5)
        # Check 3D altitude profile (peaking above 0)
        max_alt = max(w[2] for w in flight.waypoints_3d)
        self.assertGreater(max_alt, 5000)

    def test_filter_inbound_flight_plans_by_country(self) -> None:
        resp = get_inbound_flight_plans("Tokyo", origin_country_filter="United Kingdom")
        self.assertGreaterEqual(resp.total_inbound_flights, 1)
        for f in resp.flights:
            self.assertEqual(f.origin_country, "United Kingdom")

    def test_calculate_road_route_fallback(self) -> None:
        fallback = _fallback_road_route(
            origin_lat=35.5494,
            origin_lon=139.7798,
            dest_lat=35.7148,
            dest_lon=139.7967,
            origin_name="Tokyo Haneda",
            dest_name="Sensō-ji Temple",
        )
        self.assertGreater(fallback.total_distance_km, 10.0)
        self.assertGreater(fallback.total_duration_min, 10.0)
        self.assertGreaterEqual(len(fallback.steps), 4)
        self.assertGreater(len(fallback.polyline), 10)

    def test_calculate_road_route(self) -> None:
        route = calculate_road_route(
            origin_lat=35.5494,
            origin_lon=139.7798,
            dest_lat=35.7148,
            dest_lon=139.7967,
            origin_name="Tokyo Haneda Airport",
            dest_name="Sensō-ji Temple",
        )
        self.assertGreater(route.total_distance_km, 15.0)
        self.assertGreaterEqual(len(route.steps), 4)
        self.assertGreater(len(route.polyline), 20)
        self.assertTrue(route.steps[0].instruction)

    def test_main_endpoints(self) -> None:
        # Test get_flight_plans_endpoint
        fp_resp = get_flight_plans_endpoint(destination="Tokyo")
        self.assertEqual(fp_resp.destination_city, "Tokyo")
        self.assertGreaterEqual(fp_resp.total_inbound_flights, 1)

        # Test get_road_route_endpoint
        rr_resp = get_road_route_endpoint(
            origin_lat=35.5494,
            origin_lon=139.7798,
            dest_lat=35.7148,
            dest_lon=139.7967,
            origin_name="Haneda",
            dest_name="Senso-ji",
        )
        self.assertGreater(rr_resp.total_distance_km, 15.0)
        self.assertGreaterEqual(len(rr_resp.steps), 4)


if __name__ == "__main__":
    unittest.main()
