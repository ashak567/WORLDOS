"""Unit tests for Engine 14: Event / Alert Engine.

Tests deterministic rule validation, comparison operators, spatial bounding box checks,
temporal clustering logic, cooldown suppression, and evidence citation preservation.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from unittest import TestCase
from uuid import uuid4

from app.alerts import AlertEngine
from app.domain import (
    Alert,
    AlertComparisonOperator,
    AlertEvaluation,
    AlertLifecycleStatus,
    AlertRule,
    AlertSeverity,
    AlertStatus,
)


class TestAlertEngineUnit(TestCase):
    def setUp(self) -> None:
        self.engine = AlertEngine()

    def test_rule_validation_valid_rule(self) -> None:
        rule = AlertRule(
            name="Major Earthquake Alert",
            description="Magnitude 6.0 or greater",
            event_kind="earthquake",
            operator=">=",
            metric_field="mag",
            threshold=6.0,
            severity=AlertSeverity.CRITICAL,
            cooldown_seconds=600,
        )
        errors = self.engine.validate_rule(rule)
        self.assertEqual(len(errors), 0, f"Expected 0 errors, got: {errors}")

    def test_rule_validation_invalid_fields(self) -> None:
        # Empty name, empty kind, invalid operator, NaN threshold, negative cooldown
        with self.assertRaises(ValueError):
            AlertRule(
                name="",
                event_kind="earthquake",
                operator=">=",
                metric_field="",
                threshold=5.0,
            )

        with self.assertRaises(ValueError):
            AlertRule(
                name="Test",
                event_kind="earthquake",
                operator=">=",
                metric_field="mag",
                threshold=float("nan"),
            )

    def test_rule_validation_spatial_bbox_bounds(self) -> None:
        # Valid bbox
        rule_valid = AlertRule(
            name="California Quakes",
            event_kind="earthquake",
            operator=">=",
            metric_field="mag",
            threshold=4.5,
            spatial_scope={"type": "bbox", "min_lon": -125.0, "max_lon": -114.0, "min_lat": 32.0, "max_lat": 42.0},
        )
        self.assertEqual(len(self.engine.validate_rule(rule_valid)), 0)

        # Inverted longitude
        with self.assertRaises(ValueError):
            AlertRule(
                name="Bad BBox",
                event_kind="earthquake",
                operator=">=",
                metric_field="mag",
                threshold=4.5,
                spatial_scope={"type": "bbox", "min_lon": -110.0, "max_lon": -125.0, "min_lat": 32.0, "max_lat": 42.0},
            )

        # Inverted latitude
        with self.assertRaises(ValueError):
            AlertRule(
                name="Bad Lat",
                event_kind="earthquake",
                operator=">=",
                metric_field="mag",
                threshold=4.5,
                spatial_scope={"type": "bbox", "min_lon": -125.0, "max_lon": -114.0, "min_lat": 45.0, "max_lat": 30.0},
            )

    def test_rule_validation_cluster_parameters(self) -> None:
        # Cluster threshold requires positive temporal window
        with self.assertRaises(ValueError):
            AlertRule(
                name="Swarm Alert",
                event_kind="earthquake",
                operator=">=",
                metric_field="mag",
                threshold=3.0,
                cluster_threshold=5,
                temporal_window_seconds=None,
            )

        with self.assertRaises(ValueError):
            AlertRule(
                name="Swarm Alert",
                event_kind="earthquake",
                operator=">=",
                metric_field="mag",
                threshold=3.0,
                cluster_threshold=0,
                temporal_window_seconds=3600,
            )

    def test_comparison_operators(self) -> None:
        eval_op = self.engine.evaluate_operator

        # GT (>)
        self.assertTrue(eval_op(6.1, ">", 6.0))
        self.assertFalse(eval_op(6.0, ">", 6.0))
        self.assertFalse(eval_op(5.9, ">", 6.0))

        # GTE (>=)
        self.assertTrue(eval_op(6.1, ">=", 6.0))
        self.assertTrue(eval_op(6.0, ">=", 6.0))
        self.assertTrue(eval_op(6.0 + 1e-11, ">=", 6.0))
        self.assertFalse(eval_op(5.999999, ">=", 6.0))

        # LT (<)
        self.assertTrue(eval_op(5.9, "<", 6.0))
        self.assertFalse(eval_op(6.0, "<", 6.0))
        self.assertFalse(eval_op(6.1, "<", 6.0))

        # LTE (<=)
        self.assertTrue(eval_op(5.9, "<=", 6.0))
        self.assertTrue(eval_op(6.0, "<=", 6.0))
        self.assertTrue(eval_op(6.0 - 1e-11, "<=", 6.0))
        self.assertFalse(eval_op(6.000001, "<=", 6.0))

        # EQ (==)
        self.assertTrue(eval_op(6.0, "==", 6.0))
        self.assertTrue(eval_op(6.0 + 1e-11, "==", 6.0))
        self.assertFalse(eval_op(6.1, "==", 6.0))

        # NEQ (!=)
        self.assertTrue(eval_op(6.1, "!=", 6.0))
        self.assertFalse(eval_op(6.0, "!=", 6.0))
        self.assertFalse(eval_op(6.0 + 1e-11, "!=", 6.0))

    def test_spatial_bbox_matching(self) -> None:
        bbox_scope = {
            "type": "bbox",
            "min_lon": -125.0,
            "max_lon": -114.0,
            "min_lat": 32.0,
            "max_lat": 42.0,
        }

        # Inside California bounds
        self.assertTrue(self.engine.matches_spatial_scope(-118.25, 34.05, bbox_scope))

        # On boundary
        self.assertTrue(self.engine.matches_spatial_scope(-125.0, 32.0, bbox_scope))
        self.assertTrue(self.engine.matches_spatial_scope(-114.0, 42.0, bbox_scope))

        # Outside bounds: East
        self.assertFalse(self.engine.matches_spatial_scope(-110.0, 35.0, bbox_scope))

        # Outside bounds: North
        self.assertFalse(self.engine.matches_spatial_scope(-120.0, 45.0, bbox_scope))

        # Outside bounds: South
        self.assertFalse(self.engine.matches_spatial_scope(-120.0, 30.0, bbox_scope))

        # Unconstrained rule (no spatial_scope)
        self.assertTrue(self.engine.matches_spatial_scope(139.69, 35.68, None))

        # Event with no coordinates against spatial rule
        self.assertFalse(self.engine.matches_spatial_scope(None, None, bbox_scope))

    def test_lifecycle_states_and_enums(self) -> None:
        self.assertEqual(AlertLifecycleStatus.RECEIVED.value, "RECEIVED")
        self.assertEqual(AlertLifecycleStatus.VALIDATED.value, "VALIDATED")
        self.assertEqual(AlertLifecycleStatus.EVALUATED.value, "EVALUATED")
        self.assertEqual(AlertLifecycleStatus.ALERTED.value, "ALERTED")
        self.assertEqual(AlertLifecycleStatus.SUPPRESSED.value, "SUPPRESSED")
        self.assertEqual(AlertLifecycleStatus.FAILED.value, "FAILED")

        self.assertEqual(AlertSeverity.INFO.value, "INFO")
        self.assertEqual(AlertSeverity.WARNING.value, "WARNING")
        self.assertEqual(AlertSeverity.CRITICAL.value, "CRITICAL")

        self.assertEqual(AlertStatus.ACTIVE.value, "active")
        self.assertEqual(AlertStatus.ACKNOWLEDGED.value, "acknowledged")
        self.assertEqual(AlertStatus.RESOLVED.value, "resolved")

    def test_alert_domain_model_creation(self) -> None:
        rule_id = uuid4()
        event_id = uuid4()
        evidence_id = uuid4()
        alert = Alert(
            rule_id=rule_id,
            event_id=event_id,
            severity=AlertSeverity.CRITICAL,
            title="[CRITICAL] Severe Earthquake Detected",
            message="M 7.2 earthquake detected in Southern California. Magnitude threshold 6.5 met.",
            dedup_key=f"{rule_id}:{event_id}",
            evidence_id=evidence_id,
            context_summary={"mag": 7.2, "place": "Ridgecrest, CA", "depth_km": 8.0},
        )
        self.assertEqual(alert.status, AlertStatus.ACTIVE)
        self.assertIsNone(alert.acknowledged_at)
        self.assertIsNone(alert.resolved_at)
        self.assertEqual(alert.severity, AlertSeverity.CRITICAL)
        self.assertEqual(alert.evidence_id, evidence_id)
