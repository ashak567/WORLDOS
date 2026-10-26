"""Unit tests for Engine 13: Deterministic Decision Support Engine.

Tests:
1. Valid and invalid decision requests and criteria definitions.
2. Weight validation, normalization, and zero-sum fallback.
3. Maximize, minimize, and target-range normalization formulas.
4. Hard-constraint exclusion (feasibility gate and non-compensability).
5. Soft-preference weighted utility calculation.
6. Missing data policies: EXCLUDE, NEUTRAL_SCORE, PENALIZE_MIN.
7. Unknown vs. genuine zero (0.0) distinction.
8. Deterministic tie-breaking and repeated evaluation reproducibility.
9. Evidence citations and uncertainty tracking.
10. Trade-off analysis explanations.
11. Bounded weight sensitivity analysis.
"""
from __future__ import annotations

import math
from unittest import TestCase
from uuid import uuid4

from app.decisions import DecisionEngine
from app.domain import (
    CriterionDirection,
    DecisionAlternative,
    DecisionCriterion,
    DecisionRequest,
    DecisionResult,
    MissingDataPolicy,
    TruthClass,
)


class TestDecisionEngineUnit(TestCase):
    def setUp(self) -> None:
        self.engine = DecisionEngine()

    # -------------------------------------------------------------------------
    # 1. Validation & Input Sanity
    # -------------------------------------------------------------------------

    def test_request_validation_valid(self) -> None:
        req = DecisionRequest(
            objective="Select regional operations center",
            alternatives=[
                DecisionAlternative(id="alt_1", name="Site Alpha", attributes={"cost": 100, "capacity": 500}),
                DecisionAlternative(id="alt_2", name="Site Beta", attributes={"cost": 80, "capacity": 450}),
            ],
            criteria=[
                DecisionCriterion(id="c_cost", name="Cost", metric_field="cost", direction=CriterionDirection.MINIMIZE, weight=1.0),
                DecisionCriterion(id="c_cap", name="Capacity", metric_field="capacity", direction=CriterionDirection.MAXIMIZE, weight=2.0),
            ],
        )
        errors = self.engine.validate_request(req)
        self.assertEqual(len(errors), 0, f"Expected 0 errors, got: {errors}")

    def test_request_validation_empty_fields(self) -> None:
        with self.assertRaises(ValueError):
            DecisionRequest(
                objective="",
                alternatives=[DecisionAlternative(id="alt_1", name="Site Alpha")],
                criteria=[DecisionCriterion(id="c1", name="C1", metric_field="m1")],
            )

        with self.assertRaises(ValueError):
            DecisionRequest(
                objective="Valid Objective",
                alternatives=[],
                criteria=[DecisionCriterion(id="c1", name="C1", metric_field="m1")],
            )

        with self.assertRaises(ValueError):
            DecisionRequest(
                objective="Valid Objective",
                alternatives=[DecisionAlternative(id="alt_1", name="Site Alpha")],
                criteria=[],
            )

    def test_criterion_validation_invalid_weights_and_ranges(self) -> None:
        with self.assertRaises(ValueError):
            DecisionCriterion(id="c1", name="C1", metric_field="m1", weight=-1.0)

        with self.assertRaises(ValueError):
            DecisionCriterion(id="c1", name="C1", metric_field="m1", weight=float("nan"))

        with self.assertRaises(ValueError):
            DecisionCriterion(
                id="c1",
                name="C1",
                metric_field="m1",
                direction=CriterionDirection.TARGET_RANGE,
                target_min=100.0,
                target_max=50.0,  # min > max
            )

        with self.assertRaises(ValueError):
            DecisionCriterion(
                id="c1",
                name="C1",
                metric_field="m1",
                hard_constraint_min=200.0,
                hard_constraint_max=100.0,  # min > max
            )

    # -------------------------------------------------------------------------
    # 2. Criterion Directions & Normalization Formulas
    # -------------------------------------------------------------------------

    def test_criterion_directions_normalization(self) -> None:
        c_max = DecisionCriterion(id="c_max", name="Benefit", metric_field="b", direction=CriterionDirection.MAXIMIZE)
        c_min = DecisionCriterion(id="c_min", name="Cost", metric_field="c", direction=CriterionDirection.MINIMIZE)
        c_tgt = DecisionCriterion(
            id="c_tgt",
            name="Temperature",
            metric_field="t",
            direction=CriterionDirection.TARGET_RANGE,
            target_min=20.0,
            target_max=25.0,
        )

        policy = MissingDataPolicy.NEUTRAL_SCORE

        # Maximize: value 80 in [50, 100] -> (80-50)/(100-50) = 30/50 = 0.6
        score_max = self.engine.normalize_criterion_value(80.0, c_max, 50.0, 100.0, policy)
        self.assertAlmostEqual(score_max, 0.6, places=4)

        # Minimize: value 80 in [50, 100] -> (100-80)/(100-50) = 20/50 = 0.4
        score_min = self.engine.normalize_criterion_value(80.0, c_min, 50.0, 100.0, policy)
        self.assertAlmostEqual(score_min, 0.4, places=4)

        # Target range: inside [20, 25] -> 1.0
        score_tgt_inside = self.engine.normalize_criterion_value(22.0, c_tgt, 10.0, 40.0, policy)
        self.assertEqual(score_tgt_inside, 1.0)

        # Target range: outside [20, 25], value 15 (distance 5, width 5, penalty 5/(5*2) = 0.5) -> 0.5
        score_tgt_outside = self.engine.normalize_criterion_value(15.0, c_tgt, 10.0, 40.0, policy)
        self.assertAlmostEqual(score_tgt_outside, 0.5, places=4)

        # Equal min and max bounds: should return 1.0 cleanly without division by zero
        score_equal_bounds = self.engine.normalize_criterion_value(50.0, c_max, 50.0, 50.0, policy)
        self.assertEqual(score_equal_bounds, 1.0)

    # -------------------------------------------------------------------------
    # 3. Hard Constraints vs. Soft Preferences
    # -------------------------------------------------------------------------

    def test_hard_constraint_exclusion_non_compensable(self) -> None:
        # Candidate A has high benefit (1000) but fails budget hard constraint (< 500 required)
        # Candidate B has modest benefit (500) and meets budget (400)
        req = DecisionRequest(
            objective="Select project under strict budget",
            persist=False,
            alternatives=[
                DecisionAlternative(id="proj_A", name="Project Alpha", attributes={"benefit": 1000, "budget": 600}),
                DecisionAlternative(id="proj_B", name="Project Beta", attributes={"benefit": 500, "budget": 400}),
            ],
            criteria=[
                DecisionCriterion(
                    id="c_benefit",
                    name="Benefit",
                    metric_field="benefit",
                    direction=CriterionDirection.MAXIMIZE,
                    weight=10.0,  # very high weight
                ),
                DecisionCriterion(
                    id="c_budget",
                    name="Budget",
                    metric_field="budget",
                    direction=CriterionDirection.MINIMIZE,
                    weight=1.0,
                    hard_constraint_max=500.0,  # Hard constraint: budget <= 500
                ),
            ],
        )

        res = self.engine.evaluate(req)

        # Project Alpha must be excluded as infeasible despite having 2x the benefit
        self.assertEqual(len(res.feasible_alternatives), 1)
        self.assertEqual(len(res.infeasible_alternatives), 1)

        feasible_id = res.feasible_alternatives[0].alternative_id
        self.assertEqual(feasible_id, "proj_B")

        infeasible = res.infeasible_alternatives[0]
        self.assertEqual(infeasible.alternative_id, "proj_A")
        self.assertTrue(any("exceeds hard constraint threshold 500" in r for r in infeasible.blocking_reasons))

    # -------------------------------------------------------------------------
    # 4. Soft Preference Ranking & Weight Normalization
    # -------------------------------------------------------------------------

    def test_soft_preferences_weighted_utility(self) -> None:
        req = DecisionRequest(
            objective="Rank suppliers",
            persist=False,
            alternatives=[
                DecisionAlternative(id="s1", name="Supplier One", attributes={"quality": 90, "lead_time": 10}),
                DecisionAlternative(id="s2", name="Supplier Two", attributes={"quality": 70, "lead_time": 5}),
            ],
            criteria=[
                DecisionCriterion(id="q", name="Quality", metric_field="quality", direction=CriterionDirection.MAXIMIZE, weight=3.0),
                DecisionCriterion(id="l", name="Lead Time", metric_field="lead_time", direction=CriterionDirection.MINIMIZE, weight=1.0),
            ],
        )
        res = self.engine.evaluate(req)

        self.assertEqual(res.feasible_count, 2)
        # Weights: 3.0 and 1.0 -> 0.75 and 0.25
        self.assertAlmostEqual(res.normalized_weights["q"], 0.75, places=4)
        self.assertAlmostEqual(res.normalized_weights["l"], 0.25, places=4)

        # Supplier One:
        # Quality: 90 vs 70 -> norm = 1.0 (weight 0.75) -> 0.75
        # Lead time: 10 vs 5 (MINIMIZE) -> norm = 0.0 (weight 0.25) -> 0.0
        # Total = 0.75
        s1 = next(a for a in res.feasible_alternatives if a.alternative_id == "s1")
        self.assertAlmostEqual(s1.overall_score, 0.75, places=4)
        self.assertEqual(s1.rank, 1)

        # Supplier Two:
        # Quality: 70 vs 90 -> norm = 0.0 (weight 0.75) -> 0.0
        # Lead time: 5 vs 10 (MINIMIZE) -> norm = 1.0 (weight 0.25) -> 0.25
        # Total = 0.25
        s2 = next(a for a in res.feasible_alternatives if a.alternative_id == "s2")
        self.assertAlmostEqual(s2.overall_score, 0.25, places=4)
        self.assertEqual(s2.rank, 2)

    def test_zero_total_weights_equal_fallback(self) -> None:
        req = DecisionRequest(
            objective="Equal weights fallback",
            persist=False,
            alternatives=[
                DecisionAlternative(id="a1", name="Alpha", attributes={"m1": 10, "m2": 20}),
                DecisionAlternative(id="a2", name="Beta", attributes={"m1": 20, "m2": 10}),
            ],
            criteria=[
                DecisionCriterion(id="c1", name="Metric 1", metric_field="m1", weight=0.0),
                DecisionCriterion(id="c2", name="Metric 2", metric_field="m2", weight=0.0),
            ],
        )
        res = self.engine.evaluate(req)

        # Both criteria weights 0.0 -> fallback to equal weights 0.5 each
        self.assertAlmostEqual(res.normalized_weights["c1"], 0.5, places=4)
        self.assertAlmostEqual(res.normalized_weights["c2"], 0.5, places=4)
        self.assertTrue(any("equal weights" in note.lower() for note in res.ranking_limitations))

    # -------------------------------------------------------------------------
    # 5. Missing Data Policies: EXCLUDE, NEUTRAL_SCORE, PENALIZE_MIN
    # -------------------------------------------------------------------------

    def test_missing_data_policy_exclude(self) -> None:
        req = DecisionRequest(
            objective="Exclude missing",
            persist=False,
            missing_data_policy=MissingDataPolicy.EXCLUDE,
            alternatives=[
                DecisionAlternative(id="a1", name="Complete", attributes={"val": 50}),
                DecisionAlternative(id="a2", name="Incomplete", attributes={}),  # missing 'val'
            ],
            criteria=[
                DecisionCriterion(id="c1", name="Value", metric_field="val", direction=CriterionDirection.MAXIMIZE),
            ],
        )
        res = self.engine.evaluate(req)

        self.assertEqual(res.feasible_count, 1)
        self.assertEqual(res.infeasible_count, 1)
        self.assertEqual(res.infeasible_alternatives[0].alternative_id, "a2")
        self.assertTrue(any("Missing required data" in r for r in res.infeasible_alternatives[0].blocking_reasons))

    def test_missing_data_policy_neutral_score(self) -> None:
        req = DecisionRequest(
            objective="Neutral score for missing",
            persist=False,
            missing_data_policy=MissingDataPolicy.NEUTRAL_SCORE,
            alternatives=[
                DecisionAlternative(id="a1", name="High", attributes={"val": 100}),
                DecisionAlternative(id="a2", name="Missing", attributes={}),
                DecisionAlternative(id="a3", name="Low", attributes={"val": 0}),
            ],
            criteria=[
                DecisionCriterion(id="c1", name="Value", metric_field="val", direction=CriterionDirection.MAXIMIZE),
            ],
        )
        res = self.engine.evaluate(req)

        self.assertEqual(res.feasible_count, 3)
        a2 = next(a for a in res.feasible_alternatives if a.alternative_id == "a2")
        self.assertTrue(a2.criteria_breakdown["c1"].is_missing)
        self.assertIsNone(a2.criteria_breakdown["c1"].raw_value)
        # Normalized score should be 0.5
        self.assertEqual(a2.criteria_breakdown["c1"].normalized_score, 0.5)

    def test_missing_data_policy_penalize_min(self) -> None:
        req = DecisionRequest(
            objective="Penalize minimum for missing",
            persist=False,
            missing_data_policy=MissingDataPolicy.PENALIZE_MIN,
            alternatives=[
                DecisionAlternative(id="a1", name="High", attributes={"val": 100}),
                DecisionAlternative(id="a2", name="Missing", attributes={}),
            ],
            criteria=[
                DecisionCriterion(id="c1", name="Value", metric_field="val", direction=CriterionDirection.MAXIMIZE),
            ],
        )
        res = self.engine.evaluate(req)

        a2 = next(a for a in res.feasible_alternatives if a.alternative_id == "a2")
        self.assertTrue(a2.criteria_breakdown["c1"].is_missing)
        self.assertIsNone(a2.criteria_breakdown["c1"].raw_value)
        # Normalized score should be 0.0 (penalty)
        self.assertEqual(a2.criteria_breakdown["c1"].normalized_score, 0.0)

    # -------------------------------------------------------------------------
    # 6. Unknown vs. Genuine Zero (0.0)
    # -------------------------------------------------------------------------

    def test_distinguish_unknown_from_genuine_zero(self) -> None:
        # Cost criterion (MINIMIZE):
        # Alternative Zero: cost = 0.0 (genuine free tier/zero cost) -> should receive 1.0!
        # Alternative Missing: cost not provided (unknown) -> should receive 0.5 (neutral)
        # Alternative Expensive: cost = 100.0 -> should receive 0.0
        req = DecisionRequest(
            objective="Free vs Unknown cost",
            persist=False,
            missing_data_policy=MissingDataPolicy.NEUTRAL_SCORE,
            alternatives=[
                DecisionAlternative(id="alt_zero", name="Zero Cost", attributes={"cost": 0.0}),
                DecisionAlternative(id="alt_unknown", name="Unknown Cost", attributes={}),
                DecisionAlternative(id="alt_exp", name="Expensive", attributes={"cost": 100.0}),
            ],
            criteria=[
                DecisionCriterion(id="c_cost", name="Cost", metric_field="cost", direction=CriterionDirection.MINIMIZE),
            ],
        )
        res = self.engine.evaluate(req)

        alt_zero = next(a for a in res.feasible_alternatives if a.alternative_id == "alt_zero")
        alt_unknown = next(a for a in res.feasible_alternatives if a.alternative_id == "alt_unknown")

        # Zero cost is a genuine number
        self.assertFalse(alt_zero.criteria_breakdown["c_cost"].is_missing)
        self.assertEqual(alt_zero.criteria_breakdown["c_cost"].raw_value, 0.0)
        self.assertEqual(alt_zero.criteria_breakdown["c_cost"].normalized_score, 1.0)
        self.assertEqual(alt_zero.rank, 1)

        # Unknown cost is missing
        self.assertTrue(alt_unknown.criteria_breakdown["c_cost"].is_missing)
        self.assertIsNone(alt_unknown.criteria_breakdown["c_cost"].raw_value)
        self.assertEqual(alt_unknown.criteria_breakdown["c_cost"].normalized_score, 0.5)
        self.assertEqual(alt_unknown.rank, 2)

    # -------------------------------------------------------------------------
    # 7. Deterministic Tie-Breaking & Reproducibility
    # -------------------------------------------------------------------------

    def test_deterministic_tie_breaking_and_reproducibility(self) -> None:
        # Two alternatives with exactly identical scores
        req = DecisionRequest(
            objective="Tie breaking test",
            persist=False,
            alternatives=[
                DecisionAlternative(id="alt_z", name="Bravo", attributes={"m": 50}),
                DecisionAlternative(id="alt_a", name="Alpha", attributes={"m": 50}),
            ],
            criteria=[
                DecisionCriterion(id="c1", name="Metric", metric_field="m", direction=CriterionDirection.MAXIMIZE),
            ],
        )

        res1 = self.engine.evaluate(req)
        # Sorted by overall_score desc, c0_score desc, name asc, id asc
        # "Alpha" precedes "Bravo" alphabetically
        self.assertEqual(res1.feasible_alternatives[0].name, "Alpha")
        self.assertEqual(res1.feasible_alternatives[1].name, "Bravo")

        # Run 10 times: must produce identical results
        for _ in range(10):
            res_repeat = self.engine.evaluate(req)
            self.assertEqual(
                [a.alternative_id for a in res_repeat.feasible_alternatives],
                [a.alternative_id for a in res1.feasible_alternatives],
            )
            self.assertEqual(
                [a.overall_score for a in res_repeat.feasible_alternatives],
                [a.overall_score for a in res1.feasible_alternatives],
            )

    # -------------------------------------------------------------------------
    # 8. Trade-Off Explanations & Sensitivity Analysis
    # -------------------------------------------------------------------------

    def test_trade_off_analysis(self) -> None:
        req = DecisionRequest(
            objective="Compare alternatives",
            persist=False,
            alternatives=[
                DecisionAlternative(id="a1", name="Alpha", attributes={"speed": 100, "cost": 100}),
                DecisionAlternative(id="a2", name="Beta", attributes={"speed": 50, "cost": 20}),
            ],
            criteria=[
                DecisionCriterion(id="spd", name="Speed", metric_field="speed", direction=CriterionDirection.MAXIMIZE, weight=1.0),
                DecisionCriterion(id="cst", name="Cost", metric_field="cost", direction=CriterionDirection.MINIMIZE, weight=1.0),
            ],
        )
        res = self.engine.evaluate(req)

        trade_offs = res.trade_off_analysis
        self.assertIn("top_choice", trade_offs)
        self.assertIn("comparisons", trade_offs)
        self.assertGreater(len(trade_offs["comparisons"]), 0)

    def test_sensitivity_analysis(self) -> None:
        # Alpha wins primarily because speed weight is high
        req = DecisionRequest(
            objective="Sensitivity test",
            persist=False,
            alternatives=[
                DecisionAlternative(id="fast", name="Fast but Expensive", attributes={"speed": 100, "cost": 100}),
                DecisionAlternative(id="cheap", name="Slow but Cheap", attributes={"speed": 20, "cost": 10}),
            ],
            criteria=[
                DecisionCriterion(id="spd", name="Speed", metric_field="speed", direction=CriterionDirection.MAXIMIZE, weight=1.1),
                DecisionCriterion(id="cst", name="Cost", metric_field="cost", direction=CriterionDirection.MINIMIZE, weight=1.0),
            ],
        )

        variations = self.engine.run_sensitivity_analysis(req, delta_pct=0.30)
        self.assertGreater(len(variations), 0)

        # Check variation fields
        v0 = variations[0]
        self.assertIsNotNone(v0.criterion_id)
        self.assertIsNotNone(v0.top_alternative_id)
        self.assertIsInstance(v0.rank_changed, bool)

    def test_sensitivity_analysis_invalid_delta(self) -> None:
        req = DecisionRequest(
            objective="Sensitivity bounds check",
            persist=False,
            alternatives=[DecisionAlternative(id="a", name="A", attributes={"m": 1})],
            criteria=[DecisionCriterion(id="c", name="C", metric_field="m")],
        )
        with self.assertRaises(ValueError):
            self.engine.run_sensitivity_analysis(req, delta_pct=0.0)

        with self.assertRaises(ValueError):
            self.engine.run_sensitivity_analysis(req, delta_pct=1.5)
