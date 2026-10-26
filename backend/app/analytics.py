"""DuckDB is an analytical read boundary, never a competing system of record."""
from __future__ import annotations

from contextlib import contextmanager
import logging
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID

import duckdb

from .domain import Claim, Confidence, TruthClass
from .snapshots import SnapshotCatalog

logger = logging.getLogger("worldos.analytics")


class DuckDbSpatialAnalytics:
    """In-process columnar analytical query engine operating over Parquet snapshots or DuckDB files."""

    def __init__(self, replica_path: Path | str | None = None) -> None:
        self.catalog = SnapshotCatalog()
        if replica_path is None:
            latest = self.catalog.get_latest_completed_snapshot()
            if latest:
                self.target_path = Path(latest.storage_path)
            else:
                self.target_path = Path("worldos-analytics.duckdb")
        else:
            self.target_path = Path(replica_path)

        self.is_duckdb_file = self.target_path.is_file() or str(self.target_path).endswith(".duckdb")

    @contextmanager
    def _connection(self) -> Iterator[duckdb.DuckDBPyConnection]:
        if self.is_duckdb_file:
            with duckdb.connect(str(self.target_path), read_only=True) as conn:
                yield conn
        else:
            with duckdb.connect(":memory:") as conn:
                self._register_views(conn)
                yield conn

    def _register_views(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Register views over Hive-partitioned Parquet files with graceful empty table fallbacks."""
        # 1. Observations
        obs_dir = self.target_path / "observations"
        obs_files = list(obs_dir.rglob("*.parquet")) if obs_dir.exists() else []
        if obs_files:
            conn.execute(
                f"CREATE TEMPORARY VIEW observations AS SELECT * FROM read_parquet('{obs_dir.as_posix()}/**/*.parquet', hive_partitioning=True)"
            )
        else:
            conn.execute("""
                CREATE TEMPORARY TABLE observations (
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
        conn.execute("CREATE TEMPORARY VIEW observations_export AS SELECT * FROM observations")

        # 2. Entities
        ent_dir = self.target_path / "entities"
        ent_files = list(ent_dir.rglob("*.parquet")) if ent_dir.exists() else []
        if ent_files:
            conn.execute(
                f"CREATE TEMPORARY VIEW entities AS SELECT * FROM read_parquet('{ent_dir.as_posix()}/**/*.parquet', hive_partitioning=True)"
            )
        else:
            conn.execute("""
                CREATE TEMPORARY TABLE entities (
                    id VARCHAR,
                    canonical_name VARCHAR,
                    entity_type VARCHAR,
                    source_id VARCHAR,
                    confidence DOUBLE,
                    attributes_json VARCHAR,
                    created_at TIMESTAMPTZ
                )
            """)

        # 3. Geometries
        geom_dir = self.target_path / "geometries"
        geom_files = list(geom_dir.rglob("*.parquet")) if geom_dir.exists() else []
        if geom_files:
            conn.execute(
                f"CREATE TEMPORARY VIEW geometries AS SELECT * FROM read_parquet('{geom_dir.as_posix()}/**/*.parquet', hive_partitioning=True)"
            )
        else:
            conn.execute("""
                CREATE TEMPORARY TABLE geometries (
                    id VARCHAR,
                    entity_id VARCHAR,
                    geometry_kind VARCHAR,
                    geometry_geojson VARCHAR,
                    source_id VARCHAR,
                    evidence_id VARCHAR,
                    confidence DOUBLE
                )
            """)

        # 4. Events
        ev_dir = self.target_path / "events"
        ev_files = list(ev_dir.rglob("*.parquet")) if ev_dir.exists() else []
        if ev_files:
            conn.execute(
                f"CREATE TEMPORARY VIEW events AS SELECT * FROM read_parquet('{ev_dir.as_posix()}/**/*.parquet', hive_partitioning=True)"
            )
        else:
            conn.execute("""
                CREATE TEMPORARY TABLE events (
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

    def population_series(self, entity_id: str) -> list[tuple]:
        """Query historical values for an entity; operates over both DuckDB replicas and Parquet snapshots."""
        with self._connection() as connection:
            return connection.execute(
                "SELECT starts_at, value FROM observations_export WHERE subject_entity_id=? ORDER BY starts_at",
                [str(entity_id)],
            ).fetchall()

    def derive_population_growth(self, entity_id: str | UUID) -> Claim | None:
        """Derive growth rate from historical observation points, preserving inputs and evidence."""
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT id, value, starts_at, evidence_id
                   FROM observations_export
                   WHERE subject_entity_id=? AND measure='population.total'
                   ORDER BY starts_at ASC""",
                [str(entity_id)],
            ).fetchall()
        if len(rows) < 2:
            return None
        first_id, first_val, first_time, first_ev = rows[0]
        last_id, last_val, last_time, last_ev = rows[-1]
        if first_val <= 0:
            return None
        pct_change = ((last_val - first_val) / first_val) * 100.0
        evidence_list = []
        for ev in (first_ev, last_ev):
            if ev:
                try:
                    evidence_list.append(UUID(str(ev)))
                except ValueError:
                    pass

        return Claim(
            subject_entity_id=UUID(str(entity_id)),
            claim_type="population_growth_percentage",
            truth_class=TruthClass.DERIVED,
            value={"percentage_change": round(pct_change, 4), "baseline_value": first_val, "latest_value": last_val},
            unit="percent",
            method="two_point_percentage_change_v1",
            computation_version="worldos-duckdb-analytics-v1",
            inputs={
                "baseline_observation_id": str(first_id),
                "latest_observation_id": str(last_id),
                "baseline_timestamp": first_time.isoformat() if hasattr(first_time, "isoformat") else str(first_time),
                "latest_timestamp": last_time.isoformat() if hasattr(last_time, "isoformat") else str(last_time),
            },
            evidence_ids=evidence_list,
            confidence=Confidence(value=0.95, method="deterministic_analytical_derivation"),
        )

    def entity_counts_by_type(self, entity_kind: str | None = None) -> list[dict[str, Any]]:
        """Multi-entity aggregation of entity counts grouped by entity type."""
        with self._connection() as conn:
            if entity_kind:
                rows = conn.execute(
                    "SELECT entity_type, count(*) AS entity_count FROM entities WHERE entity_type = ? GROUP BY entity_type ORDER BY entity_count DESC",
                    [entity_kind],
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT entity_type, count(*) AS entity_count FROM entities GROUP BY entity_type ORDER BY entity_count DESC"
                ).fetchall()
            return [{"entity_type": r[0], "count": r[1]} for r in rows]

    def observation_counts_by_year_and_type(self, measure: str | None = None) -> list[dict[str, Any]]:
        """Multi-entity observation and entity counts grouped by calendar year and entity type."""
        with self._connection() as conn:
            where_sql = "WHERE measure = ?" if measure else ""
            params = [measure] if measure else []
            sql = f"""
                SELECT
                    year,
                    entity_type,
                    measure,
                    count(*) AS observation_count,
                    count(DISTINCT subject_entity_id) AS distinct_entities
                FROM observations
                {where_sql}
                GROUP BY year, entity_type, measure
                ORDER BY year ASC, entity_type ASC
            """
            rows = conn.execute(sql, params).fetchall()
            return [
                {
                    "year": str(r[0]),
                    "entity_type": r[1],
                    "measure": r[2],
                    "observation_count": r[3],
                    "distinct_entities": r[4],
                }
                for r in rows
            ]

    def spatial_summaries(
        self,
        measure: str = "population.total",
        year: str | int | None = None,
        entity_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Spatial summaries grouped by country or administrative entity across the snapshot."""
        with self._connection() as conn:
            conditions = ["measure = ?"]
            params: list[Any] = [measure]
            if year:
                conditions.append("year = ?")
                params.append(str(year))
            if entity_type:
                conditions.append("entity_type = ?")
                params.append(entity_type)

            where_sql = f"WHERE {' AND '.join(conditions)}"
            sql = f"""
                SELECT
                    subject_entity_id,
                    entity_canonical_name,
                    entity_type,
                    measure,
                    year,
                    count(*) AS observation_count,
                    sum(value) AS total_value,
                    avg(value) AS mean_value,
                    min(value) AS min_value,
                    max(value) AS max_value,
                    count(DISTINCT evidence_id) AS evidence_count
                FROM observations
                {where_sql}
                GROUP BY subject_entity_id, entity_canonical_name, entity_type, measure, year
                ORDER BY total_value DESC
            """
            rows = conn.execute(sql, params).fetchall()
            return [
                {
                    "entity_id": r[0],
                    "entity_canonical_name": r[1],
                    "entity_type": r[2],
                    "measure": r[3],
                    "year": str(r[4]),
                    "observation_count": r[5],
                    "total_value": round(float(r[6]), 4) if r[6] is not None else 0.0,
                    "mean_value": round(float(r[7]), 4) if r[7] is not None else 0.0,
                    "min_value": round(float(r[8]), 4) if r[8] is not None else 0.0,
                    "max_value": round(float(r[9]), 4) if r[9] is not None else 0.0,
                    "evidence_count": r[10],
                    "has_data": True,
                }
                for r in rows
            ]

    def multi_entity_temporal_trends(
        self,
        entity_ids: list[str | UUID] | None = None,
        measure: str = "population.total",
    ) -> list[dict[str, Any]]:
        """Temporal trends across multiple entities over historical snapshot data."""
        with self._connection() as conn:
            clauses = ["measure = ?"]
            params: list[Any] = [measure]
            if entity_ids:
                placeholders = ", ".join(["?"] * len(entity_ids))
                clauses.append(f"subject_entity_id IN ({placeholders})")
                params.extend([str(eid) for eid in entity_ids])

            where_sql = f"WHERE {' AND '.join(clauses)}"
            sql = f"""
                SELECT
                    subject_entity_id,
                    entity_canonical_name,
                    year,
                    starts_at,
                    value,
                    evidence_id
                FROM observations
                {where_sql}
                ORDER BY subject_entity_id ASC, starts_at ASC
            """
            rows = conn.execute(sql, params).fetchall()

            entities_map: dict[str, dict[str, Any]] = {}
            for r in rows:
                eid, name, yr, starts, val, ev_id = r
                if eid not in entities_map:
                    entities_map[eid] = {
                        "entity_id": eid,
                        "entity_canonical_name": name,
                        "measure": measure,
                        "series": [],
                        "evidence_ids": set(),
                    }
                entities_map[eid]["series"].append({
                    "year": str(yr),
                    "starts_at": starts.isoformat() if hasattr(starts, "isoformat") else str(starts),
                    "value": float(val),
                })
                if ev_id:
                    entities_map[eid]["evidence_ids"].add(str(ev_id))

            results: list[dict[str, Any]] = []
            for eid, data in entities_map.items():
                series = data["series"]
                earliest_val = series[0]["value"] if series else None
                latest_val = series[-1]["value"] if series else None
                earliest_year = series[0]["year"] if series else None
                latest_year = series[-1]["year"] if series else None
                pct_change = None
                if earliest_val is not None and latest_val is not None and earliest_val > 0:
                    pct_change = round(((latest_val - earliest_val) / earliest_val) * 100.0, 4)

                results.append({
                    "entity_id": eid,
                    "entity_canonical_name": data["entity_canonical_name"],
                    "measure": measure,
                    "earliest_year": earliest_year,
                    "latest_year": latest_year,
                    "earliest_value": earliest_val,
                    "latest_value": latest_val,
                    "percentage_change": pct_change,
                    "observation_count": len(series),
                    "series": series,
                    "evidence_ids": sorted(list(data["evidence_ids"])),
                })
            return results

    def evidence_coverage_and_freshness(self) -> dict[str, Any]:
        """Evidence-backed data coverage and freshness summaries across the analytical snapshot."""
        with self._connection() as conn:
            obs_stats = conn.execute("""
                SELECT
                    count(*) AS total_obs,
                    count(DISTINCT subject_entity_id) AS distinct_entities,
                    count(DISTINCT evidence_id) AS distinct_evidence,
                    count(DISTINCT source_slug) AS distinct_sources,
                    min(starts_at) AS earliest,
                    max(starts_at) AS latest
                FROM observations
            """).fetchone()

            source_rows = conn.execute("""
                SELECT
                    source_slug,
                    count(*) AS observation_count,
                    count(DISTINCT subject_entity_id) AS distinct_entities,
                    count(DISTINCT evidence_id) AS distinct_evidence
                FROM observations
                GROUP BY source_slug
                ORDER BY observation_count DESC
            """).fetchall()

            total_entities_res = conn.execute("SELECT count(*) FROM entities").fetchone()
            total_geom_res = conn.execute("SELECT count(DISTINCT entity_id) FROM geometries").fetchone()

            total_obs = obs_stats[0] if obs_stats else 0
            distinct_obs_entities = obs_stats[1] if obs_stats else 0
            distinct_ev = obs_stats[2] if obs_stats else 0
            distinct_src = obs_stats[3] if obs_stats else 0
            earliest_dt = obs_stats[4] if obs_stats else None
            latest_dt = obs_stats[5] if obs_stats else None
            total_entities = total_entities_res[0] if total_entities_res else 0
            entities_with_geom = total_geom_res[0] if total_geom_res else 0

            return {
                "total_observations": total_obs,
                "total_entities": total_entities,
                "total_evidence_citations": distinct_ev,
                "distinct_sources": distinct_src,
                "source_breakdown": [
                    {
                        "source_slug": sr[0],
                        "observation_count": sr[1],
                        "distinct_entities": sr[2],
                        "distinct_evidence": sr[3],
                    }
                    for sr in source_rows
                ],
                "earliest_observation": earliest_dt.isoformat() if hasattr(earliest_dt, "isoformat") else str(earliest_dt) if earliest_dt else None,
                "latest_observation": latest_dt.isoformat() if hasattr(latest_dt, "isoformat") else str(latest_dt) if latest_dt else None,
                "entities_with_observations": distinct_obs_entities,
                "entities_with_geometry": entities_with_geom,
            }

    def compare_spatial_slices(
        self,
        entity_a_id: str | UUID,
        entity_b_id: str | UUID,
        measure: str = "population.total",
        year: str | int | None = None,
    ) -> dict[str, Any]:
        """Deterministic comparison between two spatial entities for a given measure and time slice."""
        with self._connection() as conn:
            year_clause = "AND year = ?" if year else ""
            params: list[Any] = [str(entity_a_id), str(entity_b_id), measure]
            if year:
                params.append(str(year))

            sql = f"""
                SELECT
                    subject_entity_id,
                    entity_canonical_name,
                    year,
                    value,
                    unit,
                    evidence_id
                FROM observations
                WHERE subject_entity_id IN (?, ?) AND measure = ? {year_clause}
                ORDER BY starts_at DESC
            """
            rows = conn.execute(sql, params).fetchall()

            rec_a = next((r for r in rows if r[0] == str(entity_a_id)), None)
            rec_b = next((r for r in rows if r[0] == str(entity_b_id)), None)

            val_a = float(rec_a[3]) if rec_a and rec_a[3] is not None else None
            val_b = float(rec_b[3]) if rec_b and rec_b[3] is not None else None

            abs_diff = None
            ratio = None
            larger = None

            if val_a is not None and val_b is not None:
                abs_diff = round(abs(val_a - val_b), 4)
                if val_b != 0:
                    ratio = round(val_a / val_b, 4)
                if val_a > val_b:
                    larger = rec_a[1]
                elif val_b > val_a:
                    larger = rec_b[1]
                else:
                    larger = "equal"

            return {
                "measure": measure,
                "year": str(year) if year else (rec_a[2] if rec_a else rec_b[2] if rec_b else None),
                "entity_a": {
                    "entity_id": str(entity_a_id),
                    "name": rec_a[1] if rec_a else "unknown",
                    "value": val_a,
                    "unit": rec_a[4] if rec_a else None,
                    "evidence_id": str(rec_a[5]) if rec_a and rec_a[5] else None,
                },
                "entity_b": {
                    "entity_id": str(entity_b_id),
                    "name": rec_b[1] if rec_b else "unknown",
                    "value": val_b,
                    "unit": rec_b[4] if rec_b else None,
                    "evidence_id": str(rec_b[5]) if rec_b and rec_b[5] else None,
                },
                "absolute_difference": abs_diff,
                "ratio": ratio,
                "larger_entity": larger,
            }
