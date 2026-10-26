"""Engine 13: Deterministic Decision Support Engine.

Provides evidence-linked, reproducible Multi-Criteria Decision Analysis (MCDA)
over authoritative world-state data, candidate alternatives, and scenario proposals.
Distinguishes hard constraints (feasibility gates) from soft preferences (weighted ranking),
enforces missing-data policies without conflating unknown values with genuine zero,
and generates deterministic trade-off explanations and sensitivity bounds.
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from .domain import (
    ConstraintSeverity,
    ConstraintStatus,
    CriterionDirection,
    CriterionScoreBreakdown,
    DecisionAlternative,
    DecisionCriterion,
    DecisionRequest,
    DecisionResult,
    InfeasibleAlternative,
    MissingDataPolicy,
    RankedAlternative,
    SensitivityVariation,
    TruthClass,
)


class DecisionEngine:
    """Deterministic Multi-Criteria Decision Analysis (MCDA) Engine for WORLDOS.

    Key Architectural Principles:
    1. Operational Non-Mutation: Decision evaluation never mutates world-state facts.
    2. Strict Hard-Constraint Feasibility: Hard constraints gate alternatives before scoring.
       A high score on soft criteria cannot compensate for a hard constraint violation.
    3. Missing Data vs. Zero: Missing observations are explicitly distinguished from genuine
       zero (0.0) values.
    4. Determinism & Auditability: All intermediate calculations (raw values, normalized scores,
       weights, contributions) are retained and returned in the audit trace.
    5. Deterministic Tie-Breaking: Strict multi-level ordering eliminates non-deterministic sort order.
    """

    def __init__(self, repository: Any = None) -> None:
        self.repository = repository

    # -------------------------------------------------------------------------
    # 1. Validation & Input Sanity
    # -------------------------------------------------------------------------

    def validate_request(self, request: DecisionRequest) -> list[str]:
        """Validate decision request parameters and criteria consistency."""
        errors: list[str] = []

        if not request.objective or not request.objective.strip():
            errors.append("Decision objective cannot be empty")

        if not request.alternatives:
            errors.append("At least one candidate alternative must be provided")

        if not request.criteria:
            errors.append("At least one evaluation criterion must be provided")

        alt_ids = set()
        for alt in request.alternatives:
            if not alt.id or not alt.id.strip():
                errors.append("Alternative ID cannot be empty")
            elif alt.id in alt_ids:
                errors.append(f"Duplicate alternative ID '{alt.id}'")
            alt_ids.add(alt.id)

        crit_ids = set()
        for crit in request.criteria:
            if not crit.id or not crit.id.strip():
                errors.append("Criterion ID cannot be empty")
            elif crit.id in crit_ids:
                errors.append(f"Duplicate criterion ID '{crit.id}'")
            crit_ids.add(crit.id)

            if math.isnan(crit.weight) or math.isinf(crit.weight) or crit.weight < 0:
                errors.append(f"Criterion '{crit.name}' has invalid weight: {crit.weight}")

            if crit.direction == CriterionDirection.TARGET_RANGE:
                if crit.target_min is None or crit.target_max is None:
                    errors.append(f"Criterion '{crit.name}' requires target_min and target_max")
                elif crit.target_min > crit.target_max:
                    errors.append(
                        f"Criterion '{crit.name}': target_min ({crit.target_min}) > target_max ({crit.target_max})"
                    )

            if crit.hard_constraint_min is not None and crit.hard_constraint_max is not None:
                if crit.hard_constraint_min > crit.hard_constraint_max:
                    errors.append(
                        f"Criterion '{crit.name}': hard_constraint_min ({crit.hard_constraint_min}) > hard_constraint_max ({crit.hard_constraint_max})"
                    )

        return errors

    # -------------------------------------------------------------------------
    # 2. Metric Resolution & Authoritative World-State Linking
    # -------------------------------------------------------------------------

    def resolve_alternative_metrics(
        self,
        alternative: DecisionAlternative,
        criteria: list[DecisionCriterion],
        conn: psycopg.Connection | None = None,
    ) -> tuple[dict[str, float | None], dict[str, dict[str, Any]], list[UUID]]:
        """Resolve metric values for an alternative across explicit attributes and world state.

        Returns:
            (raw_values, metadata_by_metric, cited_evidence_ids)
        """
        raw_values: dict[str, float | None] = {}
        metadata: dict[str, dict[str, Any]] = {}
        cited_evidence_ids: list[UUID] = []

        # 1. Start with user-supplied attributes
        supplied_attrs = dict(alternative.attributes or {})

        # 2. If alternative has an entity_id and database connection is available, query observations & claims
        db_observations: dict[str, dict[str, Any]] = {}
        if alternative.entity_id and conn:
            with conn.cursor() as cur:
                # Query most recent observations for this entity
                cur.execute(
                    """
                    SELECT o.measure, o.value, o.unit, o.confidence, o.evidence_id, o.truth_class,
                           t.starts_at, t.ends_at, ev.locator AS evidence_locator
                    FROM observations o
                    JOIN time_intervals t ON t.id = o.time_interval_id
                    JOIN evidence ev ON ev.id = o.evidence_id
                    WHERE o.subject_entity_id = %s
                    ORDER BY t.starts_at DESC
                    """,
                    (alternative.entity_id,),
                )
                for row in cur.fetchall():
                    measure = row["measure"]
                    if measure not in db_observations:
                        db_observations[measure] = {
                            "value": float(row["value"]),
                            "unit": row["unit"],
                            "confidence": float(row["confidence"]),
                            "evidence_id": row["evidence_id"],
                            "truth_class": row["truth_class"],
                            "locator": row["evidence_locator"],
                            "starts_at": row["starts_at"],
                            "ends_at": row["ends_at"],
                        }

        # 3. For each criterion, resolve metric value
        for crit in criteria:
            metric_key = crit.metric_field
            if metric_key in supplied_attrs and supplied_attrs[metric_key] is not None:
                val = supplied_attrs[metric_key]
                try:
                    num_val = float(val)
                    if math.isfinite(num_val):
                        raw_values[crit.id] = num_val
                        metadata[crit.id] = {
                            "unit": crit.unit or supplied_attrs.get(f"{metric_key}_unit"),
                            "truth_class": supplied_attrs.get(f"{metric_key}_truth_class", TruthClass.OBSERVED.value),
                            "evidence_id": supplied_attrs.get(f"{metric_key}_evidence_id"),
                        }
                        if supplied_attrs.get(f"{metric_key}_evidence_id"):
                            try:
                                cited_evidence_ids.append(UUID(str(supplied_attrs[f"{metric_key}_evidence_id"])))
                            except (ValueError, TypeError):
                                pass
                    else:
                        raw_values[crit.id] = None
                        metadata[crit.id] = {"error": "non-finite value"}
                except (ValueError, TypeError):
                    raw_values[crit.id] = None
                    metadata[crit.id] = {"error": "invalid numeric format"}

            elif metric_key in db_observations:
                obs = db_observations[metric_key]
                raw_values[crit.id] = obs["value"]
                metadata[crit.id] = {
                    "unit": obs["unit"] or crit.unit,
                    "truth_class": obs["truth_class"],
                    "confidence": obs["confidence"],
                    "evidence_id": obs["evidence_id"],
                    "locator": obs["locator"],
                    "starts_at": obs["starts_at"],
                    "ends_at": obs["ends_at"],
                }
                cited_evidence_ids.append(obs["evidence_id"])
            else:
                # Value is missing (not found)
                raw_values[crit.id] = None
                metadata[crit.id] = {"is_missing": True}

        return raw_values, metadata, cited_evidence_ids

    # -------------------------------------------------------------------------
    # 3. Hard Constraint Evaluation (Feasibility Gate)
    # -------------------------------------------------------------------------

    def evaluate_hard_constraints(
        self,
        alternative: DecisionAlternative,
        raw_values: dict[str, float | None],
        criteria: list[DecisionCriterion],
        missing_data_policy: MissingDataPolicy,
        conn: psycopg.Connection | None = None,
    ) -> tuple[bool, list[str], list[dict[str, Any]]]:
        """Check all hard constraints. Returns (is_feasible, blocking_reasons, constraint_findings)."""
        blocking_reasons: list[str] = []
        findings: list[dict[str, Any]] = []

        # 1. Constraint Engine validation if alternative specifies a ScenarioProposal
        if alternative.scenario_proposal and self.repository and hasattr(self.repository, "constraint_engine"):
            proposal_res = self.repository.constraint_engine.validate_scenario_proposal(
                alternative.scenario_proposal, conn=conn
            )
            if proposal_res.status == ConstraintStatus.INVALID:
                for f in proposal_res.findings:
                    if f.severity == ConstraintSeverity.BLOCKING:
                        blocking_reasons.append(f"Scenario proposal constraint violation: {f.message}")
                        findings.append(f.model_dump())

        # 2. Criterion-level hard constraints & missing data checks
        for crit in criteria:
            val = raw_values.get(crit.id)

            # Check missing data under EXCLUDE policy or when criterion is explicitly required
            if val is None:
                if crit.required or missing_data_policy == MissingDataPolicy.EXCLUDE:
                    reason = f"Missing required data for criterion '{crit.name}' ({crit.metric_field})"
                    blocking_reasons.append(reason)
                    findings.append({
                        "category": "decision_criteria",
                        "severity": "BLOCKING",
                        "message": reason,
                        "criterion_id": crit.id,
                    })
                continue

            # Hard constraint minimum
            if crit.hard_constraint_min is not None and val < crit.hard_constraint_min:
                reason = (
                    f"Criterion '{crit.name}' value {val} is below hard constraint threshold {crit.hard_constraint_min}"
                )
                blocking_reasons.append(reason)
                findings.append({
                    "category": "decision_criteria",
                    "severity": "BLOCKING",
                    "message": reason,
                    "criterion_id": crit.id,
                    "value": val,
                    "threshold": crit.hard_constraint_min,
                })

            # Hard constraint maximum
            if crit.hard_constraint_max is not None and val > crit.hard_constraint_max:
                reason = (
                    f"Criterion '{crit.name}' value {val} exceeds hard constraint threshold {crit.hard_constraint_max}"
                )
                blocking_reasons.append(reason)
                findings.append({
                    "category": "decision_criteria",
                    "severity": "BLOCKING",
                    "message": reason,
                    "criterion_id": crit.id,
                    "value": val,
                    "threshold": crit.hard_constraint_max,
                })

        is_feasible = len(blocking_reasons) == 0
        return is_feasible, blocking_reasons, findings

    # -------------------------------------------------------------------------
    # 4. Deterministic Normalization & Scoring
    # -------------------------------------------------------------------------

    @staticmethod
    def normalize_criterion_value(
        value: float | None,
        criterion: DecisionCriterion,
        min_val: float,
        max_val: float,
        missing_data_policy: MissingDataPolicy,
    ) -> float:
        """Deterministic normalization scaling into [0.0, 1.0].

        - MAXIMIZE: (x - min) / (max - min)
        - MINIMIZE: (max - x) / (max - min)
        - TARGET_RANGE: 1.0 inside [target_min, target_max], linear decay outside
        - Missing: 0.5 (NEUTRAL_SCORE), 0.0 (PENALIZE_MIN), or excluded earlier
        """
        if value is None:
            if missing_data_policy == MissingDataPolicy.NEUTRAL_SCORE:
                return 0.5
            elif missing_data_policy == MissingDataPolicy.PENALIZE_MIN:
                return 0.0
            return 0.0

        if not math.isfinite(value):
            return 0.0

        direction = criterion.direction

        if direction == CriterionDirection.MAXIMIZE:
            if max_val == min_val:
                return 1.0
            norm = (value - min_val) / (max_val - min_val)
            return max(0.0, min(1.0, float(norm)))

        elif direction == CriterionDirection.MINIMIZE:
            if max_val == min_val:
                return 1.0
            norm = (max_val - value) / (max_val - min_val)
            return max(0.0, min(1.0, float(norm)))

        elif direction == CriterionDirection.TARGET_RANGE:
            t_min = criterion.target_min if criterion.target_min is not None else min_val
            t_max = criterion.target_max if criterion.target_max is not None else max_val

            if t_min <= value <= t_max:
                return 1.0

            # Linear penalty based on distance from the closest boundary
            width = max(1e-6, t_max - t_min)
            if value < t_min:
                distance = t_min - value
            else:
                distance = value - t_max

            # Scale penalty so distance equal to 2x width yields 0.0
            penalty = distance / (width * 2.0)
            score = max(0.0, 1.0 - penalty)
            return max(0.0, min(1.0, float(score)))

        return 0.0

    @staticmethod
    def normalize_weights(criteria: list[DecisionCriterion]) -> tuple[dict[str, float], list[str]]:
        """Normalize criterion weights so sum(w_i) == 1.0.

        Handles total weight == 0 by applying equal weights (1/N) explicitly.
        """
        notes: list[str] = []
        total_weight = sum(c.weight for c in criteria)

        if total_weight <= 0:
            notes.append("Total criterion weight was 0.0; equal weights (1/N) applied deterministically.")
            n = max(1, len(criteria))
            return {c.id: 1.0 / n for c in criteria}, notes

        norm_weights = {c.id: c.weight / total_weight for c in criteria}
        return norm_weights, notes

    # -------------------------------------------------------------------------
    # 5. Core Evaluation Pipeline
    # -------------------------------------------------------------------------

    def evaluate(self, request: DecisionRequest, conn: psycopg.Connection | None = None) -> DecisionResult:
        """Execute deterministic Multi-Criteria Decision Analysis.

        Returns an auditable, reproducible DecisionResult with full calculation trace.
        """
        # Step 1: Validate request
        validation_errors = self.validate_request(request)
        if validation_errors:
            raise ValueError(f"Invalid decision request: {'; '.join(validation_errors)}")

        criteria = request.criteria
        alternatives = request.alternatives
        policy = request.missing_data_policy

        # Step 2: Weight normalization
        norm_weights, weight_notes = self.normalize_weights(criteria)

        # Step 3: Resolve raw values and check hard constraints
        candidate_data: dict[str, dict[str, Any]] = {}
        feasible_alts: list[DecisionAlternative] = []
        infeasible_alts: list[InfeasibleAlternative] = []
        all_cited_evidence: list[dict[str, Any]] = []
        seen_evidence_ids: set[UUID] = set()

        for alt in alternatives:
            raw_vals, meta, cited_ev_ids = self.resolve_alternative_metrics(alt, criteria, conn=conn)

            # Record evidence citations
            for ev_id in cited_ev_ids:
                if ev_id not in seen_evidence_ids:
                    seen_evidence_ids.add(ev_id)
                    all_cited_evidence.append({
                        "evidence_id": str(ev_id),
                        "locator": meta.get(list(raw_vals.keys())[0], {}).get("locator") if raw_vals else None,
                        "source": meta.get(list(raw_vals.keys())[0], {}).get("source_slug") if raw_vals else None,
                    })

            is_feasible, blocking_reasons, findings = self.evaluate_hard_constraints(
                alt, raw_vals, criteria, policy, conn=conn
            )

            if not is_feasible or (request.enforce_constraints and blocking_reasons):
                infeasible_alts.append(
                    InfeasibleAlternative(
                        alternative_id=alt.id,
                        name=alt.name,
                        entity_id=alt.entity_id,
                        blocking_reasons=blocking_reasons,
                        constraint_findings=findings,
                    )
                )
            else:
                feasible_alts.append(alt)
                candidate_data[alt.id] = {
                    "raw_values": raw_vals,
                    "metadata": meta,
                    "evidence_ids": cited_ev_ids,
                }

        # Step 4: Compute bounds (min/max) for each criterion over feasible alternatives with values
        crit_bounds: dict[str, tuple[float, float]] = {}
        for crit in criteria:
            vals = [
                candidate_data[alt.id]["raw_values"][crit.id]
                for alt in feasible_alts
                if candidate_data[alt.id]["raw_values"].get(crit.id) is not None
            ]
            if vals:
                crit_bounds[crit.id] = (min(vals), max(vals))
            else:
                crit_bounds[crit.id] = (0.0, 1.0)

        # Step 5: Score feasible alternatives
        ranked_list: list[RankedAlternative] = []

        for alt in feasible_alts:
            alt_info = candidate_data[alt.id]
            raw_vals = alt_info["raw_values"]
            meta = alt_info["metadata"]
            ev_ids = alt_info["evidence_ids"]

            overall_score = 0.0
            breakdown: dict[str, CriterionScoreBreakdown] = {}
            missing_crit_names: list[str] = []
            uncertainty_notes: list[str] = []

            for crit in criteria:
                raw_v = raw_vals.get(crit.id)
                min_v, max_v = crit_bounds[crit.id]
                w_norm = norm_weights[crit.id]

                is_missing = raw_v is None
                if is_missing:
                    missing_crit_names.append(crit.name)
                    uncertainty_notes.append(
                        f"Criterion '{crit.name}' is missing; policy '{policy.value}' applied."
                    )

                norm_score = self.normalize_criterion_value(
                    value=raw_v,
                    criterion=crit,
                    min_val=min_v,
                    max_val=max_v,
                    missing_data_policy=policy,
                )

                contribution = w_norm * norm_score
                overall_score += contribution

                crit_meta = meta.get(crit.id, {})
                truth_class = None
                if crit_meta.get("truth_class"):
                    try:
                        truth_class = TruthClass(crit_meta["truth_class"])
                    except (ValueError, TypeError):
                        pass

                breakdown[crit.id] = CriterionScoreBreakdown(
                    criterion_id=crit.id,
                    criterion_name=crit.name,
                    raw_value=raw_v,
                    unit=crit_meta.get("unit") or crit.unit,
                    is_missing=is_missing,
                    normalized_score=round(norm_score, 6),
                    weight=crit.weight,
                    normalized_weight=round(w_norm, 6),
                    weighted_contribution=round(contribution, 6),
                    evidence_id=crit_meta.get("evidence_id"),
                    truth_class=truth_class,
                    notes=f"Raw: {raw_v}, Norm: {round(norm_score, 4)}, W: {round(w_norm, 4)}",
                )

            ranked_list.append(
                RankedAlternative(
                    alternative_id=alt.id,
                    name=alt.name,
                    entity_id=alt.entity_id,
                    rank=0,  # Assigned in tie-breaking sort below
                    overall_score=round(overall_score, 6),
                    criteria_breakdown=breakdown,
                    missing_criteria=missing_crit_names,
                    uncertainty_notes=uncertainty_notes,
                    evidence_ids=ev_ids,
                )
            )

        # Step 6: Deterministic Ranking and Tie-Breaking
        # Sort key order:
        # 1. -round(overall_score, 6) (higher overall score first)
        # 2. -first criterion score (secondary criteria tie-break)
        # 3. alt.name (alphabetical ascending)
        # 4. alt.alternative_id (stable unique ID tie-break)
        c0_id = criteria[0].id if criteria else ""

        def sort_key(item: RankedAlternative) -> tuple[float, float, str, str]:
            c0_score = item.criteria_breakdown.get(c0_id).normalized_score if item.criteria_breakdown.get(c0_id) else 0.0
            return (
                -round(item.overall_score, 6),
                -round(c0_score, 6),
                item.name,
                item.alternative_id,
            )

        ranked_list.sort(key=sort_key)

        for i, item in enumerate(ranked_list):
            item.rank = i + 1

        # Step 7: Trade-off analysis and limitations
        trade_off_analysis = self._generate_trade_off_analysis(ranked_list, criteria)
        ranking_limitations = list(weight_notes)
        if any(item.missing_criteria for item in ranked_list):
            ranking_limitations.append(
                f"Missing observations handled via '{policy.value}'. Highly ranked alternatives may have missing indicators."
            )
        if len(feasible_alts) == 0 and len(infeasible_alts) > 0:
            ranking_limitations.append("All proposed alternatives failed hard constraints.")

        result = DecisionResult(
            decision_id=request.decision_id,
            objective=request.objective,
            scope=request.scope,
            evaluated_at=datetime.now(UTC),
            status="completed",
            alternatives_count=len(alternatives),
            feasible_count=len(ranked_list),
            infeasible_count=len(infeasible_alts),
            missing_data_policy=policy,
            feasible_alternatives=ranked_list,
            infeasible_alternatives=infeasible_alts,
            criteria=criteria,
            normalized_weights={k: round(v, 6) for k, v in norm_weights.items()},
            trade_off_analysis=trade_off_analysis,
            ranking_limitations=ranking_limitations,
            evidence_citations=all_cited_evidence,
        )

        # Step 8: Persist decision run if requested and repository is present
        if request.persist and self.repository and hasattr(self.repository, "persist_decision"):
            try:
                self.repository.persist_decision(result, request.model_dump())
            except Exception as e:
                # Log or note persistence limitation without failing the deterministic evaluation
                result.ranking_limitations.append(f"Persistence notice: {e}")

        return result

    # -------------------------------------------------------------------------
    # 6. Trade-Off Analysis
    # -------------------------------------------------------------------------

    def _generate_trade_off_analysis(
        self,
        ranked: list[RankedAlternative],
        criteria: list[DecisionCriterion],
    ) -> dict[str, Any]:
        """Produce an explainable, deterministic trade-off comparison between top alternatives."""
        if not ranked:
            return {"summary": "No feasible alternatives to compare."}

        top = ranked[0]
        analysis: dict[str, Any] = {
            "top_choice": {
                "id": top.alternative_id,
                "name": top.name,
                "score": top.overall_score,
            },
            "comparisons": [],
        }

        # Compare top alternative with subsequent alternatives
        for other in ranked[1:4]:  # Top 3 competitors
            advantages: list[str] = []
            disadvantages: list[str] = []

            for c in criteria:
                top_c = top.criteria_breakdown.get(c.id)
                oth_c = other.criteria_breakdown.get(c.id)
                if top_c and oth_c:
                    diff = top_c.normalized_score - oth_c.normalized_score
                    if diff > 0.05:
                        advantages.append(
                            f"Outperforms on '{c.name}' (+{round(diff, 2)} norm score)"
                        )
                    elif diff < -0.05:
                        disadvantages.append(
                            f"Lags behind on '{c.name}' ({round(diff, 2)} norm score)"
                        )

            analysis["comparisons"].append({
                "competitor_id": other.alternative_id,
                "competitor_name": other.name,
                "competitor_rank": other.rank,
                "score_delta": round(top.overall_score - other.overall_score, 4),
                "top_advantages": advantages,
                "top_disadvantages": disadvantages,
            })

        return analysis

    # -------------------------------------------------------------------------
    # 7. Bounded Sensitivity Analysis
    # -------------------------------------------------------------------------

    def run_sensitivity_analysis(
        self,
        request: DecisionRequest,
        delta_pct: float = 0.20,
        conn: psycopg.Connection | None = None,
    ) -> list[SensitivityVariation]:
        """Perform bounded one-at-a-time (OAT) weight sensitivity analysis.

        Varies each criterion weight by +delta_pct and -delta_pct, re-evaluates ranking,
        and identifies whether the top choice flips.
        """
        if delta_pct <= 0 or delta_pct > 1.0:
            raise ValueError("delta_pct must be in range (0.0, 1.0]")

        base_res = self.evaluate(request, conn=conn)
        if not base_res.feasible_alternatives:
            return []

        base_top = base_res.feasible_alternatives[0]
        variations: list[SensitivityVariation] = []

        for crit in request.criteria:
            orig_w = crit.weight

            # Test variations: +delta_pct and -delta_pct
            for factor, label in [(1.0 + delta_pct, f"+{int(delta_pct * 100)}%"), (max(0.0, 1.0 - delta_pct), f"-{int(delta_pct * 100)}%")]:
                modified_criteria = []
                for c in request.criteria:
                    c_copy = c.model_copy()
                    if c.id == crit.id:
                        c_copy.weight = round(orig_w * factor, 4)
                    modified_criteria.append(c_copy)

                mod_req = request.model_copy(update={"criteria": modified_criteria, "persist": False})
                mod_res = self.evaluate(mod_req, conn=conn)

                if mod_res.feasible_alternatives:
                    new_top = mod_res.feasible_alternatives[0]
                    rank_changed = new_top.alternative_id != base_top.alternative_id

                    variations.append(
                        SensitivityVariation(
                            criterion_id=crit.id,
                            criterion_name=f"{crit.name} ({label})",
                            original_weight=round(orig_w, 4),
                            varied_weight=round(orig_w * factor, 4),
                            top_alternative_id=new_top.alternative_id,
                            top_alternative_name=new_top.name,
                            top_alternative_score=new_top.overall_score,
                            rank_changed=rank_changed,
                            new_rankings=[
                                {"rank": a.rank, "id": a.alternative_id, "name": a.name, "score": a.overall_score}
                                for a in mod_res.feasible_alternatives
                            ],
                        )
                    )

        return variations
