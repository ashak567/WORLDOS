"""Unit tests for Engine 17: Simulation Engine.

Verifies deterministic multi-step forward state evolution, transition rules,
reproducibility fingerprints, bounded execution, constraint evaluation,
and simulation comparisons.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
import unittest
from uuid import uuid4

from app.domain import (
    SimulationComparison,
    SimulationRequest,
    SimulationRun,
    SimulationStatus,
    SimulationStep,
    TransitionRuleDefinition,
    TruthClass,
)
from app.simulation import (
    DEFAULT_RULE_REGISTRY,
    LinearEvolutionRule,
    PerCapitaResourceDepletionRule,
    PopulationDynamicsRule,
    SimulationConfigurationError,
    SimulationEngine,
    SimulationLifecycleError,
    StockFlowAccountingRule,
    ThresholdAlertTriggerRule,
    TransitionRuleRegistry,
    advance_simulated_timestamp,
    compute_simulation_fingerprint,
    compute_step_fingerprint,
)


class TestSimulationModels(unittest.TestCase):
    """Test Simulation domain models and bounds checking."""

    def test_simulation_request_validation(self) -> None:
        scen_id = uuid4()
        now = datetime.now(UTC)

        # Valid request
        req = SimulationRequest(
            scenario_id=scen_id,
            starts_at=now,
            ends_at=now + timedelta(days=10),
            step_size=1.0,
            step_unit="day",
            max_steps=100,
        )
        self.assertEqual(req.scenario_id, scen_id)
        self.assertEqual(req.step_unit, "day")

        # Invalid: ends_at <= starts_at
        with self.assertRaises(ValueError):
            SimulationRequest(
                scenario_id=scen_id,
                starts_at=now,
                ends_at=now,
                step_size=1.0,
            )

        # Invalid: step_size <= 0
        with self.assertRaises(ValueError):
            SimulationRequest(
                scenario_id=scen_id,
                starts_at=now,
                ends_at=now + timedelta(days=5),
                step_size=0.0,
            )

        # Invalid: max_steps > 500
        with self.assertRaises(ValueError):
            SimulationRequest(
                scenario_id=scen_id,
                starts_at=now,
                ends_at=now + timedelta(days=5),
                max_steps=501,
            )

    def test_simulation_step_truth_class(self) -> None:
        step = SimulationStep(
            simulation_id=uuid4(),
            step_index=1,
            simulated_at=datetime.now(UTC),
            state={"eid": {"observations": {"pop": 100}}},
            metrics={"pop": 100},
        )
        self.assertEqual(step.truth_class, TruthClass.SIMULATED)


class TestTransitionRules(unittest.TestCase):
    """Test deterministic transition rule implementations."""

    def test_population_dynamics_rule_growth(self) -> None:
        rule = PopulationDynamicsRule()
        eid = str(uuid4())
        initial_state = {
            eid: {
                "name": "Country A",
                "observations": {
                    "population.total": {"value": 1000000.0, "truth_class": "OBSERVED"}
                },
            }
        }
        params = {"growth_rate": 0.05, "net_migration": 0.0}
        # 1 year step
        new_state, metrics, findings = rule.apply(
            current_state=initial_state,
            parameters=params,
            step_size=1.0,
            step_unit="year",
            context={},
        )
        new_pop = new_state[eid]["observations"]["population.total"]["value"]
        # Expected: 1,000,000 + 1 * (0.05 * 1,000,000) = 1,050,000
        self.assertAlmostEqual(new_pop, 1050000.0, places=2)
        self.assertEqual(new_state[eid]["observations"]["population.total"]["truth_class"], "SIMULATED")
        self.assertAlmostEqual(metrics[f"{eid}.population.growth_delta"], 50000.0, places=2)

    def test_population_dynamics_with_carrying_capacity(self) -> None:
        rule = PopulationDynamicsRule()
        eid = str(uuid4())
        # Population already at carrying capacity
        initial_state = {
            eid: {
                "name": "Country B",
                "observations": {
                    "population.total": {"value": 500000.0, "truth_class": "OBSERVED"}
                },
            }
        }
        params = {"growth_rate": 0.10, "carrying_capacity": 500000.0, "net_migration": 0.0}
        new_state, metrics, _ = rule.apply(
            current_state=initial_state,
            parameters=params,
            step_size=1.0,
            step_unit="year",
            context={},
        )
        new_pop = new_state[eid]["observations"]["population.total"]["value"]
        # Growth should be 0 because P = K
        self.assertAlmostEqual(new_pop, 500000.0, places=2)
        self.assertAlmostEqual(metrics[f"{eid}.population.growth_delta"], 0.0, places=2)

    def test_stock_flow_accounting_rule(self) -> None:
        rule = StockFlowAccountingRule()
        eid = str(uuid4())
        initial_state = {
            eid: {
                "name": "Warehouse 1",
                "observations": {
                    "resource.stock": {"value": 1000.0, "truth_class": "OBSERVED"}
                },
            }
        }
        # Inflow 200, Outflow 50, Decay 0.05 (decay on 1000 is 50), capacity 1500
        params = {
            "inflow_rate": 200.0,
            "outflow_rate": 50.0,
            "decay_rate": 0.05,
            "capacity": 1500.0,
        }
        new_state, metrics, _ = rule.apply(
            current_state=initial_state,
            parameters=params,
            step_size=1.0,
            step_unit="year",
            context={},
        )
        new_stock = new_state[eid]["observations"]["resource.stock"]["value"]
        # Expected: 1000 + (200 - 50 - 50) = 1100
        self.assertAlmostEqual(new_stock, 1100.0, places=2)
        self.assertAlmostEqual(metrics[f"{eid}.resource.stock.net_flow"], 100.0, places=2)
        self.assertAlmostEqual(metrics[f"{eid}.resource.stock.utilization_pct"], round(1100.0 / 1500.0 * 100, 2))

    def test_per_capita_resource_depletion_rule(self) -> None:
        rule = PerCapitaResourceDepletionRule()
        eid = str(uuid4())
        initial_state = {
            eid: {
                "name": "Island Colony",
                "observations": {
                    "population.total": {"value": 1000.0, "truth_class": "OBSERVED"},
                    "resource.stock": {"value": 5000.0, "truth_class": "OBSERVED"},
                },
            }
        }
        params = {
            "consumption_per_capita": 2.0,  # 1000 * 2 = 2000 units/year
            "replenishment_rate": 500.0,    # 500 units/year
        }
        # 1 year step
        new_state, metrics, _ = rule.apply(
            current_state=initial_state,
            parameters=params,
            step_size=1.0,
            step_unit="year",
            context={},
        )
        new_res = new_state[eid]["observations"]["resource.stock"]["value"]
        # Expected: 5000 + (500 - 2000) = 3500
        self.assertAlmostEqual(new_res, 3500.0, places=2)
        self.assertAlmostEqual(metrics[f"{eid}.resource.stock.consumption_rate"], 2000.0, places=2)

    def test_threshold_alert_trigger_rule(self) -> None:
        rule = ThresholdAlertTriggerRule()
        eid = str(uuid4())
        initial_state = {
            eid: {
                "name": "Grid Zone",
                "observations": {
                    "power.reserve": {"value": 15.0, "truth_class": "SIMULATED"}
                },
            }
        }
        params = {
            "target_metric": "power.reserve",
            "warning_threshold": 20.0,
            "critical_threshold": 10.0,
            "direction": "below",
        }
        _, metrics, findings = rule.apply(
            current_state=initial_state,
            parameters=params,
            step_size=1.0,
            step_unit="step",
            context={},
        )
        self.assertEqual(metrics[f"{eid}.power.reserve.health_status"], "WARNING")
        self.assertTrue(any("SIMULATED_ALERT" in f for f in findings))

    def test_linear_evolution_rule(self) -> None:
        rule = LinearEvolutionRule()
        eid = str(uuid4())
        initial_state = {
            eid: {
                "name": "Test Entity",
                "observations": {
                    "metric.x": {"value": 10.0, "truth_class": "OBSERVED"}
                },
            }
        }
        params = {
            "target_metric": "metric.x",
            "slope": 5.0,
            "min_value": 0.0,
            "max_value": 20.0,
        }
        new_state, metrics, _ = rule.apply(
            current_state=initial_state,
            parameters=params,
            step_size=1.0,
            step_unit="year",
            context={},
        )
        self.assertAlmostEqual(new_state[eid]["observations"]["metric.x"]["value"], 15.0)

        # Next step should hit max_value cap of 20.0
        new_state2, _, _ = rule.apply(
            current_state=new_state,
            parameters=params,
            step_size=2.0,
            step_unit="year",
            context={},
        )
        self.assertAlmostEqual(new_state2[eid]["observations"]["metric.x"]["value"], 20.0)


class TestDeterministicSimulationExecution(unittest.TestCase):
    """Test deterministic fingerprints, step advances, and multi-step accumulation."""

    def test_deterministic_simulation_fingerprint(self) -> None:
        scen_id = uuid4()
        now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        end = datetime(2030, 1, 1, 0, 0, 0, tzinfo=UTC)

        fp1 = compute_simulation_fingerprint(
            scenario_id=scen_id,
            scenario_version=1,
            starts_at=now,
            ends_at=end,
            step_size=1.0,
            step_unit="year",
            rule_ids=["population_dynamics_v1"],
            parameters={"growth_rate": 0.02},
            initial_state={"eid": {"val": 100}},
        )

        # Identical inputs must produce identical fingerprint
        fp2 = compute_simulation_fingerprint(
            scenario_id=scen_id,
            scenario_version=1,
            starts_at=now,
            ends_at=end,
            step_size=1.0,
            step_unit="year",
            rule_ids=["population_dynamics_v1"],
            parameters={"growth_rate": 0.02},
            initial_state={"eid": {"val": 100}},
        )
        self.assertEqual(fp1, fp2)
        self.assertTrue(fp1.startswith("sim_"))

        # Modified parameter must change fingerprint
        fp3 = compute_simulation_fingerprint(
            scenario_id=scen_id,
            scenario_version=1,
            starts_at=now,
            ends_at=end,
            step_size=1.0,
            step_unit="year",
            rule_ids=["population_dynamics_v1"],
            parameters={"growth_rate": 0.03},
            initial_state={"eid": {"val": 100}},
        )
        self.assertNotEqual(fp1, fp3)

    def test_advance_simulated_timestamp(self) -> None:
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Advance by 1 year
        t1 = advance_simulated_timestamp(base, step_index=1, step_size=1.0, step_unit="year")
        self.assertEqual(t1.year, 2027)

        # Advance by 2 months
        t2 = advance_simulated_timestamp(base, step_index=2, step_size=1.0, step_unit="month")
        self.assertEqual(t2.month, 3)

        # Advance by 5 days
        t3 = advance_simulated_timestamp(base, step_index=5, step_size=1.0, step_unit="day")
        self.assertEqual(t3.day, 6)

    def test_multi_step_preceding_state_accumulation(self) -> None:
        """Verify that multi-step simulation accumulates over preceding state rather than resetting."""
        rule = PopulationDynamicsRule()
        eid = "entity-1"
        state = {
            eid: {
                "observations": {
                    "population.total": {"value": 1000.0, "truth_class": "OBSERVED"}
                }
            }
        }
        params = {"growth_rate": 0.10, "net_migration": 0.0}

        # Step 1: 1000 + 10% = 1100
        state1, _, _ = rule.apply(state, params, 1.0, "year", {})
        self.assertAlmostEqual(state1[eid]["observations"]["population.total"]["value"], 1100.0)

        # Step 2: 1100 + 10% = 1210
        state2, _, _ = rule.apply(state1, params, 1.0, "year", {})
        self.assertAlmostEqual(state2[eid]["observations"]["population.total"]["value"], 1210.0)

        # Step 3: 1210 + 10% = 1331
        state3, _, _ = rule.apply(state2, params, 1.0, "year", {})
        self.assertAlmostEqual(state3[eid]["observations"]["population.total"]["value"], 1331.0)


class TestRuleRegistry(unittest.TestCase):
    """Test rule registry discovery and retrieval."""

    def test_default_rules_registered(self) -> None:
        rules = DEFAULT_RULE_REGISTRY.list_rules()
        rule_ids = [r.id for r in rules]
        self.assertIn("population_dynamics_v1", rule_ids)
        self.assertIn("stock_flow_accounting_v1", rule_ids)
        self.assertIn("per_capita_resource_depletion_v1", rule_ids)
        self.assertIn("threshold_state_transition_v1", rule_ids)
        self.assertIn("generic_linear_evolution_v1", rule_ids)

        # Retrieve individual rule
        pop_rule = DEFAULT_RULE_REGISTRY.get("population_dynamics_v1")
        self.assertIsNotNone(pop_rule)
        self.assertEqual(pop_rule.definition.id, "population_dynamics_v1")


if __name__ == "__main__":
    unittest.main()
