"""Unit tests for WORLDOS multi-domain intelligence ingestion adapters.

Tests:
- Maritime AIS vessel state vector ingestion and canonical WorldBundle normalization.
- Active satellite orbital elements, ground tracks, and DERIVED truth classification in provenance.
- Public observation camera infrastructure, snapshot URLs, and attributes.
- NASA FIRMS thermal anomaly detection and fire event normalization.
- Strategic critical infrastructure node normalization (airports, ports, spaceports).
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.ingestion.cameras import (
    camera_to_world_bundle,
    load_authoritative_cameras,
)
from app.ingestion.fires import (
    load_authoritative_thermal_anomalies,
    thermal_anomaly_to_world_bundle,
)
from app.ingestion.infrastructure import (
    infrastructure_to_world_bundle,
    load_authoritative_infrastructure,
)
from app.ingestion.maritime import (
    load_sample_vessels,
    maritime_vessel_bundle,
)
from app.ingestion.satellites import (
    generate_orbital_ground_track,
    load_authoritative_satellites,
    satellite_to_world_bundle,
)


class MultiDomainIngestionTests(unittest.TestCase):
    """Test suite for multi-domain intelligence ingestion."""

    def setUp(self) -> None:
        self.now = datetime.now(timezone.utc)

    def test_maritime_vessels_normalization(self) -> None:
        """Verify AIS vessel state normalization and canonical bundle construction."""
        vessels = load_sample_vessels()
        self.assertGreater(len(vessels), 0)

        first = vessels[0]
        self.assertTrue(first.mmsi)
        self.assertTrue(first.name)
        self.assertIsInstance(first.latitude, float)
        self.assertIsInstance(first.longitude, float)

        bundles = [maritime_vessel_bundle(v, self.now) for v in vessels]
        self.assertEqual(len(bundles), len(vessels))
        for bundle in bundles:
            self.assertEqual(bundle.entity.kind, "asset")
            self.assertEqual(bundle.source.slug, "worldos-sample-vessels")
            self.assertEqual(bundle.observation.attributes["truth_class"], "SIMULATED")
            self.assertIn("mmsi", bundle.entity.attributes)
            self.assertIn("sog_knots", bundle.observation.attributes)
            self.assertEqual(bundle.geometry.geojson["type"], "Point")

    def test_satellite_orbital_propagation(self) -> None:
        """Verify satellite orbital elements produce DERIVED truth classifications and ground tracks."""
        sats = load_authoritative_satellites(now=self.now)
        self.assertGreater(len(sats), 0)

        for sat in sats:
            self.assertGreaterEqual(sat.current_lat, -90.0)
            self.assertLessEqual(sat.current_lat, 90.0)
            self.assertGreaterEqual(sat.current_lon, -180.0)
            self.assertLessEqual(sat.current_lon, 180.0)
            self.assertGreater(sat.current_alt_km, 100.0)
            self.assertGreater(len(sat.ground_track), 10)

        track = generate_orbital_ground_track(51.64, 10.0, 20.0, 92.9, num_points=72)
        self.assertEqual(len(track), 73)

        bundles = [satellite_to_world_bundle(s, self.now) for s in sats]
        self.assertEqual(len(bundles), len(sats))
        for bundle in bundles:
            self.assertEqual(bundle.entity.kind, "asset")
            self.assertEqual(bundle.observation.truth_class, "OBSERVED")
            self.assertEqual(bundle.provenance.transformation["truth_class"], "DERIVED")
            self.assertEqual(bundle.observation.attributes["derivation_class"], "DERIVED")
            self.assertEqual(
                bundle.observation.attributes["calculation_method"],
                "kepler_sgp4_orbit_propagation",
            )
            self.assertIn("ground_track", bundle.observation.attributes)

    def test_cameras_normalization(self) -> None:
        """Verify public observation camera metadata and snapshot URL normalization."""
        cams = load_authoritative_cameras(now=self.now)
        self.assertGreater(len(cams), 0)

        bundles = [camera_to_world_bundle(c, self.now) for c in cams]
        self.assertEqual(len(bundles), len(cams))
        for bundle in bundles:
            self.assertEqual(bundle.entity.kind, "asset")
            self.assertEqual(bundle.observation.truth_class, "OBSERVED")
            self.assertTrue(bundle.observation.attributes.get("snapshot_url"))
            self.assertEqual(bundle.geometry.geojson["type"], "Point")

    def test_thermal_anomalies_normalization(self) -> None:
        """Verify NASA FIRMS thermal anomaly detection and fire event normalization."""
        fires = load_authoritative_thermal_anomalies(now=self.now)
        self.assertGreater(len(fires), 0)

        bundles = [thermal_anomaly_to_world_bundle(f, self.now) for f in fires]
        self.assertEqual(len(bundles), len(fires))
        for bundle in bundles:
            self.assertEqual(bundle.observation.truth_class, "OBSERVED")
            self.assertGreater(bundle.observation.attributes["frp_mw"], 0.0)
            self.assertIn("brightness_kelvin", bundle.observation.attributes)

    def test_strategic_infrastructure_normalization(self) -> None:
        """Verify airports, deep-water ports, and spaceports canonical entity mapping."""
        nodes = load_authoritative_infrastructure(now=self.now)
        self.assertGreaterEqual(len(nodes), 15)

        categories = {n.node_type for n in nodes}
        self.assertIn("airport", categories)
        self.assertIn("port", categories)
        self.assertIn("spaceport", categories)

        bundles = [infrastructure_to_world_bundle(n, self.now) for n in nodes]
        self.assertEqual(len(bundles), len(nodes))
        for bundle in bundles:
            self.assertEqual(bundle.entity.kind, "place")
            self.assertEqual(bundle.observation.truth_class, "OBSERVED")
            self.assertIn("capabilities", bundle.entity.attributes)


if __name__ == "__main__":
    unittest.main()
