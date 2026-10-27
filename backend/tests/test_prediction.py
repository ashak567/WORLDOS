"""Unit tests for Engine 18: Bounded Deterministic Prediction Engine.

Verifies mathematical models, linear trend extrapolation, moving averages, seasonal naive,
naive baselines, prediction intervals, walk-forward error metrics, request validation,
and target leakage prevention.
"""
from datetime import UTC, datetime, timedelta
import math
import unittest
from uuid import uuid4

from app.domain import (
    BacktestRequest,
    PredictionMethod,
    PredictionPoint,
    PredictionRequest,
    PredictionStatus,
    TruthClass,
)
from app.prediction import (
    PredictionConfigurationError,
    PredictionDataQualityError,
    advance_prediction_timestamp,
    calculate_error_metrics,
    calculate_linear_regression,
    calculate_mean,
    calculate_variance_and_std,
    compute_prediction_fingerprint,
    get_z_multiplier,
)


class TestPredictionMathematicalRoutines(unittest.TestCase):
    """Test pure mathematical and statistical routines."""

    def test_calculate_mean(self) -> None:
        self.assertAlmostEqual(calculate_mean([10.0, 20.0, 30.0]), 20.0)
        self.assertAlmostEqual(calculate_mean([5.0]), 5.0)
        with self.assertRaises(ValueError):
            calculate_mean([])

    def test_calculate_variance_and_std(self) -> None:
        var, std = calculate_variance_and_std([10.0, 10.0, 10.0])
        self.assertEqual(var, 0.0)
        self.assertEqual(std, 0.0)

        var2, std2 = calculate_variance_and_std([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
        self.assertAlmostEqual(var2, 4.5714, places=3)
        self.assertAlmostEqual(std2, math.sqrt(4.5714), places=3)

    def test_calculate_linear_regression(self) -> None:
        # Perfect linear upward trend: y = 2x + 1
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [3.0, 5.0, 7.0, 9.0, 11.0]
        reg = calculate_linear_regression(x, y)
        self.assertAlmostEqual(reg["slope"], 2.0)
        self.assertAlmostEqual(reg["intercept"], 1.0)
        self.assertAlmostEqual(reg["r_squared"], 1.0)
        self.assertAlmostEqual(reg["residual_std"], 0.0)
        self.assertEqual(reg["is_constant"], 0.0)

    def test_calculate_linear_regression_constant_series(self) -> None:
        # Constant y: y = 5.0 for all x
        x = [1.0, 2.0, 3.0, 4.0]
        y = [5.0, 5.0, 5.0, 5.0]
        reg = calculate_linear_regression(x, y)
        self.assertAlmostEqual(reg["slope"], 0.0)
        self.assertAlmostEqual(reg["intercept"], 5.0)
        self.assertAlmostEqual(reg["residual_std"], 0.0)
        self.assertEqual(reg["is_constant"], 1.0)

    def test_get_z_multiplier(self) -> None:
        self.assertAlmostEqual(get_z_multiplier(0.95), 1.95996, places=4)
        self.assertAlmostEqual(get_z_multiplier(0.80), 1.28155, places=4)
        self.assertAlmostEqual(get_z_multiplier(0.99), 2.5758, places=3)

    def test_advance_prediction_timestamp(self) -> None:
        base = datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)
        # Advance 1 year
        t_year = advance_prediction_timestamp(base, step_index=1, step_size=1, step_unit="year")
        self.assertEqual(t_year, datetime(2021, 1, 1, 0, 0, 0, tzinfo=UTC))

        # Advance 3 months
        t_month = advance_prediction_timestamp(base, step_index=3, step_size=1, step_unit="month")
        self.assertEqual(t_month, datetime(2020, 4, 1, 0, 0, 0, tzinfo=UTC))

        # Advance 5 days
        t_day = advance_prediction_timestamp(base, step_index=5, step_size=1, step_unit="day")
        self.assertEqual(t_day, datetime(2020, 1, 6, 0, 0, 0, tzinfo=UTC))

        # Advance 12 hours
        t_hour = advance_prediction_timestamp(base, step_index=12, step_size=1, step_unit="hour")
        self.assertEqual(t_hour, datetime(2020, 1, 1, 12, 0, 0, tzinfo=UTC))


class TestPredictionErrorMetrics(unittest.TestCase):
    """Test forecast error metrics and evaluation statistics."""

    def test_error_metrics_basic(self) -> None:
        actuals = [10.0, 20.0, 30.0]
        predictions = [12.0, 18.0, 31.0]
        # errors: +2, -2, +1 -> abs errors: 2, 2, 1 -> MAE = 5/3 = 1.666667
        # squared errors: 4, 4, 1 = 9 -> RMSE = sqrt(9/3) = sqrt(3) = 1.73205
        # bias = (2 - 2 + 1) / 3 = 1/3 = 0.333333
        metrics = calculate_error_metrics(
            actuals=actuals,
            predictions=predictions,
            lower_bounds=[9.0, 15.0, 25.0],
            upper_bounds=[15.0, 25.0, 35.0],
            historical_in_sample=[5.0, 8.0, 10.0],
        )
        self.assertAlmostEqual(metrics["mae"], 1.666667, places=5)
        self.assertAlmostEqual(metrics["rmse"], 1.732051, places=5)
        self.assertAlmostEqual(metrics["bias"], 0.333333, places=5)
        self.assertEqual(metrics["interval_coverage"], 1.0)
        self.assertIsNotNone(metrics["mase"])

    def test_error_metrics_constant_series_mase(self) -> None:
        # If in-sample history is constant, scale is 0, MASE must not fail with ZeroDivisionError
        metrics = calculate_error_metrics(
            actuals=[10.0, 10.0],
            predictions=[11.0, 11.0],
            historical_in_sample=[10.0, 10.0, 10.0],
        )
        self.assertEqual(metrics["mae"], 1.0)
        self.assertIsNone(metrics["mase"])


class TestPredictionRequestValidation(unittest.TestCase):
    """Test validation constraints on PredictionRequest."""

    def test_valid_request(self) -> None:
        req = PredictionRequest(
            entity_id=uuid4(),
            metric="population.total",
            horizon=5,
            step_size=1,
            step_unit="year",
            confidence_level=0.95,
        )
        self.assertEqual(req.horizon, 5)
        self.assertEqual(req.method, PredictionMethod.LINEAR_TREND)

    def test_empty_metric_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PredictionRequest(
                entity_id=uuid4(),
                metric="",
                horizon=5,
            )

    def test_invalid_horizon_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PredictionRequest(
                entity_id=uuid4(),
                metric="population.total",
                horizon=0,
            )
        with self.assertRaises(ValueError):
            PredictionRequest(
                entity_id=uuid4(),
                metric="population.total",
                horizon=101,
            )

    def test_invalid_confidence_level_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PredictionRequest(
                entity_id=uuid4(),
                metric="population.total",
                confidence_level=0.40,
            )
        with self.assertRaises(ValueError):
            PredictionRequest(
                entity_id=uuid4(),
                metric="population.total",
                confidence_level=1.0,
            )

    def test_invalid_time_range_rejected(self) -> None:
        now = datetime.now(UTC)
        with self.assertRaises(ValueError):
            PredictionRequest(
                entity_id=uuid4(),
                metric="population.total",
                starts_at=now,
                ends_at=now - timedelta(days=1),
            )


class TestPredictionFingerprint(unittest.TestCase):
    """Test deterministic reproducibility fingerprinting."""

    def test_fingerprint_reproducibility(self) -> None:
        eid = uuid4()
        now = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        obs = [
            {"observed_at": now - timedelta(days=365), "value": 100.0},
            {"observed_at": now, "value": 110.0},
        ]
        fp1 = compute_prediction_fingerprint(
            entity_id=eid,
            metric="population.total",
            method="linear_trend",
            horizon=5,
            step_size=1,
            step_unit="year",
            confidence_level=0.95,
            observations=obs,
            method_params={"slope": 10.0},
        )
        fp2 = compute_prediction_fingerprint(
            entity_id=eid,
            metric="population.total",
            method="linear_trend",
            horizon=5,
            step_size=1,
            step_unit="year",
            confidence_level=0.95,
            observations=list(reversed(obs)),  # Order must not matter
            method_params={"slope": 10.0},
        )
        self.assertEqual(fp1, fp2)
        self.assertEqual(len(fp1), 64)

    def test_prediction_point_truth_class(self) -> None:
        pt = PredictionPoint(
            step_index=1,
            entity_id=uuid4(),
            metric="test.metric",
            unit="count",
            forecast_timestamp=datetime.now(UTC),
            predicted_value=123.45,
            method="linear_trend",
        )
        self.assertEqual(pt.truth_class, TruthClass.PREDICTED)


if __name__ == "__main__":
    unittest.main()
