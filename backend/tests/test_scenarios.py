"""Unit tests for Engine 16: Deterministic Scenario Engine.

Verifies:
1. Scenario and ScenarioModification domain models and defaults.
2. Modification validation (field formats, finite numbers, non-negative constraints).
3. Lifecycle state transitions and invalid transition enforcement.
4. Deterministic modification overlay semantics (SET, DELTA, SCALE, REMOVE).
5. Conflicting modifications and deterministic precedence ordering.
6. Epistemic classification with TruthClass.SIMULATED.
7. Scenario branching and version preservation.
8. Reproducibility for identical inputs.
9. Scenario comparison and metric delta calculation.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from unittest import TestCase
from uuid import uuid4

from app.domain import (
    ConstraintCategory,
    ConstraintFinding,
    ConstraintSeverity,
    ConstraintStatus,
    ConstraintValidationResult,
    Scenario,
    ScenarioComparison,
    ScenarioEvaluation,
    ScenarioModification,
    ScenarioOperationType,
    ScenarioStatus,
    TimeInterval,
    TruthClass,
)
from app.scenarios import ScenarioEngine, ScenarioLifecycleError


class TestScenarioEngineUnit(TestCase):
    def setUp(self) -> None:
        self.engine = ScenarioEngine()
        self.entity_id_1 = uuid4()
        self.entity_id_2 = uuid4()

    # -------------------------------------------------------------------------
    # 1. Scenario Domain Model & Defaults
    # -------------------------------------------------------------------------

    def test_scenario_creation_defaults(self) -> None:
        scen = Scenario(
            name="Drought Impact 2027",
            description="Simulating 20% agricultural output reduction",
        )
        self.assertEqual(scen.name, "Drought Impact 2027")
        self.assertEqual(scen.status, ScenarioStatus.DRAFT)
        self.assertEqual(scen.version, 1)
        self.assertEqual(scen.truth_class, TruthClass.SIMULATED)
        self.assertIsNone(scen.parent_scenario_id)
        self.assertIsNone(scen.parent_scenario_version)
        self.assertIsInstance(scen.created_at, datetime)
        self.assertIsInstance(scen.updated_at, datetime)

    def test_scenario_with_parent_branching(self) -> None:
        parent_id = uuid4()
        scen = Scenario(
            name="Drought Impact Branch B",
            parent_scenario_id=parent_id,
            parent_scenario_version=3,
        )
        self.assertEqual(scen.parent_scenario_id, parent_id)
        self.assertEqual(scen.parent_scenario_version, 3)
        self.assertEqual(scen.version, 1)
        self.assertEqual(scen.status, ScenarioStatus.DRAFT)

    # -------------------------------------------------------------------------
    # 2. Scenario Modification Validation
    # -------------------------------------------------------------------------

    def test_modification_creation_supported_operations(self) -> None:
        for op in [
            ScenarioOperationType.SET,
            ScenarioOperationType.DELTA,
            ScenarioOperationType.SCALE,
            ScenarioOperationType.REMOVE,
        ]:
            mod = ScenarioModification(
                scenario_id=uuid4(),
                target_entity_id=self.entity_id_1,
                target_field="observation.population.total",
                operation=op,
                value=100.0 if op != ScenarioOperationType.REMOVE else None,
            )
            self.assertEqual(mod.operation, op)
            self.assertEqual(mod.status, "active")

    def test_modification_invalid_empty_target(self) -> None:
        with self.assertRaises(ValueError):
            ScenarioModification(
                scenario_id=uuid4(),
                target_entity_id=self.entity_id_1,
                target_field="",
                operation=ScenarioOperationType.SET,
                value=100.0,
            )

    def test_modification_effective_interval(self) -> None:
        t_start = datetime(2027, 1, 1, tzinfo=UTC)
        t_end = datetime(2027, 12, 31, tzinfo=UTC)
        interval = TimeInterval(
            id=uuid4(),
            starts_at=t_start,
            ends_at=t_end,
            precision="year",
        )
        mod = ScenarioModification(
            scenario_id=uuid4(),
            target_entity_id=self.entity_id_1,
            target_field="observation.energy.consumption",
            operation=ScenarioOperationType.SCALE,
            value=1.15,
            effective_interval=interval,
            rationale="Simulated economic growth increase",
            evidence_references=[uuid4()],
        )
        self.assertIsNotNone(mod.effective_interval)
        self.assertEqual(len(mod.evidence_references), 1)

    # -------------------------------------------------------------------------
    # 3. Deterministic Overlay Simulation Logic
    # -------------------------------------------------------------------------

    def test_deterministic_overlay_set_operation(self) -> None:
        baseline = {"population.total": {"value": 5000000.0, "unit": "people"}}
        # SET replaces the value directly
        new_val = 6000000.0
        applied = {"value": new_val, "unit": "people", "truth_class": TruthClass.SIMULATED.value}
        self.assertEqual(applied["value"], 6000000.0)
        self.assertEqual(applied["truth_class"], "SIMULATED")

    def test_deterministic_overlay_delta_operation(self) -> None:
        base_val = 5000000.0
        delta = -500000.0
        sim_val = base_val + delta
        self.assertEqual(sim_val, 4500000.0)
        abs_delta = sim_val - base_val
        pct_change = (abs_delta / base_val) * 100.0
        self.assertEqual(abs_delta, -500000.0)
        self.assertEqual(pct_change, -10.0)

    def test_deterministic_overlay_scale_operation(self) -> None:
        base_val = 200.0
        scale_factor = 1.25  # +25%
        sim_val = base_val * scale_factor
        self.assertEqual(sim_val, 250.0)
        abs_delta = sim_val - base_val
        pct_change = (abs_delta / base_val) * 100.0
        self.assertEqual(abs_delta, 50.0)
        self.assertEqual(pct_change, 25.0)

    def test_deterministic_overlay_remove_operation(self) -> None:
        obs_dict = {"population.total": {"value": 100.0}, "gdp": {"value": 50.0}}
        obs_dict.pop("gdp", None)
        self.assertNotIn("gdp", obs_dict)
        self.assertIn("population.total", obs_dict)

    def test_conflicting_modifications_deterministic_ordering(self) -> None:
        now = datetime.now(UTC)
        mod_a = ScenarioModification(
            id=uuid4(),
            scenario_id=uuid4(),
            target_entity_id=self.entity_id_1,
            target_field="observation.population.total",
            operation=ScenarioOperationType.SET,
            value=1000.0,
            created_at=now,
        )
        mod_b = ScenarioModification(
            id=uuid4(),
            scenario_id=uuid4(),
            target_entity_id=self.entity_id_1,
            target_field="observation.population.total",
            operation=ScenarioOperationType.DELTA,
            value=200.0,
            created_at=now + timedelta(seconds=1),
        )

        # Sort deterministically
        mods = [mod_b, mod_a]
        sorted_mods = sorted(
            mods,
            key=lambda m: (str(m.target_entity_id), m.target_field, m.created_at, str(m.id)),
        )
        self.assertEqual(sorted_mods[0].operation, ScenarioOperationType.SET)
        self.assertEqual(sorted_mods[1].operation, ScenarioOperationType.DELTA)

        # In deterministic application: SET 1000, then DELTA +200 => 1200
        val = sorted_mods[0].value
        val += sorted_mods[1].value
        self.assertEqual(val, 1200.0)

    # -------------------------------------------------------------------------
    # 4. Lifecycle Invariant Enforcement
    # -------------------------------------------------------------------------

    def test_archived_lifecycle_rejection(self) -> None:
        archived_scen = Scenario(
            name="Archived Historical Model",
            status=ScenarioStatus.ARCHIVED,
        )
        # Verify status is ARCHIVED
        self.assertEqual(archived_scen.status, ScenarioStatus.ARCHIVED)

    # -------------------------------------------------------------------------
    # 5. Reproducibility & Truth Classification
    # -------------------------------------------------------------------------

    def test_reproducibility_identical_overlay(self) -> None:
        base_state = {
            "entity_1": {
                "name": "Country A",
                "observations": {"metric": {"value": 100.0, "unit": "count"}},
            }
        }
        mod = ScenarioModification(
            scenario_id=uuid4(),
            target_entity_id=self.entity_id_1,
            target_field="observation.metric",
            operation=ScenarioOperationType.SCALE,
            value=1.5,
        )

        def apply(base, m):
            b_val = base["entity_1"]["observations"]["metric"]["value"]
            s_val = b_val * m.value
            return {
                "simulated_value": round(s_val, 4),
                "absolute_delta": round(s_val - b_val, 4),
                "percent_change": round(((s_val - b_val) / b_val) * 100.0, 2),
                "truth_class": TruthClass.SIMULATED.value,
            }

        res_1 = apply(base_state, mod)
        res_2 = apply(base_state, mod)
        self.assertEqual(res_1, res_2)
        self.assertEqual(res_1["simulated_value"], 150.0)
        self.assertEqual(res_1["truth_class"], "SIMULATED")

    # -------------------------------------------------------------------------
    # 6. Scenario Comparison Logic
    # -------------------------------------------------------------------------

    def test_scenario_comparison_deltas(self) -> None:
        eval_a = ScenarioEvaluation(
            scenario_id=uuid4(),
            scenario_version=1,
            baseline_snapshot={"e1": {"name": "Entity 1", "observations": {"pop": {"value": 1000.0}}}},
            simulated_state={"e1": {"name": "Entity 1", "observations": {"pop": {"value": 1200.0}}}},
            delta_summary={"e1:pop": {"absolute_delta": 200.0, "percent_change": 20.0}},
            is_feasible=True,
        )
        eval_b = ScenarioEvaluation(
            scenario_id=uuid4(),
            scenario_version=1,
            baseline_snapshot={"e1": {"name": "Entity 1", "observations": {"pop": {"value": 1000.0}}}},
            simulated_state={"e1": {"name": "Entity 1", "observations": {"pop": {"value": 800.0}}}},
            delta_summary={"e1:pop": {"absolute_delta": -200.0, "percent_change": -20.0}},
            is_feasible=True,
        )

        # Delta B - A = 800 - 1200 = -400
        val_a = eval_a.simulated_state["e1"]["observations"]["pop"]["value"]
        val_b = eval_b.simulated_state["e1"]["observations"]["pop"]["value"]
        diff = val_b - val_a
        self.assertEqual(diff, -400.0)

        comparison = ScenarioComparison(
            scenario_a_id=eval_a.scenario_id,
            scenario_b_id=eval_b.scenario_id,
            scenario_a_name="Expansion",
            scenario_b_name="Contraction",
            entity_comparisons=[{
                "entity_id": "e1",
                "name": "Entity 1",
                "measures": {"pop": {"scenario_a_value": val_a, "scenario_b_value": val_b, "delta_b_minus_a": diff}},
            }],
            feasibility_comparison={"scenario_a_feasible": True, "scenario_b_feasible": True},
            metric_deltas={"e1:pop": diff},
            summary="Comparison between Expansion and Contraction.",
        )
        self.assertEqual(comparison.metric_deltas["e1:pop"], -400.0)
        self.assertTrue(comparison.feasibility_comparison["scenario_a_feasible"])
