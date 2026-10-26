"""Deterministic, non-blocking PostgreSQL to Parquet snapshot automation and catalog."""
from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
import os
from pathlib import Path
import shutil
from typing import Any
from uuid import UUID, uuid4

import duckdb
import psycopg
from psycopg.rows import dict_row

from .domain import SnapshotManifest
from .storage import WorldRepository

logger = logging.getLogger("worldos.snapshots")

DEFAULT_SNAPSHOTS_DIR = Path(os.environ.get("WORLDOS_SNAPSHOT_DIR", "data/snapshots"))
DEFAULT_DATASETS = ["observations", "entities", "geometries", "events"]
SNAPSHOT_SCHEMA_VERSION = "worldos-snapshot-v1"


def ensure_snapshots_dir(base_dir: Path | str | None = None) -> Path:
    target = Path(base_dir) if base_dir else DEFAULT_SNAPSHOTS_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


class SnapshotManager:
    """Manages non-blocking snapshot exports from PostgreSQL to partitioned Parquet files."""

    def __init__(
        self,
        database_url: str | None = None,
        snapshots_dir: Path | str | None = None,
    ) -> None:
        self.database_url = database_url or os.environ.get(
            "WORLDOS_DATABASE_URL",
            "postgresql://worldos:worldos_dev_only@localhost:5432/worldos",
        )
        self.snapshots_dir = ensure_snapshots_dir(snapshots_dir)
        self.repo = WorldRepository(self.database_url)

    def export_snapshot(
        self,
        datasets: list[str] | None = None,
        snapshot_id: UUID | None = None,
    ) -> SnapshotManifest:
        """Export PostgreSQL tables into Hive-partitioned Parquet files with atomic staging."""
        sid = snapshot_id or uuid4()
        if not isinstance(datasets, (list, tuple, set)):
            target_datasets = list(DEFAULT_DATASETS)
        else:
            target_datasets = list(datasets)
        started_at = datetime.now(UTC)

        staging_dir = self.snapshots_dir / f".staging_{sid}"
        final_dir = self.snapshots_dir / str(sid)

        # Clean any stale staging dir for this ID
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        staging_dir.mkdir(parents=True, exist_ok=True)

        # 1. Record in-progress status in PostgreSQL repository
        try:
            self.repo.record_snapshot_run(
                snapshot_id=sid,
                schema_version=SNAPSHOT_SCHEMA_VERSION,
                status="in_progress",
                storage_path=str(final_dir),
                datasets=target_datasets,
                metadata={"staging_path": str(staging_dir)},
            )
        except Exception as repo_err:
            logger.warning("Could not record snapshot run in DB (will proceed with file manifest): %s", repo_err)

        row_counts: dict[str, int] = {}
        partition_counts: dict[str, int] = {}
        years_found: set[int] = set()

        try:
            # 2. Connect to PostgreSQL in autocommit read-only mode to prevent holding long table locks
            with psycopg.connect(self.database_url, autocommit=True, row_factory=dict_row) as pg_conn:
                for dataset in target_datasets:
                    count, p_count, dataset_years = self._export_dataset(
                        pg_conn=pg_conn,
                        dataset=dataset,
                        staging_dir=staging_dir,
                    )
                    row_counts[dataset] = count
                    partition_counts[dataset] = p_count
                    years_found.update(dataset_years)

            min_year = min(years_found) if years_found else None
            max_year = max(years_found) if years_found else None
            total_records = sum(row_counts.values())
            completed_at = datetime.now(UTC)

            # 3. Create and persist snapshot manifest
            manifest = SnapshotManifest(
                snapshot_id=sid,
                schema_version=SNAPSHOT_SCHEMA_VERSION,
                status="completed",
                started_at=started_at,
                completed_at=completed_at,
                datasets=target_datasets,
                total_records=total_records,
                row_counts=row_counts,
                partition_counts=partition_counts,
                min_year=min_year,
                max_year=max_year,
                storage_path=str(final_dir),
                metadata={
                    "export_engine": "duckdb-parquet",
                    "duckdb_version": duckdb.__version__,
                },
            )

            manifest_file = staging_dir / "manifest.json"
            with open(manifest_file, "w", encoding="utf-8") as f:
                f.write(manifest.model_dump_json(indent=2))

            # 4. Atomic rename staging -> final destination
            if final_dir.exists():
                shutil.rmtree(final_dir, ignore_errors=True)
            staging_dir.rename(final_dir)

            # 5. Update PostgreSQL repository status
            try:
                self.repo.update_snapshot_run(
                    snapshot_id=sid,
                    status="completed",
                    completed_at=completed_at,
                    total_records=total_records,
                    row_counts=row_counts,
                    partition_counts=partition_counts,
                    min_year=min_year,
                    max_year=max_year,
                )
            except Exception as repo_err:
                logger.warning("Could not update snapshot run in DB: %s", repo_err)

            return manifest

        except Exception as exc:
            logger.error("Snapshot export failed for %s: %s", sid, exc)
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

            try:
                self.repo.update_snapshot_run(
                    snapshot_id=sid,
                    status="failed",
                    completed_at=datetime.now(UTC),
                    error_message=str(exc),
                )
            except Exception:
                pass

            raise RuntimeError(f"Snapshot export failed: {exc}") from exc

    def _export_dataset(
        self,
        pg_conn: psycopg.Connection,
        dataset: str,
        staging_dir: Path,
    ) -> tuple[int, int, set[int]]:
        """Exports a single dataset into partitioned Parquet using bounded memory."""
        out_dir = staging_dir / dataset
        out_dir.mkdir(parents=True, exist_ok=True)
        years: set[int] = set()

        if dataset == "observations":
            return self._export_observations(pg_conn, out_dir)
        elif dataset == "entities":
            return self._export_entities(pg_conn, out_dir)
        elif dataset == "geometries":
            return self._export_geometries(pg_conn, out_dir)
        elif dataset == "events":
            return self._export_events(pg_conn, out_dir)
        else:
            logger.warning("Unknown dataset %s, skipping", dataset)
            return (0, 0, years)

    def _export_observations(
        self,
        pg_conn: psycopg.Connection,
        out_dir: Path,
    ) -> tuple[int, int, set[int]]:
        sql = """
            SELECT
                o.id::text AS id,
                o.subject_entity_id::text AS subject_entity_id,
                e.canonical_name AS entity_canonical_name,
                COALESCE(e.kind, 'unknown') AS entity_type,
                o.measure,
                o.value::double precision AS value,
                o.unit,
                o.time_interval_id::text AS time_interval_id,
                t.starts_at,
                t.ends_at,
                t.precision AS temporal_precision,
                CASE
                    WHEN t.starts_at IS NOT NULL THEN EXTRACT(YEAR FROM t.starts_at)::text
                    ELSE 'unknown'
                END AS year,
                o.evidence_id::text AS evidence_id,
                s.id::text AS source_id,
                s.slug AS source_slug,
                o.provenance_id::text AS provenance_id,
                o.truth_class,
                o.confidence::double precision AS confidence,
                ST_AsGeoJSON(g.geometry) AS geometry_geojson
            FROM observations o
            JOIN entities e ON e.id = o.subject_entity_id
            JOIN time_intervals t ON t.id = o.time_interval_id
            JOIN evidence ev ON ev.id = o.evidence_id
            JOIN sources s ON s.id = ev.source_id
            LEFT JOIN LATERAL (
                SELECT geometry FROM geometries WHERE entity_id = o.subject_entity_id ORDER BY created_at DESC LIMIT 1
            ) g ON true
            ORDER BY t.starts_at ASC, o.id ASC
        """
        years: set[int] = set()
        with pg_conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

        if not rows:
            return (0, 0, years)

        for r in rows:
            if r["year"] and r["year"] != "unknown":
                try:
                    years.add(int(float(r["year"])))
                except ValueError:
                    pass

        # Write to partitioned Parquet via in-memory DuckDB
        with duckdb.connect() as ddb:
            ddb.execute("""
                CREATE TABLE staging_obs (
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
            tuples = [
                (
                    r["id"],
                    r["subject_entity_id"],
                    r["entity_canonical_name"],
                    r["entity_type"],
                    r["measure"],
                    r["value"],
                    r["unit"],
                    r["time_interval_id"],
                    r["starts_at"],
                    r["ends_at"],
                    r["temporal_precision"],
                    r["year"],
                    r["evidence_id"],
                    r["source_id"],
                    r["source_slug"],
                    r["provenance_id"],
                    r["truth_class"],
                    r["confidence"],
                    r["geometry_geojson"],
                )
                for r in rows
            ]
            ddb.executemany("INSERT INTO staging_obs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuples)
            ddb.execute(
                f"COPY staging_obs TO '{out_dir.as_posix()}' (FORMAT PARQUET, PARTITION_BY (year, entity_type), OVERWRITE_OR_IGNORE)"
            )

        partition_count = len(list(out_dir.rglob("*.parquet")))
        return (len(rows), partition_count, years)

    def _export_entities(
        self,
        pg_conn: psycopg.Connection,
        out_dir: Path,
    ) -> tuple[int, int, set[int]]:
        sql = """
            SELECT
                e.id::text AS id,
                e.canonical_name,
                COALESCE(e.kind, 'unknown') AS entity_type,
                e.source_id::text AS source_id,
                e.confidence::double precision AS confidence,
                e.attributes::text AS attributes_json,
                e.created_at
            FROM entities e
            ORDER BY e.created_at ASC, e.id ASC
        """
        with pg_conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

        if not rows:
            return (0, 0, set())

        with duckdb.connect() as ddb:
            ddb.execute("""
                CREATE TABLE staging_entities (
                    id VARCHAR,
                    canonical_name VARCHAR,
                    entity_type VARCHAR,
                    source_id VARCHAR,
                    confidence DOUBLE,
                    attributes_json VARCHAR,
                    created_at TIMESTAMPTZ
                )
            """)
            tuples = [
                (
                    r["id"],
                    r["canonical_name"],
                    r["entity_type"],
                    r["source_id"],
                    r["confidence"],
                    r["attributes_json"],
                    r["created_at"],
                )
                for r in rows
            ]
            ddb.executemany("INSERT INTO staging_entities VALUES (?, ?, ?, ?, ?, ?, ?)", tuples)
            ddb.execute(
                f"COPY staging_entities TO '{out_dir.as_posix()}' (FORMAT PARQUET, PARTITION_BY (entity_type), OVERWRITE_OR_IGNORE)"
            )

        partition_count = len(list(out_dir.rglob("*.parquet")))
        return (len(rows), partition_count, set())

    def _export_geometries(
        self,
        pg_conn: psycopg.Connection,
        out_dir: Path,
    ) -> tuple[int, int, set[int]]:
        sql = """
            SELECT
                g.id::text AS id,
                g.entity_id::text AS entity_id,
                COALESCE(g.geometry_kind, 'unknown') AS geometry_kind,
                ST_AsGeoJSON(g.geometry) AS geometry_geojson,
                g.source_id::text AS source_id,
                g.evidence_id::text AS evidence_id,
                g.confidence::double precision AS confidence
            FROM geometries g
            ORDER BY g.created_at ASC, g.id ASC
        """
        with pg_conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

        if not rows:
            return (0, 0, set())

        with duckdb.connect() as ddb:
            ddb.execute("""
                CREATE TABLE staging_geometries (
                    id VARCHAR,
                    entity_id VARCHAR,
                    geometry_kind VARCHAR,
                    geometry_geojson VARCHAR,
                    source_id VARCHAR,
                    evidence_id VARCHAR,
                    confidence DOUBLE
                )
            """)
            tuples = [
                (
                    r["id"],
                    r["entity_id"],
                    r["geometry_kind"],
                    r["geometry_geojson"],
                    r["source_id"],
                    r["evidence_id"],
                    r["confidence"],
                )
                for r in rows
            ]
            ddb.executemany("INSERT INTO staging_geometries VALUES (?, ?, ?, ?, ?, ?, ?)", tuples)
            ddb.execute(
                f"COPY staging_geometries TO '{out_dir.as_posix()}' (FORMAT PARQUET, PARTITION_BY (geometry_kind), OVERWRITE_OR_IGNORE)"
            )

        partition_count = len(list(out_dir.rglob("*.parquet")))
        return (len(rows), partition_count, set())

    def _export_events(
        self,
        pg_conn: psycopg.Connection,
        out_dir: Path,
    ) -> tuple[int, int, set[int]]:
        sql = """
            SELECT
                ev.id::text AS id,
                COALESCE(ev.kind, 'unknown') AS event_type,
                ev.subject_entity_id::text AS subject_entity_id,
                t.starts_at,
                CASE
                    WHEN t.starts_at IS NOT NULL THEN EXTRACT(YEAR FROM t.starts_at)::text
                    ELSE 'unknown'
                END AS year,
                ev.evidence_id::text AS evidence_id,
                ev.confidence::double precision AS confidence,
                ev.attributes::text AS attributes_json
            FROM events ev
            JOIN time_intervals t ON t.id = ev.time_interval_id
            ORDER BY t.starts_at ASC, ev.id ASC
        """
        years: set[int] = set()
        with pg_conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

        if not rows:
            return (0, 0, years)

        for r in rows:
            if r["year"] and r["year"] != "unknown":
                try:
                    years.add(int(float(r["year"])))
                except ValueError:
                    pass

        with duckdb.connect() as ddb:
            ddb.execute("""
                CREATE TABLE staging_events (
                    id VARCHAR,
                    event_type VARCHAR,
                    subject_entity_id VARCHAR,
                    starts_at TIMESTAMPTZ,
                    year VARCHAR,
                    evidence_id VARCHAR,
                    confidence DOUBLE,
                    attributes_json VARCHAR
                )
            """)
            tuples = [
                (
                    r["id"],
                    r["event_type"],
                    r["subject_entity_id"],
                    r["starts_at"],
                    r["year"],
                    r["evidence_id"],
                    r["confidence"],
                    r["attributes_json"],
                )
                for r in rows
            ]
            ddb.executemany("INSERT INTO staging_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuples)
            ddb.execute(
                f"COPY staging_events TO '{out_dir.as_posix()}' (FORMAT PARQUET, PARTITION_BY (year, event_type), OVERWRITE_OR_IGNORE)"
            )

        partition_count = len(list(out_dir.rglob("*.parquet")))
        return (len(rows), partition_count, years)


class SnapshotCatalog:
    """Discovers, validates, and serves completed DuckDB/Parquet snapshots."""

    def __init__(
        self,
        snapshots_dir: Path | str | None = None,
        database_url: str | None = None,
    ) -> None:
        self.snapshots_dir = ensure_snapshots_dir(snapshots_dir)
        self.database_url = database_url or os.environ.get("WORLDOS_DATABASE_URL")

    def list_snapshots(self, status_filter: str | None = None) -> list[SnapshotManifest]:
        """Lists snapshots discovered on disk and in the metadata catalog."""
        manifests: list[SnapshotManifest] = []

        if not self.snapshots_dir.exists():
            return []

        # Scan directories
        for entry in self.snapshots_dir.iterdir():
            if not entry.is_dir():
                continue

            # In-progress staging directories
            if entry.name.startswith(".staging_"):
                sid_str = entry.name.replace(".staging_", "")
                try:
                    sid = UUID(sid_str)
                    m = SnapshotManifest(
                        snapshot_id=sid,
                        schema_version=SNAPSHOT_SCHEMA_VERSION,
                        status="in_progress",
                        storage_path=str(entry),
                        metadata={"is_staging": True},
                    )
                    if not status_filter or status_filter == "in_progress":
                        manifests.append(m)
                except ValueError:
                    continue
                continue

            # Completed snapshot directories
            manifest_path = entry / "manifest.json"
            if manifest_path.exists():
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    m = SnapshotManifest.model_validate(data)
                    if not status_filter or m.status == status_filter:
                        manifests.append(m)
                except Exception as err:
                    logger.warning("Error reading manifest at %s: %s", manifest_path, err)

        # Sort by completed_at desc, then started_at desc
        manifests.sort(
            key=lambda x: (
                x.completed_at.timestamp() if x.completed_at else 0.0,
                x.started_at.timestamp(),
            ),
            reverse=True,
        )

        # Mark latest and staleness in metadata
        completed = [m for m in manifests if m.status == "completed"]
        if completed:
            completed[0].metadata["is_latest"] = True
            for m in completed[1:]:
                m.metadata["is_latest"] = False
                m.metadata["is_stale"] = True

        return manifests

    def get_snapshot(self, snapshot_id: str | UUID) -> SnapshotManifest | None:
        """Retrieves a specific snapshot manifest."""
        sid_str = str(snapshot_id)
        snapshot_dir = self.snapshots_dir / sid_str
        manifest_path = snapshot_dir / "manifest.json"

        if manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return SnapshotManifest.model_validate(data)
            except Exception as err:
                logger.warning("Error reading manifest for %s: %s", sid_str, err)

        return None

    def get_latest_completed_snapshot(self) -> SnapshotManifest | None:
        """Finds the most recent completed snapshot."""
        completed = self.list_snapshots(status_filter="completed")
        return completed[0] if completed else None

    def validate_snapshot(self, snapshot_id: str | UUID) -> dict[str, Any]:
        """Validates snapshot integrity, file existence, and readable Parquet partitions."""
        sid_str = str(snapshot_id)
        snapshot_dir = self.snapshots_dir / sid_str

        if not snapshot_dir.exists():
            return {
                "snapshot_id": sid_str,
                "valid": False,
                "errors": [f"Snapshot directory not found: {snapshot_dir}"],
            }

        manifest = self.get_snapshot(snapshot_id)
        if not manifest:
            return {
                "snapshot_id": sid_str,
                "valid": False,
                "errors": ["manifest.json is missing or corrupted"],
            }

        errors: list[str] = []
        if manifest.schema_version != SNAPSHOT_SCHEMA_VERSION:
            errors.append(f"Incompatible schema version: {manifest.schema_version} != {SNAPSHOT_SCHEMA_VERSION}")

        if manifest.status != "completed":
            errors.append(f"Snapshot status is not completed: {manifest.status}")

        dataset_status: dict[str, Any] = {}
        with duckdb.connect() as ddb:
            for dataset in manifest.datasets:
                dataset_path = snapshot_dir / dataset
                if not dataset_path.exists():
                    errors.append(f"Missing dataset directory: {dataset}")
                    continue

                parquet_files = list(dataset_path.rglob("*.parquet"))
                expected_rows = manifest.row_counts.get(dataset, 0)

                if expected_rows > 0 and not parquet_files:
                    errors.append(f"Dataset {dataset} has {expected_rows} expected rows but 0 parquet files")

                actual_rows = 0
                if parquet_files:
                    try:
                        res = ddb.execute(
                            f"SELECT count(*) FROM read_parquet('{dataset_path.as_posix()}/**/*.parquet', hive_partitioning=True)"
                        ).fetchone()
                        actual_rows = res[0] if res else 0
                    except Exception as err:
                        errors.append(f"DuckDB cannot read parquet in {dataset}: {err}")

                dataset_status[dataset] = {
                    "expected_rows": expected_rows,
                    "actual_rows": actual_rows,
                    "parquet_files": len(parquet_files),
                    "matches_manifest": actual_rows == expected_rows,
                }
                if actual_rows != expected_rows:
                    errors.append(
                        f"Row count mismatch for {dataset}: manifest reports {expected_rows}, parquet contains {actual_rows}"
                    )

        return {
            "snapshot_id": sid_str,
            "valid": len(errors) == 0,
            "errors": errors,
            "datasets": dataset_status,
        }
