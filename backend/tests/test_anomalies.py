"""Unit tests for Engine 15: Anomaly Detection Engine.

Covers mathematical routines, robust statistical deviation (MAD & modified z-scores),
temporal change detection, constant series handling, zero dispersion handling,
fingerprint determinism, severity mapping, and domain request validation.
"""
from __future__ import annotations

import math
import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.anomalies import (
    METHOD_DEFINITIONS,
    AnomalyConfigurationError,
    AnomalyEngine,
    calculate_mad,
    calculate_mean_and_std,
    calculate_median,
    calculate_modified_zscore,
    compute_finding_fingerprint,
    map_severity,
)
from app.domain import (
    AnomalyDetectionRequest,
    AnomalyFinding,
    AnomalySeverity,
    DetectionMethod,
    FindingLifecycleStatus,
    TruthClass,
)


class TestAnomalyMathRoutines(unittest.TestCase):
    """Test deterministic pure mathematical routines."""

    def test_calculate_median(self) -> None:
        self.assertEqual(calculate_median([1.0, 2.0, 3.0]), 2.0)
        self.assertEqual(calculate_median([1.0, 2.0, 3.0, 4.0]), 2.5)
        self.assertEqual(calculate_median([5.0]), 5.0)
        self.assertEqual(calculate_median([10.0, 1.0, 5.0]), 5.0)
        with self.assertRaises(ValueError):
            calculate_median([])

    def test_calculate_mad(self) -> None:
        # Series [1, 2, 3, 4, 5, 6, 7], median = 4
        # Deviations: [3, 2, 1, 0, 1, 2, 3] -> sorted [0, 1, 1, 2, 2, 3, 3] -> median = 2.0
        self.assertEqual(calculate_mad([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]), 2.0)

        # Constant series: deviations all 0 -> MAD = 0
        self.assertEqual(calculate_mad([10.0, 10.0, 10.0, 10.0]), 0.0)

    def test_calculate_modified_zscore_normal(self) -> None:
        # When MAD > 0
        # med = 10, mad = 2, val = 16 -> diff = 6 -> 0.6745 * 6 / 2 = 2.0235
        score = calculate_modified_zscore(16.0, 10.0, 2.0)
        self.assertAlmostEqual(score, 2.0235, places=4)

        # Value equal to median -> 0.0
        self.assertEqual(calculate_modified_zscore(10.0, 10.0, 2.0), 0.0)

    def test_calculate_modified_zscore_zero_mad(self) -> None:
        # Constant baseline: mad = 0
        # If val == median, score = 0
        self.assertEqual(calculate_modified_zscore(5.0, 5.0, 0.0), 0.0)

        # If val != median with 0 MAD, returns infinite signed distance without division by zero
        score_pos = calculate_modified_zscore(10.0, 5.0, 0.0)
        self.assertTrue(math.isinf(score_pos))
        self.assertGreater(score_pos, 0)

        score_neg = calculate_modified_zscore(2.0, 5.0, 0.0)
        self.assertTrue(math.isinf(score_neg))
        self.assertLess(score_neg, 0)

    def test_calculate_mean_and_std(self) -> None:
        vals = [10.0, 12.0, 14.0, 16.0, 18.0]
        mean, std = calculate_mean_and_std(vals)
        self.assertEqual(mean, 14.0)
        self.assertAlmostEqual(std, 3.162277, places=5)

        # Single element series
        mean_single, std_single = calculate_mean_and_std([42.0])
        self.assertEqual(mean_single, 42.0)
        self.assertEqual(std_single, 0.0)


