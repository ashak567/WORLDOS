"""Reproducible analytical benchmark suite for DuckDB analytical workloads."""
from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
import platform
import sys
import time
from pathlib import Path
from typing import Any

import duckdb

from .analytics import DuckDbSpatialAnalytics
from .snapshots import SnapshotCatalog

logger = logging.getLogger("worldos.benchmarks")


class AnalyticalBenchmarkSuite:
    """Measures representative DuckDB analytical workloads over partitioned Parquet snapshots."""

    def __init__(self, snapshot_path: Path | str | None = None) -> None:
        if snapshot_path:
            self.snapshot_path = Path(snapshot_path)
            self.catalog = SnapshotCatalog(snapshots_dir=self.snapshot_path.parent)
            manifest_file = self.snapshot_path / "manifest.json"
            if manifest_file.exists():
                try:
                    with open(manifest_file, "r", encoding="utf-8") as f:
                        self.manifest = SnapshotManifest.model_validate(json.load(f))
                except Exception:
                    self.manifest = self.catalog.get_snapshot(self.snapshot_path.name)
            else:
                self.manifest = self.catalog.get_snapshot(self.snapshot_path.name)
        else:
            self.catalog = SnapshotCatalog()
            latest = self.catalog.get_latest_completed_snapshot()
            if not latest:
                raise ValueError("No completed snapshots found to benchmark.")
            self.snapshot_path = Path(latest.storage_path)
            self.manifest = latest

        self.analytics = DuckDbSpatialAnalytics(self.snapshot_path)
        self.parquet_files = list(self.snapshot_path.rglob("*.parquet"))

    def _measure(self, name: str, description: str, query_fn: Any, iterations: int = 5) -> dict[str, Any]:
        durations_ms: list[float] = []
        result_sample: Any = None

        # Warm-up run
        try:
            result_sample = query_fn()
        except Exception as e:
            logger.warning("Warm-up run failed for %s: %s", name, e)

        for _ in range(iterations):
            start = time.perf_counter()
            query_fn()
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            durations_ms.append(elapsed_ms)

        mean_duration = sum(durations_ms) / len(durations_ms)
        min_duration = min(durations_ms)
        max_duration = max(durations_ms)

        result_count = len(result_sample) if isinstance(result_sample, (list, dict, tuple)) else 1

        return {
            "name": name,
            "description": description,
            "iterations": iterations,
            "mean_duration_ms": round(mean_duration, 3),
            "min_duration_ms": round(min_duration, 3),
            "max_duration_ms": round(max_duration, 3),
            "result_rows_or_keys": result_count,
            "snapshot_records": self.manifest.total_records if self.manifest else 0,
            "parquet_files": len(self.parquet_files),
        }

    def benchmark_snapshot_discovery(self, iterations: int = 5) -> dict[str, Any]:
        """Measures catalog discovery, manifest parsing, and schema validation."""
        def run():
            cat = SnapshotCatalog(snapshots_dir=self.snapshot_path.parent)
            snaps = cat.list_snapshots(status_filter="completed")
            if snaps:
                cat.validate_snapshot(snaps[0].snapshot_id)
            return snaps

        return self._measure(
            name="snapshot_discovery_and_validation",
            description="Scans snapshot catalogue, loads manifest, and validates partition integrity.",
            query_fn=run,
            iterations=iterations,
        )

    def benchmark_spatial_rollups(self, iterations: int = 5) -> dict[str, Any]:
        """Measures spatial summary aggregations grouped by entity over partitioned observations."""
        return self._measure(
            name="multi_entity_spatial_rollups",
            description="Aggregates observation counts, sums, means, and min/max grouped by entity and measure.",
            query_fn=lambda: self.analytics.spatial_summaries(measure="population.total"),
            iterations=iterations,
        )

    def benchmark_temporal_aggregations(self, iterations: int = 5) -> dict[str, Any]:
        """Measures observation counts grouped by calendar year and entity type."""
        return self._measure(
            name="temporal_aggregations_by_year",
            description="Columnar grouping across all observation partitions by year and entity type.",
            query_fn=lambda: self.analytics.observation_counts_by_year_and_type(),
            iterations=iterations,
        )

    def benchmark_multi_entity_trends(self, iterations: int = 5) -> dict[str, Any]:
        """Measures multi-entity time-series reconstruction and percentage change derivation."""
        return self._measure(
            name="multi_entity_temporal_trends",
            description="Reconstructs historical observation sequences and percentage deltas across entities.",
            query_fn=lambda: self.analytics.multi_entity_temporal_trends(measure="population.total"),
            iterations=iterations,
        )

    def benchmark_evidence_coverage(self, iterations: int = 5) -> dict[str, Any]:
        """Measures distinct evidence, source, and temporal boundary coverage scan."""
        return self._measure(
            name="evidence_coverage_and_freshness",
            description="Scans distinct evidence references, publisher sources, and temporal bounds.",
            query_fn=lambda: self.analytics.evidence_coverage_and_freshness(),
            iterations=iterations,
        )

    def benchmark_multi_partition_scans(self, iterations: int = 5) -> dict[str, Any]:
        """Measures deep multi-partition predicate scan across Hive partitions."""
        def run():
            with self.analytics._connection() as conn:
                return conn.execute("""
                    SELECT
                        year,
                        entity_type,
                        avg(value) AS avg_val,
                        count(*) AS cnt
                    FROM observations
                    WHERE value > 0
                    GROUP BY year, entity_type
                    ORDER BY year ASC
                """).fetchall()

        return self._measure(
            name="multi_partition_predicate_scan",
            description="Direct predicate scan and multi-dimension aggregation across Parquet partitions.",
            query_fn=run,
            iterations=iterations,
        )

    def run_all(self, iterations: int = 5) -> dict[str, Any]:
        """Executes all benchmarks and aggregates environment and workload metrics."""
        results = [
            self.benchmark_snapshot_discovery(iterations=iterations),
            self.benchmark_spatial_rollups(iterations=iterations),
            self.benchmark_temporal_aggregations(iterations=iterations),
            self.benchmark_multi_entity_trends(iterations=iterations),
            self.benchmark_evidence_coverage(iterations=iterations),
            self.benchmark_multi_partition_scans(iterations=iterations),
        ]

        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "snapshot_id": str(self.manifest.snapshot_id) if self.manifest else "unknown",
            "snapshot_path": str(self.snapshot_path),
            "total_records": self.manifest.total_records if self.manifest else 0,
            "partition_files": len(self.parquet_files),
            "environment": {
                "duckdb_version": duckdb.__version__,
                "python_version": sys.version.split()[0],
                "platform": platform.platform(),
                "processor": platform.processor(),
            },
            "benchmarks": results,
        }


def format_benchmark_table(report: dict[str, Any]) -> str:
    """Formats benchmark results as a GitHub markdown table."""
    lines = [
        "| Benchmark Workload | Mean (ms) | Min (ms) | Max (ms) | Iterations | Results |",
        "| ------------------- | ---------: | --------: | --------: | ---------: | ------: |",
    ]
    for b in report.get("benchmarks", []):
        lines.append(
            f"| `{b['name']}` | {b['mean_duration_ms']:.3f} | {b['min_duration_ms']:.3f} | {b['max_duration_ms']:.3f} | {b['iterations']} | {b['result_rows_or_keys']} |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    suite = AnalyticalBenchmarkSuite()
    rep = suite.run_all(iterations=5)
    print(json.dumps(rep, indent=2))
    print("\n" + format_benchmark_table(rep))
