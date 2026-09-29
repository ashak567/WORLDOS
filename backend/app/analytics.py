"""DuckDB is an analytical read boundary, never a competing system of record."""
from __future__ import annotations

from pathlib import Path

import duckdb


class DuckDbSpatialAnalytics:
    def __init__(self, replica_path: Path) -> None:
        self.replica_path = replica_path

    def population_series(self, entity_id: str) -> list[tuple]:
        """Query an exported, versioned Postgres snapshot; refresh is an explicit job."""
        with duckdb.connect(str(self.replica_path), read_only=True) as connection:
            return connection.execute(
                "SELECT starts_at, value FROM observations_export WHERE subject_entity_id=? ORDER BY starts_at",
                [entity_id],
            ).fetchall()