class TestAnomalyFingerprintAndSeverity(unittest.TestCase):
    """Test deterministic fingerprinting and severity mappings."""

    def test_compute_finding_fingerprint_deterministic(self) -> None:
        eid = uuid4()
        t = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
        fp1 = compute_finding_fingerprint(
            entity_id=eid,
            metric="population.total",
            observed_at=t,
            method="robust_zscore_mad",
            method_version="v1.0.0",
            observed_value=1500000.123456,
        )
        fp2 = compute_finding_fingerprint(
            entity_id=eid,
            metric="population.total",
            observed_at=t,
            method="robust_zscore_mad",
            method_version="v1.0.0",
            observed_value=1500000.123456,
        )
        self.assertEqual(fp1, fp2)
        self.assertEqual(len(fp1), 64)

        # Different value -> different fingerprint
        fp3 = compute_finding_fingerprint(
            entity_id=eid,
            metric="population.total",
            observed_at=t,
            method="robust_zscore_mad",
            method_version="v1.0.0",
            observed_value=1600000.0,
        )
        self.assertNotEqual(fp1, fp3)

    def test_map_severity(self) -> None:
        # threshold = 3.0
        # ratio < 1.5 -> INFO
        self.assertEqual(map_severity(3.5, 3.0), AnomalySeverity.INFO)
        # ratio >= 1.5 -> WARNING (score = 5.0 -> ratio 1.67)
        self.assertEqual(map_severity(5.0, 3.0), AnomalySeverity.WARNING)
        # ratio >= 2.5 -> HIGH (score = 8.0 -> ratio 2.67)
        self.assertEqual(map_severity(8.0, 3.0), AnomalySeverity.HIGH)
        # ratio >= 4.0 -> CRITICAL (score = 15.0 -> ratio 5.0)
        self.assertEqual(map_severity(15.0, 3.0), AnomalySeverity.CRITICAL)

        # Custom thresholds
        custom = {"WARNING": 4.0, "HIGH": 7.0, "CRITICAL": 10.0}
        self.assertEqual(map_severity(2.0, 3.0, custom), AnomalySeverity.INFO)
        self.assertEqual(map_severity(4.5, 3.0, custom), AnomalySeverity.WARNING)
        self.assertEqual(map_severity(7.5, 3.0, custom), AnomalySeverity.HIGH)
        self.assertEqual(map_severity(12.0, 3.0, custom), AnomalySeverity.CRITICAL)


class TestAnomalyRequestValidation(unittest.TestCase):
    """Test validation of AnomalyDetectionRequest."""

    def test_valid_request(self) -> None:
        req = AnomalyDetectionRequest(
            metric="usgs.magnitude",
            threshold=3.5,
            min_observations=4,
            detection_methods=[DetectionMethod.ROBUST_ZSCORE_MAD],
        )
        self.assertEqual(req.metric, "usgs.magnitude")
        self.assertEqual(req.threshold, 3.5)
        self.assertEqual(req.min_observations, 4)

    def test_invalid_metric_empty(self) -> None:
        with self.assertRaises(ValueError):
            AnomalyDetectionRequest(metric="   ")

    def test_invalid_threshold_negative_or_zero(self) -> None:
        with self.assertRaises(ValueError):
            AnomalyDetectionRequest(metric="pop", threshold=-1.0)
        with self.assertRaises(ValueError):
            AnomalyDetectionRequest(metric="pop", threshold=0.0)

    def test_invalid_time_range(self) -> None:
        t1 = datetime(2025, 1, 1, tzinfo=UTC)
        t2 = datetime(2024, 1, 1, tzinfo=UTC)
        with self.assertRaises(ValueError):
            AnomalyDetectionRequest(metric="pop", starts_at=t1, ends_at=t2)


class TestMethodDefinitions(unittest.TestCase):
    """Test registered detection method specifications."""

    def test_method_definitions_coverage(self) -> None:
        self.assertIn(DetectionMethod.ROBUST_ZSCORE_MAD, METHOD_DEFINITIONS)
        self.assertIn(DetectionMethod.TEMPORAL_CHANGE, METHOD_DEFINITIONS)
        self.assertIn(DetectionMethod.PEER_GROUP_DEVIATION, METHOD_DEFINITIONS)
        self.assertIn(DetectionMethod.SPATIAL_DEVIATION, METHOD_DEFINITIONS)
        self.assertIn(DetectionMethod.MULTIVARIATE_MAHALANOBIS, METHOD_DEFINITIONS)

        for m, defn in METHOD_DEFINITIONS.items():
            self.assertEqual(m, defn.method)
            self.assertTrue(defn.name)
            self.assertTrue(defn.description)
            self.assertGreater(defn.default_threshold, 0)
            self.assertTrue(defn.assumptions)
            self.assertTrue(defn.limitations)


if __name__ == "__main__":
    unittest.main()
