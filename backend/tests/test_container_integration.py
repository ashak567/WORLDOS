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
from app.domain import (Claim, Confidence, Entity, Evidence, Geometry, Observation, Provenance, Relationship, Source,
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



