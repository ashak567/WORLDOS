"""Unit tests for WORLDOS Navigation, Road Routing, and Inbound Flight Plans."""
from __future__ import annotations

import unittest

from backend.app.navigation import (
    calculate_road_route,
    geocode_location,
    get_inbound_flight_plans,
    list_airports,
    resolve_airport,
    resolve_destination_airport,
    resolve_location_coordinates,
    _fallback_road_route,
)
from backend.app.main import (
    geocode_endpoint,
    get_flight_plans_endpoint,
    get_road_route_endpoint,
    list_airports_endpoint,
)


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

    def test_list_and_resolve_airports(self) -> None:
        # Default top airports
        top_apts = list_airports("", limit=10)
        self.assertGreaterEqual(len(top_apts), 5)
        top_iatas = [a.iata for a in top_apts]
        self.assertIn("HND", top_iatas)
        self.assertIn("JFK", top_iatas)

        # Search by code or city
        del_apts = list_airports("Delhi")
        self.assertGreaterEqual(len(del_apts), 1)
        self.assertEqual(del_apts[0].iata, "DEL")

        # Resolve airport
        del_apt = resolve_airport("DEL")
        self.assertIsNotNone(del_apt)
        self.assertEqual(del_apt.icao, "VIDP")

        hnd_apt = resolve_airport("Tokyo")
        self.assertIsNotNone(hnd_apt)
        self.assertEqual(hnd_apt.iata, "HND")

    def test_custom_corridor_flight_plans(self) -> None:
        # Custom pair: DEL to HND
        resp = get_inbound_flight_plans(destination="HND", origin="DEL")
        self.assertGreaterEqual(resp.total_inbound_flights, 4)
        airlines = [f.airline for f in resp.flights]
        self.assertIn("Air India", airlines)
        self.assertIn("Emirates", airlines)

        for f in resp.flights:
            self.assertEqual(f.origin_airport.iata, "DEL")
            self.assertEqual(f.destination_airport.iata, "HND")
            self.assertGreater(f.distance_km, 5000.0)
            self.assertGreater(len(f.waypoints_3d), 10)

        # Custom pair: JFK to LHR
        jfk_lhr = get_inbound_flight_plans(destination="LHR", origin="JFK")
        self.assertGreaterEqual(jfk_lhr.total_inbound_flights, 4)
        for f in jfk_lhr.flights:
            self.assertEqual(f.origin_airport.iata, "JFK")
            self.assertEqual(f.destination_airport.iata, "LHR")

    def test_expanded_inbound_flights(self) -> None:
        # Inbound flights to Tokyo should now be >= 30 across 20+ countries
        resp = get_inbound_flight_plans("Tokyo")
        self.assertGreaterEqual(resp.total_inbound_flights, 30)
        self.assertGreaterEqual(len(resp.origin_countries), 15)

    def test_main_endpoints(self) -> None:
        # Test list_airports_endpoint
        apts = list_airports_endpoint(query="Dubai")
        self.assertGreaterEqual(len(apts), 1)
        self.assertEqual(apts[0].iata, "DXB")

        # Test get_flight_plans_endpoint with custom origin
        custom_fp = get_flight_plans_endpoint(destination="HND", origin="DEL")
        self.assertGreaterEqual(custom_fp.total_inbound_flights, 4)
        self.assertEqual(custom_fp.flights[0].origin_airport.iata, "DEL")

        # Test get_flight_plans_endpoint worldwide inbound
        fp_resp = get_flight_plans_endpoint(destination="Tokyo")
        self.assertEqual(fp_resp.destination_city, "Tokyo")
        self.assertGreaterEqual(fp_resp.total_inbound_flights, 30)

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

        # Test geocode_endpoint
        geo = geocode_endpoint(query="Eiffel Tower")
        self.assertAlmostEqual(geo.latitude, 48.8584, delta=0.1)
        self.assertAlmostEqual(geo.longitude, 2.2945, delta=0.1)

    def test_road_route_auto_resolution_different_cities(self) -> None:
        # Paris route: even if passed Tokyo coordinates, auto-resolves to Paris!
        paris_route = calculate_road_route(
            origin_lat=35.5494,
            origin_lon=139.7798,
            dest_lat=35.7148,
            dest_lon=139.7967,
            origin_name="Charles de Gaulle (CDG)",
            dest_name="Eiffel Tower",
        )
        self.assertAlmostEqual(paris_route.origin_coords[1], 49.0097, delta=0.1) # Paris lat
        self.assertAlmostEqual(paris_route.destination_coords[1], 48.8584, delta=0.1) # Eiffel lat
        self.assertGreater(paris_route.total_distance_km, 25.0)

        # Rome route: should have distinct coordinates in Rome (~41.9° N, 12.5° E)
        rome_route = calculate_road_route(
            origin_lat=35.5494,
            origin_lon=139.7798,
            dest_lat=35.7148,
            dest_lon=139.7967,
            origin_name="Rome",
            dest_name="Colosseum",
        )
        self.assertAlmostEqual(rome_route.origin_coords[1], 41.9028, delta=0.2)
        self.assertAlmostEqual(rome_route.destination_coords[1], 41.8902, delta=0.2)
        # Distance between Rome center and Colosseum is ~2-3 km, NOT 25 km!
        self.assertLess(rome_route.total_distance_km, 10.0)

        # Cross-country Paris to Berlin: ~1000 km
        europe_route = calculate_road_route(
            origin_lat=0,
            origin_lon=0,
            dest_lat=0,
            dest_lon=0,
            origin_name="Paris",
            dest_name="Berlin",
        )
        self.assertGreater(europe_route.total_distance_km, 800.0)


if __name__ == "__main__":
    unittest.main()
