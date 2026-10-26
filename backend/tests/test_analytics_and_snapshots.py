"""Unit tests for deterministic snapshot management, partition layout, and DuckDB analytics."""
from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from uuid import uuid4

import duckdb

from app.analytics import DuckDbSpatialAnalytics
from app.domain import SnapshotManifest
from app.snapshots import SnapshotCatalog, SNAPSHOT_SCHEMA_VERSION


class AnalyticsAndSnapshotsUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = Path(tempfile.mkdtemp())
        self.snapshots_dir = self.test_dir / "snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_mock_snapshot(
        self,
        snapshot_id: str,
        status: str = "completed",
        include_data: bool = True,
        schema_version: str = SNAPSHOT_SCHEMA_VERSION,
    ) -> Path:
        snap_path = self.snapshots_dir / snapshot_id
        snap_path.mkdir(parents=True, exist_ok=True)
        obs_dir = snap_path / "observations"
        ent_dir = snap_path / "entities"
        geom_dir = snap_path / "geometries"
        ev_dir = snap_path / "events"
        obs_dir.mkdir(parents=True, exist_ok=True)
        ent_dir.mkdir(parents=True, exist_ok=True)
        geom_dir.mkdir(parents=True, exist_ok=True)
        ev_dir.mkdir(parents=True, exist_ok=True)

        row_counts = {"observations": 0, "entities": 0, "geometries": 0, "events": 0}
        partition_counts = {"observations": 0, "entities": 0}

        if include_data:
            with duckdb.connect() as ddb:
                # 1. Observations
                ddb.execute("""
                    CREATE TABLE obs (
                        id VARCHAR,
                        subject_entity_id VARCHAR,
                        entity_canonical_name VARCHAR,
                        entity_type VARCHAR,
                        measure VARCHAR,
                        value DOUBLE,
                        unit VARCHAR,
                        time_interval_id VARCHAR,
                        starts_at TIMESTAMPTZ,
                        ends_at TIMESTAMPTZ,
                        temporal_precision VARCHAR,
                        year VARCHAR,
                        evidence_id VARCHAR,
                        source_id VARCHAR,
                        source_slug VARCHAR,
                        provenance_id VARCHAR,
                        truth_class VARCHAR,
                        confidence DOUBLE,
                        geometry_geojson VARCHAR
                    )
                """)
                ddb.execute("""
                    INSERT INTO obs VALUES
                    ('obs-1', 'ent-ind', 'India', 'place', 'population.total', 1400000000.0, 'people', 't-1', '2020-01-01 00:00:00+00', NULL, 'year', '2020', 'ev-1', 'src-wb', 'world-bank-open-data', 'pr-1', 'OBSERVED', 1.0, NULL),
                    ('obs-2', 'ent-ind', 'India', 'place', 'population.total', 1420000000.0, 'people', 't-2', '2023-01-01 00:00:00+00', NULL, 'year', '2023', 'ev-2', 'src-wb', 'world-bank-open-data', 'pr-2', 'OBSERVED', 1.0, NULL),
                    ('obs-3', 'ent-jpn', 'Japan', 'place', 'population.total', 125000000.0, 'people', 't-3', '2023-01-01 00:00:00+00', NULL, 'year', '2023', 'ev-3', 'src-wb', 'world-bank-open-data', 'pr-3', 'OBSERVED', 1.0, NULL),
                    ('obs-4', 'ent-unk', 'Mystery Entity', 'unknown', 'population.total', 500000.0, 'people', 't-4', NULL, NULL, 'unknown', 'unknown', 'ev-4', 'src-wb', 'world-bank-open-data', 'pr-4', 'OBSERVED', 0.8, NULL)
                """)
                ddb.execute(
                    f"COPY obs TO '{obs_dir.as_posix()}' (FORMAT PARQUET, PARTITION_BY (year, entity_type), OVERWRITE_OR_IGNORE)"
                )

                # 2. Entities
                ddb.execute("""
                    CREATE TABLE ent (
                        id VARCHAR,
                        canonical_name VARCHAR,
                        entity_type VARCHAR,
                        source_id VARCHAR,
                        confidence DOUBLE,
                        attributes_json VARCHAR,
                        created_at TIMESTAMPTZ
                    )
                """)
                ddb.execute("""
                    INSERT INTO ent VALUES
                    ('ent-ind', 'India', 'place', 'src-wb', 1.0, '{}', '2026-09-29 00:00:00+00'),
                    ('ent-jpn', 'Japan', 'place', 'src-wb', 1.0, '{}', '2026-09-29 00:00:00+00'),
                    ('ent-unk', 'Mystery Entity', 'unknown', 'src-wb', 0.8, '{}', '2026-09-29 00:00:00+00')
                """)
                ddb.execute(
                    f"COPY ent TO '{ent_dir.as_posix()}' (FORMAT PARQUET, PARTITION_BY (entity_type), OVERWRITE_OR_IGNORE)"
                )

            row_counts["observations"] = 4
            row_counts["entities"] = 3
            partition_counts["observations"] = len(list(obs_dir.rglob("*.parquet")))
            partition_counts["entities"] = len(list(ent_dir.rglob("*.parquet")))

        manifest = SnapshotManifest(
            snapshot_id=uuid4(),
            schema_version=schema_version,
            status=status,
            started_at=datetime(2026, 10, 26, 20, 0, tzinfo=UTC),
            completed_at=datetime(2026, 10, 26, 20, 5, tzinfo=UTC) if status == "completed" else None,
            datasets=["observations", "entities", "geometries", "events"],
            total_records=sum(row_counts.values()),
            row_counts=row_counts,
            partition_counts=partition_counts,
            min_year=2020,
            max_year=2023,
            storage_path=str(snap_path),
        )

        with open(snap_path / "manifest.json", "w", encoding="utf-8") as f:
            f.write(manifest.model_dump_json(indent=2))

        return snap_path

    def test_snapshot_manifest_validation(self) -> None:
        sid = uuid4()
        m = SnapshotManifest(
            snapshot_id=sid,
            status="completed",
            storage_path="/tmp/snapshots/123",
            total_records=42,
            row_counts={"observations": 40, "entities": 2},
        )
        self.assertEqual(m.snapshot_id, sid)
        self.assertEqual(m.status, "completed")
        self.assertEqual(m.schema_version, SNAPSHOT_SCHEMA_VERSION)
        dump = m.model_dump()
        self.assertEqual(dump["total_records"], 42)

    def test_partition_naming_and_temporal_bucketing(self) -> None:
        snap_path = self._create_mock_snapshot("test-snap-1")
        obs_dir = snap_path / "observations"
        self.assertTrue((obs_dir / "year=2020" / "entity_type=place").exists())
        self.assertTrue((obs_dir / "year=2023" / "entity_type=place").exists())
        # Unknown year and unknown entity type partitions explicitly handled
        self.assertTrue((obs_dir / "year=unknown" / "entity_type=unknown").exists())

    def test_snapshot_catalog_discovery_and_staleness(self) -> None:
        # Create two snapshots: snap-old and snap-new
        self._create_mock_snapshot("snap-old")
        self._create_mock_snapshot("snap-new")

        # Create an in-progress staging directory
        staging_dir = self.snapshots_dir / ".staging_12345678-1234-5678-1234-567812345678"
        staging_dir.mkdir()

        catalog = SnapshotCatalog(snapshots_dir=self.snapshots_dir)
        all_snaps = catalog.list_snapshots()
        self.assertEqual(len(all_snaps), 3)

        completed = catalog.list_snapshots(status_filter="completed")
        self.assertEqual(len(completed), 2)

        in_prog = catalog.list_snapshots(status_filter="in_progress")
        self.assertEqual(len(in_prog), 1)

        latest = catalog.get_latest_completed_snapshot()
        self.assertIsNotNone(latest)
        self.assertTrue(latest.metadata.get("is_latest"))

    def test_snapshot_integrity_validation(self) -> None:
        snap_path = self._create_mock_snapshot("valid-snap")
        catalog = SnapshotCatalog(snapshots_dir=self.snapshots_dir)
        res = catalog.validate_snapshot("valid-snap")
        self.assertTrue(res["valid"])
        self.assertEqual(len(res["errors"]), 0)
        self.assertEqual(res["datasets"]["observations"]["actual_rows"], 4)

        # Corrupt one dataset by adding a record mismatch
        manifest_file = snap_path / "manifest.json"
        with open(manifest_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["row_counts"]["observations"] = 999  # mismatch!
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

        res_corrupt = catalog.validate_snapshot("valid-snap")
        self.assertFalse(res_corrupt["valid"])
        self.assertTrue(any("Row count mismatch" in err for err in res_corrupt["errors"]))

    def test_duckdb_spatial_rollups_over_parquet(self) -> None:
        snap_path = self._create_mock_snapshot("analytics-snap")
        analytics = DuckDbSpatialAnalytics(replica_path=snap_path)

        # 1. Entity counts by type
        counts = analytics.entity_counts_by_type()
        place_count = next(c["count"] for c in counts if c["entity_type"] == "place")
        self.assertEqual(place_count, 2)

        # 2. Observation counts by year and type
        year_counts = analytics.observation_counts_by_year_and_type(measure="population.total")
        self.assertEqual(len(year_counts), 3)  # 2020, 2023, unknown

        # 3. Spatial summaries for 2023
        summaries_2023 = analytics.spatial_summaries(measure="population.total", year=2023)
        self.assertEqual(len(summaries_2023), 2)  # India and Japan
        ind_summary = next(s for s in summaries_2023 if s["entity_canonical_name"] == "India")
        self.assertEqual(ind_summary["total_value"], 1420000000.0)
        self.assertTrue(ind_summary["has_data"])

        # 4. Temporal trends for India
        trends = analytics.multi_entity_temporal_trends(entity_ids=["ent-ind"], measure="population.total")
        self.assertEqual(len(trends), 1)
        ind_trend = trends[0]
        self.assertEqual(ind_trend["observation_count"], 2)
        self.assertEqual(ind_trend["earliest_value"], 1400000000.0)
        self.assertEqual(ind_trend["latest_value"], 1420000000.0)
        self.assertAlmostEqual(ind_trend["percentage_change"], 1.4286, places=3)
        self.assertIn("ev-1", ind_trend["evidence_ids"])
        self.assertIn("ev-2", ind_trend["evidence_ids"])

        # 5. Coverage and freshness
        coverage = analytics.evidence_coverage_and_freshness()
        self.assertEqual(coverage["total_observations"], 4)
        self.assertEqual(coverage["total_entities"], 3)
        self.assertEqual(coverage["total_evidence_citations"], 4)
        self.assertEqual(coverage["distinct_sources"], 1)

        # 6. Spatial comparison between India and Japan
        comp = analytics.compare_spatial_slices(entity_a_id="ent-ind", entity_b_id="ent-jpn", measure="population.total", year=2023)
        self.assertEqual(comp["larger_entity"], "India")
        self.assertGreater(comp["ratio"], 10.0)


if __name__ == "__main__":
    unittest.main()
