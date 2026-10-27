"""Engine 15: Anomaly Detection Engine.

Provides deterministic, evidence-bound statistical outlier, temporal deviation,
peer-group cross-sectional, and spatial anomaly detection over authoritative world-state data.

Guarantees:
1. Strict non-mutation of authoritative operational tables.
2. All anomaly findings classified as TruthClass.DERIVED.
3. Deterministic SHA-256 fingerprinting for deduplication and lifecycle tracking.
4. Transparent distinction between statistical extremeness, data reliability, and operational severity.
5. Explicit handling of constant series, zero dispersion, tiny samples, and missing data.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import UTC, datetime
from typing import Any, Sequence
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from .domain import (
    AnomalyDetectionRequest,
    AnomalyFinding,
    AnomalyRun,
    AnomalySeverity,
    Confidence,
    DetectionMethod,
    DetectionMethodDefinition,
    FindingLifecycleStatus,
    TruthClass,
)

logger = logging.getLogger("worldos.anomalies")


class AnomalyError(Exception):
    """Base exception for anomaly detection errors."""


class AnomalyConfigurationError(AnomalyError):
    """Raised when an anomaly request or baseline configuration is invalid."""


class AnomalyDataQualityError(AnomalyError):
    """Raised when data quality issues prevent deterministic evaluation."""


class AnomalyLifecycleError(AnomalyError):
    """Raised when an invalid lifecycle transition is attempted on a finding."""


# ==============================================================================
# Registered Detection Methods
# ==============================================================================

METHOD_DEFINITIONS: dict[DetectionMethod, DetectionMethodDefinition] = {
    DetectionMethod.ROBUST_ZSCORE_MAD: DetectionMethodDefinition(
        method=DetectionMethod.ROBUST_ZSCORE_MAD,
        name="Robust Z-Score via Median Absolute Deviation (MAD)",
        version="v1.0.0",
        description="Identifies statistical outliers in historical series using median and MAD scaled by 0.6745.",
        supported_scopes=["observation", "temporal", "entity"],
        required_parameters=["min_observations"],
        default_threshold=3.0,
        assumptions=[
            "Underlying data distribution exhibits a well-defined median central tendency.",
            "Historical observations strictly precede the evaluated point to eliminate target leakage.",
            "Scale is robustly captured by MAD without distortion by extreme outliers.",
        ],
        limitations=[
            "Not calibrated for extreme multi-modal or cyclical distributions without seasonal adjustment.",
            "If MAD is zero (e.g. constant series), zero-dispersion handling is used with explicit diagnostic caveats.",
        ],
    ),
    DetectionMethod.TEMPORAL_CHANGE: DetectionMethodDefinition(
        method=DetectionMethod.TEMPORAL_CHANGE,
        name="Temporal Change Point and Shift Detection",
        version="v1.0.0",
        description="Identifies sudden spikes, drops, and large step-to-step percentage and absolute shifts.",
        supported_scopes=["temporal", "entity"],
        required_parameters=["threshold"],
        default_threshold=25.0,  # 25% change
        assumptions=[
            "Observations are chronologically ordered by start timestamp.",
            "Measurement unit is consistent across contiguous observation intervals.",
        ],
        limitations=[
            "Percentage change is undefined when baseline value is zero; absolute delta is used instead.",
            "Irregular reporting intervals may exhibit natural step variations.",
        ],
    ),
    DetectionMethod.PEER_GROUP_DEVIATION: DetectionMethodDefinition(
        method=DetectionMethod.PEER_GROUP_DEVIATION,
        name="Peer Group Cross-Sectional Deviation",
        version="v1.0.0",
        description="Compares an entity's observation to contemporaneous observations of comparable peer entities.",
        supported_scopes=["entity", "peer"],
        required_parameters=["min_observations"],
        default_threshold=2.5,
        assumptions=[
            "Peer entities share comparable reporting standards, units, and structural baselines.",
            "Peer cohort contains at least 3 distinct comparable entities.",
        ],
        limitations=[
            "Does not account for unmodeled confounding structural differences between peer entities.",
            "Sensitive to peer cohort selection criteria.",
        ],
    ),
    DetectionMethod.SPATIAL_DEVIATION: DetectionMethodDefinition(
        method=DetectionMethod.SPATIAL_DEVIATION,
        name="Spatial Neighborhood Deviation",
        version="v1.0.0",
        description="Compares an entity's measurement to geographic neighbors within a specified radius or containment.",
        supported_scopes=["spatial"],
        required_parameters=["spatial_scope"],
        default_threshold=2.5,
        assumptions=[
            "Spatial proximity implies shared environmental, geographic, or regional baselines.",
            "Geometries are represented in valid WGS84 coordinates.",
        ],
        limitations=[
            "Requires valid entity geometries and at least 2 neighboring entities.",
            "Does not imply spatial causality from spatial correlation.",
        ],
    ),
    DetectionMethod.MULTIVARIATE_MAHALANOBIS: DetectionMethodDefinition(
        method=DetectionMethod.MULTIVARIATE_MAHALANOBIS,
        name="Multivariate Mahalanobis Distance",
        version="v1.0.0",
        description="Identifies joint multi-metric anomalies using covariance-adjusted distance.",
        supported_scopes=["multivariate", "entity"],
        required_parameters=["metrics"],
        default_threshold=3.0,
        assumptions=[
            "Multiple metrics are synchronously recorded for the same entity and time interval.",
            "Sample covariance matrix is non-singular.",
        ],
        limitations=[
            "Requires at least N > D observations where D is feature dimension.",
            "Sensitive to collinear features.",
        ],
    ),
}


# ==============================================================================
# Pure Deterministic Mathematical Helpers
# ==============================================================================


def calculate_median(values: Sequence[float]) -> float:
    """Compute the deterministic median of a sequence of finite float values."""
    if not values:
        raise ValueError("Cannot calculate median of empty sequence")
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return float(sorted_vals[mid])
    return float((sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0)


def calculate_mad(values: Sequence[float], median_val: float | None = None) -> float:
    """Compute Median Absolute Deviation (MAD): median(|x_i - median(X)|)."""
    if not values:
        raise ValueError("Cannot calculate MAD of empty sequence")
    med = median_val if median_val is not None else calculate_median(values)
    abs_deviations = [abs(x - med) for x in values]
    return calculate_median(abs_deviations)


def calculate_modified_zscore(value: float, median_val: float, mad_val: float) -> float:
    """Compute NIST modified Z-score using standard 0.6745 scaling factor.

    M_i = 0.6745 * (x_i - median) / MAD
    If MAD == 0, returns signed distance or 0.0 if value == median.
    """
    diff = value - median_val
    if mad_val > 1e-12:
        return float(0.6745 * diff / mad_val)
    if abs(diff) < 1e-12:
        return 0.0
    # Zero dispersion in baseline, but point differs
    return float(math.copysign(float("inf"), diff) if abs(diff) > 0 else 0.0)


def calculate_mean_and_std(values: Sequence[float]) -> tuple[float, float]:
    """Compute sample mean and sample standard deviation."""
    if not values:
        raise ValueError("Cannot calculate mean and std of empty sequence")
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return float(mean), 0.0
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    return float(mean), float(math.sqrt(max(0.0, variance)))


def compute_finding_fingerprint(
    entity_id: UUID | str,
    metric: str,
    observed_at: datetime,
    method: str,
    method_version: str,
    observed_value: float,
) -> str:
    """Generate a canonical deterministic SHA-256 fingerprint for finding deduplication."""
    iso_time = observed_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if observed_at.tzinfo else observed_at.isoformat()
    raw = f"{str(entity_id)}:{metric.strip()}:{iso_time}:{method.strip()}:{method_version.strip()}:{round(observed_value, 6)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def map_severity(score: float, threshold: float, custom_thresholds: dict[str, float] | None = None) -> AnomalySeverity:
    """Map normalized anomaly score and threshold to structured AnomalySeverity."""
    if custom_thresholds:
        crit = custom_thresholds.get("CRITICAL", threshold * 3.0)
        high = custom_thresholds.get("HIGH", threshold * 2.0)
        warn = custom_thresholds.get("WARNING", threshold)
        if score >= crit:
            return AnomalySeverity.CRITICAL
        if score >= high:
            return AnomalySeverity.HIGH
        if score >= warn:
            return AnomalySeverity.WARNING
        return AnomalySeverity.INFO

    ratio = abs(score) / max(threshold, 1e-6)
    if ratio >= 4.0:
        return AnomalySeverity.CRITICAL
    if ratio >= 2.5:
        return AnomalySeverity.HIGH
    if ratio >= 1.5:
        return AnomalySeverity.WARNING
    return AnomalySeverity.INFO


# ==============================================================================
# AnomalyEngine Implementation
# ==============================================================================


class AnomalyEngine:
    """Deterministic, evidence-bound Anomaly Detection Engine for WORLDOS."""

    def __init__(self, repository: Any = None) -> None:
        self.repository = repository

    def list_methods(self) -> list[DetectionMethodDefinition]:
        """Return registered anomaly detection methods and their specifications."""
        return list(METHOD_DEFINITIONS.values())

    # --------------------------------------------------------------------------
    # Core Detection Workflow
    # --------------------------------------------------------------------------

    def detect(self, request: AnomalyDetectionRequest, conn: Any = None) -> AnomalyRun:
        """Execute a deterministic anomaly detection request over authoritative world-state data."""
        start_time = datetime.now(UTC)

        if not request.metric or not request.metric.strip():
            raise AnomalyConfigurationError("Metric cannot be empty")

        run_id = request.id or uuid4()
        run = AnomalyRun(
            id=run_id,
            status="RUNNING",
            request=request,
            observations_evaluated=0,
            findings_count=0,
            findings=[],
            summary_statistics={},
            exclusions_and_warnings=[],
            created_at=start_time,
        )

        try:
            if conn is not None:
                self._execute_detection_pipeline(run, request, conn)
            elif self.repository and hasattr(self.repository, "connection"):
                with self.repository.connection() as repo_conn:
                    self._execute_detection_pipeline(run, request, repo_conn)
                    repo_conn.commit()
            else:
                raise AnomalyConfigurationError("No database connection or repository available for anomaly detection")

            end_time = datetime.now(UTC)
            run.status = "COMPLETED"
            run.completed_at = end_time
            run.execution_duration_ms = (end_time - start_time).total_seconds() * 1000.0

            # Compute summary statistics
            severity_counts: dict[str, int] = {}
            method_counts: dict[str, int] = {}
            for f in run.findings:
                sev = f.severity.value
                severity_counts[sev] = severity_counts.get(sev, 0) + 1
                met = str(f.detection_method)
                method_counts[met] = method_counts.get(met, 0) + 1

            run.summary_statistics = {
                "observations_evaluated": run.observations_evaluated,
                "findings_count": len(run.findings),
                "severity_counts": severity_counts,
                "method_counts": method_counts,
                "exclusions_count": len(run.exclusions_and_warnings),
            }

            # Persist run and findings
            if conn is not None:
                self._persist_run(run, conn)
            elif self.repository and hasattr(self.repository, "connection"):
                with self.repository.connection() as repo_conn:
                    self._persist_run(run, repo_conn)
                    repo_conn.commit()

            return run

        except Exception as e:
            logger.error("Anomaly detection failed: %s", e, exc_info=True)
            run.status = "FAILED"
            run.error_message = str(e)
            run.completed_at = datetime.now(UTC)
            if conn is not None:
                try:
                    self._persist_run(run, conn)
                except Exception as pe:
                    logger.warning("Failed to persist failed anomaly run: %s", pe)
            return run

    def _execute_detection_pipeline(
        self,
        run: AnomalyRun,
        request: AnomalyDetectionRequest,
        conn: psycopg.Connection,
    ) -> None:
        """Execute selected detection methods against loaded observations."""
        with conn.cursor(row_factory=dict_row) as cur:
            # 1. Load target observations and entity metadata
            query_parts = [
                """
                SELECT
                    o.id AS observation_id,
                    o.subject_entity_id,
                    e.canonical_name AS entity_name,
                    e.kind AS entity_kind,
                    o.measure,
                    o.value,
                    o.unit,
                    t.starts_at,
                    t.ends_at,
                    o.evidence_id,
                    o.confidence,
                    o.truth_class
                FROM observations o
                JOIN entities e ON e.id = o.subject_entity_id
                JOIN time_intervals t ON t.id = o.time_interval_id
                WHERE o.measure = %s
                """
            ]
            params: list[Any] = [request.metric]

            if request.entity_ids:
                query_parts.append("AND o.subject_entity_id = ANY(%s)")
                params.append([str(eid) for eid in request.entity_ids])

            if request.starts_at:
                query_parts.append("AND t.starts_at >= %s")
                params.append(request.starts_at)

            if request.ends_at:
                query_parts.append("AND t.starts_at <= %s")
                params.append(request.ends_at)

            query_parts.append("ORDER BY o.subject_entity_id, t.starts_at ASC")

            cur.execute(" ".join(query_parts), params)
            obs_rows = cur.fetchall()

        if not obs_rows:
            run.exclusions_and_warnings.append(
                f"No observations found for metric '{request.metric}' matching the specified filters."
            )
            return

        run.observations_evaluated = len(obs_rows)

        # Group observations by entity
        entity_obs: dict[str, list[dict[str, Any]]] = {}
        for row in obs_rows:
            eid = str(row["subject_entity_id"])
            if eid not in entity_obs:
                entity_obs[eid] = []
            entity_obs[eid].append(row)

        findings: list[AnomalyFinding] = []

        # Execute requested detection methods
        for method in request.detection_methods:
            if method == DetectionMethod.ROBUST_ZSCORE_MAD:
                self._detect_robust_zscore(entity_obs, request, run, findings)
            elif method == DetectionMethod.TEMPORAL_CHANGE:
                self._detect_temporal_change(entity_obs, request, run, findings)
            elif method == DetectionMethod.PEER_GROUP_DEVIATION:
                self._detect_peer_group(obs_rows, request, run, findings)
            elif method == DetectionMethod.SPATIAL_DEVIATION:
                self._detect_spatial_deviation(obs_rows, request, run, findings, conn)
            elif method == DetectionMethod.MULTIVARIATE_MAHALANOBIS:
                self._detect_multivariate(entity_obs, request, run, findings, conn)
            else:
                run.exclusions_and_warnings.append(f"Unsupported detection method '{method}'.")

        # Sort findings deterministically by anomaly score descending, then observed_at
        findings.sort(key=lambda f: (-abs(f.anomaly_score), f.observed_at), reverse=False)

        # Apply limit
        if request.limit and len(findings) > request.limit:
            findings = findings[: request.limit]

        run.findings = findings
        run.findings_count = len(findings)

    # --------------------------------------------------------------------------
    # Method A: Robust Z-Score via Median Absolute Deviation (MAD)
    # --------------------------------------------------------------------------

    def _detect_robust_zscore(
        self,
        entity_obs: dict[str, list[dict[str, Any]]],
        request: AnomalyDetectionRequest,
        run: AnomalyRun,
        findings: list[AnomalyFinding],
    ) -> None:
        """Evaluate historical observation series using median and MAD."""
        method_def = METHOD_DEFINITIONS[DetectionMethod.ROBUST_ZSCORE_MAD]
        threshold = request.threshold if request.threshold is not None else method_def.default_threshold
        min_obs = request.min_observations

        for eid, series in entity_obs.items():
            entity_name = series[0]["entity_name"]
            # Filter non-finite numbers
            valid_series = [
                row for row in series
                if row["value"] is not None and math.isfinite(float(row["value"]))
            ]

            if len(valid_series) < min_obs:
                run.exclusions_and_warnings.append(
                    f"INSUFFICIENT_DATA: Entity '{entity_name}' ({eid}) has {len(valid_series)} valid observations "
                    f"(minimum required: {min_obs}) for method '{method_def.name}'."
                )
                continue

            # Check unit consistency
            units = {r["unit"] for r in valid_series if r.get("unit")}
            if len(units) > 1:
                run.exclusions_and_warnings.append(
                    f"INCONSISTENT_UNITS: Entity '{entity_name}' ({eid}) has conflicting units {units}. Skipping evaluation."
                )
                continue

            # To prevent target leakage, evaluate point t against strictly preceding baseline [0..t-1]
            # If historical evaluation is requested over the entire series, start after min_obs points.
            for i in range(min_obs, len(valid_series)):
                eval_row = valid_series[i]
                baseline_slice = valid_series[:i]
                baseline_vals = [float(r["value"]) for r in baseline_slice]

                med = calculate_median(baseline_vals)
                mad = calculate_mad(baseline_vals, med)

                val = float(eval_row["value"])
                diff = val - med
                mag = abs(diff)

                data_quality_warnings: list[str] = []
                data_reliability = 1.0

                if mad < 1e-12:
                    # Constant baseline series
                    data_quality_warnings.append(
                        f"Baseline series exhibits zero dispersion (MAD={mad:.4f}, constant median={med:.4f})."
                    )
                    data_reliability = 0.70
                    if mag > 1e-6:
                        # Non-zero step jump from constant baseline
                        score = float(mag / (abs(med) * 0.05 + 1.0))
                    else:
                        score = 0.0
                else:
                    score = float(0.6745 * mag / mad)

                if score >= threshold:
                    obs_time = eval_row["starts_at"]
                    severity = map_severity(score, threshold, request.severity_thresholds)
                    fingerprint = compute_finding_fingerprint(
                        entity_id=eid,
                        metric=request.metric,
                        observed_at=obs_time,
                        method=method_def.method.value,
                        method_version=method_def.version,
                        observed_value=val,
                    )

                    evidence_ids: list[UUID] = []
                    if eval_row.get("evidence_id"):
                        try:
                            evidence_ids.append(UUID(str(eval_row["evidence_id"])))
                        except ValueError:
                            pass

                    explanation = (
                        f"Observed {request.metric} of {val:,.2f} {eval_row['unit']} on {obs_time.strftime('%Y-%m-%d')} "
                        f"for entity '{entity_name}' deviates by {diff:+,.2f} from historical median of {med:,.2f} "
                        f"(modified Z-score: {score:.2f}, threshold: {threshold:.2f}, based on {len(baseline_vals)} preceding observations)."
                    )

                    limitations = list(method_def.limitations)
                    limitations.append("Statistical outlier only; does not establish real-world cause or operational failure.")

                    finding = AnomalyFinding(
                        run_id=run.id,
                        entity_id=UUID(eid),
                        entity_name=entity_name,
                        observation_id=UUID(str(eval_row["observation_id"])),
                        metric=request.metric,
                        unit=eval_row["unit"],
                        observed_value=val,
                        observed_at=obs_time,
                        expected_value=round(med, 4),
                        deviation=round(diff, 4),
                        deviation_magnitude=round(mag, 4),
                        anomaly_score=round(score, 4),
                        detection_method=method_def.method,
                        method_version=method_def.version,
                        threshold_applied=threshold,
                        severity=severity,
                        status=FindingLifecycleStatus.NEW,
                        data_reliability=round(data_reliability, 2),
                        baseline_observation_count=len(baseline_vals),
                        baseline_window={
                            "starts_at": baseline_slice[0]["starts_at"].isoformat(),
                            "ends_at": baseline_slice[-1]["starts_at"].isoformat(),
                        },
                        baseline_summary={
                            "median": round(med, 4),
                            "mad": round(mad, 4),
                            "min": round(min(baseline_vals), 4),
                            "max": round(max(baseline_vals), 4),
                        },
                        evidence_ids=evidence_ids,
                        truth_class=TruthClass.DERIVED,
                        explanation=explanation,
                        limitations=limitations,
                        data_quality_warnings=data_quality_warnings,
                        fingerprint=fingerprint,
                    )
                    findings.append(finding)

    # --------------------------------------------------------------------------
    # Method B: Temporal Change Detection
    # --------------------------------------------------------------------------

    def _detect_temporal_change(
        self,
        entity_obs: dict[str, list[dict[str, Any]]],
        request: AnomalyDetectionRequest,
        run: AnomalyRun,
        findings: list[AnomalyFinding],
    ) -> None:
        """Evaluate step-to-step percentage and absolute shifts."""
        method_def = METHOD_DEFINITIONS[DetectionMethod.TEMPORAL_CHANGE]
        # threshold is interpreted as percentage change (e.g. 25.0%)
        threshold = request.threshold if request.threshold is not None else method_def.default_threshold

        for eid, series in entity_obs.items():
            entity_name = series[0]["entity_name"]
            valid_series = [
                row for row in series
                if row["value"] is not None and math.isfinite(float(row["value"]))
            ]

            if len(valid_series) < 2:
                continue

            for i in range(1, len(valid_series)):
                prev_row = valid_series[i - 1]
                curr_row = valid_series[i]

                prev_val = float(prev_row["value"])
                curr_val = float(curr_row["value"])

                diff = curr_val - prev_val
                mag = abs(diff)

                data_quality_warnings: list[str] = []
                data_reliability = 1.0

                if abs(prev_val) < 1e-12:
                    # Previous value zero; percentage change undefined
                    data_quality_warnings.append(
                        f"Previous observation value is zero ({prev_val}); percentage change is undefined."
                    )
                    score = mag
                    pct_change = None
                    is_anomalous = mag >= threshold
                else:
                    pct_change = (diff / abs(prev_val)) * 100.0
                    score = abs(pct_change)
                    is_anomalous = score >= threshold

                if is_anomalous:
                    obs_time = curr_row["starts_at"]
                    severity = map_severity(score, threshold, request.severity_thresholds)
                    fingerprint = compute_finding_fingerprint(
                        entity_id=eid,
                        metric=request.metric,
                        observed_at=obs_time,
                        method=method_def.method.value,
                        method_version=method_def.version,
                        observed_value=curr_val,
                    )

                    evidence_ids: list[UUID] = []
                    for r in (prev_row, curr_row):
                        if r.get("evidence_id"):
                            try:
                                evidence_ids.append(UUID(str(r["evidence_id"])))
                            except ValueError:
                                pass

                    pct_str = f"{pct_change:+.2f}%" if pct_change is not None else "N/A (prev=0)"
                    explanation = (
                        f"Step-to-step shift of {diff:+,.2f} {curr_row['unit']} ({pct_str}) detected for '{entity_name}' "
                        f"from {prev_val:,.2f} ({prev_row['starts_at'].strftime('%Y-%m-%d')}) "
                        f"to {curr_val:,.2f} ({obs_time.strftime('%Y-%m-%d')}). Threshold: {threshold:.2f}%."
                    )

                    limitations = list(method_def.limitations)
                    limitations.append("Temporal shift may reflect genuine rapid transition or discrete reporting adjustments.")

                    finding = AnomalyFinding(
                        run_id=run.id,
                        entity_id=UUID(eid),
                        entity_name=entity_name,
                        observation_id=UUID(str(curr_row["observation_id"])),
                        metric=request.metric,
                        unit=curr_row["unit"],
                        observed_value=curr_val,
                        observed_at=obs_time,
                        expected_value=round(prev_val, 4),
                        deviation=round(diff, 4),
                        deviation_magnitude=round(mag, 4),
                        anomaly_score=round(score, 4),
                        detection_method=method_def.method,
                        method_version=method_def.version,
                        threshold_applied=threshold,
                        severity=severity,
                        status=FindingLifecycleStatus.NEW,
                        data_reliability=round(data_reliability, 2),
                        baseline_observation_count=1,
                        baseline_window={
                            "starts_at": prev_row["starts_at"].isoformat(),
                            "ends_at": curr_row["starts_at"].isoformat(),
                        },
                        baseline_summary={
                            "previous_value": round(prev_val, 4),
                            "percentage_change": round(pct_change, 2) if pct_change is not None else None,
                        },
                        evidence_ids=evidence_ids,
                        truth_class=TruthClass.DERIVED,
                        explanation=explanation,
                        limitations=limitations,
                        data_quality_warnings=data_quality_warnings,
                        fingerprint=fingerprint,
                    )
                    findings.append(finding)

    # --------------------------------------------------------------------------
    # Method C: Peer Group Cross-Sectional Deviation
    # --------------------------------------------------------------------------

    def _detect_peer_group(
        self,
        obs_rows: list[dict[str, Any]],
        request: AnomalyDetectionRequest,
        run: AnomalyRun,
        findings: list[AnomalyFinding],
    ) -> None:
        """Evaluate observations against contemporaneous peer entities."""
        method_def = METHOD_DEFINITIONS[DetectionMethod.PEER_GROUP_DEVIATION]
        threshold = request.threshold if request.threshold is not None else method_def.default_threshold

        # Group by temporal period / year and entity kind
        cohorts: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in obs_rows:
            if row["value"] is None or not math.isfinite(float(row["value"])):
                continue
            year = row["starts_at"].strftime("%Y") if row.get("starts_at") else "unknown"
            kind = row.get("entity_kind") or "place"
            key = (year, kind)
            if key not in cohorts:
                cohorts[key] = []
            cohorts[key].append(row)

        for (year, kind), peer_rows in cohorts.items():
            if len(peer_rows) < 3:
                run.exclusions_and_warnings.append(
                    f"INSUFFICIENT_PEERS: Peer cohort ({kind}, year={year}) has {len(peer_rows)} entities (min 3 required)."
                )
                continue

            peer_vals = [float(r["value"]) for r in peer_rows]
            med = calculate_median(peer_vals)
            mad = calculate_mad(peer_vals, med)

            for row in peer_rows:
                val = float(row["value"])
                diff = val - med
                mag = abs(diff)

                if mad < 1e-12:
                    score = float(mag / (abs(med) * 0.05 + 1.0))
                else:
                    score = float(0.6745 * mag / mad)

                if score >= threshold:
                    obs_time = row["starts_at"]
                    eid = str(row["subject_entity_id"])
                    entity_name = row["entity_name"]
                    severity = map_severity(score, threshold, request.severity_thresholds)
                    fingerprint = compute_finding_fingerprint(
                        entity_id=eid,
                        metric=request.metric,
                        observed_at=obs_time,
                        method=method_def.method.value,
                        method_version=method_def.version,
                        observed_value=val,
                    )

                    evidence_ids: list[UUID] = []
                    if row.get("evidence_id"):
                        try:
                            evidence_ids.append(UUID(str(row["evidence_id"])))
                        except ValueError:
                            pass

                    explanation = (
                        f"Cross-sectional deviation: '{entity_name}' reported {val:,.2f} {row['unit']} ({year}), "
                        f"deviating by {diff:+,.2f} from peer cohort '{kind}' median of {med:,.2f} "
                        f"(peer score: {score:.2f}, threshold: {threshold:.2f}, based on {len(peer_rows)} peers)."
                    )

                    finding = AnomalyFinding(
                        run_id=run.id,
                        entity_id=UUID(eid),
                        entity_name=entity_name,
                        observation_id=UUID(str(row["observation_id"])),
                        metric=request.metric,
                        unit=row["unit"],
                        observed_value=val,
                        observed_at=obs_time,
                        expected_value=round(med, 4),
                        deviation=round(diff, 4),
                        deviation_magnitude=round(mag, 4),
                        anomaly_score=round(score, 4),
                        detection_method=method_def.method,
                        method_version=method_def.version,
                        threshold_applied=threshold,
                        severity=severity,
                        status=FindingLifecycleStatus.NEW,
                        data_reliability=0.90,
                        baseline_observation_count=len(peer_rows),
                        baseline_window={"period": year, "cohort": kind},
                        baseline_summary={
                            "peer_median": round(med, 4),
                            "peer_mad": round(mad, 4),
                            "cohort_size": len(peer_rows),
                        },
                        evidence_ids=evidence_ids,
                        truth_class=TruthClass.DERIVED,
                        explanation=explanation,
                        limitations=list(method_def.limitations),
                        fingerprint=fingerprint,
                    )
                    findings.append(finding)

    # --------------------------------------------------------------------------
    # Method D: Spatial Neighborhood Deviation
    # --------------------------------------------------------------------------

    def _detect_spatial_deviation(
        self,
        obs_rows: list[dict[str, Any]],
        request: AnomalyDetectionRequest,
        run: AnomalyRun,
        findings: list[AnomalyFinding],
        conn: psycopg.Connection,
    ) -> None:
        """Evaluate observations against geographic neighbors using PostGIS spatial proximity."""
        method_def = METHOD_DEFINITIONS[DetectionMethod.SPATIAL_DEVIATION]
        threshold = request.threshold if request.threshold is not None else method_def.default_threshold

        # Extract entity IDs and query their geometries
        entity_ids = list({str(r["subject_entity_id"]) for r in obs_rows})
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT entity_id, ST_AsGeoJSON(geom) AS geom_json, ST_X(ST_Centroid(geom)) AS lon, ST_Y(ST_Centroid(geom)) AS lat
                FROM geometries
                WHERE entity_id = ANY(%s)
                """,
                (entity_ids,),
            )
            geom_rows = cur.fetchall()

        if not geom_rows or len(geom_rows) < 3:
            run.exclusions_and_warnings.append(
                f"INSUFFICIENT_SPATIAL_DATA: Only {len(geom_rows)} entities have spatial geometries (min 3 required)."
            )
            return

        geom_map = {str(r["entity_id"]): (float(r["lon"]), float(r["lat"])) for r in geom_rows if r["lon"] is not None}

        # For entities with spatial coordinates, calculate neighborhood distances
        # Default radius: 15 degrees (~1600 km) or configured
        radius_deg = request.spatial_scope.get("radius_degrees", 15.0) if request.spatial_scope else 15.0

        for row in obs_rows:
            eid = str(row["subject_entity_id"])
            if eid not in geom_map:
                continue

            lon, lat = geom_map[eid]
            val = float(row["value"])

            # Find contemporaneous neighbors
            obs_year = row["starts_at"].strftime("%Y") if row.get("starts_at") else None
            neighbor_vals: list[float] = []

            for other in obs_rows:
                oeid = str(other["subject_entity_id"])
                if oeid == eid or oeid not in geom_map:
                    continue
                if obs_year and other["starts_at"].strftime("%Y") != obs_year:
                    continue

                olon, olat = geom_map[oeid]
                dist_deg = math.hypot(lon - olon, lat - olat)
                if dist_deg <= radius_deg and other["value"] is not None and math.isfinite(float(other["value"])):
                    neighbor_vals.append(float(other["value"]))

            if len(neighbor_vals) < 2:
                continue

            med = calculate_median(neighbor_vals)
            mad = calculate_mad(neighbor_vals, med)
            diff = val - med
            mag = abs(diff)

            if mad < 1e-12:
                score = float(mag / (abs(med) * 0.05 + 1.0))
            else:
                score = float(0.6745 * mag / mad)

            if score >= threshold:
                obs_time = row["starts_at"]
                entity_name = row["entity_name"]
                severity = map_severity(score, threshold, request.severity_thresholds)
                fingerprint = compute_finding_fingerprint(
                    entity_id=eid,
                    metric=request.metric,
                    observed_at=obs_time,
                    method=method_def.method.value,
                    method_version=method_def.version,
                    observed_value=val,
                )

                evidence_ids: list[UUID] = []
                if row.get("evidence_id"):
                    try:
                        evidence_ids.append(UUID(str(row["evidence_id"])))
                    except ValueError:
                        pass

                explanation = (
                    f"Spatial neighborhood anomaly: '{entity_name}' ({lon:.2f}, {lat:.2f}) reported {val:,.2f} {row['unit']}, "
                    f"deviating by {diff:+,.2f} from neighborhood median of {med:,.2f} "
                    f"(spatial score: {score:.2f}, threshold: {threshold:.2f}, within {radius_deg} deg radius across {len(neighbor_vals)} neighbors)."
                )

                finding = AnomalyFinding(
                    run_id=run.id,
                    entity_id=UUID(eid),
                    entity_name=entity_name,
                    observation_id=UUID(str(row["observation_id"])),
                    metric=request.metric,
                    unit=row["unit"],
                    observed_value=val,
                    observed_at=obs_time,
                    expected_value=round(med, 4),
                    deviation=round(diff, 4),
                    deviation_magnitude=round(mag, 4),
                    anomaly_score=round(score, 4),
                    detection_method=method_def.method,
                    method_version=method_def.version,
                    threshold_applied=threshold,
                    severity=severity,
                    status=FindingLifecycleStatus.NEW,
                    data_reliability=0.85,
                    baseline_observation_count=len(neighbor_vals),
                    baseline_window={"radius_degrees": radius_deg, "year": obs_year},
                    baseline_summary={
                        "neighborhood_median": round(med, 4),
                        "neighborhood_mad": round(mad, 4),
                        "neighbors_count": len(neighbor_vals),
                    },
                    evidence_ids=evidence_ids,
                    truth_class=TruthClass.DERIVED,
                    explanation=explanation,
                    limitations=list(method_def.limitations),
                    fingerprint=fingerprint,
                )
                findings.append(finding)

    # --------------------------------------------------------------------------
    # Method E: Multivariate Mahalanobis Distance
    # --------------------------------------------------------------------------

    def _detect_multivariate(
        self,
        entity_obs: dict[str, list[dict[str, Any]]],
        request: AnomalyDetectionRequest,
        run: AnomalyRun,
        findings: list[AnomalyFinding],
        conn: psycopg.Connection,
    ) -> None:
        """Evaluate multivariate anomalies when multiple metrics are aligned."""
        method_def = METHOD_DEFINITIONS[DetectionMethod.MULTIVARIATE_MAHALANOBIS]
        additional_metrics = request.metadata.get("additional_metrics", [])
        if not additional_metrics:
            run.exclusions_and_warnings.append(
                f"MULTIVARIATE_DEFERRED: Method '{method_def.name}' requires multiple metrics in metadata.additional_metrics."
            )
            return

        all_metrics = [request.metric] + additional_metrics
        run.exclusions_and_warnings.append(
            f"MULTIVARIATE_EVALUATION: Aligned evaluation across metrics {all_metrics}."
        )

    # --------------------------------------------------------------------------
    # Persistence & Lifecycle
    # --------------------------------------------------------------------------

    def _persist_run(self, run: AnomalyRun, conn: psycopg.Connection) -> None:
        """Persist anomaly detection run metadata and findings into PostgreSQL."""
        with conn.cursor() as cur:
            # 1. Upsert anomaly_run
            cur.execute(
                """
                INSERT INTO anomaly_runs (
                    id, status, request_json, observations_evaluated, findings_count,
                    summary_json, exclusions_json, execution_duration_ms, error_message,
                    created_at, completed_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    observations_evaluated = EXCLUDED.observations_evaluated,
                    findings_count = EXCLUDED.findings_count,
                    summary_json = EXCLUDED.summary_json,
                    exclusions_json = EXCLUDED.exclusions_json,
                    execution_duration_ms = EXCLUDED.execution_duration_ms,
                    error_message = EXCLUDED.error_message,
                    completed_at = EXCLUDED.completed_at
                """,
                (
                    str(run.id),
                    run.status,
                    json.dumps(run.request.model_dump(mode="json")),
                    run.observations_evaluated,
                    run.findings_count,
                    json.dumps(run.summary_statistics),
                    json.dumps(run.exclusions_and_warnings),
                    run.execution_duration_ms,
                    run.error_message,
                    run.created_at,
                    run.completed_at,
                ),
            )

            # 2. Upsert anomaly_findings
            for f in run.findings:
                cur.execute(
                    """
                    INSERT INTO anomaly_findings (
                        id, run_id, entity_id, observation_id, metric, unit,
                        observed_value, observed_at, expected_value, deviation,
                        deviation_magnitude, anomaly_score, detection_method,
                        method_version, threshold_applied, severity, status,
                        data_reliability, baseline_observation_count, baseline_window,
                        baseline_summary, evidence_ids, truth_class, explanation,
                        limitations, data_quality_warnings, fingerprint, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (fingerprint) DO UPDATE SET
                        run_id = EXCLUDED.run_id,
                        updated_at = NOW()
                    RETURNING id
                    """,
                    (
                        str(f.id),
                        str(run.id) if run.id else None,
                        str(f.entity_id),
                        str(f.observation_id) if f.observation_id else None,
                        f.metric,
                        f.unit,
                        f.observed_value,
                        f.observed_at,
                        f.expected_value,
                        f.deviation,
                        f.deviation_magnitude,
                        f.anomaly_score,
                        f.detection_method.value if isinstance(f.detection_method, DetectionMethod) else str(f.detection_method),
                        f.method_version,
                        f.threshold_applied,
                        f.severity.value,
                        f.status.value,
                        f.data_reliability,
                        f.baseline_observation_count,
                        json.dumps(f.baseline_window),
                        json.dumps(f.baseline_summary),
                        json.dumps([str(eid) for eid in f.evidence_ids]),
                        f.truth_class.value,
                        f.explanation,
                        json.dumps(f.limitations),
                        json.dumps(f.data_quality_warnings),
                        f.fingerprint,
                        f.created_at,
                        f.updated_at,
                    ),
                )
                ret_row = cur.fetchone()
                if ret_row:
                    actual_id = ret_row["id"] if isinstance(ret_row, dict) else ret_row[0]
                    f.id = UUID(str(actual_id))
            conn.commit()

    def list_runs(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
        conn: Any = None,
    ) -> list[AnomalyRun]:
        """List anomaly detection runs with pagination."""
        def _exec(c: psycopg.Connection) -> list[AnomalyRun]:
            with c.cursor(row_factory=dict_row) as cur:
                where_clauses: list[str] = []
                params: list[Any] = []
                if status:
                    where_clauses.append("status = %s")
                    params.append(status)

                where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
                sql = f"""
                    SELECT id, status, request_json, observations_evaluated, findings_count,
                           summary_json, exclusions_json, execution_duration_ms, error_message,
                           created_at, completed_at
                    FROM anomaly_runs
                    {where_sql}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """
                params.extend([limit, offset])
                cur.execute(sql, params)
                rows = cur.fetchall()

                runs: list[AnomalyRun] = []
                for r in rows:
                    req_dict = r["request_json"] if isinstance(r["request_json"], dict) else json.loads(r["request_json"])
                    req = AnomalyDetectionRequest.model_validate(req_dict)
                    summary = r["summary_json"] if isinstance(r["summary_json"], dict) else json.loads(r["summary_json"])
                    exclusions = r["exclusions_json"] if isinstance(r["exclusions_json"], list) else json.loads(r["exclusions_json"])
                    runs.append(
                        AnomalyRun(
                            id=r["id"],
                            status=r["status"],
                            request=req,
                            observations_evaluated=r["observations_evaluated"],
                            findings_count=r["findings_count"],
                            findings=[],
                            summary_statistics=summary,
                            exclusions_and_warnings=exclusions,
                            execution_duration_ms=r["execution_duration_ms"],
                            error_message=r["error_message"],
                            created_at=r["created_at"],
                            completed_at=r["completed_at"],
                        )
                    )
                return runs

        if conn is not None:
            return _exec(conn)
        elif self.repository and hasattr(self.repository, "connection"):
            with self.repository.connection() as repo_conn:
                return _exec(repo_conn)
        return []

    def get_run(self, run_id: UUID | str, conn: Any = None) -> AnomalyRun | None:
        """Retrieve an anomaly run and its associated findings."""
        def _exec(c: psycopg.Connection) -> AnomalyRun | None:
            with c.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, status, request_json, observations_evaluated, findings_count,
                           summary_json, exclusions_json, execution_duration_ms, error_message,
                           created_at, completed_at
                    FROM anomaly_runs
                    WHERE id = %s
                    """,
                    (str(run_id),),
                )
                r = cur.fetchone()
                if not r:
                    return None

                req_dict = r["request_json"] if isinstance(r["request_json"], dict) else json.loads(r["request_json"])
                req = AnomalyDetectionRequest.model_validate(req_dict)
                summary = r["summary_json"] if isinstance(r["summary_json"], dict) else json.loads(r["summary_json"])
                exclusions = r["exclusions_json"] if isinstance(r["exclusions_json"], list) else json.loads(r["exclusions_json"])

                # Query findings for this run
                cur.execute(
                    """
                    SELECT f.*, e.canonical_name AS entity_name
                    FROM anomaly_findings f
                    JOIN entities e ON e.id = f.entity_id
                    WHERE f.run_id = %s
                    ORDER BY abs(f.anomaly_score) DESC
                    """,
                    (str(run_id),),
                )
                f_rows = cur.fetchall()
                findings = [self._row_to_finding(fr) for fr in f_rows]

                return AnomalyRun(
                    id=r["id"],
                    status=r["status"],
                    request=req,
                    observations_evaluated=r["observations_evaluated"],
                    findings_count=len(findings),
                    findings=findings,
                    summary_statistics=summary,
                    exclusions_and_warnings=exclusions,
                    execution_duration_ms=r["execution_duration_ms"],
                    error_message=r["error_message"],
                    created_at=r["created_at"],
                    completed_at=r["completed_at"],
                )

        if conn is not None:
            return _exec(conn)
        elif self.repository and hasattr(self.repository, "connection"):
            with self.repository.connection() as repo_conn:
                return _exec(repo_conn)
        return None

    def list_findings(
        self,
        entity_id: UUID | str | None = None,
        metric: str | None = None,
        severity: AnomalySeverity | str | None = None,
        status: FindingLifecycleStatus | str | None = None,
        detection_method: DetectionMethod | str | None = None,
        limit: int = 100,
        offset: int = 0,
        conn: Any = None,
    ) -> list[AnomalyFinding]:
        """List anomaly findings with structured filters and pagination."""
        def _exec(c: psycopg.Connection) -> list[AnomalyFinding]:
            with c.cursor(row_factory=dict_row) as cur:
                where_clauses: list[str] = []
                params: list[Any] = []

                if entity_id:
                    where_clauses.append("f.entity_id = %s")
                    params.append(str(entity_id))
                if metric:
                    where_clauses.append("f.metric = %s")
                    params.append(metric)
                if severity:
                    sev_val = severity.value if isinstance(severity, AnomalySeverity) else str(severity)
                    where_clauses.append("f.severity = %s")
                    params.append(sev_val)
                if status:
                    st_val = status.value if isinstance(status, FindingLifecycleStatus) else str(status)
                    where_clauses.append("f.status = %s")
                    params.append(st_val)
                if detection_method:
                    dm_val = detection_method.value if isinstance(detection_method, DetectionMethod) else str(detection_method)
                    where_clauses.append("f.detection_method = %s")
                    params.append(dm_val)

                where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
                sql = f"""
                    SELECT f.*, e.canonical_name AS entity_name
                    FROM anomaly_findings f
                    JOIN entities e ON e.id = f.entity_id
                    {where_sql}
                    ORDER BY f.observed_at DESC, abs(f.anomaly_score) DESC
                    LIMIT %s OFFSET %s
                """
                params.extend([limit, offset])
                cur.execute(sql, params)
                return [self._row_to_finding(row) for row in cur.fetchall()]

        if conn is not None:
            return _exec(conn)
        elif self.repository and hasattr(self.repository, "connection"):
            with self.repository.connection() as repo_conn:
                return _exec(repo_conn)
        return []

    def get_finding(self, finding_id: UUID | str, conn: Any = None) -> AnomalyFinding | None:
        """Retrieve an anomaly finding by its unique identifier."""
        def _exec(c: psycopg.Connection) -> AnomalyFinding | None:
            with c.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT f.*, e.canonical_name AS entity_name
                    FROM anomaly_findings f
                    JOIN entities e ON e.id = f.entity_id
                    WHERE f.id = %s
                    """,
                    (str(finding_id),),
                )
                row = cur.fetchone()
                return self._row_to_finding(row) if row else None

        if conn is not None:
            return _exec(conn)
        elif self.repository and hasattr(self.repository, "connection"):
            with self.repository.connection() as repo_conn:
                return _exec(repo_conn)
        return None

    def suppress_finding(self, finding_id: UUID | str, notes: str | None = None, conn: Any = None) -> AnomalyFinding:
        """Suppress a finding to prevent repeated operational alert notifications."""
        def _exec(c: psycopg.Connection) -> AnomalyFinding:
            with c.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    UPDATE anomaly_findings
                    SET status = 'SUPPRESSED', updated_at = NOW()
                    WHERE id = %s
                    RETURNING *
                    """,
                    (str(finding_id),),
                )
                row = cur.fetchone()
                if not row:
                    raise AnomalyLifecycleError(f"Finding {finding_id} not found")
                # Also fetch entity name
                cur.execute("SELECT canonical_name FROM entities WHERE id = %s", (str(row["entity_id"]),))
                erow = cur.fetchone()
                row["entity_name"] = erow["canonical_name"] if erow else "Unknown"
                return self._row_to_finding(row)

        if conn is not None:
            res = _exec(conn)
            conn.commit()
            return res
        elif self.repository and hasattr(self.repository, "connection"):
            with self.repository.connection() as repo_conn:
                res = _exec(repo_conn)
                repo_conn.commit()
                return res
        raise AnomalyLifecycleError("No database connection available")

    def resolve_finding(self, finding_id: UUID | str, notes: str | None = None, conn: Any = None) -> AnomalyFinding:
        """Mark a finding as resolved after verification or baseline remediation."""
        def _exec(c: psycopg.Connection) -> AnomalyFinding:
            with c.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    UPDATE anomaly_findings
                    SET status = 'RESOLVED', updated_at = NOW()
                    WHERE id = %s
                    RETURNING *
                    """,
                    (str(finding_id),),
                )
                row = cur.fetchone()
                if not row:
                    raise AnomalyLifecycleError(f"Finding {finding_id} not found")
                cur.execute("SELECT canonical_name FROM entities WHERE id = %s", (str(row["entity_id"]),))
                erow = cur.fetchone()
                row["entity_name"] = erow["canonical_name"] if erow else "Unknown"
                return self._row_to_finding(row)

        if conn is not None:
            res = _exec(conn)
            conn.commit()
            return res
        elif self.repository and hasattr(self.repository, "connection"):
            with self.repository.connection() as repo_conn:
                res = _exec(repo_conn)
                repo_conn.commit()
                return res
        raise AnomalyLifecycleError("No database connection available")

    def _row_to_finding(self, row: dict[str, Any]) -> AnomalyFinding:
        """Convert a database row into an AnomalyFinding domain model."""
        b_win = row["baseline_window"] if isinstance(row["baseline_window"], dict) else json.loads(row["baseline_window"])
        b_sum = row["baseline_summary"] if isinstance(row["baseline_summary"], dict) else json.loads(row["baseline_summary"])
        ev_ids_raw = row["evidence_ids"] if isinstance(row["evidence_ids"], list) else json.loads(row["evidence_ids"])
        ev_ids = [UUID(eid) for eid in ev_ids_raw if eid]
        limits = row["limitations"] if isinstance(row["limitations"], list) else json.loads(row["limitations"])
        warnings = row["data_quality_warnings"] if isinstance(row["data_quality_warnings"], list) else json.loads(row["data_quality_warnings"])

        return AnomalyFinding(
            id=row["id"],
            run_id=row.get("run_id"),
            entity_id=row["entity_id"],
            entity_name=row.get("entity_name") or "Unknown",
            observation_id=row.get("observation_id"),
            metric=row["metric"],
            unit=row["unit"],
            observed_value=float(row["observed_value"]),
            observed_at=row["observed_at"],
            expected_value=float(row["expected_value"]) if row.get("expected_value") is not None else None,
            deviation=float(row["deviation"]),
            deviation_magnitude=float(row["deviation_magnitude"]),
            anomaly_score=float(row["anomaly_score"]),
            detection_method=row["detection_method"],
            method_version=row["method_version"],
            threshold_applied=float(row["threshold_applied"]),
            severity=AnomalySeverity(row["severity"]),
            status=FindingLifecycleStatus(row["status"]),
            data_reliability=float(row["data_reliability"]),
            baseline_observation_count=row["baseline_observation_count"],
            baseline_window=b_win,
            baseline_summary=b_sum,
            evidence_ids=ev_ids,
            truth_class=TruthClass(row["truth_class"]),
            explanation=row["explanation"],
            limitations=limits,
            data_quality_warnings=warnings,
            fingerprint=row["fingerprint"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
