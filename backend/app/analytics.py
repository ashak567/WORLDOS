"""DuckDB is an analytical read boundary, never a competing system of record."""
from __future__ import annotations

from pathlib import Path
from uuid import UUID

import duckdb

from app.domain import Claim, Confidence, TruthClass


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

    def derive_population_growth(self, entity_id: str | UUID) -> Claim | None:
        """Derive growth rate from historical observation points, preserving inputs and evidence."""
        with duckdb.connect(str(self.replica_path), read_only=True) as connection:
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

