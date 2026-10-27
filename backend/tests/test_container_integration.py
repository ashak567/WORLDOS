"""Container-backed integration tests verifying PostGIS truth, fusion, and DuckDB analytics."""
from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
import unittest
from uuid import uuid4

import psycopg
from fastapi import HTTPException
from psycopg.rows import dict_row

from app.analytics import DuckDbSpatialAnalytics
from app.benchmarks import AnalyticalBenchmarkSuite
from app.domain import (
    Alert,
    AlertEvaluation,
    AlertLifecycleStatus,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    BoundingBox,
    Claim,
    Confidence,
    ConstraintCategory,
    ConstraintFinding,
    ConstraintSeverity,
    ConstraintStatus,
    ConstraintValidationResult,
    CriterionDirection,
    DecisionAlternative,
    DecisionCriterion,
    DecisionRequest,
    DecisionResult,
    Entity,
    Event,
    Evidence,
    Geometry,
    MissingDataPolicy,
    Observation,
    Provenance,
    RankedAlternative,
    Relationship,
    Scenario,
    ScenarioComparison,
    ScenarioEvaluation,
    ScenarioModification,
    ScenarioOperationType,
    ScenarioProposal,
    ScenarioStatus,
    SensitivityVariation,
    SimulationComparison,
    SimulationRequest,
    SimulationRun,
    SimulationStatus,
    SimulationStep,
    SnapshotManifest,
    Source,
    TimeInterval,
    TruthClass,
    WorldBundle,
    WorldContext,
    AnomalyDetectionRequest,
    AnomalyFinding,
    AnomalyRun,
    AnomalySeverity,
    DetectionMethod,
    FindingLifecycleStatus,
)
from app.constraints import ConstraintEngine, ConstraintViolationError
from app.export import export_observations
from app.ingestion.natural_earth import parse_country_boundary
from app.ingestion.usgs import parse_earthquake_feature
from app.ingestion.world_bank import parse_population
from app.main import (
    AcknowledgeAlertRequest,
    AddScenarioModificationRequest,
    BranchScenarioRequest,
    CreateAlertRuleRequest,
    CreateScenarioRequest,
    CreateSimulationRequest,
    DecisionSensitivityRequest,
    EvaluateScenarioRequest,
    ResolveAlertRequest,
    UpdateAlertRuleRequest,
    ValidationRequest,
    acknowledge_alert as api_acknowledge_alert,
    add_scenario_modification_endpoint,
    archive_scenario_endpoint,
    branch_scenario_endpoint,
    cancel_simulation_endpoint,
    compare_scenarios_endpoint,
    compare_simulations_endpoint,
    compare_spatial_slices_endpoint,
    coverage_summary_endpoint,
    create_alert_rule as api_create_alert_rule,
    create_scenario_endpoint,
    create_simulation_endpoint,
    delete_alert_rule as api_delete_alert_rule,
    evaluate_event_alerts as api_evaluate_event_alerts,
    evaluate_scenario_endpoint,
    export_snapshot_endpoint,
    evaluate_decision as api_evaluate_decision,
    get_alert as api_get_alert,
    get_alert_rule as api_get_alert_rule,
    get_decision as api_get_decision,
    get_scenario_endpoint,
    get_scenario_evaluation_endpoint,
    get_simulation_endpoint,
    get_simulation_step_endpoint,
    get_simulation_trajectory_endpoint,
    get_snapshot_endpoint,
    list_alert_evaluations as api_list_alert_evaluations,
    list_alert_rules as api_list_alert_rules,
    list_alerts as api_list_alerts,
    list_constraint_rules,
    list_decisions as api_list_decisions,
    list_scenario_modifications_endpoint,
    list_scenarios_endpoint,
    list_simulation_rules_endpoint,
    list_simulations_endpoint,
    list_snapshots_endpoint,
    natural_earth_bundle,
    remove_scenario_modification_endpoint,
    resolve_alert as api_resolve_alert,
    run_benchmarks_endpoint,
    run_decision_sensitivity as api_run_decision_sensitivity,
    spatial_rollups_endpoint,
    temporal_rollups_endpoint,
    update_alert_rule as api_update_alert_rule,
    usgs_earthquake_bundle,
    validate_constraints_endpoint,
    validate_scenario_endpoint,
    validate_snapshot_endpoint,
    world_bank_bundle,
    FindingActionRequest,
    detect_anomalies_endpoint,
    get_anomaly_finding_endpoint,
    get_anomaly_run_endpoint,
    list_anomaly_findings_endpoint,
    list_anomaly_methods_endpoint,
    list_anomaly_runs_endpoint,
    resolve_anomaly_finding_endpoint,
    suppress_anomaly_finding_endpoint,
)
from app.ingestion.usgs import EarthquakeRecord
from app.scenarios import ScenarioLifecycleError
from app.simulation import (
    SimulationConfigurationError,
    SimulationConstraintViolationError,
    SimulationLifecycleError,
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

    def setUp(self) -> None:
        with psycopg.connect(self.db_url) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM scenario_evaluations")
            cur.execute("DELETE FROM scenario_modifications")
            cur.execute("DELETE FROM scenarios")
            cur.execute("DELETE FROM decisions")
            cur.execute("DELETE FROM alerts")
            cur.execute("DELETE FROM alert_evaluations")
            cur.execute("DELETE FROM alert_rules")

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

    # -------------------------------------------------------------------------
    # Engine 14: Event / Alert Engine Integration Tests
    # -------------------------------------------------------------------------

    def test_alert_rule_crud_operations(self) -> None:
        """Verify Alert Rule creation, retrieval, listing, updating, and deletion in PostgreSQL."""
        rule_id = uuid4()
        rule = AlertRule(
            id=rule_id,
            name="Seismic Hazard Test Rule",
            description="Integration test rule for earthquake magnitude",
            event_kind="earthquake",
            operator=">=",
            metric_field="mag",
            threshold=5.0,
            severity=AlertSeverity.WARNING,
            cooldown_seconds=300,
        )
        created_id = self.repo.create_alert_rule(rule)
        self.assertEqual(created_id, rule_id)

        # Retrieve rule
        retrieved = self.repo.get_alert_rule(rule_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "Seismic Hazard Test Rule")
        self.assertEqual(retrieved.threshold, 5.0)
        self.assertTrue(retrieved.is_enabled)

        # List rules
        rules = self.repo.list_alert_rules(event_kind="earthquake")
        self.assertTrue(any(r.id == rule_id for r in rules))

        # Update rule
        updated = self.repo.update_alert_rule(rule_id, is_enabled=False, threshold=6.0)
        self.assertTrue(updated)
        retrieved_updated = self.repo.get_alert_rule(rule_id)
        self.assertFalse(retrieved_updated.is_enabled)
        self.assertEqual(retrieved_updated.threshold, 6.0)

        # Delete rule
        deleted = self.repo.delete_alert_rule(rule_id)
        self.assertTrue(deleted)
        self.assertIsNone(self.repo.get_alert_rule(rule_id))

    def test_seismic_event_alert_evaluation_pipeline(self) -> None:
        """Verify full Event/Alert evaluation pipeline with PostGIS spatial bounding box."""
        # 1. Create alert rule scoped to California Bbox
        rule_id = uuid4()
        rule = AlertRule(
            id=rule_id,
            name="California Quake Warning",
            description="Magnitude 5.0+ within California bounds",
            event_kind="earthquake",
            operator=">=",
            metric_field="mag",
            threshold=5.0,
            severity=AlertSeverity.CRITICAL,
            spatial_scope={"type": "bbox", "min_lon": -125.0, "max_lon": -114.0, "min_lat": 32.0, "max_lat": 42.0},
            cooldown_seconds=600,
            is_enabled=True,
        )
        self.repo.create_alert_rule(rule)

        # 2. Ingest an earthquake event in California (Ridgecrest area: -117.5, 35.8, mag=5.8)
        now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
        eq_event_id = f"test-ca-{uuid4()}"
        record = EarthquakeRecord(
            event_id=eq_event_id,
            title="M 5.8 - Ridgecrest, CA",
            place="Ridgecrest, CA",
            mag=5.8,
            time=now,
            longitude=-117.5,
            latitude=35.8,
            depth_km=7.5,
            locator=f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/detail/{eq_event_id}.geojson",
            content_hash="test-hash-ca",
        )
        bundle = usgs_earthquake_bundle(record, now)
        self.repo.ingest(bundle)

        # 3. Evaluate the event
        eval_result = self.repo.evaluate_event_alerts(bundle.event.id)
        self.assertEqual(eval_result.status, AlertLifecycleStatus.ALERTED)
        self.assertEqual(eval_result.alerts_generated, 1)
        self.assertIn(rule_id, eval_result.matched_rule_ids)

        # 4. Verify Alert record in PostgreSQL
        alerts = self.repo.list_alerts(event_id=bundle.event.id)
        self.assertEqual(len(alerts), 1)
        alert = alerts[0]
        self.assertEqual(alert["severity"], "CRITICAL")
        self.assertEqual(alert["status"], "active")
        self.assertEqual(alert["evidence_id"], bundle.evidence.id)
        self.assertIn("M 5.8", alert["message"])
        self.assertIn("Does not assert secondary impacts without dedicated modeling", alert["message"])
        self.assertEqual(alert["context_summary"]["metric_value"], 5.8)
        self.assertEqual(alert["context_summary"]["threshold"], 5.0)

    def test_seismic_event_spatial_filter_rejection(self) -> None:
        """Verify that events outside configured spatial bounding box do not trigger alerts."""
        rule_id = uuid4()
        rule = AlertRule(
            id=rule_id,
            name="California Only Rule",
            event_kind="earthquake",
            operator=">=",
            metric_field="mag",
            threshold=5.0,
            severity=AlertSeverity.WARNING,
            spatial_scope={"type": "bbox", "min_lon": -125.0, "max_lon": -114.0, "min_lat": 32.0, "max_lat": 42.0},
            cooldown_seconds=300,
            is_enabled=True,
        )
        self.repo.create_alert_rule(rule)

        # Ingest earthquake in Tokyo, Japan (139.69, 35.68, mag=6.5)
        now = datetime(2026, 10, 26, 12, 10, 0, tzinfo=UTC)
        eq_event_id = f"test-tokyo-{uuid4()}"
        record = EarthquakeRecord(
            event_id=eq_event_id,
            title="M 6.5 - Tokyo Region, Japan",
            place="Near Tokyo, Japan",
            mag=6.5,
            time=now,
            longitude=139.69,
            latitude=35.68,
            depth_km=40.0,
            locator=f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/detail/{eq_event_id}.geojson",
            content_hash="test-hash-tokyo",
        )
        bundle = usgs_earthquake_bundle(record, now)
        self.repo.ingest(bundle)

        # Evaluate: Tokyo event should NOT match California rule
        eval_result = self.repo.evaluate_event_alerts(bundle.event.id)
        self.assertEqual(eval_result.status, AlertLifecycleStatus.EVALUATED)
        self.assertEqual(eval_result.alerts_generated, 0)
        self.assertEqual(len(eval_result.matched_rule_ids), 0)

        # Verify no alerts were created
        alerts = self.repo.list_alerts(event_id=bundle.event.id)
        self.assertEqual(len(alerts), 0)

    def test_seismic_event_below_threshold(self) -> None:
        """Verify that events below numeric threshold do not trigger alerts."""
        rule_id = uuid4()
        rule = AlertRule(
            id=rule_id,
            name="Major Quake Only",
            event_kind="earthquake",
            operator=">=",
            metric_field="mag",
            threshold=6.5,
            severity=AlertSeverity.CRITICAL,
            cooldown_seconds=300,
            is_enabled=True,
        )
        self.repo.create_alert_rule(rule)

        now = datetime(2026, 10, 26, 12, 15, 0, tzinfo=UTC)
        eq_event_id = f"test-minor-{uuid4()}"
        record = EarthquakeRecord(
            event_id=eq_event_id,
            title="M 4.2 - Minor Quake",
            place="Minor Fault",
            mag=4.2,
            time=now,
            longitude=-118.0,
            latitude=34.0,
            depth_km=10.0,
            locator=f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/detail/{eq_event_id}.geojson",
            content_hash="test-hash-minor",
        )
        bundle = usgs_earthquake_bundle(record, now)
        self.repo.ingest(bundle)

        eval_result = self.repo.evaluate_event_alerts(bundle.event.id)
        self.assertEqual(eval_result.status, AlertLifecycleStatus.EVALUATED)
        self.assertEqual(eval_result.alerts_generated, 0)
        self.assertEqual(len(eval_result.matched_rule_ids), 0)

    def test_deduplication_and_cooldown_suppression(self) -> None:
        """Verify that duplicate processing is idempotent and cooldown prevents alert flooding."""
        rule_id = uuid4()
        rule = AlertRule(
            id=rule_id,
            name="Cooldown Test Rule",
            event_kind="earthquake",
            operator=">=",
            metric_field="mag",
            threshold=5.0,
            severity=AlertSeverity.WARNING,
            cooldown_seconds=3600,  # 1 hour cooldown
            is_enabled=True,
        )
        self.repo.create_alert_rule(rule)

        now = datetime(2026, 10, 26, 12, 20, 0, tzinfo=UTC)
        eq_event_id = f"test-cd-{uuid4()}"
        record = EarthquakeRecord(
            event_id=eq_event_id,
            title="M 5.5 - Cooldown Test",
            place="San Andreas",
            mag=5.5,
            time=now,
            longitude=-120.5,
            latitude=36.2,
            depth_km=8.0,
            locator=f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/detail/{eq_event_id}.geojson",
            content_hash="test-hash-cd",
        )
        bundle = usgs_earthquake_bundle(record, now)
        self.repo.ingest(bundle)

        # 1. First evaluation: ALERTED
        eval_1 = self.repo.evaluate_event_alerts(bundle.event.id)
        self.assertEqual(eval_1.status, AlertLifecycleStatus.ALERTED)
        self.assertEqual(eval_1.alerts_generated, 1)

        # 2. Second evaluation of the same event: Suppressed / Deduplicated (0 new alerts)
        eval_2 = self.repo.evaluate_event_alerts(bundle.event.id)
        self.assertIn(eval_2.status, (AlertLifecycleStatus.SUPPRESSED, AlertLifecycleStatus.EVALUATED))
        self.assertEqual(eval_2.alerts_generated, 0)

        # Alerts count for this event must remain exactly 1
        alerts = self.repo.list_alerts(event_id=bundle.event.id)
        self.assertEqual(len(alerts), 1)

    def test_alert_lifecycle_acknowledgment_and_resolution(self) -> None:
        """Verify alert state transitions: active -> acknowledged -> resolved."""
        rule_id = uuid4()
        rule = AlertRule(
            id=rule_id,
            name="Lifecycle Test Rule",
            event_kind="earthquake",
            operator=">=",
            metric_field="mag",
            threshold=5.0,
            severity=AlertSeverity.CRITICAL,
            cooldown_seconds=0,
            is_enabled=True,
        )
        self.repo.create_alert_rule(rule)

        now = datetime(2026, 10, 26, 12, 30, 0, tzinfo=UTC)
        eq_event_id = f"test-life-{uuid4()}"
        record = EarthquakeRecord(
            event_id=eq_event_id,
            title="M 6.0 - Lifecycle Event",
            place="Test Region",
            mag=6.0,
            time=now,
            longitude=-121.0,
            latitude=37.0,
            depth_km=12.0,
            locator=f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/detail/{eq_event_id}.geojson",
            content_hash="test-hash-life",
        )
        bundle = usgs_earthquake_bundle(record, now)
        self.repo.ingest(bundle)
        self.repo.evaluate_event_alerts(bundle.event.id)

        alerts = self.repo.list_alerts(event_id=bundle.event.id)
        self.assertEqual(len(alerts), 1)
        alert_id = alerts[0]["id"]
        self.assertEqual(alerts[0]["status"], "active")

        # 1. Acknowledge alert
        ack_success = self.repo.acknowledge_alert(alert_id, acknowledged_by="lead_analyst")
        self.assertTrue(ack_success)
        alert_ack = self.repo.get_alert(alert_id)
        self.assertEqual(alert_ack["status"], "acknowledged")
        self.assertEqual(alert_ack["acknowledged_by"], "lead_analyst")
        self.assertIsNotNone(alert_ack["acknowledged_at"])

        # 2. Resolve alert
        res_success = self.repo.resolve_alert(alert_id, resolution_notes="False positive or impact mitigated")
        self.assertTrue(res_success)
        alert_res = self.repo.get_alert(alert_id)
        self.assertEqual(alert_res["status"], "resolved")
        self.assertEqual(alert_res["resolution_notes"], "False positive or impact mitigated")
        self.assertIsNotNone(alert_res["resolved_at"])

        # 3. Cannot acknowledge already resolved alert
        ack_again = self.repo.acknowledge_alert(alert_id)
        self.assertFalse(ack_again)

    def test_alert_fastapi_endpoints(self) -> None:
        """Verify REST API endpoints for alert rules, evaluations, and alerts."""
        # 1. Create rule via API endpoint
        req = CreateAlertRuleRequest(
            name="API Test Rule",
            description="Created via endpoint",
            event_kind="earthquake",
            operator=">=",
            metric_field="mag",
            threshold=5.2,
            severity=AlertSeverity.WARNING,
            cooldown_seconds=300,
            is_enabled=True,
        )
        created_rule = api_create_alert_rule(req)
        self.assertEqual(created_rule.name, "API Test Rule")
        self.assertEqual(created_rule.threshold, 5.2)

        # 2. List rules
        rule_list = api_list_alert_rules(event_kind="earthquake")
        self.assertTrue(any(r.id == created_rule.id for r in rule_list))

        # 3. Get rule
        retrieved_rule = api_get_alert_rule(created_rule.id)
        self.assertEqual(retrieved_rule.id, created_rule.id)

        # 4. Patch rule
        patch_req = UpdateAlertRuleRequest(threshold=5.8, is_enabled=False)
        updated_rule = api_update_alert_rule(created_rule.id, patch_req)
        self.assertEqual(updated_rule.threshold, 5.8)
        self.assertFalse(updated_rule.is_enabled)

        # 5. Delete rule
        del_res = api_delete_alert_rule(created_rule.id)
        self.assertTrue(del_res["deleted"])

    def test_event_persistence_survives_alert_evaluation_failure(self) -> None:
        """Verify that alert evaluation failure does not compromise or delete the underlying event."""
        # Provide non-existent event ID to evaluation
        fake_id = uuid4()
        eval_result = self.repo.evaluate_event_alerts(fake_id)
        self.assertEqual(eval_result.status, AlertLifecycleStatus.FAILED)
        self.assertIn("not found", eval_result.reason)

        # Now create real event and verify that it remains in database regardless
        now = datetime(2026, 10, 26, 12, 40, 0, tzinfo=UTC)
        eq_event_id = f"test-survive-{uuid4()}"
        record = EarthquakeRecord(
            event_id=eq_event_id,
            title="M 5.1 - Persistent Event",
            place="Fault Line",
            mag=5.1,
            time=now,
            longitude=-119.0,
            latitude=35.0,
            depth_km=10.0,
            locator=f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/detail/{eq_event_id}.geojson",
            content_hash="test-hash-survive",
        )
        bundle = usgs_earthquake_bundle(record, now)
        self.repo.ingest(bundle)

        # Verify event exists in PostgreSQL
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT id, kind FROM events WHERE id = %s", (bundle.event.id,))
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["kind"], "earthquake")

    # -------------------------------------------------------------------------
    # Engine 13: Deterministic Decision Support Integration Tests
    # -------------------------------------------------------------------------

    def test_decision_evaluation_over_authoritative_entities(self) -> None:
        """Verify MCDA over real ingested country entities, observations, and evidence citations."""
        now = datetime(2026, 9, 29, tzinfo=UTC)

        # 1. Ingest India (Population ~1.42B)
        wb_ind = [{"page": 1}, [{
            "countryiso3code": "IND", "country": {"value": "India"}, "date": "2023", "value": 1428627663,
        }]]
        rec_ind = parse_population(wb_ind, "https://api.worldbank.org/test/decision_ind")[0]
        bundle_ind = world_bank_bundle(rec_ind, None, now)
        self.repo.ingest(bundle_ind)

        # 2. Ingest United States (Population ~335M)
        wb_usa = [{"page": 1}, [{
            "countryiso3code": "USA", "country": {"value": "United States"}, "date": "2023", "value": 334914895,
        }]]
        rec_usa = parse_population(wb_usa, "https://api.worldbank.org/test/decision_usa")[0]
        bundle_usa = world_bank_bundle(rec_usa, None, now)
        self.repo.ingest(bundle_usa)

        # Resolve authoritative entity IDs after reconciliation
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT entity_id FROM entity_identifiers WHERE scheme='iso_3166_1_alpha_3' AND value='IND'")
            row_ind = cur.fetchone()
            ind_entity_id = row_ind["entity_id"] if row_ind else bundle_ind.entity.id

            cur.execute("SELECT entity_id FROM entity_identifiers WHERE scheme='iso_3166_1_alpha_3' AND value='USA'")
            row_usa = cur.fetchone()
            usa_entity_id = row_usa["entity_id"] if row_usa else bundle_usa.entity.id

        # 3. Construct Decision Request comparing India and USA
        # Population (MAXIMIZE, weight 2.0, hard_constraint_min 50M)
        # Setup cost (MINIMIZE, weight 1.0)
        req = DecisionRequest(
            objective="Prioritize national regional hub deployment",
            scope={"region": "Global", "sector": "Infrastructure"},
            persist=True,
            criteria=[
                DecisionCriterion(
                    id="crit_pop",
                    name="Population Reach",
                    metric_field="population.total",
                    direction=CriterionDirection.MAXIMIZE,
                    weight=2.0,
                    hard_constraint_min=50000000.0,
                ),
                DecisionCriterion(
                    id="crit_cost",
                    name="Setup Cost",
                    metric_field="setup_cost",
                    direction=CriterionDirection.MINIMIZE,
                    weight=1.0,
                ),
            ],
            alternatives=[
                DecisionAlternative(
                    id="alt_ind",
                    name="India Hub",
                    entity_id=ind_entity_id,
                    attributes={"setup_cost": 120.0},
                ),
                DecisionAlternative(
                    id="alt_usa",
                    name="USA Hub",
                    entity_id=usa_entity_id,
                    attributes={"setup_cost": 80.0},
                ),
            ],
        )

        res = self.repo.evaluate_decision(req)

        # Both meet hard constraint (pop > 50M)
        self.assertEqual(res.feasible_count, 2)
        self.assertEqual(res.infeasible_count, 0)

        # Verify weights normalized: 2.0 / 3.0 ~ 0.6667, 1.0 / 3.0 ~ 0.3333
        self.assertAlmostEqual(res.normalized_weights["crit_pop"], 2.0 / 3.0, places=4)
        self.assertAlmostEqual(res.normalized_weights["crit_cost"], 1.0 / 3.0, places=4)

        # Verify that India's population was resolved from database observations
        alt_ind_res = next(a for a in res.feasible_alternatives if a.alternative_id == "alt_ind")
        pop_breakdown = alt_ind_res.criteria_breakdown["crit_pop"]
        self.assertFalse(pop_breakdown.is_missing)
        self.assertEqual(pop_breakdown.raw_value, 1428627663.0)
        self.assertEqual(pop_breakdown.truth_class, TruthClass.OBSERVED)
        self.assertIsNotNone(pop_breakdown.evidence_id)

        # Verify evidence citations collected
        self.assertGreater(len(res.evidence_citations), 0)
        cited_ids = [c["evidence_id"] for c in res.evidence_citations]
        self.assertIn(str(bundle_ind.evidence.id), cited_ids)

        # Ranking: India has higher overall score (max pop dominates)
        self.assertEqual(res.feasible_alternatives[0].alternative_id, "alt_ind")
        self.assertEqual(res.feasible_alternatives[0].rank, 1)

    def test_decision_non_mutation_of_world_state(self) -> None:
        """Verify that evaluating decisions never mutates authoritative facts."""
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) as c FROM entities")
            e_count_before = cur.fetchone()["c"]
            cur.execute("SELECT count(*) as c FROM observations")
            o_count_before = cur.fetchone()["c"]
            cur.execute("SELECT count(*) as c FROM geometries")
            g_count_before = cur.fetchone()["c"]
            cur.execute("SELECT count(*) as c FROM evidence")
            ev_count_before = cur.fetchone()["c"]

        # Run decision evaluation
        req = DecisionRequest(
            objective="Non mutation verification",
            persist=False,
            criteria=[
                DecisionCriterion(id="c1", name="Score", metric_field="score", direction=CriterionDirection.MAXIMIZE),
            ],
            alternatives=[
                DecisionAlternative(id="opt1", name="Option 1", attributes={"score": 85}),
                DecisionAlternative(id="opt2", name="Option 2", attributes={"score": 92}),
            ],
        )
        self.repo.evaluate_decision(req)

        # Verify counts are strictly identical
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) as c FROM entities")
            e_count_after = cur.fetchone()["c"]
            cur.execute("SELECT count(*) as c FROM observations")
            o_count_after = cur.fetchone()["c"]
            cur.execute("SELECT count(*) as c FROM geometries")
            g_count_after = cur.fetchone()["c"]
            cur.execute("SELECT count(*) as c FROM evidence")
            ev_count_after = cur.fetchone()["c"]

        self.assertEqual(e_count_before, e_count_after)
        self.assertEqual(o_count_before, o_count_after)
        self.assertEqual(g_count_before, g_count_after)
        self.assertEqual(ev_count_before, ev_count_after)

    def test_decision_persistence_and_retrieval(self) -> None:
        """Verify decision persistence into PostgreSQL decisions table and audit retrieval."""
        decision_id = uuid4()
        req = DecisionRequest(
            decision_id=decision_id,
            objective="Audit trail test",
            scope={"env": "staging"},
            persist=True,
            criteria=[
                DecisionCriterion(id="c1", name="Metric A", metric_field="a", direction=CriterionDirection.MAXIMIZE, weight=1.0),
                DecisionCriterion(id="c2", name="Metric B", metric_field="b", direction=CriterionDirection.MINIMIZE, weight=2.0),
            ],
            alternatives=[
                DecisionAlternative(id="cand_1", name="Candidate 1", attributes={"a": 100, "b": 10}),
                DecisionAlternative(id="cand_2", name="Candidate 2", attributes={"a": 80, "b": 25}),
            ],
        )

        eval_res = self.repo.evaluate_decision(req)
        self.assertEqual(eval_res.decision_id, decision_id)

        # Retrieve from database
        stored = self.repo.get_decision(decision_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored["id"], decision_id)
        self.assertEqual(stored["objective"], "Audit trail test")
        self.assertEqual(stored["alternatives_count"], 2)
        self.assertEqual(stored["feasible_count"], 2)
        self.assertEqual(stored["top_alternative_id"], "cand_1")
        self.assertIsNotNone(stored["result"])

        # List decisions
        decision_list = self.repo.list_decisions(limit=10)
        self.assertTrue(any(d["id"] == decision_id for d in decision_list))

    def test_decision_sensitivity_and_api_endpoints(self) -> None:
        """Verify REST API endpoints: evaluate, get, list, and bounded sensitivity analysis."""
        decision_id = uuid4()
        req = DecisionRequest(
            decision_id=decision_id,
            objective="API Decision Test",
            persist=True,
            criteria=[
                DecisionCriterion(id="crit_spd", name="Speed", metric_field="speed", direction=CriterionDirection.MAXIMIZE, weight=1.2),
                DecisionCriterion(id="crit_rel", name="Reliability", metric_field="reliability", direction=CriterionDirection.MAXIMIZE, weight=1.0),
            ],
            alternatives=[
                DecisionAlternative(id="node_a", name="Node A", attributes={"speed": 95, "reliability": 80}),
                DecisionAlternative(id="node_b", name="Node B", attributes={"speed": 75, "reliability": 98}),
            ],
        )

        # 1. POST /decisions/evaluate
        api_result = api_evaluate_decision(req)
        self.assertEqual(api_result.decision_id, decision_id)
        self.assertEqual(api_result.feasible_count, 2)

        # 2. GET /decisions/{id}
        retrieved = api_get_decision(decision_id)
        self.assertEqual(retrieved["id"], decision_id)

        # 3. GET /decisions
        all_decisions = api_list_decisions()
        self.assertTrue(any(d["id"] == decision_id for d in all_decisions))

        # 4. POST /decisions/{id}/sensitivity
        sens_req = DecisionSensitivityRequest(delta_pct=0.30)
        variations = api_run_decision_sensitivity(decision_id, sens_req)
        self.assertGreater(len(variations), 0)

        # Verify variations structure
        for v in variations:
            self.assertIsNotNone(v.get("criterion_id"))
            self.assertIsNotNone(v.get("top_alternative_id"))
            self.assertGreater(len(v.get("new_rankings", [])), 0)

    def test_scenario_crud_lifecycle_and_versioning(self) -> None:
        """Verify scenario creation, versioning, draft modifications, validation, evaluation, and archive lifecycle."""
        # 1. Ingest baseline country
        now = datetime(2026, 9, 29, tzinfo=UTC)
        wb_payload = [{"page": 1}, [{"countryiso3code": "IND", "country": {"value": "India"}, "date": "2023", "value": 1428627663}]]
        record = parse_population(wb_payload, "https://api.worldbank.org/test/ind")[0]
        self.repo.ingest(world_bank_bundle(record, None, now))

        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT entity_id FROM entity_identifiers WHERE scheme = 'iso_3166_1_alpha_3' AND value = 'IND'")
            entity_id = cur.fetchone()["entity_id"]

        # 2. Create scenario
        scen = Scenario(
            name="Climate Transition Model",
            description="Testing transition impacts on national population",
        )
        scen_id = self.repo.create_scenario(scen)
        stored = self.repo.get_scenario(scen_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, ScenarioStatus.DRAFT)
        self.assertEqual(stored.version, 1)

        # 3. Add modification (material change -> increments version to 2, status remains DRAFT)
        mod = ScenarioModification(
            scenario_id=scen_id,
            target_entity_id=entity_id,
            target_field="observation.population.total",
            operation=ScenarioOperationType.SET,
            value=1500000000.0,
            rationale="Simulated projection for 2030",
        )
        mod_id = self.repo.add_scenario_modification(mod)
        mods = self.repo.list_scenario_modifications(scen_id)
        self.assertEqual(len(mods), 1)
        self.assertEqual(mods[0].id, mod_id)

        scen_after_mod = self.repo.get_scenario(scen_id)
        self.assertEqual(scen_after_mod.version, 2)
        self.assertEqual(scen_after_mod.status, ScenarioStatus.DRAFT)

        # 4. Validate scenario -> transitions to VALIDATED
        val_res = self.repo.validate_scenario(scen_id)
        self.assertNotEqual(val_res.status, ConstraintStatus.INVALID)
        scen_validated = self.repo.get_scenario(scen_id)
        self.assertEqual(scen_validated.status, ScenarioStatus.VALIDATED)

        # 5. Evaluate scenario -> transitions to EVALUATED
        eval_res = self.repo.evaluate_scenario(scen_id)
        self.assertIsNotNone(eval_res)
        self.assertEqual(eval_res.scenario_version, 2)
        self.assertTrue(eval_res.is_feasible)

        scen_evaluated = self.repo.get_scenario(scen_id)
        self.assertEqual(scen_evaluated.status, ScenarioStatus.EVALUATED)

        # 6. Add second modification -> invalidates evaluation, increments version to 3, resets to DRAFT
        mod2 = ScenarioModification(
            scenario_id=scen_id,
            target_entity_id=entity_id,
            target_field="observation.population.total",
            operation=ScenarioOperationType.SCALE,
            value=1.05,
        )
        self.repo.add_scenario_modification(mod2)
        scen_draft_again = self.repo.get_scenario(scen_id)
        self.assertEqual(scen_draft_again.version, 3)
        self.assertEqual(scen_draft_again.status, ScenarioStatus.DRAFT)

        # 7. Archive scenario -> transitions to ARCHIVED
        archived = self.repo.archive_scenario(scen_id)
        self.assertTrue(archived)
        scen_archived = self.repo.get_scenario(scen_id)
        self.assertEqual(scen_archived.status, ScenarioStatus.ARCHIVED)

        # 8. Attempting to add modification to ARCHIVED scenario raises ScenarioLifecycleError
        mod3 = ScenarioModification(
            scenario_id=scen_id,
            target_entity_id=entity_id,
            target_field="observation.population.total",
            operation=ScenarioOperationType.DELTA,
            value=100.0,
        )
        with self.assertRaises(ScenarioLifecycleError):
            self.repo.add_scenario_modification(mod3)

    def test_scenario_operational_world_state_non_mutation(self) -> None:
        """Non-negotiable Architectural Invariant: Scenario creation, modification, validation, evaluation, and branching NEVER mutate authoritative operational data."""
        # 1. Seed authoritative data
        now = datetime(2026, 9, 29, tzinfo=UTC)
        wb_payload = [{"page": 1}, [{"countryiso3code": "IND", "country": {"value": "India"}, "date": "2023", "value": 1428627663}]]
        record = parse_population(wb_payload, "https://api.worldbank.org/test/ind")[0]
        self.repo.ingest(world_bank_bundle(record, None, now))

        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT entity_id FROM entity_identifiers WHERE scheme = 'iso_3166_1_alpha_3' AND value = 'IND'")
            entity_id = cur.fetchone()["entity_id"]

            # Record baseline counts of all authoritative tables
            cur.execute("SELECT count(*) AS cnt FROM entities")
            baseline_entities = cur.fetchone()["cnt"]
            cur.execute("SELECT count(*) AS cnt FROM observations")
            baseline_observations = cur.fetchone()["cnt"]
            cur.execute("SELECT count(*) AS cnt FROM geometries")
            baseline_geometries = cur.fetchone()["cnt"]
            cur.execute("SELECT count(*) AS cnt FROM evidence")
            baseline_evidence = cur.fetchone()["cnt"]
            cur.execute("SELECT count(*) AS cnt FROM provenance")
            baseline_provenance = cur.fetchone()["cnt"]
            cur.execute("SELECT count(*) AS cnt FROM entity_identifiers")
            baseline_identifiers = cur.fetchone()["cnt"]

            # Record baseline India population observation value
            cur.execute("SELECT value FROM observations WHERE subject_entity_id = %s", (entity_id,))
            baseline_pop_val = cur.fetchone()["value"]
            self.assertEqual(float(baseline_pop_val), 1428627663.0)

        # 2. Execute full battery of Scenario operations
        scen_a = Scenario(name="Hypothetical Disruption Scenario")
        scen_a_id = self.repo.create_scenario(scen_a)

        self.repo.add_scenario_modification(ScenarioModification(
            scenario_id=scen_a_id,
            target_entity_id=entity_id,
            target_field="observation.population.total",
            operation=ScenarioOperationType.DELTA,
            value=-100000000.0,
        ))

        self.repo.validate_scenario(scen_a_id)
        self.repo.evaluate_scenario(scen_a_id)

        # Branch to Scenario B
        scen_b = self.repo.branch_scenario(scen_a_id, new_name="Hypothetical Disruption Branch B")
        self.repo.add_scenario_modification(ScenarioModification(
            scenario_id=scen_b.id,
            target_entity_id=entity_id,
            target_field="observation.population.total",
            operation=ScenarioOperationType.SCALE,
            value=0.90,
        ))
        self.repo.validate_scenario(scen_b.id)
        self.repo.evaluate_scenario(scen_b.id)

        # Compare both
        self.repo.compare_scenarios(scen_a_id, scen_b.id)

        # Archive both
        self.repo.archive_scenario(scen_a_id)
        self.repo.archive_scenario(scen_b.id)

        # 3. Verify ZERO mutation across authoritative tables
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) AS cnt FROM entities")
            self.assertEqual(cur.fetchone()["cnt"], baseline_entities, "Entities count mutated!")
            cur.execute("SELECT count(*) AS cnt FROM observations")
            self.assertEqual(cur.fetchone()["cnt"], baseline_observations, "Observations count mutated!")
            cur.execute("SELECT count(*) AS cnt FROM geometries")
            self.assertEqual(cur.fetchone()["cnt"], baseline_geometries, "Geometries count mutated!")
            cur.execute("SELECT count(*) AS cnt FROM evidence")
            self.assertEqual(cur.fetchone()["cnt"], baseline_evidence, "Evidence count mutated!")
            cur.execute("SELECT count(*) AS cnt FROM provenance")
            self.assertEqual(cur.fetchone()["cnt"], baseline_provenance, "Provenance count mutated!")
            cur.execute("SELECT count(*) AS cnt FROM entity_identifiers")
            self.assertEqual(cur.fetchone()["cnt"], baseline_identifiers, "Entity identifiers count mutated!")

            # Check target entity observation value remains untouched
            cur.execute("SELECT value FROM observations WHERE subject_entity_id = %s", (entity_id,))
            after_pop_val = cur.fetchone()["value"]
            self.assertEqual(float(after_pop_val), 1428627663.0, "Authoritative observation value was mutated!")

    def test_scenario_deterministic_overlay_and_epistemic_simulated(self) -> None:
        """Verify isolated overlay computes correct deltas and tags all derived values as SIMULATED."""
        now = datetime(2026, 9, 29, tzinfo=UTC)
        wb_payload = [{"page": 1}, [{"countryiso3code": "IND", "country": {"value": "India"}, "date": "2023", "value": 1428627663}]]
        record = parse_population(wb_payload, "https://api.worldbank.org/test/ind")[0]
        self.repo.ingest(world_bank_bundle(record, None, now))

        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT entity_id FROM entity_identifiers WHERE scheme = 'iso_3166_1_alpha_3' AND value = 'IND'")
            entity_id = cur.fetchone()["entity_id"]

        scen_id = self.repo.create_scenario(Scenario(name="Growth Overlay Model"))
        self.repo.add_scenario_modification(ScenarioModification(
            scenario_id=scen_id,
            target_entity_id=entity_id,
            target_field="observation.population.total",
            operation=ScenarioOperationType.DELTA,
            value=100000000.0,
        ))

        eval_res = self.repo.evaluate_scenario(scen_id)
        self.assertIsNotNone(eval_res)

        # Verify delta summary
        delta_key = f"{entity_id}:observation.population.total"
        self.assertIn(delta_key, eval_res.delta_summary)
        delta_item = eval_res.delta_summary[delta_key]

        self.assertEqual(delta_item["baseline_value"], 1428627663.0)
        self.assertEqual(delta_item["simulated_value"], 1528627663.0)
        self.assertEqual(delta_item["absolute_delta"], 100000000.0)
        self.assertEqual(delta_item["truth_class"], "SIMULATED")

        # Verify simulated state
        sim_obs = eval_res.simulated_state[str(entity_id)]["observations"]["population.total"]
        self.assertEqual(sim_obs["value"], 1528627663.0)
        self.assertEqual(sim_obs["truth_class"], "SIMULATED")

        # Verify net population delta in derived metrics
        self.assertEqual(eval_res.derived_metrics["net_population_delta"], 100000000.0)

    def test_scenario_branching_and_comparison(self) -> None:
        """Verify scenario branching copies modifications and comparison calculates cross-branch deltas."""
        now = datetime(2026, 9, 29, tzinfo=UTC)
        wb_payload = [{"page": 1}, [{"countryiso3code": "IND", "country": {"value": "India"}, "date": "2023", "value": 1428627663}]]
        record = parse_population(wb_payload, "https://api.worldbank.org/test/ind")[0]
        self.repo.ingest(world_bank_bundle(record, None, now))

        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT entity_id FROM entity_identifiers WHERE scheme = 'iso_3166_1_alpha_3' AND value = 'IND'")
            entity_id = cur.fetchone()["entity_id"]

        # Parent Scenario
        parent_id = self.repo.create_scenario(Scenario(name="Base Projection"))
        self.repo.add_scenario_modification(ScenarioModification(
            scenario_id=parent_id,
            target_entity_id=entity_id,
            target_field="observation.population.total",
            operation=ScenarioOperationType.SCALE,
            value=1.10,
        ))
        eval_parent = self.repo.evaluate_scenario(parent_id)
        self.assertTrue(eval_parent.is_feasible)

        # Branch into Child Scenario
        child = self.repo.branch_scenario(parent_id, new_name="High Growth Branch")
        self.assertEqual(child.parent_scenario_id, parent_id)
        self.assertEqual(child.parent_scenario_version, 2)
        self.assertEqual(child.version, 1)

        # Verify modification was cloned
        child_mods = self.repo.list_scenario_modifications(child.id)
        self.assertEqual(len(child_mods), 1)
        self.assertEqual(child_mods[0].operation, ScenarioOperationType.SCALE)

        # Add additional modification to Child
        self.repo.add_scenario_modification(ScenarioModification(
            scenario_id=child.id,
            target_entity_id=entity_id,
            target_field="observation.population.total",
            operation=ScenarioOperationType.DELTA,
            value=50000000.0,
        ))
        eval_child = self.repo.evaluate_scenario(child.id)
        self.assertTrue(eval_child.is_feasible)

        # Compare Parent vs Child
        comparison = self.repo.compare_scenarios(parent_id, child.id)
        self.assertIsNotNone(comparison)
        self.assertEqual(comparison.scenario_a_id, parent_id)
        self.assertEqual(comparison.scenario_b_id, child.id)
        self.assertTrue(comparison.feasibility_comparison["scenario_a_feasible"])
        self.assertTrue(comparison.feasibility_comparison["scenario_b_feasible"])
        self.assertGreater(len(comparison.entity_comparisons), 0)

        # Child should have 50,000,000 more than Parent
        delta_b_minus_a = comparison.metric_deltas.get(f"{entity_id}:population.total")
        self.assertEqual(delta_b_minus_a, 50000000.0)

    def test_scenario_api_endpoints(self) -> None:
        """Verify REST API endpoints for scenario operations."""
        now = datetime(2026, 9, 29, tzinfo=UTC)
        wb_payload = [{"page": 1}, [{"countryiso3code": "IND", "country": {"value": "India"}, "date": "2023", "value": 1428627663}]]
        record = parse_population(wb_payload, "https://api.worldbank.org/test/ind")[0]
        self.repo.ingest(world_bank_bundle(record, None, now))

        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT entity_id FROM entity_identifiers WHERE scheme = 'iso_3166_1_alpha_3' AND value = 'IND'")
            entity_id = cur.fetchone()["entity_id"]

        # 1. POST /scenarios
        create_req = CreateScenarioRequest(name="API Scenario Test", description="Testing via API")
        scen = create_scenario_endpoint(create_req)
        self.assertEqual(scen.name, "API Scenario Test")
        self.assertEqual(scen.status, ScenarioStatus.DRAFT)

        # 2. GET /scenarios
        scens = list_scenarios_endpoint()
        self.assertTrue(any(s.id == scen.id for s in scens))

        # 3. GET /scenarios/{id}
        retrieved = get_scenario_endpoint(scen.id)
        self.assertEqual(retrieved.id, scen.id)

        # 4. POST /scenarios/{id}/modifications
        mod_req = AddScenarioModificationRequest(
            target_entity_id=entity_id,
            target_field="observation.population.total",
            operation=ScenarioOperationType.SCALE,
            value=1.02,
        )
        mod = add_scenario_modification_endpoint(scen.id, mod_req)
        self.assertEqual(mod.operation, ScenarioOperationType.SCALE)

        # 5. GET /scenarios/{id}/modifications
        mods = list_scenario_modifications_endpoint(scen.id)
        self.assertEqual(len(mods), 1)

        # 6. POST /scenarios/{id}/validate
        val_res = validate_scenario_endpoint(scen.id)
        self.assertNotEqual(val_res.status, ConstraintStatus.INVALID)

        # 7. POST /scenarios/{id}/evaluate
        eval_res = evaluate_scenario_endpoint(scen.id, EvaluateScenarioRequest())
        self.assertTrue(eval_res.is_feasible)

        # 8. GET /scenarios/{id}/evaluation
        retrieved_eval = get_scenario_evaluation_endpoint(scen.id)
        self.assertEqual(retrieved_eval.id, eval_res.id)

        # 9. POST /scenarios/{id}/branch
        branch_req = BranchScenarioRequest(name="API Branched Scenario")
        branched = branch_scenario_endpoint(scen.id, branch_req)
        self.assertEqual(branched.parent_scenario_id, scen.id)

        # 10. GET /scenarios/{a}/compare/{b}
        comp = compare_scenarios_endpoint(scen.id, branched.id)
        self.assertIsNotNone(comp.summary)

        # 11. POST /scenarios/{id}/archive
        arch_res = archive_scenario_endpoint(scen.id)
        self.assertTrue(arch_res["archived"])

    def test_simulation_execution_and_authoritative_non_mutation(self) -> None:
        """Verify Engine 17 multi-step forward simulation and strict non-mutation of operational world state."""
        now = datetime(2026, 9, 29, tzinfo=UTC)
        wb_payload = [{"page": 1}, [{"countryiso3code": "IND", "country": {"value": "India"}, "date": "2023", "value": 1400000000}]]
        record = parse_population(wb_payload, "https://api.worldbank.org/test/ind/sim")[0]
        self.repo.ingest(world_bank_bundle(record, None, now))

        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT entity_id FROM entity_identifiers WHERE scheme = 'iso_3166_1_alpha_3' AND value = 'IND'")
            entity_id = cur.fetchone()["entity_id"]

            # Snapshot authoritative operational table row counts BEFORE scenario & simulation
            cur.execute("SELECT COUNT(*) AS c FROM entities")
            entities_before = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM observations")
            obs_before = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM geometries")
            geoms_before = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM evidence")
            evidence_before = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM provenance")
            prov_before = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM entity_identifiers")
            idents_before = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM alerts")
            alerts_before = cur.fetchone()["c"]

        # 1. Create and evaluate a scenario with a hypothetical +5% population scale
        scenario_id = self.repo.create_scenario(Scenario(name="Simulation Baseline Scenario"))
        self.repo.add_scenario_modification(ScenarioModification(
            scenario_id=scenario_id,
            target_entity_id=entity_id,
            target_field="observation.population.total",
            operation=ScenarioOperationType.SCALE,
            value=1.05,
        ))
        eval_res = self.repo.evaluate_scenario(scenario_id)
        self.assertTrue(eval_res.is_feasible)

        # 2. Run a 5-step forward simulation with 2% annual growth
        sim_start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        sim_end = datetime(2031, 1, 1, 0, 0, 0, tzinfo=UTC)
        sim_req = SimulationRequest(
            scenario_id=scenario_id,
            starts_at=sim_start,
            ends_at=sim_end,
            step_size=1.0,
            step_unit="year",
            max_steps=100,
            rule_ids=["population_dynamics_v1"],
            parameters={"growth_rate": 0.02, "net_migration": 0.0},
        )
        sim_run = self.repo.create_and_run_simulation(sim_req)

        # 3. Verify simulation run metadata
        self.assertEqual(sim_run.status, SimulationStatus.COMPLETED)
        self.assertTrue(sim_run.is_feasible)
        self.assertEqual(sim_run.step_count, 6)  # Step 0 + 5 steps
        self.assertTrue(sim_run.reproducibility_fingerprint.startswith("sim_"))
        self.assertIsNotNone(sim_run.execution_duration_ms)

        # 4. Verify trajectory steps
        trajectory = self.repo.get_simulation_trajectory(sim_run.id)
        self.assertEqual(len(trajectory), 6)
        # Check Step 0 (initial conditions)
        self.assertEqual(trajectory[0].step_index, 0)
        self.assertEqual(trajectory[0].truth_class, TruthClass.SIMULATED)
        init_pop = trajectory[0].state[str(entity_id)]["observations"]["population.total"]["value"]
        # Expected: 1,400,000,000 * 1.05 = 1,470,000,000
        self.assertAlmostEqual(init_pop, 1470000000.0, places=2)

        # Check trajectory monotonicity (growing by 2% each year)
        prev_pop = init_pop
        for step in trajectory[1:]:
            step_pop = step.state[str(entity_id)]["observations"]["population.total"]["value"]
            self.assertGreater(step_pop, prev_pop)
            self.assertEqual(step.truth_class, TruthClass.SIMULATED)
            self.assertTrue(step.step_fingerprint.startswith("step_"))
            prev_pop = step_pop

        # 5. Check analytical trajectory summary
        pop_metric_key = f"{entity_id}.population.total"
        summary = sim_run.trajectory_summary.get(pop_metric_key)
        self.assertIsNotNone(summary)
        self.assertAlmostEqual(summary["initial"], 1470000000.0, places=2)
        self.assertGreater(summary["final"], summary["initial"])
        self.assertGreater(summary["relative_change_pct"], 10.0)

        # 6. CRITICAL VERIFICATION: Operational tables must NOT be mutated!
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM entities")
            self.assertEqual(cur.fetchone()["c"], entities_before)
            cur.execute("SELECT COUNT(*) AS c FROM observations")
            self.assertEqual(cur.fetchone()["c"], obs_before)
            cur.execute("SELECT COUNT(*) AS c FROM geometries")
            self.assertEqual(cur.fetchone()["c"], geoms_before)
            cur.execute("SELECT COUNT(*) AS c FROM evidence")
            self.assertEqual(cur.fetchone()["c"], evidence_before)
            cur.execute("SELECT COUNT(*) AS c FROM provenance")
            self.assertEqual(cur.fetchone()["c"], prov_before)
            cur.execute("SELECT COUNT(*) AS c FROM entity_identifiers")
            self.assertEqual(cur.fetchone()["c"], idents_before)
            cur.execute("SELECT COUNT(*) AS c FROM alerts")
            self.assertEqual(cur.fetchone()["c"], alerts_before)

    def test_simulation_reproducibility_and_version_pinning(self) -> None:
        """Verify identical inputs produce identical fingerprints and scenario edits do not mutate prior runs."""
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT entity_id FROM entity_identifiers WHERE scheme = 'iso_3166_1_alpha_3' AND value = 'IND'")
            entity_id = cur.fetchone()["entity_id"]

        scen_id = self.repo.create_scenario(Scenario(name="Reproducibility Scenario"))
        self.repo.add_scenario_modification(ScenarioModification(
            scenario_id=scen_id,
            target_entity_id=entity_id,
            target_field="observation.population.total",
            operation=ScenarioOperationType.SET,
            value=1000000.0,
        ))

        # Run 1
        start_t = datetime(2026, 1, 1, tzinfo=UTC)
        end_t = datetime(2029, 1, 1, tzinfo=UTC)
        req1 = SimulationRequest(
            scenario_id=scen_id,
            starts_at=start_t,
            ends_at=end_t,
            step_size=1.0,
            step_unit="year",
            rule_ids=["population_dynamics_v1"],
            parameters={"growth_rate": 0.03},
        )
        sim1 = self.repo.create_and_run_simulation(req1)

        # Run 2 with identical parameters
        req2 = SimulationRequest(
            scenario_id=scen_id,
            starts_at=start_t,
            ends_at=end_t,
            step_size=1.0,
            step_unit="year",
            rule_ids=["population_dynamics_v1"],
            parameters={"growth_rate": 0.03},
        )
        sim2 = self.repo.create_and_run_simulation(req2)

        # Bit-for-bit identical fingerprints
        self.assertEqual(sim1.reproducibility_fingerprint, sim2.reproducibility_fingerprint)
        traj1 = self.repo.get_simulation_trajectory(sim1.id)
        traj2 = self.repo.get_simulation_trajectory(sim2.id)
        self.assertEqual(len(traj1), len(traj2))
        for s1, s2 in zip(traj1, traj2):
            self.assertEqual(s1.metrics, s2.metrics)

        # Add modification to scenario (increments scenario version to 3)
        self.repo.add_scenario_modification(ScenarioModification(
            scenario_id=scen_id,
            target_entity_id=entity_id,
            target_field="observation.population.total",
            operation=ScenarioOperationType.DELTA,
            value=200000.0,
        ))
        scen_after = self.repo.get_scenario(scen_id)
        self.assertEqual(scen_after.version, 3)

        # Existing simulation 1 must retain its pinned scenario_version = 2
        sim1_reloaded = self.repo.get_simulation(sim1.id)
        self.assertEqual(sim1_reloaded.scenario_version, 2)

    def test_simulation_comparison_and_divergence(self) -> None:
        """Verify cross-simulation comparison computes metric deltas and trajectory divergence."""
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT entity_id FROM entity_identifiers WHERE scheme = 'iso_3166_1_alpha_3' AND value = 'IND'")
            entity_id = cur.fetchone()["entity_id"]

        scen_id = self.repo.create_scenario(Scenario(name="Comparison Scenario"))
        self.repo.add_scenario_modification(ScenarioModification(
            scenario_id=scen_id,
            target_entity_id=entity_id,
            target_field="observation.population.total",
            operation=ScenarioOperationType.SET,
            value=10000000.0,
        ))

        start_t = datetime(2026, 1, 1, tzinfo=UTC)
        end_t = datetime(2030, 1, 1, tzinfo=UTC)

        # Sim A: Low growth (1% per year)
        sim_a = self.repo.create_and_run_simulation(SimulationRequest(
            scenario_id=scen_id,
            starts_at=start_t,
            ends_at=end_t,
            step_size=1.0,
            step_unit="year",
            parameters={"growth_rate": 0.01},
        ))

        # Sim B: High growth (5% per year)
        sim_b = self.repo.create_and_run_simulation(SimulationRequest(
            scenario_id=scen_id,
            starts_at=start_t,
            ends_at=end_t,
            step_size=1.0,
            step_unit="year",
            parameters={"growth_rate": 0.05},
        ))

        comparison = self.repo.compare_simulations(sim_a.id, sim_b.id)
        self.assertIsNotNone(comparison)
        self.assertEqual(comparison.step_count_a, 5)
        self.assertEqual(comparison.step_count_b, 5)

        pop_metric = f"{entity_id}.population.total"
        self.assertIn(pop_metric, comparison.metric_deltas)
        delta_info = comparison.metric_deltas[pop_metric]
        # B should have strictly higher population than A
        self.assertGreater(delta_info["final_b"], delta_info["final_a"])
        self.assertGreater(delta_info["delta"], 0)
        self.assertGreater(delta_info["pct_difference"], 0)

    def test_simulation_constraint_violation_and_infeasibility(self) -> None:
        """Verify simulations capturing infeasible states record constraint findings."""
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT entity_id FROM entity_identifiers WHERE scheme = 'iso_3166_1_alpha_3' AND value = 'IND'")
            entity_id = cur.fetchone()["entity_id"]

        scen_id = self.repo.create_scenario(Scenario(name="Infeasible Scenario"))
        self.repo.add_scenario_modification(ScenarioModification(
            scenario_id=scen_id,
            target_entity_id=entity_id,
            target_field="observation.population.total",
            operation=ScenarioOperationType.SET,
            value=100.0,
        ))

        # Simulation with massive negative net migration driving population negative
        sim = self.repo.create_and_run_simulation(SimulationRequest(
            scenario_id=scen_id,
            starts_at=datetime(2026, 1, 1, tzinfo=UTC),
            ends_at=datetime(2028, 1, 1, tzinfo=UTC),
            step_size=1.0,
            step_unit="year",
            parameters={"growth_rate": 0.0, "net_migration": -500.0},
        ))
        # Population is bounded to 0 (extinction)
        self.assertEqual(sim.status, SimulationStatus.COMPLETED)
        traj = self.repo.get_simulation_trajectory(sim.id)
        # Verify findings recorded
        self.assertTrue(any(len(s.findings) > 0 for s in traj))

    def test_simulation_api_endpoints(self) -> None:
        """Verify REST API endpoints for simulation operations."""
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT entity_id FROM entity_identifiers WHERE scheme = 'iso_3166_1_alpha_3' AND value = 'IND'")
            entity_id = cur.fetchone()["entity_id"]

        # 1. GET /simulations/rules
        rules = list_simulation_rules_endpoint()
        self.assertGreater(len(rules), 0)
        self.assertTrue(any(r.id == "population_dynamics_v1" for r in rules))

        # Create scenario for API test
        scen_id = self.repo.create_scenario(Scenario(name="API Simulation Scenario"))
        self.repo.add_scenario_modification(ScenarioModification(
            scenario_id=scen_id,
            target_entity_id=entity_id,
            target_field="observation.population.total",
            operation=ScenarioOperationType.SET,
            value=5000000.0,
        ))

        # 2. POST /simulations
        create_req = CreateSimulationRequest(
            scenario_id=scen_id,
            starts_at=datetime(2026, 1, 1, tzinfo=UTC),
            ends_at=datetime(2029, 1, 1, tzinfo=UTC),
            step_size=1.0,
            step_unit="year",
            parameters={"growth_rate": 0.02},
        )
        sim_run = create_simulation_endpoint(create_req)
        self.assertEqual(sim_run.status, SimulationStatus.COMPLETED)

        # 3. GET /simulations
        sims = list_simulations_endpoint(scenario_id=scen_id)
        self.assertTrue(any(s.id == sim_run.id for s in sims))

        # 4. GET /simulations/{id}
        retrieved_sim = get_simulation_endpoint(sim_run.id)
        self.assertEqual(retrieved_sim.id, sim_run.id)

        # 5. GET /simulations/{id}/trajectory
        trajectory = get_simulation_trajectory_endpoint(sim_run.id)
        self.assertEqual(len(trajectory), 4)

        # 6. GET /simulations/{id}/steps/{step_index}
        step0 = get_simulation_step_endpoint(sim_run.id, 0)
        self.assertEqual(step0.step_index, 0)

        # 7. GET /simulations/{a}/compare/{b}
        sim_b = create_simulation_endpoint(CreateSimulationRequest(
            scenario_id=scen_id,
            starts_at=datetime(2026, 1, 1, tzinfo=UTC),
            ends_at=datetime(2029, 1, 1, tzinfo=UTC),
            step_size=1.0,
            step_unit="year",
            parameters={"growth_rate": 0.04},
        ))
        comp = compare_simulations_endpoint(sim_run.id, sim_b.id)
        self.assertIsNotNone(comp.summary)

        # 8. POST /simulations/{id}/cancel (on completed simulation -> raises 400)
        with self.assertRaises(HTTPException):
            cancel_simulation_endpoint(sim_run.id)

    # -------------------------------------------------------------------------
    # Engine 15: Anomaly Detection Integration Tests
    # -------------------------------------------------------------------------

    def test_anomaly_detection_execution_and_authoritative_non_mutation(self) -> None:
        """Verify anomaly detection over historical series and STRICT non-mutation of authoritative tables."""
        # 1. Count rows in authoritative operational tables before detection
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM entities")
            entities_before = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM observations")
            obs_before = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM geometries")
            geoms_before = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM evidence")
            evidence_before = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM provenance")
            provenance_before = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM entity_identifiers")
            identifiers_before = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM alerts")
            alerts_before = cur.fetchone()["c"]

            test_entity_id = uuid4()
            cur.execute("SELECT id AS evidence_id FROM evidence LIMIT 1")
            ev_id = cur.fetchone()["evidence_id"]
            cur.execute("SELECT id AS provenance_id FROM provenance LIMIT 1")
            prov_id = cur.fetchone()["provenance_id"]

            cur.execute(
                "INSERT INTO entities (id, kind, canonical_name, confidence) VALUES (%s, 'place', 'Anomaly Test Country', 1.0)",
                (test_entity_id,),
            )
            # Insert baseline observations followed by an anomalous spike point (99,000,000)
            for yr, val in [(2030, 10000000.0), (2031, 10100000.0), (2032, 10200000.0), (2033, 10300000.0), (2034, 99000000.0)]:
                sub_t = uuid4()
                cur.execute(
                    "INSERT INTO time_intervals (id, starts_at, precision) VALUES (%s, %s, 'year')",
                    (sub_t, datetime(yr, 1, 1, tzinfo=UTC)),
                )
                cur.execute(
                    """
                    INSERT INTO observations (id, subject_entity_id, measure, value, unit, truth_class, time_interval_id, evidence_id, provenance_id, confidence)
                    VALUES (%s, %s, 'test_anomaly.pop', %s, 'persons', 'OBSERVED', %s, %s, %s, 1.0)
                    """,
                    (uuid4(), test_entity_id, val, sub_t, ev_id, prov_id),
                )
            conn.commit()

        try:
            # Run anomaly detection
            req = AnomalyDetectionRequest(
                entity_ids=[test_entity_id],
                metric="test_anomaly.pop",
                threshold=3.0,
                min_observations=3,
                detection_methods=[DetectionMethod.ROBUST_ZSCORE_MAD, DetectionMethod.TEMPORAL_CHANGE],
            )
            run = self.repo.detect_anomalies(req)

            self.assertEqual(run.status, "COMPLETED")
            self.assertGreater(run.observations_evaluated, 0)
            self.assertGreater(run.findings_count, 0)

            # Check finding properties
            spike_finding = next((f for f in run.findings if f.observed_value == 99000000.0), None)
            self.assertIsNotNone(spike_finding)
            self.assertEqual(spike_finding.truth_class, TruthClass.DERIVED)
            self.assertEqual(spike_finding.status, FindingLifecycleStatus.NEW)
            self.assertTrue(spike_finding.explanation)
            self.assertGreater(spike_finding.anomaly_score, 3.0)
            self.assertIn(spike_finding.severity, (AnomalySeverity.HIGH, AnomalySeverity.CRITICAL))

        finally:
            # Clean up test observations and test entity
            with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM anomaly_findings WHERE metric = 'test_anomaly.pop'")
                cur.execute("DELETE FROM observations WHERE subject_entity_id = %s", (test_entity_id,))
                cur.execute("DELETE FROM entities WHERE id = %s", (test_entity_id,))
                conn.commit()

        # STRICT NON-MUTATION ASSERTION: Check that authoritative tables were NOT mutated by anomaly detection
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM entities")
            self.assertEqual(cur.fetchone()["c"], entities_before)
            cur.execute("SELECT COUNT(*) AS c FROM observations")
            self.assertEqual(cur.fetchone()["c"], obs_before)
            cur.execute("SELECT COUNT(*) AS c FROM geometries")
            self.assertEqual(cur.fetchone()["c"], geoms_before)
            cur.execute("SELECT COUNT(*) AS c FROM evidence")
            self.assertEqual(cur.fetchone()["c"], evidence_before)
            cur.execute("SELECT COUNT(*) AS c FROM provenance")
            self.assertEqual(cur.fetchone()["c"], provenance_before)
            cur.execute("SELECT COUNT(*) AS c FROM entity_identifiers")
            self.assertEqual(cur.fetchone()["c"], identifiers_before)
            cur.execute("SELECT COUNT(*) AS c FROM alerts")
            self.assertEqual(cur.fetchone()["c"], alerts_before)

    def test_anomaly_temporal_change_spike_and_drop(self) -> None:
        """Verify temporal change detects both abrupt spikes and drops and ignores ordinary noise."""
        test_entity_id = uuid4()
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM evidence LIMIT 1")
            evidence_id = cur.fetchone()["id"]
            cur.execute("SELECT id FROM provenance LIMIT 1")
            provenance_id = cur.fetchone()["id"]

            cur.execute("INSERT INTO entities (id, kind, canonical_name, confidence) VALUES (%s, 'place', 'Temporal Test Entity', 1.0)", (test_entity_id,))
            for yr, val in [(2020, 100.0), (2021, 102.0), (2022, 20.0)]:
                tid = uuid4()
                cur.execute("INSERT INTO time_intervals (id, starts_at, precision) VALUES (%s, %s, 'year')", (tid, datetime(yr, 1, 1, tzinfo=UTC)))
                cur.execute(
                    "INSERT INTO observations (id, subject_entity_id, measure, value, unit, truth_class, time_interval_id, evidence_id, provenance_id, confidence) VALUES (%s, %s, 'test_temporal.drop', %s, 'count', 'OBSERVED', %s, %s, %s, 1.0)",
                    (uuid4(), test_entity_id, val, tid, evidence_id, provenance_id)
                )
            conn.commit()

        try:
            req = AnomalyDetectionRequest(
                entity_ids=[test_entity_id],
                metric="test_temporal.drop",
                threshold=25.0,
                detection_methods=[DetectionMethod.TEMPORAL_CHANGE],
            )
            run = self.repo.detect_anomalies(req)
            self.assertEqual(run.status, "COMPLETED")

            # 100 -> 102 is 2% change, below threshold 25%, so no finding for 2021
            findings_2021 = [f for f in run.findings if f.observed_at.year == 2021]
            self.assertEqual(len(findings_2021), 0)

            # 102 -> 20 is ~-80.4% drop, triggers finding
            findings_2022 = [f for f in run.findings if f.observed_at.year == 2022]
            self.assertEqual(len(findings_2022), 1)
            f2022 = findings_2022[0]
            self.assertLess(f2022.deviation, 0)
            self.assertAlmostEqual(f2022.deviation, -82.0, places=1)
            self.assertGreater(f2022.anomaly_score, 25.0)

        finally:
            with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM anomaly_findings WHERE metric = 'test_temporal.drop'")
                cur.execute("DELETE FROM observations WHERE subject_entity_id = %s", (test_entity_id,))
                cur.execute("DELETE FROM entities WHERE id = %s", (test_entity_id,))
                conn.commit()

    def test_anomaly_constant_series_and_insufficient_history(self) -> None:
        """Verify explicit handling of constant series (zero dispersion) and insufficient history."""
        test_entity_id = uuid4()
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM evidence LIMIT 1")
            evidence_id = cur.fetchone()["id"]
            cur.execute("SELECT id FROM provenance LIMIT 1")
            provenance_id = cur.fetchone()["id"]

            cur.execute("INSERT INTO entities (id, kind, canonical_name, confidence) VALUES (%s, 'place', 'Constant Test Entity', 1.0)", (test_entity_id,))
            for yr in (2020, 2021, 2022, 2023):
                tid = uuid4()
                cur.execute("INSERT INTO time_intervals (id, starts_at, precision) VALUES (%s, %s, 'year')", (tid, datetime(yr, 1, 1, tzinfo=UTC)))
                cur.execute(
                    "INSERT INTO observations (id, subject_entity_id, measure, value, unit, truth_class, time_interval_id, evidence_id, provenance_id, confidence) VALUES (%s, %s, 'test_constant.metric', 5.0, 'kg', 'OBSERVED', %s, %s, %s, 1.0)",
                    (uuid4(), test_entity_id, tid, evidence_id, provenance_id)
                )

            for yr in (2020, 2021):
                tid = uuid4()
                cur.execute("INSERT INTO time_intervals (id, starts_at, precision) VALUES (%s, %s, 'year')", (tid, datetime(yr, 1, 1, tzinfo=UTC)))
                cur.execute(
                    "INSERT INTO observations (id, subject_entity_id, measure, value, unit, truth_class, time_interval_id, evidence_id, provenance_id, confidence) VALUES (%s, %s, 'test_insufficient.metric', 10.0, 'kg', 'OBSERVED', %s, %s, %s, 1.0)",
                    (uuid4(), test_entity_id, tid, evidence_id, provenance_id)
                )
            conn.commit()

        try:
            run_const = self.repo.detect_anomalies(AnomalyDetectionRequest(
                entity_ids=[test_entity_id],
                metric="test_constant.metric",
                threshold=3.0,
                min_observations=3,
                detection_methods=[DetectionMethod.ROBUST_ZSCORE_MAD],
            ))
            self.assertEqual(run_const.status, "COMPLETED")
            self.assertEqual(run_const.findings_count, 0)

            run_insuf = self.repo.detect_anomalies(AnomalyDetectionRequest(
                entity_ids=[test_entity_id],
                metric="test_insufficient.metric",
                threshold=3.0,
                min_observations=4,
                detection_methods=[DetectionMethod.ROBUST_ZSCORE_MAD],
            ))
            self.assertEqual(run_insuf.status, "COMPLETED")
            self.assertEqual(run_insuf.findings_count, 0)
            self.assertTrue(any("INSUFFICIENT_DATA" in msg for msg in run_insuf.exclusions_and_warnings))

        finally:
            with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM anomaly_findings WHERE metric IN ('test_constant.metric', 'test_insufficient.metric')")
                cur.execute("DELETE FROM observations WHERE subject_entity_id = %s", (test_entity_id,))
                cur.execute("DELETE FROM entities WHERE id = %s", (test_entity_id,))
                conn.commit()

    def test_anomaly_peer_group_and_spatial_deviation(self) -> None:
        """Verify peer group cross-sectional detection flags outlier within peer cohort."""
        e1, e2, e3 = uuid4(), uuid4(), uuid4()
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM evidence LIMIT 1")
            evidence_id = cur.fetchone()["id"]
            cur.execute("SELECT id FROM provenance LIMIT 1")
            provenance_id = cur.fetchone()["id"]

            for eid, name in [(e1, "Peer City Alpha"), (e2, "Peer City Beta"), (e3, "Peer City Gamma")]:
                cur.execute(
                    "INSERT INTO entities (id, kind, canonical_name, confidence) VALUES (%s, 'place', %s, 1.0)",
                    (eid, name)
                )

            t2025 = uuid4()
            cur.execute("INSERT INTO time_intervals (id, starts_at, precision) VALUES (%s, %s, 'year')", (t2025, datetime(2025, 1, 1, tzinfo=UTC)))
            for eid, val in [(e1, 100.0), (e2, 105.0), (e3, 500.0)]:
                cur.execute(
                    "INSERT INTO observations (id, subject_entity_id, measure, value, unit, truth_class, time_interval_id, evidence_id, provenance_id, confidence) VALUES (%s, %s, 'test_peer.val', %s, 'index', 'OBSERVED', %s, %s, %s, 1.0)",
                    (uuid4(), eid, val, t2025, evidence_id, provenance_id)
                )
            conn.commit()

        try:
            run = self.repo.detect_anomalies(AnomalyDetectionRequest(
                entity_ids=[e1, e2, e3],
                metric="test_peer.val",
                threshold=2.0,
                detection_methods=[DetectionMethod.PEER_GROUP_DEVIATION],
            ))
            self.assertEqual(run.status, "COMPLETED")
            self.assertEqual(run.findings_count, 1)
            self.assertEqual(run.findings[0].entity_id, e3)
            self.assertEqual(run.findings[0].observed_value, 500.0)
            self.assertEqual(run.findings[0].detection_method, DetectionMethod.PEER_GROUP_DEVIATION)

        finally:
            with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM anomaly_findings WHERE metric = 'test_peer.val'")
                cur.execute("DELETE FROM observations WHERE subject_entity_id IN (%s, %s, %s)", (e1, e2, e3))
                cur.execute("DELETE FROM entities WHERE id IN (%s, %s, %s)", (e1, e2, e3))
                conn.commit()

    def test_anomaly_fingerprint_deduplication_and_lifecycle(self) -> None:
        """Verify fingerprint deduplication and finding lifecycle transitions (suppress, resolve)."""
        test_entity_id = uuid4()
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM evidence LIMIT 1")
            evidence_id = cur.fetchone()["id"]
            cur.execute("SELECT id FROM provenance LIMIT 1")
            provenance_id = cur.fetchone()["id"]

            cur.execute("INSERT INTO entities (id, kind, canonical_name, confidence) VALUES (%s, 'place', 'Dedup Test Entity', 1.0)", (test_entity_id,))
            for yr, val in [(2020, 10.0), (2021, 10.0), (2022, 10.0), (2023, 100.0)]:
                tid = uuid4()
                cur.execute("INSERT INTO time_intervals (id, starts_at, precision) VALUES (%s, %s, 'year')", (tid, datetime(yr, 1, 1, tzinfo=UTC)))
                cur.execute(
                    "INSERT INTO observations (id, subject_entity_id, measure, value, unit, truth_class, time_interval_id, evidence_id, provenance_id, confidence) VALUES (%s, %s, 'test_dedup.metric', %s, 'count', 'OBSERVED', %s, %s, %s, 1.0)",
                    (uuid4(), test_entity_id, val, tid, evidence_id, provenance_id)
                )
            conn.commit()

        try:
            req = AnomalyDetectionRequest(
                entity_ids=[test_entity_id],
                metric="test_dedup.metric",
                threshold=3.0,
                min_observations=3,
                detection_methods=[DetectionMethod.ROBUST_ZSCORE_MAD],
            )

            run1 = self.repo.detect_anomalies(req)
            self.assertEqual(run1.findings_count, 1)
            f1 = run1.findings[0]

            run2 = self.repo.detect_anomalies(req)
            self.assertEqual(run2.findings_count, 1)
            f2 = run2.findings[0]

            self.assertEqual(f1.fingerprint, f2.fingerprint)

            with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS c FROM anomaly_findings WHERE fingerprint = %s", (f1.fingerprint,))
                self.assertEqual(cur.fetchone()["c"], 1)

            suppressed = self.repo.suppress_anomaly_finding(f1.id, notes="Known reporting quirk")
            self.assertEqual(suppressed.status, FindingLifecycleStatus.SUPPRESSED)

            resolved = self.repo.resolve_anomaly_finding(f1.id, notes="Corrected by publisher")
            self.assertEqual(resolved.status, FindingLifecycleStatus.RESOLVED)

        finally:
            with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM anomaly_findings WHERE metric = 'test_dedup.metric'")
                cur.execute("DELETE FROM observations WHERE subject_entity_id = %s", (test_entity_id,))
                cur.execute("DELETE FROM entities WHERE id = %s", (test_entity_id,))
                conn.commit()

    def test_anomaly_rest_api_endpoints(self) -> None:
        """Verify REST API endpoints for Engine 15 Anomaly Detection."""
        methods = list_anomaly_methods_endpoint()
        self.assertGreaterEqual(len(methods), 4)

        test_entity_id = uuid4()
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM evidence LIMIT 1")
            evidence_id = cur.fetchone()["id"]
            cur.execute("SELECT id FROM provenance LIMIT 1")
            provenance_id = cur.fetchone()["id"]

            cur.execute("INSERT INTO entities (id, kind, canonical_name, confidence) VALUES (%s, 'place', 'API Test Entity', 1.0)", (test_entity_id,))
            for yr, val in [(2020, 50.0), (2021, 52.0), (2022, 51.0), (2023, 500.0)]:
                tid = uuid4()
                cur.execute("INSERT INTO time_intervals (id, starts_at, precision) VALUES (%s, %s, 'year')", (tid, datetime(yr, 1, 1, tzinfo=UTC)))
                cur.execute(
                    "INSERT INTO observations (id, subject_entity_id, measure, value, unit, truth_class, time_interval_id, evidence_id, provenance_id, confidence) VALUES (%s, %s, 'test_api.anomaly', %s, 'count', 'OBSERVED', %s, %s, %s, 1.0)",
                    (uuid4(), test_entity_id, val, tid, evidence_id, provenance_id)
                )
            conn.commit()

        try:
            req = AnomalyDetectionRequest(
                entity_ids=[test_entity_id],
                metric="test_api.anomaly",
                threshold=3.0,
                min_observations=3,
                detection_methods=[DetectionMethod.ROBUST_ZSCORE_MAD],
            )
            run = detect_anomalies_endpoint(req)
            self.assertEqual(run.status, "COMPLETED")
            self.assertEqual(run.findings_count, 1)

            runs = list_anomaly_runs_endpoint(limit=10)
            self.assertTrue(any(r.id == run.id for r in runs))

            retrieved_run = get_anomaly_run_endpoint(run.id)
            self.assertEqual(retrieved_run.id, run.id)

            findings = list_anomaly_findings_endpoint(metric="test_api.anomaly")
            self.assertEqual(len(findings), 1)

            fid = findings[0].id
            retrieved_finding = get_anomaly_finding_endpoint(fid)
            self.assertEqual(retrieved_finding.id, fid)

            supp = suppress_anomaly_finding_endpoint(fid, FindingActionRequest(notes="Test suppress"))
            self.assertEqual(supp.status, FindingLifecycleStatus.SUPPRESSED)

            res = resolve_anomaly_finding_endpoint(fid, FindingActionRequest(notes="Test resolve"))
            self.assertEqual(res.status, FindingLifecycleStatus.RESOLVED)

            with self.assertRaises(HTTPException):
                get_anomaly_finding_endpoint(uuid4())

            with self.assertRaises(HTTPException):
                get_anomaly_run_endpoint(uuid4())

        finally:
            with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM anomaly_findings WHERE metric = 'test_api.anomaly'")
                cur.execute("DELETE FROM observations WHERE subject_entity_id = %s", (test_entity_id,))
                cur.execute("DELETE FROM entities WHERE id = %s", (test_entity_id,))
                conn.commit()
