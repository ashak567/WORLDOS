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
from app.benchmarks import AnalyticalBenchmarkSuite
from app.domain import (
    BoundingBox,
    Claim,
    Confidence,
    ConstraintCategory,
    ConstraintFinding,
    ConstraintSeverity,
    ConstraintStatus,
    ConstraintValidationResult,
    Entity,
    Evidence,
    Geometry,
    Observation,
    Provenance,
    Relationship,
    ScenarioProposal,
    SnapshotManifest,
    Source,
    TimeInterval,
    TruthClass,
    WorldBundle,
    WorldContext,
)
from app.constraints import ConstraintEngine, ConstraintViolationError
from app.export import export_observations
from app.ingestion.natural_earth import parse_country_boundary
from app.ingestion.usgs import parse_earthquake_feature
from app.ingestion.world_bank import parse_population
from app.main import (
    ValidationRequest,
    compare_spatial_slices_endpoint,
    coverage_summary_endpoint,
    export_snapshot_endpoint,
    get_snapshot_endpoint,
    list_constraint_rules,
    list_snapshots_endpoint,
    natural_earth_bundle,
    run_benchmarks_endpoint,
    spatial_rollups_endpoint,
    temporal_rollups_endpoint,
    usgs_earthquake_bundle,
    validate_constraints_endpoint,
    validate_snapshot_endpoint,
    world_bank_bundle,
)
from app.snapshots import SnapshotCatalog, SnapshotManager
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

    def test_temporal_point_in_time_and_interval_overlap_queries(self) -> None:
        now = datetime(2026, 9, 29, tzinfo=UTC)
        source = Source(slug=f"temporal-src-{uuid4()}", name="Temporal Source", publisher="Temporal Bureau", refresh_policy="annual")
        entity = Entity(kind="place", canonical_name=f"TemporalEntity-{uuid4()}", confidence=Confidence(value=1.0))
        ev = Evidence(source_id=source.id, locator="https://example.test/temporal-indicator", retrieved_at=now)
        prov = Provenance(evidence_id=ev.id, pipeline_version="temporal-v1")

        # 1. Ingest year-precision observation spanning 2023-01-01 to 2023-12-31
        t_year = TimeInterval(
            starts_at=datetime(2023, 1, 1, tzinfo=UTC),
            ends_at=datetime(2023, 12, 31, 23, 59, 59, tzinfo=UTC),
            precision="year",
        )
        obs_year = Observation(
            subject_entity_id=entity.id,
            measure="gdp.nominal",
            value=500000.0,
            unit="usd",
            time_interval_id=t_year.id,
            evidence_id=ev.id,
            provenance_id=prov.id,
            confidence=Confidence(value=1.0),
        )
        bundle = WorldBundle(source=source, entity=entity, evidence=ev, provenance=prov, time_interval=t_year, observation=obs_year)
        self.repo.ingest(bundle)

        # 2. Query valid_at mid-year (2023-06-15) -> must match year observation
        mid_year = datetime(2023, 6, 15, 12, 0, 0, tzinfo=UTC)
        matched = self.repo.observations(measure="gdp.nominal", valid_at=mid_year, entity_id=entity.id)
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["precision"], "year")
        self.assertEqual(matched[0]["evidence_locator"], "https://example.test/temporal-indicator")
        self.assertEqual(matched[0]["source_slug"], source.slug)

        # 3. Query valid_at next year (2024-01-01) -> must NOT match
        next_year = datetime(2024, 1, 1, 0, 0, 1, tzinfo=UTC)
        unmatched = self.repo.observations(measure="gdp.nominal", valid_at=next_year, entity_id=entity.id)
        self.assertEqual(len(unmatched), 0)

        # 4. Query interval overlap: [2023-11-01, 2024-02-01] overlaps [2023-01-01, 2023-12-31]
        overlap_res = self.repo.observations(
            measure="gdp.nominal",
            start=datetime(2023, 11, 1, tzinfo=UTC),
            end=datetime(2024, 2, 1, tzinfo=UTC),
            entity_id=entity.id,
        )
        self.assertEqual(len(overlap_res), 1)

        # 5. Query disjoint interval: [2021-01-01, 2022-12-31] -> must NOT match
        disjoint_res = self.repo.observations(
            measure="gdp.nominal",
            start=datetime(2021, 1, 1, tzinfo=UTC),
            end=datetime(2022, 12, 31, tzinfo=UTC),
            entity_id=entity.id,
        )
        self.assertEqual(len(disjoint_res), 0)

        # 6. Query with precision filter
        by_precision = self.repo.observations(measure="gdp.nominal", precision="year", entity_id=entity.id)
        self.assertEqual(len(by_precision), 1)
        by_wrong_precision = self.repo.observations(measure="gdp.nominal", precision="day", entity_id=entity.id)
        self.assertEqual(len(by_wrong_precision), 0)

    def test_spatial_containment_and_intersections_with_evidence(self) -> None:
        # 1. Point containment query: New Delhi (77.2090, 28.6139) inside India boundary polygon
        containing = self.repo.containing_geometries(77.2090, 28.6139)
        self.assertGreaterEqual(len(containing), 1)
        india_match = next((g for g in containing if g["canonical_name"] == "India"), None)
        self.assertIsNotNone(india_match)
        self.assertEqual(india_match["geometry_kind"], "country_boundary")
        self.assertEqual(india_match["confidence"], 1.0)
        self.assertEqual(india_match["source_slug"], "natural-earth-admin-0")
        self.assertIsNotNone(india_match["evidence_locator"])

        # 2. Point containment query in ocean -> returns empty
        ocean = self.repo.containing_geometries(-120.0, -50.0)
        self.assertEqual(len(ocean), 0)

        # 3. Spatial intersection between earthquake and country boundary
        now = datetime(2026, 9, 29, tzinfo=UTC)
        source = Source(slug=f"quake-test-{uuid4()}", name="Test Quake", publisher="Test Seismology", refresh_policy="manual")
        quake_entity = Entity(kind="asset", canonical_name="Test Quake In India", confidence=Confidence(value=1.0))
        ev = Evidence(source_id=source.id, locator="https://example.test/quake-in-india", retrieved_at=now)
        prov = Provenance(evidence_id=ev.id, pipeline_version="test-v1")
        quake_geom = Geometry(
            entity_id=quake_entity.id,
            geojson={"type": "Point", "coordinates": [77.2090, 28.6139]},
            geometry_kind="epicenter",
            source_id=source.id,
            evidence_id=ev.id,
            confidence=Confidence(value=1.0),
        )
        bundle = WorldBundle(source=source, entity=quake_entity, evidence=ev, provenance=prov, geometry=quake_geom)
        self.repo.ingest(bundle)

        intersections = self.repo.spatial_intersections(quake_entity.id)
        self.assertGreaterEqual(len(intersections), 1)
        target_india = next((item for item in intersections if item["target_name"] == "India"), None)
        self.assertIsNotNone(target_india)
        self.assertTrue(target_india["intersects"])
        self.assertTrue(target_india["target_contains_source"])
        self.assertEqual(target_india["target_geometry_kind"], "country_boundary")

    def test_relationship_predicates_and_graph_traversal(self) -> None:
        now = datetime(2026, 9, 29, tzinfo=UTC)
        source = Source(slug=f"geo-hierarchy-{uuid4()}", name="Geo Hierarchy", publisher="Cartographic Authority", refresh_policy="manual")
        ev = Evidence(source_id=source.id, locator="https://example.test/hierarchy", retrieved_at=now)
        prov = Provenance(evidence_id=ev.id, pipeline_version="geo-v1")

        country = Entity(kind="place", canonical_name=f"Country-{uuid4()}", confidence=Confidence(value=1.0))
        state = Entity(kind="place", canonical_name=f"State-{uuid4()}", confidence=Confidence(value=1.0))
        city = Entity(kind="place", canonical_name=f"City-{uuid4()}", confidence=Confidence(value=1.0))

        # Ingest entities with point geometries
        g_c = Geometry(entity_id=country.id, geojson={"type": "Point", "coordinates": [10.0, 10.0]}, geometry_kind="point", source_id=source.id, confidence=Confidence(value=1.0))
        g_s = Geometry(entity_id=state.id, geojson={"type": "Point", "coordinates": [10.1, 10.1]}, geometry_kind="point", source_id=source.id, confidence=Confidence(value=1.0))
        g_ci = Geometry(entity_id=city.id, geojson={"type": "Point", "coordinates": [10.2, 10.2]}, geometry_kind="point", source_id=source.id, confidence=Confidence(value=1.0))

        self.repo.ingest(WorldBundle(source=source, entity=country, evidence=ev, provenance=prov, geometry=g_c))
        self.repo.ingest(WorldBundle(source=source, entity=state, evidence=ev, provenance=prov, geometry=g_s))
        self.repo.ingest(WorldBundle(source=source, entity=city, evidence=ev, provenance=prov, geometry=g_ci))

        # Create explicit relationships: city -> located_in -> state; state -> located_in -> country
        rel1 = Relationship(
            subject_entity_id=city.id,
            predicate="located_in",
            object_entity_id=state.id,
            evidence_id=ev.id,
            confidence=Confidence(value=0.98),
        )
        rel2 = Relationship(
            subject_entity_id=state.id,
            predicate="located_in",
            object_entity_id=country.id,
            evidence_id=ev.id,
            confidence=Confidence(value=0.99),
        )
        self.repo.record_relationship(rel1)
        self.repo.record_relationship(rel2)

        # 1. Query relationships by predicate
        rels = self.repo.relationships(subject_entity_id=city.id, predicate="located_in")
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0]["predicate"], "located_in")
        self.assertEqual(rels[0]["object_name"], state.canonical_name)
        self.assertEqual(rels[0]["evidence_locator"], ev.locator)

        # 2. Query 1-hop entity graph
        graph_1 = self.repo.entity_graph(city.id, depth=1)
        self.assertEqual(graph_1["node_count"], 2)  # city, state
        self.assertEqual(graph_1["edge_count"], 1)

        # 3. Query 2-hop entity graph -> returns city, state, and country
        graph_2 = self.repo.entity_graph(city.id, depth=2)
        self.assertEqual(graph_2["node_count"], 3)  # city, state, country
        self.assertEqual(graph_2["edge_count"], 2)
        node_names = {n["canonical_name"] for n in graph_2["nodes"]}
        self.assertIn(city.canonical_name, node_names)
        self.assertIn(state.canonical_name, node_names)
        self.assertIn(country.canonical_name, node_names)

    def test_fastapi_spatial_temporal_and_relationship_endpoints(self) -> None:
        from app.main import (
            observations as api_observations,
            containing_geometries as api_containing_geometries,
            spatial_intersections as api_spatial_intersections,
            relationships as api_relationships,
            create_relationship as api_create_relationship,
            entity_graph as api_entity_graph,
        )

        # 1. api_observations with valid_at
        data = api_observations(measure="population.total", valid_at=datetime(2023, 6, 15, tzinfo=UTC))
        self.assertIsInstance(data, list)

        # 2. api_containing_geometries
        containing = api_containing_geometries(longitude=77.2090, latitude=28.6139)
        self.assertGreaterEqual(len(containing), 1)
        self.assertTrue(any(c["canonical_name"] == "India" for c in containing))

        # 3. api_relationships
        rels = api_relationships(predicate="located_in")
        self.assertIsInstance(rels, list)
        self.assertGreaterEqual(len(rels), 1)

        # 4. api_create_relationship
        now = datetime(2026, 9, 29, tzinfo=UTC)
        source = Source(slug=f"api-rel-src-{uuid4()}", name="API Rel Source", publisher="Rel Authority", refresh_policy="manual")
        ev = Evidence(source_id=source.id, locator="https://example.test/api-rel", retrieved_at=now)
        prov = Provenance(evidence_id=ev.id, pipeline_version="rel-v1")
        e_a = Entity(kind="place", canonical_name=f"EntityA-{uuid4()}", confidence=Confidence(value=1.0))
        e_b = Entity(kind="place", canonical_name=f"EntityB-{uuid4()}", confidence=Confidence(value=1.0))
        g_a = Geometry(entity_id=e_a.id, geojson={"type": "Point", "coordinates": [0.0, 0.0]}, geometry_kind="point", source_id=source.id, confidence=Confidence(value=1.0))
        g_b = Geometry(entity_id=e_b.id, geojson={"type": "Point", "coordinates": [0.1, 0.1]}, geometry_kind="point", source_id=source.id, confidence=Confidence(value=1.0))
        self.repo.ingest(WorldBundle(source=source, entity=e_a, evidence=ev, provenance=prov, geometry=g_a))
        self.repo.ingest(WorldBundle(source=source, entity=e_b, evidence=ev, provenance=prov, geometry=g_b))

        new_rel = Relationship(
            subject_entity_id=e_a.id,
            predicate="connected_to",
            object_entity_id=e_b.id,
            evidence_id=ev.id,
            confidence=Confidence(value=0.95),
            attributes={"line_type": "optical_fiber"},
        )
        rel_id = api_create_relationship(new_rel)
        self.assertEqual(rel_id, new_rel.id)

        # 5. api_entity_graph
        graph = api_entity_graph(entity_id=e_a.id, depth=1)
        self.assertEqual(graph["node_count"], 2)
        self.assertEqual(graph["edge_count"], 1)
        self.assertEqual(graph["edges"][0]["predicate"], "connected_to")

    def test_context_engine_spatial_bounding_box_filtering(self) -> None:
        now = datetime(2026, 9, 29, tzinfo=UTC)
        source = Source(slug=f"bbox-src-{uuid4()}", name="Bbox Source", publisher="Bbox Authority", refresh_policy="manual")
        ev = Evidence(source_id=source.id, locator="https://example.test/bbox", retrieved_at=now)
        prov = Provenance(evidence_id=ev.id, pipeline_version="bbox-v1")

        # Entity 1: Inside India bbox [68..97, 8..35]
        e_inside = Entity(kind="place", canonical_name=f"IndiaCity-{uuid4()}", confidence=Confidence(value=1.0))
        g_inside = Geometry(
            entity_id=e_inside.id,
            geojson={"type": "Point", "coordinates": [77.2090, 28.6139]},
            geometry_kind="city_point",
            source_id=source.id,
            evidence_id=ev.id,
            confidence=Confidence(value=1.0),
        )
        self.repo.ingest(WorldBundle(source=source, entity=e_inside, evidence=ev, provenance=prov, geometry=g_inside))

        # Entity 2: Far outside India bbox (e.g., Tokyo, Japan)
        e_outside = Entity(kind="place", canonical_name=f"JapanCity-{uuid4()}", confidence=Confidence(value=1.0))
        g_outside = Geometry(
            entity_id=e_outside.id,
            geojson={"type": "Point", "coordinates": [139.6917, 35.6895]},
            geometry_kind="city_point",
            source_id=source.id,
            evidence_id=ev.id,
            confidence=Confidence(value=1.0),
        )
        self.repo.ingest(WorldBundle(source=source, entity=e_outside, evidence=ev, provenance=prov, geometry=g_outside))

        # Query bounded to India [68..97, 8..35]
        bbox = BoundingBox(min_longitude=68.0, min_latitude=8.0, max_longitude=97.0, max_latitude=35.0)
        context = self.repo.scoped_context(bbox=bbox)

        self.assertIsInstance(context, WorldContext)
        returned_entity_ids = {e["id"] for e in context.entities}
        self.assertIn(e_inside.id, returned_entity_ids)
        self.assertNotIn(e_outside.id, returned_entity_ids)

        # Geometries must preserve kind
        returned_geom_kinds = {g["geometry_kind"] for g in context.geometries if g["entity_id"] == e_inside.id}
        self.assertIn("city_point", returned_geom_kinds)

        # Query scope reflects actual bounding box
        self.assertIsNotNone(context.query_scope.spatial)
        self.assertEqual(context.query_scope.spatial.bounding_box.min_longitude, 68.0)
        self.assertEqual(context.query_scope.spatial.bounding_box.max_latitude, 35.0)

    def test_context_engine_temporal_filtering_and_precision(self) -> None:
        # Ingest India 2023 observation
        now = datetime(2026, 9, 29, tzinfo=UTC)
        source = Source(slug=f"time-src-{uuid4()}", name="Time Source", publisher="Time Authority", refresh_policy="manual")
        ev = Evidence(source_id=source.id, locator="https://example.test/time", retrieved_at=now)
        prov = Provenance(evidence_id=ev.id, pipeline_version="time-v1")
        entity = Entity(kind="place", canonical_name=f"TimeEntity-{uuid4()}", confidence=Confidence(value=1.0))

        t2023 = TimeInterval(
            starts_at=datetime(2023, 1, 1, tzinfo=UTC),
            ends_at=datetime(2023, 12, 31, 23, 59, 59, tzinfo=UTC),
            precision="year",
        )
        t2010 = TimeInterval(
            starts_at=datetime(2010, 1, 1, tzinfo=UTC),
            ends_at=datetime(2010, 12, 31, 23, 59, 59, tzinfo=UTC),
            precision="year",
        )
        obs2023 = Observation(
            subject_entity_id=entity.id,
            measure="metric.alpha",
            value=2023.0,
            unit="points",
            time_interval_id=t2023.id,
            evidence_id=ev.id,
            provenance_id=prov.id,
            confidence=Confidence(value=1.0),
        )
        obs2010 = Observation(
            subject_entity_id=entity.id,
            measure="metric.alpha",
            value=2010.0,
            unit="points",
            time_interval_id=t2010.id,
            evidence_id=ev.id,
            provenance_id=prov.id,
            confidence=Confidence(value=1.0),
        )
        self.repo.ingest(WorldBundle(source=source, entity=entity, evidence=ev, provenance=prov, time_interval=t2023, observation=obs2023))
        self.repo.ingest(WorldBundle(source=source, entity=entity, evidence=ev, provenance=prov, time_interval=t2010, observation=obs2010))

        # Point-in-time: 2023-06-15 must match 2023 obs and exclude 2010 obs
        ctx_point = self.repo.scoped_context(
            entity_ids=[entity.id],
            valid_at=datetime(2023, 6, 15, tzinfo=UTC),
        )
        obs_vals = [o["value"] for o in ctx_point.observations if o["subject_entity_id"] == entity.id]
        self.assertIn(2023.0, obs_vals)
        self.assertNotIn(2010.0, obs_vals)
        self.assertEqual(ctx_point.observations[0]["precision"], "year")

        # Interval overlap: [2009, 2011] must match 2010 obs and exclude 2023 obs
        ctx_range = self.repo.scoped_context(
            entity_ids=[entity.id],
            start=datetime(2009, 1, 1, tzinfo=UTC),
            end=datetime(2011, 1, 1, tzinfo=UTC),
        )
        range_vals = [o["value"] for o in ctx_range.observations if o["subject_entity_id"] == entity.id]
        self.assertIn(2010.0, range_vals)
        self.assertNotIn(2023.0, range_vals)

    def test_context_engine_evidence_lineage_and_deduplication(self) -> None:
        now = datetime(2026, 9, 29, tzinfo=UTC)
        source = Source(slug=f"ev-dedup-src-{uuid4()}", name="Ev Dedup Source", publisher="Ev Authority", refresh_policy="manual")
        ev = Evidence(source_id=source.id, locator="https://example.test/ev-dedup", retrieved_at=now)
        prov = Provenance(evidence_id=ev.id, pipeline_version="dedup-v1")
        entity = Entity(kind="place", canonical_name=f"DedupEntity-{uuid4()}", confidence=Confidence(value=1.0))
        geom = Geometry(
            entity_id=entity.id,
            geojson={"type": "Point", "coordinates": [10.0, 10.0]},
            geometry_kind="point",
            source_id=source.id,
            evidence_id=ev.id,
            confidence=Confidence(value=1.0),
        )
        t = TimeInterval(starts_at=now, precision="instant")
        obs1 = Observation(
            subject_entity_id=entity.id,
            measure="metric.one",
            value=1.0,
            unit="u",
            time_interval_id=t.id,
            evidence_id=ev.id,
            provenance_id=prov.id,
            confidence=Confidence(value=1.0),
        )
        obs2 = Observation(
            subject_entity_id=entity.id,
            measure="metric.two",
            value=2.0,
            unit="u",
            time_interval_id=t.id,
            evidence_id=ev.id,
            provenance_id=prov.id,
            confidence=Confidence(value=1.0),
        )
        self.repo.ingest(WorldBundle(source=source, entity=entity, evidence=ev, provenance=prov, geometry=geom))
        self.repo.ingest(WorldBundle(source=source, entity=entity, evidence=ev, provenance=prov, time_interval=t, observation=obs1))
        self.repo.ingest(WorldBundle(source=source, entity=entity, evidence=ev, provenance=prov, time_interval=t, observation=obs2))

        ctx = self.repo.scoped_context(entity_ids=[entity.id])

        # Verify evidence citations are deduplicated
        evidence_ids = [c.evidence_id for c in ctx.evidence]
        self.assertEqual(len(evidence_ids), len(set(evidence_ids)), "Evidence citations must not contain duplicates")
        self.assertIn(ev.id, evidence_ids)

        # Verify every observation has its evidence locator
        for o in ctx.observations:
            if o["subject_entity_id"] == entity.id:
                self.assertIsNotNone(o["evidence_locator"])
                self.assertEqual(o["evidence_locator"], "https://example.test/ev-dedup")

        # Verify entity deduplication
        ret_eids = [e["id"] for e in ctx.entities if e["id"] == entity.id]
        self.assertEqual(len(ret_eids), 1, "Entity must appear exactly once in entities list")

    def test_context_engine_empty_scope_behavior(self) -> None:
        # Bbox in remote Antarctica ocean with no data
        empty_bbox = BoundingBox(min_longitude=-179.0, min_latitude=-89.0, max_longitude=-178.0, max_latitude=-88.0)
        ctx = self.repo.scoped_context(bbox=empty_bbox)

        self.assertIsInstance(ctx, WorldContext)
        self.assertEqual(len(ctx.entities), 0)
        self.assertEqual(len(ctx.observations), 0)
        self.assertEqual(len(ctx.events), 0)
        self.assertEqual(len(ctx.geometries), 0)
        self.assertEqual(len(ctx.relationships), 0)
        self.assertEqual(len(ctx.claims), 0)
        self.assertEqual(len(ctx.evidence), 0)
        self.assertTrue(any("No entities matched" in a for a in ctx.assumptions_or_limitations))

    def test_context_engine_api_and_backward_compatibility(self) -> None:
        from fastapi import HTTPException
        from app.main import context as api_single_context, get_world_context as api_scoped_context

        # 1. API Scoped Context with valid bbox
        ctx = api_scoped_context(min_lon=68.0, min_lat=8.0, max_lon=97.0, max_lat=35.0, limit=50)
        self.assertIsInstance(ctx, WorldContext)
        self.assertGreaterEqual(len(ctx.entities), 1)

        # 2. API rejects partial bbox (only 2 coordinates given)
        with self.assertRaises(HTTPException) as cm:
            api_scoped_context(min_lon=68.0, min_lat=8.0)
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("Bounding box requires all four coordinates", cm.exception.detail)

        # 3. API rejects inverted bbox (min_lon > max_lon)
        with self.assertRaises(HTTPException) as cm:
            api_scoped_context(min_lon=100.0, min_lat=10.0, max_lon=50.0, max_lat=20.0)
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("min_lon must be less than or equal to max_lon", cm.exception.detail)

        # 4. API rejects inverted temporal interval (start > end)
        with self.assertRaises(HTTPException) as cm:
            api_scoped_context(
                start=datetime(2025, 1, 1, tzinfo=UTC),
                end=datetime(2020, 1, 1, tzinfo=UTC),
            )
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("start must be less than or equal to end", cm.exception.detail)

        # 5. Backward compatibility: existing GET /entities/{entity_id}/context returns entity dict
        india_entity = ctx.entities[0]
        single_ctx = api_single_context(entity_id=india_entity["id"])
        self.assertIsInstance(single_ctx, dict)
        self.assertEqual(single_ctx["id"], india_entity["id"])
        self.assertIn("observations", single_ctx)
        self.assertIn("relationships", single_ctx)
        self.assertIn("claims", single_ctx)

    def test_parquet_snapshot_export_lifecycle_and_catalog(self) -> None:
        import tempfile
        import shutil

        temp_snapshots = Path(tempfile.mkdtemp())
        try:
            manager = SnapshotManager(database_url=self.db_url, snapshots_dir=temp_snapshots)
            manifest = manager.export_snapshot()

            # 1. Manifest structure and status
            self.assertEqual(manifest.status, "completed")
            self.assertGreater(manifest.total_records, 0)
            self.assertIn("observations", manifest.row_counts)
            self.assertGreater(manifest.row_counts["observations"], 0)
            self.assertTrue(Path(manifest.storage_path).exists())

            # 2. Hive partitioned directory check
            obs_dir = Path(manifest.storage_path) / "observations"
            self.assertTrue(obs_dir.exists())
            parquet_files = list(obs_dir.rglob("*.parquet"))
            self.assertGreater(len(parquet_files), 0)
            for pf in parquet_files:
                self.assertIn("year=", str(pf))
                self.assertIn("entity_type=", str(pf))

            # 3. PostgreSQL snapshot_runs record
            run_records = self.repo.get_snapshot_runs(status="completed")
            self.assertGreater(len(run_records), 0)
            matched = next((r for r in run_records if str(r["id"]) == str(manifest.snapshot_id)), None)
            self.assertIsNotNone(matched)
            self.assertEqual(matched["status"], "completed")
            self.assertEqual(matched["total_records"], manifest.total_records)

            # 4. SnapshotCatalog discovery and validation
            catalog = SnapshotCatalog(snapshots_dir=temp_snapshots)
            snapshots = catalog.list_snapshots(status_filter="completed")
            self.assertEqual(len(snapshots), 1)
            self.assertTrue(snapshots[0].metadata.get("is_latest"))

            val = catalog.validate_snapshot(manifest.snapshot_id)
            self.assertTrue(val["valid"])
            self.assertEqual(len(val["errors"]), 0)
            self.assertEqual(val["datasets"]["observations"]["actual_rows"], manifest.row_counts["observations"])
        finally:
            shutil.rmtree(temp_snapshots, ignore_errors=True)

    def test_duckdb_spatial_rollups_and_multi_entity_analytics(self) -> None:
        import tempfile
        import shutil

        temp_snapshots = Path(tempfile.mkdtemp())
        try:
            manager = SnapshotManager(database_url=self.db_url, snapshots_dir=temp_snapshots)
            manifest = manager.export_snapshot()

            analytics = DuckDbSpatialAnalytics(replica_path=manifest.storage_path)

            # 1. Multi-entity spatial rollups
            summaries = analytics.spatial_summaries(measure="population.total")
            self.assertGreater(len(summaries), 0)
            first_summary = summaries[0]
            self.assertIn("entity_canonical_name", first_summary)
            self.assertIn("total_value", first_summary)
            self.assertGreater(first_summary["total_value"], 0)
            self.assertTrue(first_summary["has_data"])

            # 2. Multi-entity temporal trends
            trends = analytics.multi_entity_temporal_trends(measure="population.total")
            self.assertGreater(len(trends), 0)
            first_trend = trends[0]
            self.assertIn("series", first_trend)
            self.assertIn("evidence_ids", first_trend)

            # 3. Evidence coverage and freshness
            coverage = analytics.evidence_coverage_and_freshness()
            self.assertGreater(coverage["total_observations"], 0)
            self.assertGreater(coverage["total_entities"], 0)
            self.assertGreater(coverage["total_evidence_citations"], 0)
            self.assertGreater(coverage["distinct_sources"], 0)
            self.assertIsNotNone(coverage["earliest_observation"])
            self.assertIsNotNone(coverage["latest_observation"])

            # 4. Compare spatial slices between entities if at least 2 entities exist
            if len(summaries) >= 2:
                eid_a = summaries[0]["entity_id"]
                eid_b = summaries[1]["entity_id"]
                comp = analytics.compare_spatial_slices(entity_a_id=eid_a, entity_b_id=eid_b, measure="population.total")
                self.assertIsNotNone(comp["absolute_difference"])
                self.assertIsNotNone(comp["larger_entity"])

            # 5. Backward compatible population growth derivation
            ind_summary = next((s for s in summaries if "India" in s["entity_canonical_name"]), None)
            if ind_summary:
                growth_claim = analytics.derive_population_growth(ind_summary["entity_id"])
                # If India has >= 2 population points, growth claim is produced
                if growth_claim:
                    self.assertEqual(growth_claim.truth_class, TruthClass.DERIVED)
                    self.assertEqual(growth_claim.claim_type, "population_growth_percentage")
        finally:
            shutil.rmtree(temp_snapshots, ignore_errors=True)

    def test_analytical_benchmarks_runner(self) -> None:
        import tempfile
        import shutil

        temp_snapshots = Path(tempfile.mkdtemp())
        try:
            manager = SnapshotManager(database_url=self.db_url, snapshots_dir=temp_snapshots)
            manifest = manager.export_snapshot()

            suite = AnalyticalBenchmarkSuite(snapshot_path=manifest.storage_path)
            report = suite.run_all(iterations=2)

            self.assertEqual(report["snapshot_id"], str(manifest.snapshot_id))
            self.assertGreater(report["total_records"], 0)
            self.assertEqual(len(report["benchmarks"]), 6)

            for b in report["benchmarks"]:
                self.assertIn("name", b)
                self.assertIn("mean_duration_ms", b)
                self.assertGreaterEqual(b["mean_duration_ms"], 0.0)
                self.assertEqual(b["iterations"], 2)
        finally:
            shutil.rmtree(temp_snapshots, ignore_errors=True)

    def test_analytics_and_snapshot_api_endpoints(self) -> None:
        import tempfile
        import shutil

        temp_snapshots = Path(tempfile.mkdtemp())
        try:
            # Point SNAPSHOT_DIR to temp location for API test
            old_snap_dir = os.environ.get("WORLDOS_SNAPSHOT_DIR")
            os.environ["WORLDOS_SNAPSHOT_DIR"] = str(temp_snapshots)

            # 1. Trigger export via endpoint
            manifest_resp = export_snapshot_endpoint(background=False)
            self.assertIsInstance(manifest_resp, SnapshotManifest)
            self.assertEqual(manifest_resp.status, "completed")
            sid = manifest_resp.snapshot_id

            # 2. List snapshots endpoint
            snaps_list = list_snapshots_endpoint()
            self.assertGreater(len(snaps_list), 0)
            self.assertEqual(snaps_list[0].snapshot_id, sid)

            # 3. Get snapshot endpoint
            snap_detail = get_snapshot_endpoint(snapshot_id=sid)
            self.assertEqual(snap_detail.snapshot_id, sid)

            # 4. Validate snapshot endpoint
            val_res = validate_snapshot_endpoint(snapshot_id=sid)
            self.assertTrue(val_res["valid"])

            # 5. Spatial rollups endpoint
            spatial_res = spatial_rollups_endpoint(snapshot_id=sid, measure="population.total")
            self.assertIsInstance(spatial_res, list)

            # 6. Temporal rollups endpoint
            temporal_res = temporal_rollups_endpoint(snapshot_id=sid, measure="population.total")
            self.assertIsInstance(temporal_res, list)

            # 7. Coverage endpoint
            cov_res = coverage_summary_endpoint(snapshot_id=sid)
            self.assertIsInstance(cov_res, dict)
            self.assertIn("total_observations", cov_res)

            # 8. Benchmarks endpoint
            bench_res = run_benchmarks_endpoint(iterations=1)
            self.assertIn("benchmarks", bench_res)
            self.assertEqual(len(bench_res["benchmarks"]), 6)

        finally:
            if old_snap_dir:
                os.environ["WORLDOS_SNAPSHOT_DIR"] = old_snap_dir
            else:
                os.environ.pop("WORLDOS_SNAPSHOT_DIR", None)
            shutil.rmtree(temp_snapshots, ignore_errors=True)

    # -------------------------------------------------------------------------
    # Engine 12: Constraint Engine Integration Tests
    # -------------------------------------------------------------------------

    def test_postgis_geometry_topology_authoritative_validation(self) -> None:
        """Verify PostGIS ST_IsValid and ST_IsValidReason authoritative topology validation."""
        engine = self.repo.constraint_engine

        # 1. Valid geometry
        valid_geojson = {"type": "Point", "coordinates": [77.2090, 28.6139]}
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            valid_findings = engine.validate_geometry_with_postgis(valid_geojson, conn)
            self.assertEqual(len(valid_findings), 0)

            # 2. Self-intersecting polygon (bowtie - invalid topology)
            bowtie_geojson = {
                "type": "Polygon",
                "coordinates": [[[0.0, 0.0], [10.0, 10.0], [0.0, 10.0], [10.0, 0.0], [0.0, 0.0]]],
            }
            invalid_findings = engine.validate_geometry_with_postgis(bowtie_geojson, conn)
            self.assertEqual(len(invalid_findings), 1)
            self.assertEqual(invalid_findings[0].code, "GEOM_INVALID_TOPOLOGY")
            self.assertEqual(invalid_findings[0].severity, ConstraintSeverity.BLOCKING)
            self.assertIn("Self-intersection", str(invalid_findings[0].actual_value))

    def test_postgis_spatial_predicate_and_containment_consistency(self) -> None:
        """Verify spatial consistency between entity geometries using PostGIS spatial predicates."""
        now = datetime(2026, 9, 29, tzinfo=UTC)
        source = Source(
            id=uuid4(),
            slug=f"spatial-source-{uuid4().hex[:6]}",
            name="Spatial Invariant Test Source",
            publisher="Test Publisher",
        )
        evidence = Evidence(
            id=uuid4(),
            source_id=source.id,
            locator="https://test.worldos.internal/spatial",
            retrieved_at=now,
        )
        provenance = Provenance(id=uuid4(), evidence_id=evidence.id, pipeline_version="test-v1")
        time_int = TimeInterval(starts_at=now, ends_at=now, precision="day")

        # Entity A: Delhi (Point)
        entity_a = Entity(
            id=uuid4(),
            kind="place",
            canonical_name="Delhi Point",
            source_id=source.id,
            source_key=f"delhi-{uuid4().hex[:6]}",
            confidence=Confidence(value=1.0),
        )
        geom_a = Geometry(
            id=uuid4(),
            entity_id=entity_a.id,
            geometry_kind="point",
            geojson={"type": "Point", "coordinates": [77.2090, 28.6139]},
            source_id=source.id,
            confidence=Confidence(value=1.0),
        )
        bundle_a = WorldBundle(
            source=source,
            entity=entity_a,
            evidence=evidence,
            provenance=provenance,
            time_interval=time_int,
            geometry=geom_a,
        )
        self.repo.ingest(bundle_a)

        # Entity B: India (Bounding polygon covering Delhi)
        entity_b = Entity(
            id=uuid4(),
            kind="place",
            canonical_name="India Region",
            source_id=source.id,
            source_key=f"india-{uuid4().hex[:6]}",
            confidence=Confidence(value=1.0),
        )
        geom_b = Geometry(
            id=uuid4(),
            entity_id=entity_b.id,
            geometry_kind="polygon",
            geojson={
                "type": "Polygon",
                "coordinates": [[[68.0, 8.0], [97.0, 8.0], [97.0, 35.0], [68.0, 35.0], [68.0, 8.0]]],
            },
            source_id=source.id,
            confidence=Confidence(value=1.0),
        )
        bundle_b = WorldBundle(
            source=source,
            entity=entity_b,
            evidence=evidence,
            provenance=provenance,
            time_interval=time_int,
            geometry=geom_b,
        )
        self.repo.ingest(bundle_b)

        # Entity C: Iceland (Disjoint polygon)
        entity_c = Entity(
            id=uuid4(),
            kind="place",
            canonical_name="Iceland Region",
            source_id=source.id,
            source_key=f"iceland-{uuid4().hex[:6]}",
            confidence=Confidence(value=1.0),
        )
        geom_c = Geometry(
            id=uuid4(),
            entity_id=entity_c.id,
            geometry_kind="polygon",
            geojson={
                "type": "Polygon",
                "coordinates": [[[-25.0, 63.0], [-13.0, 63.0], [-13.0, 67.0], [-25.0, 67.0], [-25.0, 63.0]]],
            },
            source_id=source.id,
            confidence=Confidence(value=1.0),
        )
        bundle_c = WorldBundle(
            source=source,
            entity=entity_c,
            evidence=evidence,
            provenance=provenance,
            time_interval=time_int,
            geometry=geom_c,
        )
        self.repo.ingest(bundle_c)

        try:
            with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
                # 1. Consistent spatial containment: Delhi located_in India
                rel_valid = Relationship(
                    subject_entity_id=entity_a.id,
                    predicate="located_in",
                    object_entity_id=entity_b.id,
                    evidence_id=evidence.id,
                    confidence=Confidence(value=1.0),
                )
                findings_valid = self.repo.constraint_engine.validate_spatial_relationship(rel_valid, conn=conn)
                self.assertEqual(len(findings_valid), 0)

                # 2. Contradictory spatial containment: Delhi located_in Iceland (Disjoint!)
                rel_contradiction = Relationship(
                    subject_entity_id=entity_a.id,
                    predicate="located_in",
                    object_entity_id=entity_c.id,
                    evidence_id=evidence.id,
                    confidence=Confidence(value=1.0),
                )
                findings_contra = self.repo.constraint_engine.validate_spatial_relationship(rel_contradiction, conn=conn)
                self.assertEqual(len(findings_contra), 1)
                self.assertEqual(findings_contra[0].code, "SPATIAL_RELATION_CONTRADICTION")
                self.assertEqual(findings_contra[0].severity, ConstraintSeverity.BLOCKING)

                # 3. Missing spatial evidence: Delhi located_in NonExistentEntity
                rel_missing = Relationship(
                    subject_entity_id=entity_a.id,
                    predicate="located_in",
                    object_entity_id=uuid4(),
                    evidence_id=evidence.id,
                    confidence=Confidence(value=1.0),
                )
                findings_missing = self.repo.constraint_engine.validate_spatial_relationship(rel_missing, conn=conn)
                self.assertEqual(len(findings_missing), 1)
                self.assertEqual(findings_missing[0].code, "SPATIAL_EVIDENCE_MISSING")
                self.assertEqual(findings_missing[0].severity, ConstraintSeverity.WARNING)
        finally:
            with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM geometries WHERE entity_id IN (%s, %s, %s)", (entity_a.id, entity_b.id, entity_c.id))
                cur.execute("DELETE FROM entities WHERE id IN (%s, %s, %s)", (entity_a.id, entity_b.id, entity_c.id))
                conn.commit()

    def test_ingestion_blocks_constraint_violations_without_mutating_state(self) -> None:
        """Verify that WorldRepository.ingest blocks invalid data deterministically without persisting dirty records."""
        now = datetime(2026, 9, 29, tzinfo=UTC)
        source = Source(
            id=uuid4(),
            slug=f"rejection-source-{uuid4().hex[:6]}",
            name="Constraint Rejection Test Source",
            publisher="Test Publisher",
        )
        evidence = Evidence(
            id=uuid4(),
            source_id=source.id,
            locator="https://test.worldos.internal/rejection",
            retrieved_at=now,
        )
        provenance = Provenance(id=uuid4(), evidence_id=evidence.id, pipeline_version="test-v1")
        time_int = TimeInterval(starts_at=now, ends_at=now, precision="day")

        entity_id = uuid4()
        entity = Entity(
            id=entity_id,
            kind="place",
            canonical_name="Dirty Record City",
            source_id=source.id,
            source_key=f"dirty-{uuid4().hex[:6]}",
            confidence=Confidence(value=1.0),
        )

        # Observation with negative population -> BLOCKING constraint
        invalid_obs = Observation(
            subject_entity_id=entity_id,
            measure="population.total",
            value=-100000.0,
            unit="people",
            truth_class="OBSERVED",
            time_interval_id=time_int.id,
            evidence_id=evidence.id,
            provenance_id=provenance.id,
            confidence=Confidence(value=1.0),
        )
        invalid_bundle = WorldBundle(
            source=source,
            entity=entity,
            evidence=evidence,
            provenance=provenance,
            time_interval=time_int,
            observation=invalid_obs,
        )

        # Ingestion must raise ConstraintViolationError
        with self.assertRaises(ConstraintViolationError) as ctx:
            self.repo.ingest(invalid_bundle, enforce_constraints=True)

        self.assertIn("MEASURE_VALUE_NEGATIVE", [f.code for f in ctx.exception.result.findings])

        # Verify that entity was NOT persisted into database (rollback ensured)
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM entities WHERE id = %s", (entity_id,))
            self.assertIsNone(cur.fetchone())

    def test_constraint_engine_api_dry_run_and_rules_endpoints(self) -> None:
        """Verify POST /constraints/validate dry-run endpoint and GET /constraints/rules."""
        # 1. Rules listing endpoint
        rules_res = list_constraint_rules()
        self.assertIn("severity_tiers", rules_res)
        self.assertIn("categories", rules_res)
        self.assertIn("PHYSICAL_COORDINATES", rules_res["categories"])
        self.assertIn("SPATIAL_CONSISTENCY", rules_res["categories"])

        # 2. Dry-run validation of valid geometry
        valid_req = ValidationRequest(
            geometry=Geometry(
                id=uuid4(),
                entity_id=uuid4(),
                geometry_kind="Point",
                geojson={"type": "Point", "coordinates": [72.8777, 19.0760]},
                source_id=uuid4(),
                confidence=Confidence(value=1.0),
            )
        )
        val_res = validate_constraints_endpoint(valid_req)
        self.assertEqual(val_res.status, ConstraintStatus.VALID)
        self.assertEqual(val_res.blocking_count, 0)

        # 3. Dry-run validation of invalid coordinate geometry (lat > 90)
        invalid_req = ValidationRequest(
            geometry=Geometry.model_construct(
                id=uuid4(),
                entity_id=uuid4(),
                geometry_kind="Point",
                geojson={"type": "Point", "coordinates": [0.0, 99.0]},
                source_id=uuid4(),
                confidence=Confidence(value=1.0),
            )
        )
        inv_res = validate_constraints_endpoint(invalid_req)
        self.assertEqual(inv_res.status, ConstraintStatus.INVALID)
        self.assertIn("COORD_LAT_OUT_OF_BOUNDS", [f.code for f in inv_res.findings])

        # 4. Dry-run validation of scenario proposal
        scenario_req = ValidationRequest(
            scenario_proposal=ScenarioProposal(
                name="Hypothetical Port Expansion",
                parameters={"dredging_depth_meters": 15.0, "projected_vessels": 1200},
            )
        )
        scen_res = validate_constraints_endpoint(scenario_req)
        self.assertEqual(scen_res.status, ConstraintStatus.VALID)

        # 5. Empty request raises HTTPException 422
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            validate_constraints_endpoint(ValidationRequest())
        self.assertEqual(ctx.exception.status_code, 422)
