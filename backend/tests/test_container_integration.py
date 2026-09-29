"""Container-backed integration tests verifying PostGIS truth, fusion, and DuckDB analytics."""
from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
import unittest
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from app.analytics import DuckDbSpatialAnalytics
from app.domain import Confidence, Entity, Evidence, Geometry, Observation, Provenance, Source, TimeInterval, WorldBundle
from app.export import export_observations
from app.ingestion.natural_earth import parse_country_boundary
from app.ingestion.usgs import parse_earthquake_feature
from app.ingestion.world_bank import parse_population
from app.main import natural_earth_bundle, usgs_earthquake_bundle, world_bank_bundle
from app.storage import WorldRepository


class ContainerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.db_url = os.environ.get(
            "WORLDOS_DATABASE_URL",
            "postgresql://worldos:worldos_dev_only@localhost:5432/worldos",
        )
        try:
            with psycopg.connect(cls.db_url) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
        except Exception as err:
            raise unittest.SkipTest(f"PostGIS database not available at {cls.db_url}: {err}")
        cls.repo = WorldRepository(cls.db_url)

    def test_reconciliation_of_world_bank_and_natural_earth(self) -> None:
        now = datetime(2026, 9, 29, tzinfo=UTC)
        wb_payload = [{"page": 1}, [{
            "countryiso3code": "IND", "country": {"value": "India"}, "date": "2023", "value": 1428627663,
        }]]
        record = parse_population(wb_payload, "https://api.worldbank.org/test/ind")[0]
        wb_bundle = world_bank_bundle(record, None, now)
        self.repo.ingest(wb_bundle)

        ne_payload = {"type": "FeatureCollection", "features": [{
            "type": "Feature", "properties": {"ISO_A3": "IND", "NAME": "India"},
            "geometry": {"type": "Polygon", "coordinates": [[[68.0, 8.0], [97.0, 8.0], [97.0, 35.0], [68.0, 35.0], [68.0, 8.0]]]},
        }]}
        boundary = parse_country_boundary(ne_payload, "IND", "https://example.test/ne.geojson")
        ne_bundle = natural_earth_bundle(boundary, now)
        self.repo.ingest(ne_bundle)

        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT e.id, e.canonical_name, count(DISTINCT g.id) AS geom_count, count(DISTINCT o.id) AS obs_count
                FROM entities e
                JOIN entity_identifiers ei ON ei.entity_id = e.id
                LEFT JOIN geometries g ON g.entity_id = e.id
                LEFT JOIN observations o ON o.subject_entity_id = e.id
                WHERE ei.scheme = 'iso_3166_1_alpha_3' AND ei.value = 'IND'
                GROUP BY e.id, e.canonical_name
            """)
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["canonical_name"], "India")
            self.assertGreaterEqual(row["geom_count"], 1)
            self.assertGreaterEqual(row["obs_count"], 1)

    def test_no_false_merge_on_name_collision_without_publisher_id(self) -> None:
        now = datetime(2026, 9, 29, tzinfo=UTC)
        source = Source(slug=f"custom-source-{uuid4()}", name="Unrelated Publisher", publisher="Third Party", refresh_policy="manual")
        entity = Entity(kind="place", canonical_name="India", source_key=f"unrelated-key-{uuid4()}", confidence=Confidence(value=0.5))
        evidence = Evidence(source_id=source.id, locator="https://example.test/unrelated", retrieved_at=now)
        provenance = Provenance(evidence_id=evidence.id, pipeline_version="test-v1")
        geometry = Geometry(entity_id=entity.id, geojson={"type": "Point", "coordinates": [0.0, 0.0]}, geometry_kind="test_point", source_id=source.id, confidence=Confidence(value=0.5))
        bundle = WorldBundle(source=source, entity=entity, evidence=evidence, provenance=provenance, geometry=geometry)

        unrelated_entity_id = self.repo.ingest(bundle)

        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT entity_id FROM entity_identifiers WHERE scheme='iso_3166_1_alpha_3' AND value='IND'")
            canonical_ind = cur.fetchone()
            self.assertIsNotNone(canonical_ind)
            self.assertNotEqual(str(unrelated_entity_id), str(canonical_ind["entity_id"]))

    def test_postgis_polygon_containment_and_near_queries(self) -> None:
        containing = self.repo.find_containing_entity(139.6917, 35.6895)
        self.assertIsNotNone(containing)
        self.assertEqual(containing["canonical_name"], "Japan")

        not_containing = self.repo.find_containing_entity(-120.0, -50.0)
        self.assertIsNone(not_containing)

        nearby = self.repo.near(139.6917, 35.6895, radius_km=50.0)
        self.assertTrue(any(e["canonical_name"] == "Japan" and e["distance_km"] < 1.0 for e in nearby))
        japan_entries = [e for e in nearby if e["canonical_name"] == "Japan"]
        self.assertEqual(len(japan_entries), 1)

    def test_duckdb_snapshot_export_and_analytics(self) -> None:
        export_file = Path("test_snapshot.duckdb")
        try:
            exported_count = export_observations(self.db_url, export_file)
            self.assertGreater(exported_count, 0)
            self.assertTrue(export_file.exists())

            analytics = DuckDbSpatialAnalytics(export_file)
            with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
                cur.execute("SELECT entity_id FROM entity_identifiers WHERE scheme='iso_3166_1_alpha_3' AND value='IND'")
                ind_id = cur.fetchone()["entity_id"]

            series = analytics.population_series(str(ind_id))
            self.assertGreater(len(series), 0)
            starts_at, val = series[0]
            self.assertIsInstance(val, float)
            self.assertGreater(val, 1_000_000_000)
        finally:
            if export_file.exists():
                export_file.unlink()

    def test_usgs_earthquake_ingestion_and_spatial_relationship(self) -> None:
        now = datetime(2026, 9, 29, tzinfo=UTC)
        feature = {
            "type": "Feature",
            "id": "us6000m0xm",
            "properties": {
                "mag": 6.2,
                "place": "8 km SW of Anamizu, Japan",
                "time": 1704093521584,
                "code": "6000m0xm",
                "title": "M 6.2 - 8 km SW of Anamizu, Japan",
            },
            "geometry": {
                "type": "Point",
                "coordinates": [136.8272, 37.1895, 10.0],
            },
        }
        record = parse_earthquake_feature(feature, "https://earthquake.usgs.gov/test/us6000m0xm", "testhash")

        containing_country = self.repo.find_containing_entity(record.longitude, record.latitude)
        self.assertIsNotNone(containing_country)
        self.assertEqual(containing_country["canonical_name"], "Japan")

        bundle = usgs_earthquake_bundle(record, now, containing_entity_id=containing_country["id"])
        self.repo.ingest(bundle)

        events = self.repo.events(kind="earthquake")
        matching = [e for e in events if e["subject_name"] == record.title]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["evidence_locator"], record.locator)

        japan_ctx = self.repo.context(containing_country["id"])
        self.assertIsNotNone(japan_ctx)
        incoming_rels = [r for r in japan_ctx.get("relationships", []) if r["predicate"] == "occurred_in"]
        self.assertGreater(len(incoming_rels), 0)
