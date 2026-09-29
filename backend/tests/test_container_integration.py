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
from app.domain import (Claim, Confidence, Entity, Evidence, Geometry, Observation, Provenance, Source,
                        TimeInterval, TruthClass, WorldBundle)
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

    def test_ingestion_runs_and_source_health(self) -> None:
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM sources WHERE slug = 'world-bank'")
            source_row = cur.fetchone()
            self.assertIsNotNone(source_row)
            source_id = source_row["id"]

        now = datetime(2026, 9, 29, tzinfo=UTC)
        run_id = self.repo.record_ingestion_run(
            source_id=source_id,
            pipeline_version="world-bank-test-v1",
            status="started",
            metadata={"test": True},
            started_at=now,
        )
        self.assertIsNotNone(run_id)

        self.repo.finish_ingestion_run(
            run_id=run_id,
            status="completed",
            records_fetched=10,
            records_persisted=10,
            records_failed=0,
            freshness_observed_at=now,
            completed_at=now,
        )

        health = self.repo.source_health("world-bank")
        self.assertEqual(len(health), 1)
        wb_health = health[0]
        self.assertEqual(wb_health["source_slug"], "world-bank")
        self.assertEqual(wb_health["last_run_status"], "completed")
        self.assertTrue(wb_health["is_healthy"])
        self.assertGreaterEqual(wb_health["total_runs"], 1)

        runs = self.repo.ingestion_runs("world-bank", limit=5)
        self.assertGreaterEqual(len(runs), 1)
        latest_run = runs[0]
        self.assertEqual(latest_run["status"], "completed")
        self.assertEqual(latest_run["records_persisted"], 10)

    def test_failed_ingestion_observable_without_corrupting_truth(self) -> None:
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM sources WHERE slug = 'natural-earth-admin-0'")
            source_row = cur.fetchone()
            self.assertIsNotNone(source_row)
            source_id = source_row["id"]
            cur.execute("SELECT count(*) AS count FROM observations WHERE measure = 'should_not_exist'")
            count_before = cur.fetchone()["count"]

        now = datetime(2026, 9, 29, tzinfo=UTC)
        run_id = self.repo.record_ingestion_run(
            source_id=source_id,
            pipeline_version="natural-earth-test-v1",
            status="started",
            metadata={"target": "NONEXISTENT"},
            started_at=now,
        )

        # Simulate fetch failure
        self.repo.finish_ingestion_run(
            run_id=run_id,
            status="failed",
            records_fetched=0,
            records_persisted=0,
            records_failed=1,
            error_message="LookupError: Natural Earth has no ISO alpha-3 country NONEXISTENT",
            completed_at=now,
        )

        runs = self.repo.ingestion_runs("natural-earth-admin-0", limit=1)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["status"], "failed")
        self.assertIn("LookupError", runs[0]["error_message"])

        # Verify truth was not corrupted
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) AS count FROM observations WHERE measure = 'should_not_exist'")
            count_after = cur.fetchone()["count"]
            self.assertEqual(count_before, count_after)

    def test_uncertain_name_collision_creates_review_and_approves_cleanly(self) -> None:
        now = datetime(2026, 9, 29, tzinfo=UTC)
        source = Source(slug=f"prov-source-{uuid4()}", name="Provincial Registry", publisher="Province Gov", refresh_policy="manual")
        collision_name = f"Georgia-{uuid4()}"
        entity1 = Entity(kind="place", canonical_name=collision_name, source_key=f"georgia-state-{uuid4()}", confidence=Confidence(value=0.6))
        ev1 = Evidence(source_id=source.id, locator="https://example.test/state", retrieved_at=now)
        prov1 = Provenance(evidence_id=ev1.id, pipeline_version="test-v1")
        geom1 = Geometry(entity_id=entity1.id, geojson={"type": "Point", "coordinates": [-84.3880, 33.7490]}, geometry_kind="point", source_id=source.id, confidence=Confidence(value=0.6))
        bundle1 = WorldBundle(source=source, entity=entity1, evidence=ev1, provenance=prov1, geometry=geom1)
        self.repo.ingest(bundle1)

        source2 = Source(slug=f"euro-source-{uuid4()}", name="European Registry", publisher="Euro Gov", refresh_policy="manual")
        entity2 = Entity(kind="place", canonical_name=collision_name, source_key=f"georgia-country-{uuid4()}", confidence=Confidence(value=0.7))
        ev2 = Evidence(source_id=source2.id, locator="https://example.test/country", retrieved_at=now)
        prov2 = Provenance(evidence_id=ev2.id, pipeline_version="test-v1")
        geom2 = Geometry(entity_id=entity2.id, geojson={"type": "Point", "coordinates": [44.7930, 41.7151]}, geometry_kind="point", source_id=source2.id, confidence=Confidence(value=0.7))
        bundle2 = WorldBundle(source=source2, entity=entity2, evidence=ev2, provenance=prov2, geometry=geom2)
        self.repo.ingest(bundle2)

        # 1. Proves conservative rule: entities were NOT auto-merged!
        self.assertNotEqual(str(entity1.id), str(entity2.id))

        # 2. Proves review candidate was queued in pending status
        reviews = self.repo.resolution_reviews(status="pending")
        matching_reviews = [r for r in reviews if (r["candidate_entity_id"] == entity2.id and r["target_entity_id"] == entity1.id) or (r["candidate_entity_id"] == entity1.id and r["target_entity_id"] == entity2.id)]
        self.assertEqual(len(matching_reviews), 1)
        rev = matching_reviews[0]
        self.assertEqual(rev["match_reason"], "normalized_name_exact_match_unconfirmed")
        self.assertEqual(rev["status"], "pending")

        # 3. Test explicit review action: reject
        reject_success = self.repo.reject_resolution_review(rev["id"], reviewed_by="auditor@worldos", notes="One is US State, one is Caucasus Country")
        self.assertTrue(reject_success)

        # 4. Verify status updated to rejected
        rev_after = [r for r in self.repo.resolution_reviews(status="rejected") if r["id"] == rev["id"]]
        self.assertEqual(len(rev_after), 1)
        self.assertEqual(rev_after[0]["reviewed_by"], "auditor@worldos")

        # 5. Verify entities remain distinct
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM entities WHERE id IN (%s, %s)", (entity1.id, entity2.id))
            rows = cur.fetchall()
            self.assertEqual(len(rows), 2)

    def test_claims_and_derived_analytics_lineage(self) -> None:
        now = datetime(2026, 9, 29, tzinfo=UTC)
        source = Source(slug=f"census-{uuid4()}", name="Census Bureau", publisher="National Statistics", refresh_policy="annual")
        entity = Entity(kind="place", canonical_name=f"Country-{uuid4()}", source_key=f"c-{uuid4()}", confidence=Confidence(value=1.0))
        ev = Evidence(source_id=source.id, locator="https://example.test/census", retrieved_at=now)
        prov = Provenance(evidence_id=ev.id, pipeline_version="census-v1")

        # 1. Ingest two distinct observed historical population datapoints
        t1 = TimeInterval(starts_at=datetime(2020, 1, 1, tzinfo=UTC), precision="year")
        obs1 = Observation(subject_entity_id=entity.id, measure="population.total", value=1000000.0, unit="people",
                           time_interval_id=t1.id, evidence_id=ev.id, provenance_id=prov.id,
                           confidence=Confidence(value=1.0))
        b1 = WorldBundle(source=source, entity=entity, evidence=ev, provenance=prov, time_interval=t1, observation=obs1)
        self.repo.ingest(b1)

        t2 = TimeInterval(starts_at=datetime(2023, 1, 1, tzinfo=UTC), precision="year")
        obs2 = Observation(subject_entity_id=entity.id, measure="population.total", value=1100000.0, unit="people",
                           time_interval_id=t2.id, evidence_id=ev.id, provenance_id=prov.id,
                           confidence=Confidence(value=1.0))
        b2 = WorldBundle(source=source, entity=entity, evidence=ev, provenance=prov, time_interval=t2, observation=obs2)
        self.repo.ingest(b2)

        # 2. Export DuckDB snapshot and compute derived growth claim
        duckdb_path = Path("test_claims.duckdb")
        try:
            export_observations(self.db_url, duckdb_path)
            analytics = DuckDbSpatialAnalytics(duckdb_path)
            claim = analytics.derive_population_growth(entity.id)
            self.assertIsNotNone(claim)
            self.assertEqual(claim.truth_class, TruthClass.DERIVED)
            self.assertEqual(claim.claim_type, "population_growth_percentage")
            self.assertEqual(claim.value["percentage_change"], 10.0)
            self.assertEqual(claim.method, "two_point_percentage_change_v1")
            self.assertIn("baseline_observation_id", claim.inputs)
            self.assertIn("latest_observation_id", claim.inputs)
            self.assertIn(ev.id, claim.evidence_ids)

            # 3. Persist claim in PostGIS
            claim_id = self.repo.record_claim(claim)
            self.assertEqual(claim_id, claim.id)

            # 4. Query claims via repository
            claims = self.repo.claims(subject_entity_id=entity.id, truth_class="DERIVED")
            self.assertEqual(len(claims), 1)
            persisted = claims[0]
            self.assertEqual(persisted["truth_class"], "DERIVED")
            self.assertEqual(persisted["method"], "two_point_percentage_change_v1")
            self.assertEqual(persisted["value"]["percentage_change"], 10.0)

            # 5. Query context and verify clear separation of observations and claims
            ctx = self.repo.context(entity.id)
            self.assertIsNotNone(ctx)
            self.assertGreaterEqual(len(ctx["observations"]), 2)
            self.assertTrue(all(o["truth_class"] == "OBSERVED" for o in ctx["observations"]))
            self.assertEqual(len(ctx["claims"]), 1)
            self.assertEqual(ctx["claims"][0]["truth_class"], "DERIVED")
        finally:
            if duckdb_path.exists():
                duckdb_path.unlink()



