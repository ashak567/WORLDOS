"""Explicit Postgres-to-DuckDB snapshots for reproducible analytical work."""
from __future__ import annotations

import os
from pathlib import Path

import duckdb
import psycopg


def export_observations(database_url: str, output_path: Path) -> int:
    """Replace a derived replica atomically from the PostGIS system of record."""
    with psycopg.connect(database_url) as postgres, postgres.cursor() as cursor:
        cursor.execute(
            """SELECT o.id::text, o.subject_entity_id::text, o.measure, o.value::double precision, o.unit,
                      t.starts_at, ST_AsGeoJSON(g.geometry) AS geometry, o.evidence_id::text, o.truth_class
               FROM observations o JOIN time_intervals t ON t.id=o.time_interval_id
               LEFT JOIN LATERAL (
                 SELECT geometry FROM geometries WHERE entity_id=o.subject_entity_id ORDER BY created_at DESC LIMIT 1
               ) g ON true"""
        )
        rows = cursor.fetchall()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(output_path)) as replica:
        replica.execute("DROP TABLE IF EXISTS observations_export")
        replica.execute("""CREATE TABLE observations_export (
            id VARCHAR, subject_entity_id VARCHAR, measure VARCHAR, value DOUBLE, unit VARCHAR,
            starts_at TIMESTAMPTZ, geometry JSON, evidence_id VARCHAR, truth_class VARCHAR
        )""")
        replica.executemany("INSERT INTO observations_export VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return len(rows)


if __name__ == "__main__":
    destination = Path(os.environ.get("WORLDOS_DUCKDB_PATH", "worldos-analytics.duckdb"))
    print(f"exported {export_observations(os.environ['WORLDOS_DATABASE_URL'], destination)} observations to {destination}")
