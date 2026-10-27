"""Engine 18: Bounded Deterministic Prediction Engine.

Estimates future values and trajectories from historical observations, deterministic
forecasting models, explicit uncertainty intervals, and validated contextual inputs.

Guarantees:
1. Authoritative Operational Non-Mutation: Never mutates entities, observations, or geometries.
2. Explicit Epistemic Classification: All forecast points are classified as TruthClass.PREDICTED.
3. Target Leakage Prevention: Historical backtesting strictly isolates past observations.
4. Deterministic Computation: Pure reproducible mathematical models with SHA-256 fingerprints.
5. Honest Uncertainty Representation: Provides residual-based prediction intervals where justified.
6. Baseline Benchmarking: Always compares candidate methods against a naive baseline.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import UTC, datetime, timedelta
from typing import Any, Sequence
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from .domain import (
    BacktestRequest,
    BacktestResult,
    PredictionEvaluation,
    PredictionMethod,
    PredictionMethodDefinition,
    PredictionPoint,
    PredictionRequest,
    PredictionRun,
    PredictionStatus,
    TruthClass,
)

logger = logging.getLogger("worldos.prediction")


class PredictionError(Exception):
    """Base exception for prediction engine errors."""


class PredictionConfigurationError(PredictionError):
    """Raised when prediction parameters or requested horizons are invalid."""


class PredictionDataQualityError(PredictionError):
    """Raised when data quality issues prevent deterministic forecasting."""


# ==============================================================================
# Registered Forecasting Methods & Metadata
# ==============================================================================

METHOD_DEFINITIONS: dict[PredictionMethod, PredictionMethodDefinition] = {
    PredictionMethod.NAIVE_BASELINE: PredictionMethodDefinition(
        method=PredictionMethod.NAIVE_BASELINE,
        name="Naive Last-Observation Baseline",
        version="v1.0.0",
        description="Forecasts future values using the latest valid historical observation. Serves as benchmark.",
        required_parameters=[],
        min_observations=2,
        supports_prediction_intervals=True,
        assumptions=[
            "Future state is most reasonably estimated by the most recent verified observation.",
            "Historical one-step deviations estimate future drift uncertainty.",
        ],
        limitations=[
            "Does not capture trends, cyclicality, or structural turning points.",
            "Prediction intervals expand indefinitely with forecast horizon.",
        ],
    ),
    PredictionMethod.SEASONAL_NAIVE: PredictionMethodDefinition(
        method=PredictionMethod.SEASONAL_NAIVE,
        name="Seasonal Naive Baseline",
        version="v1.0.0",
        description="Forecasts future values by repeating the corresponding observation from the previous seasonal cycle.",
        required_parameters=["season_length"],
        min_observations=4,
        supports_prediction_intervals=True,
        assumptions=[
            "Data exhibits stable, recurrent seasonal cycles of fixed periodicity.",
            "Historical series spans at least two full seasonal cycles.",
        ],
        limitations=[
            "Requires at least 2 * season_length historical observations.",
            "Fails if reporting intervals are irregular or non-periodic.",
        ],
    ),
    PredictionMethod.MOVING_AVERAGE: PredictionMethodDefinition(
        method=PredictionMethod.MOVING_AVERAGE,
        name="Rolling-Window Moving Average",
        version="v1.0.0",
        description="Forecasts future values using the arithmetic mean of the most recent historical window.",
        required_parameters=["window"],
        min_observations=3,
        supports_prediction_intervals=True,
        assumptions=[
            "Short-term mean level represents the expected equilibrium of the metric.",
            "High-frequency noise cancels out over the rolling window.",
        ],
        limitations=[
            "Lags behind strong secular trends.",
            "Multi-step recursive projection decays toward a flat constant.",
        ],
    ),
    PredictionMethod.LINEAR_TREND: PredictionMethodDefinition(
        method=PredictionMethod.LINEAR_TREND,
        name="Ordinary Least Squares Linear Trend Extrapolation",
        version="v1.0.0",
        description="Fits an ordinary least squares linear regression over chronological time steps with analytical prediction intervals.",
        required_parameters=[],
        min_observations=3,
        supports_prediction_intervals=True,
        assumptions=[
            "The metric exhibits a steady rate of change over the observation period.",
            "Residuals are approximately homoscedastic with zero mean.",
        ],
        limitations=[
            "Linear extrapolation can produce unrealistic negative or unbounded values for bounded metrics.",
            "Sensitive to historical turning points and structural regime shifts.",
        ],
    ),
    PredictionMethod.AUTO_SELECT: PredictionMethodDefinition(
        method=PredictionMethod.AUTO_SELECT,
        name="Automated Walk-Forward Model Selection",
        version="v1.0.0",
        description="Evaluates all eligible methods via rolling-origin backtesting against the naive baseline, selecting the lowest MAE model.",
        required_parameters=[],
        min_observations=4,
        supports_prediction_intervals=True,
        assumptions=[
            "Past out-of-sample forecast accuracy indicates future out-of-sample generalization.",
            "The candidate model must outperform the naive baseline on held-out horizons.",
        ],
        limitations=[
            "Requires sufficient historical depth for walk-forward splits.",
            "Execution cost scales with the number of candidate methods.",
        ],
    ),
}


# ==============================================================================
# Pure Deterministic Mathematical Routines
# ==============================================================================


def calculate_mean(values: Sequence[float]) -> float:
    """Compute arithmetic mean of a numeric sequence."""
    if not values:
        raise ValueError("Cannot compute mean of empty sequence")
    return float(sum(values) / len(values))


def calculate_variance_and_std(values: Sequence[float], ddof: int = 1) -> tuple[float, float]:
    """Compute sample variance and sample standard deviation."""
    n = len(values)
    if n <= ddof:
        return 0.0, 0.0
    mean_val = calculate_mean(values)
    sum_sq = sum((x - mean_val) ** 2 for x in values)
    var = sum_sq / (n - ddof)
    return float(var), float(math.sqrt(max(0.0, var)))


def calculate_linear_regression(x: Sequence[float], y: Sequence[float]) -> dict[str, float]:
    """Compute ordinary least squares linear regression parameters.

    Returns:
        dict with: slope, intercept, r_squared, residual_std, is_constant
    """
    n = len(x)
    if n != len(y) or n < 2:
        raise ValueError("At least 2 points required for linear regression")

    x_mean = calculate_mean(x)
    y_mean = calculate_mean(y)

    ss_xx = sum((xi - x_mean) ** 2 for xi in x)
    ss_yy = sum((yi - y_mean) ** 2 for yi in y)
    ss_xy = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))

    if ss_xx == 0.0:
        # All x are identical
        return {
            "slope": 0.0,
            "intercept": y_mean,
            "r_squared": 1.0 if ss_yy == 0.0 else 0.0,
            "residual_std": 0.0,
            "is_constant": 1.0,
        }

    slope = ss_xy / ss_xx
    intercept = y_mean - slope * x_mean

    # Compute residuals and residual standard error
    residuals = [yi - (intercept + slope * xi) for xi, yi in zip(x, y)]
    residual_ss = sum(r**2 for r in residuals)
    df = max(1, n - 2)
    residual_std = math.sqrt(residual_ss / df) if df > 0 else 0.0

    r_squared = 1.0 - (residual_ss / ss_yy) if ss_yy > 0.0 else 1.0
    r_squared = max(0.0, min(1.0, r_squared))

    return {
        "slope": float(slope),
        "intercept": float(intercept),
        "r_squared": float(r_squared),
        "residual_std": float(residual_std),
        "is_constant": 1.0 if ss_yy == 0.0 else 0.0,
    }


def get_z_multiplier(confidence_level: float) -> float:
    """Return standard normal critical value z_(alpha/2) for confidence level."""
    # Common two-tailed normal quantiles
    if confidence_level >= 0.999:
        return 3.2905
    if confidence_level >= 0.99:
        return 2.5758
    if confidence_level >= 0.98:
        return 2.3263
    if confidence_level >= 0.95:
        return 1.95996
    if confidence_level >= 0.90:
        return 1.64485
    if confidence_level >= 0.80:
        return 1.28155
    if confidence_level >= 0.70:
        return 1.03643
    if confidence_level >= 0.50:
        return 0.67449
    return 1.960


def _extract_int(val: Any, default: int = 100) -> int:
    """Safely extract an integer from an integer, string, or Query object."""
    if hasattr(val, "default"):
        val = getattr(val, "default")
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def advance_prediction_timestamp(base: datetime, step_index: int, step_size: int, step_unit: str) -> datetime:
    """Deterministically advance a timestamp by step_index * step_size in step_unit."""
    unit = step_unit.lower()
    total_delta = step_index * step_size

    if unit in ("year", "years"):
        try:
            return base.replace(year=base.year + total_delta)
        except ValueError:
            # Leap year edge case (Feb 29)
            return base.replace(year=base.year + total_delta, day=28)

    if unit in ("month", "months"):
        year_add = (base.month + total_delta - 1) // 12
        new_month = ((base.month + total_delta - 1) % 12) + 1
        day = min(base.day, 28)
        return base.replace(year=base.year + year_add, month=new_month, day=day)

    if unit in ("day", "days"):
        return base + timedelta(days=total_delta)

    if unit in ("hour", "hours"):
        return base + timedelta(hours=total_delta)

    return base + timedelta(days=total_delta)


def compute_prediction_fingerprint(
    entity_id: UUID,
    metric: str,
    method: str,
    horizon: int,
    step_size: int,
    step_unit: str,
    confidence_level: float,
    observations: list[dict[str, Any]],
    method_params: dict[str, Any],
) -> str:
    """Compute a canonical SHA-256 fingerprint for a prediction run."""
    canonical_obs = [
        {"t": obs["observed_at"].isoformat() if isinstance(obs["observed_at"], datetime) else str(obs["observed_at"]), "v": float(obs["value"])}
        for obs in sorted(observations, key=lambda o: o["observed_at"])
    ]
    payload = {
        "entity_id": str(entity_id),
        "metric": metric.strip().lower(),
        "method": method,
        "horizon": horizon,
        "step_size": step_size,
        "step_unit": step_unit.lower(),
        "confidence_level": round(confidence_level, 4),
        "observations": canonical_obs,
        "method_params": method_params,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compute_point_fingerprint(
    run_id: UUID,
    step_index: int,
    forecast_timestamp: datetime,
    predicted_value: float,
    lower_bound: float | None,
    upper_bound: float | None,
) -> str:
    """Compute a canonical SHA-256 fingerprint for a single prediction point."""
    payload = {
        "run_id": str(run_id),
        "step_index": step_index,
        "forecast_timestamp": forecast_timestamp.isoformat(),
        "predicted_value": round(predicted_value, 6),
        "lower_bound": round(lower_bound, 6) if lower_bound is not None else None,
        "upper_bound": round(upper_bound, 6) if upper_bound is not None else None,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def calculate_error_metrics(
    actuals: Sequence[float],
    predictions: Sequence[float],
    lower_bounds: Sequence[float | None] | None = None,
    upper_bounds: Sequence[float | None] | None = None,
    historical_in_sample: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Calculate standard forecast evaluation metrics (MAE, RMSE, MASE, Bias, Coverage)."""
    n = len(actuals)
    if n == 0 or len(predictions) != n:
        raise ValueError("Actuals and predictions must have equal non-zero length")

    errors = [float(p - a) for a, p in zip(actuals, predictions)]
    abs_errors = [abs(e) for e in errors]

    mae = float(sum(abs_errors) / n)
    rmse = float(math.sqrt(sum(e**2 for e in errors) / n))
    bias = float(sum(errors) / n)

    # MASE: Mean Absolute Scaled Error (Hyndman & Koehler, 2006)
    # Scaled by in-sample one-step naive absolute errors
    mase: float | None = None
    if historical_in_sample and len(historical_in_sample) >= 2:
        naive_errors = [
            abs(historical_in_sample[i] - historical_in_sample[i - 1])
            for i in range(1, len(historical_in_sample))
        ]
        scale = sum(naive_errors) / len(naive_errors)
        if scale > 0.0:
            mase = float(mae / scale)

    # Coverage: Proportion of actuals falling within [lower_bound, upper_bound]
    interval_coverage: float | None = None
    if lower_bounds is not None and upper_bounds is not None and len(lower_bounds) == n:
        covered = 0
        valid_intervals = 0
        for a, lb, ub in zip(actuals, lower_bounds, upper_bounds):
            if lb is not None and ub is not None:
                valid_intervals += 1
                if lb <= a <= ub:
                    covered += 1
        if valid_intervals > 0:
            interval_coverage = float(covered / valid_intervals)

    return {
        "mae": round(mae, 6),
        "rmse": round(rmse, 6),
        "mase": round(mase, 6) if mase is not None else None,
        "bias": round(bias, 6),
        "interval_coverage": round(interval_coverage, 4) if interval_coverage is not None else None,
    }


# ==============================================================================
# Engine 18 Core Implementation
# ==============================================================================


class PredictionEngine:
    """Engine 18: Bounded Deterministic Forecasting and Walk-Forward Evaluation.

    Operates strictly read-only against authoritative operational world state.
    """

    def __init__(self, repository: Any = None) -> None:
        self.repository = repository
        self.method_registry = METHOD_DEFINITIONS

    def list_methods(self) -> list[PredictionMethodDefinition]:
        """List all registered deterministic forecasting methods."""
        return list(self.method_registry.values())

    def predict(
        self,
        request: PredictionRequest,
        conn: psycopg.Connection | None = None,
    ) -> PredictionRun:
        """Create, execute, and persist a bounded deterministic forecasting run."""
        start_time = datetime.now(UTC)

        # Ensure database connection
        if conn is None:
            if not self.repository:
                raise PredictionConfigurationError("WorldRepository required when no database connection provided")
            with self.repository._connection() as managed_conn:
                return self._execute_predict(request, managed_conn, start_time)
        return self._execute_predict(request, conn, start_time)

    def _execute_predict(
        self,
        request: PredictionRequest,
        conn: psycopg.Connection,
        start_time: datetime,
    ) -> PredictionRun:
        # Step 1: Read historical observations strictly read-only
        observations = self._load_observations(
            entity_id=request.entity_id,
            metric=request.metric,
            starts_at=request.starts_at,
            ends_at=request.ends_at,
            conn=conn,
        )

        quality_warnings: list[str] = []
        assumptions: list[str] = []
        limitations: list[str] = []

        # Validate minimum observations
        if len(observations) < request.min_observations:
            run_record = PredictionRun(
                id=request.id,
                status=PredictionStatus.INSUFFICIENT_DATA,
                request=request,
                selected_method=request.method,
                entity_id=request.entity_id,
                metric=request.metric,
                unit="",
                observations_count=len(observations),
                trajectory_points_count=0,
                trajectory=[],
                quality_warnings=[
                    f"Insufficient observations: found {len(observations)}, requires at least {request.min_observations}"
                ],
                assumptions=["Requires sufficient verified historical measurements."],
                limitations=["Forecast could not be generated due to insufficient empirical history."],
                reproducibility_fingerprint="",
                execution_duration_ms=(datetime.now(UTC) - start_time).total_seconds() * 1000.0,
                error_message=f"Insufficient observations ({len(observations)} < {request.min_observations})",
                created_at=start_time,
                completed_at=datetime.now(UTC),
            )
            self._persist_run(run_record, conn)
            return run_record

        # Check unit consistency
        units = {obs["unit"] for obs in observations if obs.get("unit")}
        if len(units) > 1:
            raise PredictionDataQualityError(
                f"Conflicting measurement units found for metric '{request.metric}': {sorted(units)}"
            )
        metric_unit = units.pop() if units else ""

        # Extract values and timestamps
        sorted_obs = sorted(observations, key=lambda o: o["observed_at"])
        values = [float(o["value"]) for o in sorted_obs]
        last_obs = sorted_obs[-1]
        last_timestamp: datetime = last_obs["observed_at"]

        # Check for constant series
        val_min = min(values)
        val_max = max(values)
        is_constant = val_min == val_max
        if is_constant:
            quality_warnings.append(
                f"Historical observations are constant (value={val_min}). Scale and trend variability are zero."
            )

        # Historical summary
        mean_val = calculate_mean(values)
        _, std_val = calculate_variance_and_std(values)
        historical_summary = {
            "count": len(values),
            "starts_at": sorted_obs[0]["observed_at"].isoformat(),
            "ends_at": last_timestamp.isoformat(),
            "min": val_min,
            "max": val_max,
            "mean": round(mean_val, 6),
            "std": round(std_val, 6),
            "is_constant": is_constant,
            "latest_value": values[-1],
        }

        # Step 2: Determine method (handle AUTO_SELECT)
        selected_method = request.method
        auto_selection_details: dict[str, Any] = {}

        if selected_method == PredictionMethod.AUTO_SELECT:
            selected_method, auto_selection_details = self._auto_select_method(
                values=values,
                request=request,
            )
            assumptions.append(
                f"Model auto-selected: '{selected_method.value}' achieved lowest walk-forward backtest error."
            )

        method_def = self.method_registry.get(selected_method)
        if not method_def:
            raise PredictionConfigurationError(f"Unsupported prediction method '{selected_method}'")

        assumptions.extend(method_def.assumptions)
        limitations.extend(method_def.limitations)

        # Step 3: Compute Forecast Trajectory
        trajectory: list[PredictionPoint] = []
        model_parameters: dict[str, Any] = {
            "selected_method": selected_method.value,
            "confidence_level": request.confidence_level,
            "horizon": request.horizon,
            "step_size": request.step_size,
            "step_unit": request.step_unit,
        }
        if auto_selection_details:
            model_parameters["auto_selection"] = auto_selection_details

        # Collect evidence IDs from supporting observations
        evidence_ids: list[UUID] = []
        for o in sorted_obs:
            eid = o.get("evidence_id")
            if eid and eid not in evidence_ids:
                evidence_ids.append(eid if isinstance(eid, UUID) else UUID(str(eid)))

        z_mult = get_z_multiplier(request.confidence_level)

        if selected_method == PredictionMethod.NAIVE_BASELINE:
            trajectory, method_params = self._forecast_naive(
                run_id=request.id,
                entity_id=request.entity_id,
                metric=request.metric,
                unit=metric_unit,
                values=values,
                last_timestamp=last_timestamp,
                horizon=request.horizon,
                step_size=request.step_size,
                step_unit=request.step_unit,
                confidence_level=request.confidence_level,
                z_mult=z_mult,
                evidence_ids=evidence_ids,
            )
            model_parameters.update(method_params)

        elif selected_method == PredictionMethod.SEASONAL_NAIVE:
            season_length = int(request.method_params.get("season_length", 4))
            if len(values) < 2 * season_length:
                raise PredictionDataQualityError(
                    f"Seasonal naive requires at least {2 * season_length} observations, but only {len(values)} are available"
                )
            trajectory, method_params = self._forecast_seasonal_naive(
                run_id=request.id,
                entity_id=request.entity_id,
                metric=request.metric,
                unit=metric_unit,
                values=values,
                last_timestamp=last_timestamp,
                season_length=season_length,
                horizon=request.horizon,
                step_size=request.step_size,
                step_unit=request.step_unit,
                confidence_level=request.confidence_level,
                z_mult=z_mult,
                evidence_ids=evidence_ids,
            )
            model_parameters.update(method_params)

        elif selected_method == PredictionMethod.MOVING_AVERAGE:
            window = int(request.method_params.get("window", 3))
            if len(values) < window:
                raise PredictionDataQualityError(
                    f"Moving average window {window} exceeds available observations ({len(values)})"
                )
            trajectory, method_params = self._forecast_moving_average(
                run_id=request.id,
                entity_id=request.entity_id,
                metric=request.metric,
                unit=metric_unit,
                values=values,
                last_timestamp=last_timestamp,
                window=window,
                horizon=request.horizon,
                step_size=request.step_size,
                step_unit=request.step_unit,
                confidence_level=request.confidence_level,
                z_mult=z_mult,
                evidence_ids=evidence_ids,
            )
            model_parameters.update(method_params)

        elif selected_method == PredictionMethod.LINEAR_TREND:
            trajectory, method_params = self._forecast_linear_trend(
                run_id=request.id,
                entity_id=request.entity_id,
                metric=request.metric,
                unit=metric_unit,
                values=values,
                last_timestamp=last_timestamp,
                horizon=request.horizon,
                step_size=request.step_size,
                step_unit=request.step_unit,
                confidence_level=request.confidence_level,
                z_mult=z_mult,
                evidence_ids=evidence_ids,
            )
            model_parameters.update(method_params)

        # Step 4: Reproducibility fingerprint
        fingerprint = compute_prediction_fingerprint(
            entity_id=request.entity_id,
            metric=request.metric,
            method=selected_method.value,
            horizon=request.horizon,
            step_size=request.step_size,
            step_unit=request.step_unit,
            confidence_level=request.confidence_level,
            observations=sorted_obs,
            method_params=model_parameters,
        )

        completed_at = datetime.now(UTC)
        duration_ms = (completed_at - start_time).total_seconds() * 1000.0

        run_record = PredictionRun(
            id=request.id,
            status=PredictionStatus.COMPLETED,
            request=request,
            selected_method=selected_method,
            method_version="v1.0.0",
            entity_id=request.entity_id,
            metric=request.metric,
            unit=metric_unit,
            observations_count=len(values),
            trajectory_points_count=len(trajectory),
            trajectory=trajectory,
            historical_summary=historical_summary,
            model_parameters=model_parameters,
            evaluation=None,
            quality_warnings=quality_warnings,
            assumptions=assumptions,
            limitations=limitations,
            reproducibility_fingerprint=fingerprint,
            execution_duration_ms=duration_ms,
            created_at=start_time,
            completed_at=completed_at,
        )

        # Step 5: Persist run and trajectory
        self._persist_run(run_record, conn)
        return run_record

    # --------------------------------------------------------------------------
    # Forecasting Implementations
    # --------------------------------------------------------------------------

    def _forecast_naive(
        self,
        run_id: UUID,
        entity_id: UUID,
        metric: str,
        unit: str,
        values: list[float],
        last_timestamp: datetime,
        horizon: int,
        step_size: int,
        step_unit: str,
        confidence_level: float,
        z_mult: float,
        evidence_ids: list[UUID],
    ) -> tuple[list[PredictionPoint], dict[str, Any]]:
        latest = values[-1]
        diffs = [values[i] - values[i - 1] for i in range(1, len(values))]
        _, diff_std = calculate_variance_and_std(diffs)

        trajectory: list[PredictionPoint] = []
        for h in range(1, horizon + 1):
            ts = advance_prediction_timestamp(last_timestamp, h, step_size, step_unit)
            half_width = z_mult * diff_std * math.sqrt(h)
            lb = latest - half_width
            ub = latest + half_width

            fp = compute_point_fingerprint(run_id, h, ts, latest, lb, ub)
            pt = PredictionPoint(
                run_id=run_id,
                step_index=h,
                entity_id=entity_id,
                metric=metric,
                unit=unit,
                forecast_timestamp=ts,
                predicted_value=latest,
                lower_bound=lb,
                upper_bound=ub,
                confidence_level=confidence_level,
                method=PredictionMethod.NAIVE_BASELINE,
                truth_class=TruthClass.PREDICTED,
                evidence_ids=evidence_ids,
                assumptions=["Last observed value remains constant across forecast horizon."],
                limitations=["Does not extrapolate trends."],
                fingerprint=fp,
            )
            trajectory.append(pt)

        return trajectory, {"latest_value": latest, "diff_std": round(diff_std, 6)}

    def _forecast_seasonal_naive(
        self,
        run_id: UUID,
        entity_id: UUID,
        metric: str,
        unit: str,
        values: list[float],
        last_timestamp: datetime,
        season_length: int,
        horizon: int,
        step_size: int,
        step_unit: str,
        confidence_level: float,
        z_mult: float,
        evidence_ids: list[UUID],
    ) -> tuple[list[PredictionPoint], dict[str, Any]]:
        seasonal_diffs = [
            values[i] - values[i - season_length]
            for i in range(season_length, len(values))
        ]
        _, s_std = calculate_variance_and_std(seasonal_diffs)

        trajectory: list[PredictionPoint] = []
        for h in range(1, horizon + 1):
            ts = advance_prediction_timestamp(last_timestamp, h, step_size, step_unit)
            # Cycle index back into history
            k = (h - 1) % season_length
            hist_idx = len(values) - season_length + k
            pred_val = values[hist_idx]

            cycle_count = math.ceil(h / season_length)
            half_width = z_mult * s_std * math.sqrt(cycle_count)
            lb = pred_val - half_width
            ub = pred_val + half_width

            fp = compute_point_fingerprint(run_id, h, ts, pred_val, lb, ub)
            pt = PredictionPoint(
                run_id=run_id,
                step_index=h,
                entity_id=entity_id,
                metric=metric,
                unit=unit,
                forecast_timestamp=ts,
                predicted_value=pred_val,
                lower_bound=lb,
                upper_bound=ub,
                confidence_level=confidence_level,
                method=PredictionMethod.SEASONAL_NAIVE,
                truth_class=TruthClass.PREDICTED,
                evidence_ids=evidence_ids,
                assumptions=[f"Seasonal cycle repeats every {season_length} steps."],
                limitations=["Assumes rigid seasonality without secular trend adjustment."],
                fingerprint=fp,
            )
            trajectory.append(pt)

        return trajectory, {"season_length": season_length, "seasonal_std": round(s_std, 6)}

    def _forecast_moving_average(
        self,
        run_id: UUID,
        entity_id: UUID,
        metric: str,
        unit: str,
        values: list[float],
        last_timestamp: datetime,
        window: int,
        horizon: int,
        step_size: int,
        step_unit: str,
        confidence_level: float,
        z_mult: float,
        evidence_ids: list[UUID],
    ) -> tuple[list[PredictionPoint], dict[str, Any]]:
        # In-sample residuals over rolling window
        in_sample_residuals: list[float] = []
        for i in range(window, len(values)):
            roll_mean = calculate_mean(values[i - window : i])
            in_sample_residuals.append(values[i] - roll_mean)
        _, res_std = calculate_variance_and_std(in_sample_residuals)

        # Multi-step projection using rolling buffer
        buffer = list(values[-window:])
        trajectory: list[PredictionPoint] = []
        for h in range(1, horizon + 1):
            ts = advance_prediction_timestamp(last_timestamp, h, step_size, step_unit)
            pred_val = calculate_mean(buffer)
            # Update buffer for recursive projection
            buffer.pop(0)
            buffer.append(pred_val)

            half_width = z_mult * res_std * math.sqrt(h)
            lb = pred_val - half_width
            ub = pred_val + half_width

            fp = compute_point_fingerprint(run_id, h, ts, pred_val, lb, ub)
            pt = PredictionPoint(
                run_id=run_id,
                step_index=h,
                entity_id=entity_id,
                metric=metric,
                unit=unit,
                forecast_timestamp=ts,
                predicted_value=pred_val,
                lower_bound=lb,
                upper_bound=ub,
                confidence_level=confidence_level,
                method=PredictionMethod.MOVING_AVERAGE,
                truth_class=TruthClass.PREDICTED,
                evidence_ids=evidence_ids,
                assumptions=[f"Equilibrium level modeled by {window}-step rolling window."],
                limitations=["Lags behind sharp persistent acceleration."],
                fingerprint=fp,
            )
            trajectory.append(pt)

        return trajectory, {"window": window, "residual_std": round(res_std, 6)}

    def _forecast_linear_trend(
        self,
        run_id: UUID,
        entity_id: UUID,
        metric: str,
        unit: str,
        values: list[float],
        last_timestamp: datetime,
        horizon: int,
        step_size: int,
        step_unit: str,
        confidence_level: float,
        z_mult: float,
        evidence_ids: list[UUID],
    ) -> tuple[list[PredictionPoint], dict[str, Any]]:
        n = len(values)
        x_steps = [float(i + 1) for i in range(n)]
        reg = calculate_linear_regression(x_steps, values)

        slope = reg["slope"]
        intercept = reg["intercept"]
        res_std = reg["residual_std"]
        r2 = reg["r_squared"]

        x_mean = calculate_mean(x_steps)
        ss_xx = sum((xi - x_mean) ** 2 for xi in x_steps)

        trajectory: list[PredictionPoint] = []
        for h in range(1, horizon + 1):
            x_future = float(n + h)
            ts = advance_prediction_timestamp(last_timestamp, h, step_size, step_unit)
            pred_val = intercept + slope * x_future

            # Analytical prediction interval standard error for simple linear regression:
            # s_pred = s * sqrt(1 + 1/N + (x_0 - x_bar)^2 / SS_xx)
            if ss_xx > 0.0 and res_std > 0.0:
                extrap_factor = math.sqrt(1.0 + (1.0 / n) + ((x_future - x_mean) ** 2 / ss_xx))
                half_width = z_mult * res_std * extrap_factor
                lb = pred_val - half_width
                ub = pred_val + half_width
            else:
                lb = pred_val
                ub = pred_val

            fp = compute_point_fingerprint(run_id, h, ts, pred_val, lb, ub)
            pt = PredictionPoint(
                run_id=run_id,
                step_index=h,
                entity_id=entity_id,
                metric=metric,
                unit=unit,
                forecast_timestamp=ts,
                predicted_value=pred_val,
                lower_bound=lb,
                upper_bound=ub,
                confidence_level=confidence_level,
                method=PredictionMethod.LINEAR_TREND,
                truth_class=TruthClass.PREDICTED,
                evidence_ids=evidence_ids,
                assumptions=["Constant linear trajectory extrapolated over forecast horizon."],
                limitations=["Assumes linear rate of change does not saturate or revert."],
                fingerprint=fp,
            )
            trajectory.append(pt)

        params = {
            "slope": round(slope, 6),
            "intercept": round(intercept, 6),
            "r_squared": round(r2, 4),
            "residual_std": round(res_std, 6),
            "is_constant": bool(reg["is_constant"]),
        }
        return trajectory, params

    def _auto_select_method(
        self,
        values: list[float],
        request: PredictionRequest,
    ) -> tuple[PredictionMethod, dict[str, Any]]:
        """Walk-forward backtest across eligible methods and select the lowest MAE method."""
        n = len(values)
        eval_horizon = min(request.horizon, max(1, n // 3))
        min_train = max(2, n - eval_horizon)

        candidate_methods: list[PredictionMethod] = [
            PredictionMethod.NAIVE_BASELINE,
            PredictionMethod.LINEAR_TREND,
        ]
        if n >= 4:
            candidate_methods.append(PredictionMethod.MOVING_AVERAGE)
        season_len = int(request.method_params.get("season_length", 4))
        if n >= 2 * season_len:
            candidate_methods.append(PredictionMethod.SEASONAL_NAIVE)

        results: dict[str, dict[str, float]] = {}
        for method in candidate_methods:
            # Walk-forward evaluation across origins
            actuals: list[float] = []
            predictions: list[float] = []

            for origin in range(min_train, n):
                train_slice = values[:origin]
                actual_val = values[origin]

                if method == PredictionMethod.NAIVE_BASELINE:
                    pred_val = train_slice[-1]
                elif method == PredictionMethod.LINEAR_TREND:
                    reg = calculate_linear_regression([float(i + 1) for i in range(len(train_slice))], train_slice)
                    pred_val = reg["intercept"] + reg["slope"] * float(len(train_slice) + 1)
                elif method == PredictionMethod.MOVING_AVERAGE:
                    w = min(3, len(train_slice))
                    pred_val = calculate_mean(train_slice[-w:])
                elif method == PredictionMethod.SEASONAL_NAIVE:
                    pred_val = train_slice[-season_len]
                else:
                    pred_val = train_slice[-1]

                actuals.append(actual_val)
                predictions.append(pred_val)

            metrics = calculate_error_metrics(actuals, predictions)
            results[method.value] = metrics

        # Select method with lowest MAE
        best_method_str = min(results.keys(), key=lambda k: results[k]["mae"])
        best_method = PredictionMethod(best_method_str)

        return best_method, {
            "candidate_comparisons": results,
            "selected_metric": "mae",
            "eval_origins_count": n - min_train,
        }

    # --------------------------------------------------------------------------
    # Walk-Forward Backtest & Evaluation
    # --------------------------------------------------------------------------

    def run_backtest(
        self,
        request: BacktestRequest,
        conn: psycopg.Connection | None = None,
    ) -> BacktestResult:
        """Execute a rolling-origin walk-forward backtest to evaluate out-of-sample accuracy."""
        if conn is None:
            if not self.repository:
                raise PredictionConfigurationError("WorldRepository required when no database connection provided")
            with self.repository._connection() as managed_conn:
                return self._execute_backtest(request, managed_conn)
        return self._execute_backtest(request, conn)

    def _execute_backtest(
        self,
        request: BacktestRequest,
        conn: psycopg.Connection,
    ) -> BacktestResult:
        observations = self._load_observations(
            entity_id=request.entity_id,
            metric=request.metric,
            conn=conn,
        )
        if len(observations) < request.min_train_size + request.eval_horizon:
            raise PredictionDataQualityError(
                f"Insufficient data for backtest: requires at least {request.min_train_size + request.eval_horizon} observations"
            )

        sorted_obs = sorted(observations, key=lambda o: o["observed_at"])
        values = [float(o["value"]) for o in sorted_obs]
        n = len(values)

        actuals: list[float] = []
        predictions: list[float] = []
        lower_bounds: list[float | None] = []
        upper_bounds: list[float | None] = []
        naive_predictions: list[float] = []

        origins_evaluated = 0
        z_mult = get_z_multiplier(request.confidence_level)

        # Walk-forward loop: origin j steps through time
        for origin in range(request.min_train_size, n - request.eval_horizon + 1):
            origins_evaluated += 1
            train_slice = values[:origin]
            eval_actuals = values[origin : origin + request.eval_horizon]

            # Fit candidate method on training slice strictly
            if request.method == PredictionMethod.NAIVE_BASELINE:
                latest = train_slice[-1]
                diffs = [train_slice[i] - train_slice[i - 1] for i in range(1, len(train_slice))]
                _, d_std = calculate_variance_and_std(diffs)
                for h in range(1, request.eval_horizon + 1):
                    predictions.append(latest)
                    hw = z_mult * d_std * math.sqrt(h)
                    lower_bounds.append(latest - hw)
                    upper_bounds.append(latest + hw)

            elif request.method == PredictionMethod.LINEAR_TREND:
                reg = calculate_linear_regression([float(i + 1) for i in range(len(train_slice))], train_slice)
                m = len(train_slice)
                x_mean = calculate_mean([float(i + 1) for i in range(m)])
                ss_xx = sum((float(i + 1) - x_mean) ** 2 for i in range(m))
                for h in range(1, request.eval_horizon + 1):
                    x_f = float(m + h)
                    pv = reg["intercept"] + reg["slope"] * x_f
                    predictions.append(pv)
                    if ss_xx > 0.0 and reg["residual_std"] > 0.0:
                        hw = z_mult * reg["residual_std"] * math.sqrt(1.0 + (1.0 / m) + ((x_f - x_mean) ** 2 / ss_xx))
                        lower_bounds.append(pv - hw)
                        upper_bounds.append(pv + hw)
                    else:
                        lower_bounds.append(pv)
                        upper_bounds.append(pv)

            elif request.method == PredictionMethod.MOVING_AVERAGE:
                w = min(int(request.method_params.get("window", 3)), len(train_slice))
                buf = list(train_slice[-w:])
                resids = [train_slice[i] - calculate_mean(train_slice[i - w : i]) for i in range(w, len(train_slice))]
                _, r_std = calculate_variance_and_std(resids)
                for h in range(1, request.eval_horizon + 1):
                    pv = calculate_mean(buf)
                    buf.pop(0)
                    buf.append(pv)
                    predictions.append(pv)
                    hw = z_mult * r_std * math.sqrt(h)
                    lower_bounds.append(pv - hw)
                    upper_bounds.append(pv + hw)

            elif request.method == PredictionMethod.SEASONAL_NAIVE:
                s_len = int(request.method_params.get("season_length", 4))
                for h in range(1, request.eval_horizon + 1):
                    k = (h - 1) % s_len
                    pv = train_slice[len(train_slice) - s_len + k]
                    predictions.append(pv)
                    lower_bounds.append(pv)
                    upper_bounds.append(pv)

            # Record naive baseline on identical horizon
            for _ in range(request.eval_horizon):
                naive_predictions.append(train_slice[-1])

            actuals.extend(eval_actuals)

        # Calculate metrics
        model_metrics = calculate_error_metrics(
            actuals=actuals,
            predictions=predictions,
            lower_bounds=lower_bounds,
            upper_bounds=upper_bounds,
            historical_in_sample=values,
        )
        naive_metrics = calculate_error_metrics(
            actuals=actuals,
            predictions=naive_predictions,
            historical_in_sample=values,
        )

        mae_improvement_pct: float | None = None
        if naive_metrics["mae"] > 0.0:
            mae_improvement_pct = round(((naive_metrics["mae"] - model_metrics["mae"]) / naive_metrics["mae"]) * 100.0, 2)

        baseline_comparison = {
            "naive_baseline_mae": naive_metrics["mae"],
            "naive_baseline_rmse": naive_metrics["rmse"],
            "mae_reduction_pct": mae_improvement_pct,
            "outperforms_naive": model_metrics["mae"] < naive_metrics["mae"],
        }

        return BacktestResult(
            entity_id=request.entity_id,
            metric=request.metric,
            method=request.method,
            origins_evaluated=origins_evaluated,
            total_evaluations=len(actuals),
            mae=model_metrics["mae"],
            rmse=model_metrics["rmse"],
            mase=model_metrics["mase"],
            bias=model_metrics["bias"],
            interval_coverage=model_metrics["interval_coverage"],
            baseline_comparison=baseline_comparison,
            warnings=["Walk-forward backtest reflects historical hold-out accuracy only."],
            limitations=["Future distribution shifts may alter actual forecast performance."],
        )

    def evaluate_run(
        self,
        run_id: UUID,
        conn: psycopg.Connection | None = None,
    ) -> PredictionEvaluation:
        """Evaluate a completed prediction run against subsequently observed data points."""
        if conn is None:
            if not self.repository:
                raise PredictionConfigurationError("WorldRepository required when no database connection provided")
            with self.repository._connection() as managed_conn:
                return self._execute_evaluate_run(run_id, managed_conn)
        return self._execute_evaluate_run(run_id, conn)

    def _execute_evaluate_run(
        self,
        run_id: UUID,
        conn: psycopg.Connection,
    ) -> PredictionEvaluation:
        run = self.get_run(run_id, conn=conn)
        if not run:
            raise PredictionConfigurationError(f"Prediction run {run_id} not found")

        trajectory = self.get_trajectory(run_id, limit=500, conn=conn)
        if not trajectory:
            raise PredictionConfigurationError(f"No trajectory points found for run {run_id}")

        # Load authoritative observations covering the trajectory period
        min_ts = min(pt.forecast_timestamp for pt in trajectory)
        max_ts = max(pt.forecast_timestamp for pt in trajectory)

        observations = self._load_observations(
            entity_id=run.entity_id,
            metric=run.metric,
            starts_at=min_ts,
            ends_at=max_ts,
            conn=conn,
        )

        # Match trajectory points with observations by timestamp
        obs_by_ts: dict[str, float] = {
            o["observed_at"].isoformat() if isinstance(o["observed_at"], datetime) else str(o["observed_at"]): float(o["value"])
            for o in observations
        }

        matched_actuals: list[float] = []
        matched_predictions: list[float] = []
        matched_lbs: list[float | None] = []
        matched_ubs: list[float | None] = []

        for pt in trajectory:
            ts_str = pt.forecast_timestamp.isoformat()
            if ts_str in obs_by_ts:
                matched_actuals.append(obs_by_ts[ts_str])
                matched_predictions.append(pt.predicted_value)
                matched_lbs.append(pt.lower_bound)
                matched_ubs.append(pt.upper_bound)

        if not matched_actuals:
            raise PredictionDataQualityError(
                f"No subsequent observations matched forecast timestamps for run {run_id}"
            )

        metrics = calculate_error_metrics(
            actuals=matched_actuals,
            predictions=matched_predictions,
            lower_bounds=matched_lbs,
            upper_bounds=matched_ubs,
        )

        eval_id = uuid4()
        eval_record = PredictionEvaluation(
            id=eval_id,
            run_id=run_id,
            metric=run.metric,
            evaluation_window={
                "starts_at": min_ts.isoformat(),
                "ends_at": max_ts.isoformat(),
            },
            matched_points_count=len(matched_actuals),
            mae=metrics["mae"],
            rmse=metrics["rmse"],
            mase=metrics["mase"],
            bias=metrics["bias"],
            interval_coverage=metrics["interval_coverage"],
            baseline_comparison={"matched_count": len(matched_actuals)},
            evaluation_method="observed_match",
            method_version="v1.0.0",
            limitations=["Evaluation reflects only timestamps with verified empirical observations."],
        )

        # Persist evaluation record
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO prediction_evaluations (
                    id, run_id, metric, evaluation_window, matched_points_count,
                    mae, rmse, mase, bias, interval_coverage, baseline_comparison,
                    evaluation_method, method_version, limitations, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    eval_record.id,
                    eval_record.run_id,
                    eval_record.metric,
                    json.dumps(eval_record.evaluation_window),
                    eval_record.matched_points_count,
                    eval_record.mae,
                    eval_record.rmse,
                    eval_record.mase,
                    eval_record.bias,
                    eval_record.interval_coverage,
                    json.dumps(eval_record.baseline_comparison),
                    eval_record.evaluation_method,
                    eval_record.method_version,
                    json.dumps(eval_record.limitations),
                    eval_record.created_at,
                ),
            )
            conn.commit()

        return eval_record

    def get_evaluation(
        self,
        run_id: UUID,
        conn: psycopg.Connection | None = None,
    ) -> PredictionEvaluation | None:
        """Retrieve evaluation results for a prediction run."""
        if conn is None:
            if not self.repository:
                return None
            with self.repository._connection() as managed_conn:
                return self._get_evaluation(run_id, managed_conn)
        return self._get_evaluation(run_id, conn)

    def _get_evaluation(self, run_id: UUID, conn: psycopg.Connection) -> PredictionEvaluation | None:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, run_id, metric, evaluation_window, matched_points_count,
                       mae, rmse, mase, bias, interval_coverage, baseline_comparison,
                       evaluation_method, method_version, limitations, created_at
                FROM prediction_evaluations
                WHERE run_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (run_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return PredictionEvaluation(
                id=row["id"],
                run_id=row["run_id"],
                metric=row["metric"],
                evaluation_window=row["evaluation_window"] or {},
                matched_points_count=row["matched_points_count"],
                mae=row["mae"],
                rmse=row["rmse"],
                mase=row["mase"],
                bias=row["bias"],
                interval_coverage=row["interval_coverage"],
                baseline_comparison=row["baseline_comparison"] or {},
                evaluation_method=row["evaluation_method"],
                method_version=row["method_version"],
                limitations=row["limitations"] or [],
                created_at=row["created_at"],
            )

    # --------------------------------------------------------------------------
    # Persistence & Read Queries
    # --------------------------------------------------------------------------

    def _load_observations(
        self,
        entity_id: UUID,
        metric: str,
        starts_at: datetime | None = None,
        ends_at: datetime | None = None,
        conn: psycopg.Connection | None = None,
    ) -> list[dict[str, Any]]:
        """Load authoritative observations for an entity and metric in chronological order."""
        if not conn:
            raise ValueError("Database connection required to load observations")

        query = """
            SELECT o.id, o.subject_entity_id, o.measure, o.value, o.unit, o.truth_class,
                   o.evidence_id, o.provenance_id, t.starts_at AS observed_at
            FROM observations o
            JOIN time_intervals t ON o.time_interval_id = t.id
            WHERE o.subject_entity_id = %s
              AND o.measure = %s
              AND o.truth_class = 'OBSERVED'
        """
        params: list[Any] = [entity_id, metric]

        if starts_at:
            query += " AND t.starts_at >= %s"
            params.append(starts_at)
        if ends_at:
            query += " AND t.starts_at <= %s"
            params.append(ends_at)

        query += " ORDER BY t.starts_at ASC"

        with conn.cursor() as cur:
            cur.execute(query, params)
            return list(cur.fetchall())

    def _persist_run(self, run: PredictionRun, conn: psycopg.Connection) -> None:
        """Persist prediction run and trajectory points in database."""
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO prediction_runs (
                    id, entity_id, metric, unit, status, method, method_version,
                    request_json, observations_count, trajectory_points_count,
                    historical_summary, model_parameters, quality_warnings, assumptions,
                    limitations, reproducibility_fingerprint, execution_duration_ms,
                    error_message, created_at, completed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    trajectory_points_count = EXCLUDED.trajectory_points_count,
                    historical_summary = EXCLUDED.historical_summary,
                    model_parameters = EXCLUDED.model_parameters,
                    quality_warnings = EXCLUDED.quality_warnings,
                    execution_duration_ms = EXCLUDED.execution_duration_ms,
                    completed_at = EXCLUDED.completed_at
                """,
                (
                    run.id,
                    run.entity_id,
                    run.metric,
                    run.unit,
                    run.status.value,
                    run.selected_method.value,
                    run.method_version,
                    json.dumps(run.request.model_dump(mode="json")),
                    run.observations_count,
                    run.trajectory_points_count,
                    json.dumps(run.historical_summary),
                    json.dumps(run.model_parameters),
                    json.dumps(run.quality_warnings),
                    json.dumps(run.assumptions),
                    json.dumps(run.limitations),
                    run.reproducibility_fingerprint,
                    run.execution_duration_ms,
                    run.error_message,
                    run.created_at,
                    run.completed_at,
                ),
            )

            for pt in run.trajectory:
                cur.execute(
                    """
                    INSERT INTO prediction_points (
                        id, run_id, step_index, entity_id, metric, unit,
                        forecast_timestamp, predicted_value, lower_bound, upper_bound,
                        confidence_level, method, method_version, truth_class,
                        evidence_ids, assumptions, limitations, data_quality_warnings,
                        fingerprint, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (run_id, step_index) DO UPDATE SET
                        predicted_value = EXCLUDED.predicted_value,
                        lower_bound = EXCLUDED.lower_bound,
                        upper_bound = EXCLUDED.upper_bound,
                        fingerprint = EXCLUDED.fingerprint
                    """,
                    (
                        pt.id,
                        run.id,
                        pt.step_index,
                        pt.entity_id,
                        pt.metric,
                        pt.unit,
                        pt.forecast_timestamp,
                        pt.predicted_value,
                        pt.lower_bound,
                        pt.upper_bound,
                        pt.confidence_level,
                        pt.method if isinstance(pt.method, str) else pt.method.value,
                        pt.method_version,
                        pt.truth_class.value if hasattr(pt.truth_class, "value") else str(pt.truth_class),
                        json.dumps([str(eid) for eid in pt.evidence_ids]),
                        json.dumps(pt.assumptions),
                        json.dumps(pt.limitations),
                        json.dumps(pt.data_quality_warnings),
                        pt.fingerprint,
                        pt.created_at,
                    ),
                )
            conn.commit()

    def list_runs(
        self,
        entity_id: UUID | None = None,
        metric: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
        conn: psycopg.Connection | None = None,
    ) -> list[PredictionRun]:
        """List historical prediction runs with optional filtering."""
        if conn is None:
            if not self.repository:
                return []
            with self.repository._connection() as managed_conn:
                return self._list_runs(entity_id, metric, status, limit, offset, managed_conn)
        return self._list_runs(entity_id, metric, status, limit, offset, conn)

    def _list_runs(
        self,
        entity_id: UUID | None,
        metric: str | None,
        status: str | None,
        limit: int,
        offset: int,
        conn: psycopg.Connection,
    ) -> list[PredictionRun]:
        query = """
            SELECT id, entity_id, metric, unit, status, method, method_version,
                   request_json, observations_count, trajectory_points_count,
                   historical_summary, model_parameters, quality_warnings, assumptions,
                   limitations, reproducibility_fingerprint, execution_duration_ms,
                   error_message, created_at, completed_at
            FROM prediction_runs
            WHERE 1=1
        """
        params: list[Any] = []
        if entity_id:
            query += " AND entity_id = %s"
            params.append(entity_id)
        if metric:
            query += " AND metric = %s"
            params.append(metric)
        if status:
            query += " AND status = %s"
            params.append(status)

        safe_limit = max(1, min(_extract_int(limit, 50), 500))
        safe_offset = max(0, _extract_int(offset, 0))
        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([safe_limit, safe_offset])

        with conn.cursor() as cur:
            cur.execute(query, params)
            runs: list[PredictionRun] = []
            for row in cur.fetchall():
                runs.append(self._row_to_run(row))
            return runs

    def get_run(
        self,
        run_id: UUID,
        conn: psycopg.Connection | None = None,
    ) -> PredictionRun | None:
        """Retrieve a specific prediction run by ID."""
        if conn is None:
            if not self.repository:
                return None
            with self.repository._connection() as managed_conn:
                return self._get_run(run_id, managed_conn)
        return self._get_run(run_id, conn)

    def _get_run(self, run_id: UUID, conn: psycopg.Connection) -> PredictionRun | None:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, entity_id, metric, unit, status, method, method_version,
                       request_json, observations_count, trajectory_points_count,
                       historical_summary, model_parameters, quality_warnings, assumptions,
                       limitations, reproducibility_fingerprint, execution_duration_ms,
                       error_message, created_at, completed_at
                FROM prediction_runs
                WHERE id = %s
                """,
                (run_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_run(row)

    def get_trajectory(
        self,
        run_id: UUID,
        limit: int = 100,
        offset: int = 0,
        conn: psycopg.Connection | None = None,
    ) -> list[PredictionPoint]:
        """Retrieve ordered forecast trajectory points for a run."""
        if conn is None:
            if not self.repository:
                return []
            with self.repository._connection() as managed_conn:
                return self._get_trajectory(run_id, limit, offset, managed_conn)
        return self._get_trajectory(run_id, limit, offset, conn)

    def _get_trajectory(
        self,
        run_id: UUID,
        limit: int,
        offset: int,
        conn: psycopg.Connection,
    ) -> list[PredictionPoint]:
        safe_limit = max(1, min(_extract_int(limit, 100), 1000))
        safe_offset = max(0, _extract_int(offset, 0))
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, run_id, step_index, entity_id, metric, unit,
                       forecast_timestamp, predicted_value, lower_bound, upper_bound,
                       confidence_level, method, method_version, truth_class,
                       evidence_ids, assumptions, limitations, data_quality_warnings,
                       fingerprint, created_at
                FROM prediction_points
                WHERE run_id = %s
                ORDER BY step_index ASC
                LIMIT %s OFFSET %s
                """,
                (run_id, safe_limit, safe_offset),
            )
            points: list[PredictionPoint] = []
            for row in cur.fetchall():
                evidence_ids = [
                    UUID(eid) if isinstance(eid, str) else eid
                    for eid in (row["evidence_ids"] or [])
                ]
                points.append(
                    PredictionPoint(
                        id=row["id"],
                        run_id=row["run_id"],
                        step_index=row["step_index"],
                        entity_id=row["entity_id"],
                        metric=row["metric"],
                        unit=row["unit"],
                        forecast_timestamp=row["forecast_timestamp"],
                        predicted_value=row["predicted_value"],
                        lower_bound=row["lower_bound"],
                        upper_bound=row["upper_bound"],
                        confidence_level=row["confidence_level"],
                        method=row["method"],
                        method_version=row["method_version"],
                        truth_class=TruthClass(row["truth_class"]),
                        evidence_ids=evidence_ids,
                        assumptions=row["assumptions"] or [],
                        limitations=row["limitations"] or [],
                        data_quality_warnings=row["data_quality_warnings"] or [],
                        fingerprint=row["fingerprint"],
                        created_at=row["created_at"],
                    )
                )
            return points

    def _row_to_run(self, row: dict[str, Any]) -> PredictionRun:
        req_dict = row["request_json"] if isinstance(row["request_json"], dict) else json.loads(row["request_json"])
        request = PredictionRequest.model_validate(req_dict)
        return PredictionRun(
            id=row["id"],
            status=PredictionStatus(row["status"]),
            request=request,
            selected_method=PredictionMethod(row["method"]),
            method_version=row["method_version"],
            entity_id=row["entity_id"],
            metric=row["metric"],
            unit=row["unit"] or "",
            observations_count=row["observations_count"],
            trajectory_points_count=row["trajectory_points_count"],
            historical_summary=row["historical_summary"] or {},
            model_parameters=row["model_parameters"] or {},
            quality_warnings=row["quality_warnings"] or [],
            assumptions=row["assumptions"] or [],
            limitations=row["limitations"] or [],
            reproducibility_fingerprint=row["reproducibility_fingerprint"],
            execution_duration_ms=row["execution_duration_ms"],
            error_message=row["error_message"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )
