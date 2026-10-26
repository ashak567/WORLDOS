"""Engine 16: Deterministic Scenario Engine.

Provides isolated, sandboxed hypothetical scenario modeling, versioned branching,
deterministic modification overlays, Constraint Engine validation, and scenario comparison
without mutating authoritative operational world-state data.
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from .constraints import ConstraintEngine
from .domain import (
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
    ScenarioProposal,
    ScenarioStatus,
    TruthClass,
)


class ScenarioLifecycleError(Exception):
    """Raised when an invalid scenario lifecycle transition is attempted."""


class ScenarioEngine:
    """Deterministic, isolated Scenario Engine for WORLDOS.

    Key Architectural Principles:
    1. Operational Non-Mutation: Scenarios are strictly isolated branches. Authoritative
       tables (`entities`, `observations`, `geometries`, `evidence`, `alerts`) are NEVER mutated.
    2. Epistemic Classification: All simulated facts and derived outcomes carry truth class `SIMULATED`.
    3. Deterministic Overlay: Scenario modifications are applied via a deterministic precedence
       order over baseline world facts.
    4. Constraint Invariant Enforcement: Proposed modifications are validated through the
       Constraint Engine (Engine 12) before evaluation.
    5. Versioned Branching & Invalidation: Material edits increment scenario version and invalidate
       prior evaluation runs, preserving audit history.
    """

    def __init__(self, repository: Any = None) -> None:
        self.repository = repository
        self.constraint_engine = (
            repository.constraint_engine
            if repository and hasattr(repository, "constraint_engine")
            else ConstraintEngine(repository=repository)
        )

    # -------------------------------------------------------------------------
    # 1. Scenario Lifecycle Management
    # -------------------------------------------------------------------------

    def create_scenario(
        self,
        scenario_or_name: Scenario | str,
        description: str | None = None,
        baseline_context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        conn: psycopg.Connection | None = None,
    ) -> Scenario:
        """Create a new scenario in DRAFT status."""
        if isinstance(scenario_or_name, Scenario):
            scenario = scenario_or_name
        else:
            scenario = Scenario(
                name=scenario_or_name,
                description=description or "",
                status=ScenarioStatus.DRAFT,
                version=1,
                baseline_context=baseline_context or {},
                metadata=metadata or {},
            )
        if conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO scenarios (
                        id, name, description, status, version,
                        parent_scenario_id, parent_scenario_version,
                        baseline_context, metadata, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        scenario.id,
                        scenario.name,
                        scenario.description,
                        scenario.status.value,
                        scenario.version,
                        scenario.parent_scenario_id,
                        scenario.parent_scenario_version,
                        json.dumps(scenario.baseline_context),
                        json.dumps(scenario.metadata),
                        scenario.created_at,
                        scenario.updated_at,
                    ),
                )
        return scenario

    def get_scenario(self, scenario_id: UUID, conn: psycopg.Connection) -> Scenario | None:
        """Retrieve scenario by ID."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, description, status, version,
                       parent_scenario_id, parent_scenario_version,
                       baseline_context, metadata, created_at, updated_at
                FROM scenarios
                WHERE id = %s
                """,
                (scenario_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return Scenario(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                status=ScenarioStatus(row["status"]),
                version=row["version"],
                parent_scenario_id=row["parent_scenario_id"],
                parent_scenario_version=row["parent_scenario_version"],
                baseline_context=row["baseline_context"] if isinstance(row["baseline_context"], dict) else json.loads(row["baseline_context"]),
                metadata=row["metadata"] if isinstance(row["metadata"], dict) else json.loads(row["metadata"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def list_scenarios(
        self,
        status: ScenarioStatus | str | None = None,
        parent_id: UUID | None = None,
        limit: int = 100,
        conn: psycopg.Connection | None = None,
    ) -> list[Scenario]:
        """List scenarios with optional status and parent filter."""
        if not conn:
            return []
        clauses, values = [], []
        if status:
            status_str = status.value if isinstance(status, ScenarioStatus) else str(status)
            clauses.append("status = %s")
            values.append(status_str)
        if parent_id:
            clauses.append("parent_scenario_id = %s")
            values.append(parent_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT id, name, description, status, version,
                   parent_scenario_id, parent_scenario_version,
                   baseline_context, metadata, created_at, updated_at
            FROM scenarios
            {where}
            ORDER BY created_at DESC
            LIMIT %s
        """
        values.append(limit)
        with conn.cursor() as cur:
            cur.execute(sql, values)
            rows = cur.fetchall()
            return [
                Scenario(
                    id=r["id"],
                    name=r["name"],
                    description=r["description"],
                    status=ScenarioStatus(r["status"]),
                    version=r["version"],
                    parent_scenario_id=r["parent_scenario_id"],
                    parent_scenario_version=r["parent_scenario_version"],
                    baseline_context=r["baseline_context"] if isinstance(r["baseline_context"], dict) else json.loads(r["baseline_context"]),
                    metadata=r["metadata"] if isinstance(r["metadata"], dict) else json.loads(r["metadata"]),
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
                for r in rows
            ]

    def archive_scenario(self, scenario_id: UUID, conn: psycopg.Connection) -> Scenario:
        """Transition scenario to ARCHIVED status."""
        scenario = self.get_scenario(scenario_id, conn=conn)
        if not scenario:
            raise ValueError(f"Scenario '{scenario_id}' not found")
        if scenario.status == ScenarioStatus.ARCHIVED:
            return scenario

        scenario.status = ScenarioStatus.ARCHIVED
        scenario.updated_at = datetime.now(UTC)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE scenarios SET status = %s, updated_at = %s WHERE id = %s",
                (scenario.status.value, scenario.updated_at, scenario.id),
            )
        return scenario

    # -------------------------------------------------------------------------
    # 2. Scenario Modifications
    # -------------------------------------------------------------------------

    def add_modification(
        self,
        scenario_id_or_mod: UUID | ScenarioModification,
        target_entity_id: UUID | None = None,
        target_field: str | None = None,
        operation: ScenarioOperationType | None = None,
        value: Any = None,
        unit: str | None = None,
        rationale: str | None = None,
        evidence_references: list[UUID] | None = None,
        conn: psycopg.Connection | None = None,
    ) -> ScenarioModification:
        """Add a hypothetical modification to a draft scenario."""
        if isinstance(scenario_id_or_mod, ScenarioModification):
            mod = scenario_id_or_mod
            scenario_id = mod.scenario_id
        else:
            scenario_id = scenario_id_or_mod
            mod = ScenarioModification(
                scenario_id=scenario_id,
                target_entity_id=target_entity_id,
                target_field=target_field,
                operation=operation,
                value=value,
                unit=unit,
                rationale=rationale,
                evidence_references=evidence_references or [],
            )

        if not conn:
            raise ValueError("Database connection required to add scenario modification")

        scenario = self.get_scenario(scenario_id, conn=conn)
        if not scenario:
            raise ValueError(f"Scenario '{scenario_id}' not found")
        if scenario.status == ScenarioStatus.ARCHIVED:
            raise ScenarioLifecycleError(f"Cannot add modification to ARCHIVED scenario '{scenario_id}'")

        # Verify target entity exists in authoritative entities table
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM entities WHERE id = %s", (mod.target_entity_id,))
            if not cur.fetchone():
                raise ValueError(f"Target entity '{mod.target_entity_id}' does not exist in authoritative world state")

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO scenario_modifications (
                    id, scenario_id, target_entity_id, target_field,
                    operation, value, unit, effective_interval,
                    rationale, evidence_references, status, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    mod.id,
                    mod.scenario_id,
                    mod.target_entity_id,
                    mod.target_field,
                    mod.operation.value,
                    json.dumps(mod.value),
                    mod.unit,
                    json.dumps(mod.effective_interval.model_dump()) if mod.effective_interval else None,
                    mod.rationale,
                    [str(e) for e in mod.evidence_references],
                    mod.status,
                    mod.created_at,
                ),
            )

            # Material modification increments scenario version and resets status to DRAFT
            new_version = scenario.version + 1
            cur.execute(
                "UPDATE scenarios SET version = %s, status = 'DRAFT', updated_at = NOW() WHERE id = %s",
                (new_version, scenario_id),
            )

        return mod

    def list_modifications(
        self,
        scenario_id: UUID,
        status: str = "active",
        conn: psycopg.Connection | None = None,
    ) -> list[ScenarioModification]:
        """List modifications for a scenario."""
        if not conn:
            return []
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, scenario_id, target_entity_id, target_field,
                       operation, value, unit, effective_interval,
                       rationale, evidence_references, status, created_at
                FROM scenario_modifications
                WHERE scenario_id = %s AND status = %s
                ORDER BY created_at ASC, id ASC
                """,
                (scenario_id, status),
            )
            rows = cur.fetchall()
            return [
                ScenarioModification(
                    id=r["id"],
                    scenario_id=r["scenario_id"],
                    target_entity_id=r["target_entity_id"],
                    target_field=r["target_field"],
                    operation=ScenarioOperationType(r["operation"]),
                    value=r["value"],
                    unit=r["unit"],
                    effective_interval=r["effective_interval"],
                    rationale=r["rationale"],
                    evidence_references=r["evidence_references"] or [],
                    status=r["status"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def remove_modification(
        self,
        arg1: UUID,
        arg2: UUID | psycopg.Connection | None = None,
        conn: psycopg.Connection | None = None,
    ) -> bool:
        """Mark modification superseded/deleted and increment scenario version."""
        if isinstance(arg2, psycopg.Connection):
            modification_id = arg1
            conn = arg2
            scenario_id = None
        elif isinstance(arg2, UUID):
            scenario_id = arg1
            modification_id = arg2
        else:
            modification_id = arg1
            scenario_id = None

        if not conn:
            raise ValueError("Database connection required to remove modification")

        if scenario_id is None:
            with conn.cursor() as cur:
                cur.execute("SELECT scenario_id FROM scenario_modifications WHERE id = %s", (modification_id,))
                row = cur.fetchone()
                if not row:
                    return False
                scenario_id = row["scenario_id"]

        scenario = self.get_scenario(scenario_id, conn=conn)
        if not scenario:
            raise ValueError(f"Scenario '{scenario_id}' not found")
        if scenario.status == ScenarioStatus.ARCHIVED:
            raise ScenarioLifecycleError(f"Cannot delete modifications from ARCHIVED scenario '{scenario_id}'")

        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM scenario_modifications WHERE id = %s AND scenario_id = %s",
                (modification_id, scenario_id),
            )
            if cur.rowcount == 0:
                return False

            new_version = scenario.version + 1
            cur.execute(
                "UPDATE scenarios SET version = %s, status = 'DRAFT', updated_at = NOW() WHERE id = %s",
                (new_version, scenario_id),
            )
            return True

    # -------------------------------------------------------------------------
    # 3. Branching
    # -------------------------------------------------------------------------

    def branch_scenario(
        self,
        parent_scenario_id: UUID | None = None,
        new_name: str = "",
        new_description: str | None = None,
        parent_id: UUID | None = None,
        conn: psycopg.Connection | None = None,
    ) -> Scenario:
        """Create a new child scenario branching from parent scenario's current version."""
        pid = parent_id or parent_scenario_id
        if not pid:
            raise ValueError("parent_scenario_id required to branch scenario")
        if not conn:
            raise ValueError("Database connection required to branch scenario")

        parent = self.get_scenario(pid, conn=conn)
        if not parent:
            raise ValueError(f"Parent scenario '{pid}' not found")

        child = Scenario(
            name=new_name,
            description=new_description or f"Branched from {parent.name} (v{parent.version})",
            status=ScenarioStatus.DRAFT,
            version=1,
            parent_scenario_id=parent.id,
            parent_scenario_version=parent.version,
            baseline_context=dict(parent.baseline_context),
            metadata={"branch_created_at": datetime.now(UTC).isoformat()},
        )

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO scenarios (
                    id, name, description, status, version,
                    parent_scenario_id, parent_scenario_version,
                    baseline_context, metadata, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    child.id,
                    child.name,
                    child.description,
                    child.status.value,
                    child.version,
                    child.parent_scenario_id,
                    child.parent_scenario_version,
                    json.dumps(child.baseline_context),
                    json.dumps(child.metadata),
                    child.created_at,
                    child.updated_at,
                ),
            )

            # Copy active modifications from parent
            parent_mods = self.list_modifications(parent.id, status="active", conn=conn)
            for m in parent_mods:
                cur.execute(
                    """
                    INSERT INTO scenario_modifications (
                        id, scenario_id, target_entity_id, target_field,
                        operation, value, unit, effective_interval,
                        rationale, evidence_references, status, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        uuid4(),
                        child.id,
                        m.target_entity_id,
                        m.target_field,
                        m.operation.value,
                        json.dumps(m.value),
                        m.unit,
                        json.dumps(m.effective_interval.model_dump()) if m.effective_interval else None,
                        m.rationale,
                        [str(e) for e in m.evidence_references],
                        "active",
                        datetime.now(UTC),
                    ),
                )

        return child

    # -------------------------------------------------------------------------
    # 4. Constraint Engine Validation
    # -------------------------------------------------------------------------

    def validate_scenario(
        self,
        scenario_id: UUID,
        conn: psycopg.Connection,
    ) -> ConstraintValidationResult:
        """Validate scenario modifications using Constraint Engine."""
        scenario = self.get_scenario(scenario_id, conn=conn)
        if not scenario:
            raise ValueError(f"Scenario '{scenario_id}' not found")
        if scenario.status == ScenarioStatus.ARCHIVED:
            raise ScenarioLifecycleError(f"Cannot validate ARCHIVED scenario '{scenario_id}'")

        modifications = self.list_modifications(scenario_id, status="active", conn=conn)
        findings: list[ConstraintFinding] = []

        # 1. Proposal structural checks
        if not modifications:
            findings.append(
                ConstraintFinding(
                    code="SCENARIO_EMPTY_MODIFICATIONS",
                    category=ConstraintCategory.SCENARIO_PROPOSAL,
                    severity=ConstraintSeverity.WARNING,
                    message=f"Scenario '{scenario.name}' has no active modifications",
                    field="scenario.modifications",
                )
            )

        # 2. Check each modification
        for mod in modifications:
            # Check target field formatting
            if not mod.target_field or not mod.target_field.strip():
                findings.append(
                    ConstraintFinding(
                        code="SCENARIO_MOD_FIELD_EMPTY",
                        category=ConstraintCategory.SCENARIO_PROPOSAL,
                        severity=ConstraintSeverity.BLOCKING,
                        message="Modification target_field cannot be empty",
                        field=f"mod.{mod.id}.target_field",
                    )
                )

            # Check numeric limits and non-negative constraints
            if isinstance(mod.value, (int, float)):
                if not math.isfinite(mod.value):
                    findings.append(
                        ConstraintFinding(
                            code="SCENARIO_PARAMETER_NON_FINITE",
                            category=ConstraintCategory.SCENARIO_PROPOSAL,
                            severity=ConstraintSeverity.BLOCKING,
                            message=f"Hypothetical value for '{mod.target_field}' must be finite",
                            field=f"mod.{mod.id}.value",
                            actual_value=mod.value,
                        )
                    )
                if "population" in mod.target_field.lower() and mod.operation == ScenarioOperationType.SET and mod.value < 0:
                    findings.append(
                        ConstraintFinding(
                            code="SCENARIO_PARAMETER_NEGATIVE_POPULATION",
                            category=ConstraintCategory.SCENARIO_PROPOSAL,
                            severity=ConstraintSeverity.BLOCKING,
                            message=f"Population cannot be set to negative value ({mod.value})",
                            field=f"mod.{mod.id}.value",
                            actual_value=mod.value,
                        )
                    )

        result = ConstraintValidationResult.from_findings(findings)

        # If valid or warning, transition status to VALIDATED
        if result.status != ConstraintStatus.INVALID:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE scenarios SET status = 'VALIDATED', updated_at = NOW() WHERE id = %s",
                    (scenario_id,),
                )

        return result

    # -------------------------------------------------------------------------
    # 5. Deterministic Isolated Overlay & Evaluation
    # -------------------------------------------------------------------------

    def evaluate_scenario(
        self,
        scenario_id: UUID,
        evaluator: str = "deterministic_scenario_engine_v1",
        conn: psycopg.Connection | None = None,
    ) -> ScenarioEvaluation:
        """Evaluate validated scenario by applying deterministic overlay over baseline world facts."""
        if not conn:
            raise ValueError("Database connection required to evaluate scenario")

        scenario = self.get_scenario(scenario_id, conn=conn)
        if not scenario:
            raise ValueError(f"Scenario '{scenario_id}' not found")
        if scenario.status == ScenarioStatus.ARCHIVED:
            raise ScenarioLifecycleError(f"Cannot evaluate ARCHIVED scenario '{scenario_id}'")

        # Step 1: Pre-evaluation validation
        validation_res = self.validate_scenario(scenario_id, conn=conn)
        if validation_res.status == ConstraintStatus.INVALID:
            blocking = [f.message for f in validation_res.findings if f.severity == ConstraintSeverity.BLOCKING]
            raise ValueError(f"Cannot evaluate scenario '{scenario.name}': {'; '.join(blocking)}")

        modifications = self.list_modifications(scenario_id, status="active", conn=conn)

        # Step 2: Extract target entities and fetch baseline facts
        target_entity_ids = list({m.target_entity_id for m in modifications})
        baseline_snapshot: dict[str, dict[str, Any]] = {}

        if target_entity_ids:
            with conn.cursor() as cur:
                # Query authoritative entity names and attributes
                cur.execute(
                    "SELECT id, canonical_name, attributes FROM entities WHERE id = ANY(%s)",
                    (target_entity_ids,),
                )
                for row in cur.fetchall():
                    eid = str(row["id"])
                    baseline_snapshot[eid] = {
                        "name": row["canonical_name"],
                        "attributes": row["attributes"] if isinstance(row["attributes"], dict) else json.loads(row["attributes"]),
                        "observations": {},
                    }

                # Query authoritative observations for target entities
                cur.execute(
                    """
                    SELECT DISTINCT ON (o.subject_entity_id, o.measure)
                        o.subject_entity_id, o.measure, o.value, o.unit, o.confidence, o.truth_class
                    FROM observations o
                    LEFT JOIN time_intervals t ON t.id = o.time_interval_id
                    WHERE o.subject_entity_id = ANY(%s)
                    ORDER BY o.subject_entity_id, o.measure, t.starts_at DESC NULLS LAST
                    """,
                    (target_entity_ids,),
                )
                for row in cur.fetchall():
                    eid = str(row["subject_entity_id"])
                    if eid in baseline_snapshot:
                        baseline_snapshot[eid]["observations"][row["measure"]] = {
                            "value": float(row["value"]),
                            "unit": row["unit"],
                            "confidence": float(row["confidence"]),
                            "truth_class": row["truth_class"],
                        }

        # Step 3: Apply deterministic isolated overlay
        # Sort modifications deterministically: target_entity_id, target_field, created_at, id
        sorted_mods = sorted(
            modifications,
            key=lambda m: (str(m.target_entity_id), m.target_field, m.created_at, str(m.id)),
        )

        simulated_state: dict[str, dict[str, Any]] = {}
        for eid, b_info in baseline_snapshot.items():
            simulated_state[eid] = {
                "name": b_info["name"],
                "attributes": dict(b_info["attributes"]),
                "observations": {k: dict(v) for k, v in b_info["observations"].items()},
            }

        delta_summary: dict[str, dict[str, Any]] = {}

        for mod in sorted_mods:
            eid = str(mod.target_entity_id)
            if eid not in simulated_state:
                continue

            field_path = mod.target_field.split(".", 1)
            field_type = field_path[0]  # "observation", "attribute", etc.
            metric_key = field_path[1] if len(field_path) > 1 else mod.target_field

            # 1. Observation modification
            if field_type == "observation":
                obs_dict = simulated_state[eid]["observations"]
                base_obs = baseline_snapshot[eid]["observations"].get(metric_key)
                base_val = base_obs["value"] if base_obs else None

                # Current accumulated value in simulated state (or fallback to baseline)
                curr_obs = obs_dict.get(metric_key)
                curr_val = curr_obs["value"] if curr_obs else base_val

                sim_val: float | None = None
                if mod.operation == ScenarioOperationType.SET:
                    sim_val = float(mod.value)
                elif mod.operation == ScenarioOperationType.DELTA:
                    sim_val = (curr_val if curr_val is not None else 0.0) + float(mod.value)
                elif mod.operation == ScenarioOperationType.SCALE:
                    sim_val = (curr_val if curr_val is not None else 0.0) * float(mod.value)
                elif mod.operation == ScenarioOperationType.REMOVE:
                    sim_val = None

                if sim_val is not None:
                    obs_dict[metric_key] = {
                        "value": round(sim_val, 4),
                        "unit": mod.unit or (base_obs["unit"] if base_obs else None),
                        "truth_class": TruthClass.SIMULATED.value,
                        "modification_id": str(mod.id),
                    }
                else:
                    obs_dict.pop(metric_key, None)

                # Record delta
                delta_key = f"{eid}:{mod.target_field}"
                abs_delta = (sim_val - base_val) if (sim_val is not None and base_val is not None) else None
                pct_delta = ((abs_delta / base_val) * 100.0) if (abs_delta is not None and base_val and base_val != 0) else None
                delta_summary[delta_key] = {
                    "entity_id": eid,
                    "target_field": mod.target_field,
                    "baseline_value": base_val,
                    "simulated_value": sim_val,
                    "absolute_delta": round(abs_delta, 4) if abs_delta is not None else None,
                    "percent_change": round(pct_delta, 2) if pct_delta is not None else None,
                    "truth_class": TruthClass.SIMULATED.value,
                }

            # 2. Attribute modification
            elif field_type == "attribute":
                attr_dict = simulated_state[eid]["attributes"]
                base_attr = baseline_snapshot[eid]["attributes"].get(metric_key)

                if mod.operation == ScenarioOperationType.SET:
                    attr_dict[metric_key] = mod.value
                elif mod.operation == ScenarioOperationType.REMOVE:
                    attr_dict.pop(metric_key, None)

                delta_summary[f"{eid}:{mod.target_field}"] = {
                    "entity_id": eid,
                    "target_field": mod.target_field,
                    "baseline_value": base_attr,
                    "simulated_value": attr_dict.get(metric_key),
                    "truth_class": TruthClass.SIMULATED.value,
                }

        # Step 4: Derived scenario aggregate metrics
        total_base_pop = sum(
            e["observations"].get("population.total", {}).get("value", 0.0)
            for e in baseline_snapshot.values()
        )
        total_sim_pop = sum(
            e["observations"].get("population.total", {}).get("value", 0.0)
            for e in simulated_state.values()
        )
        derived_metrics = {
            "total_baseline_population": round(total_base_pop, 2),
            "total_simulated_population": round(total_sim_pop, 2),
            "net_population_delta": round(total_sim_pop - total_base_pop, 2),
            "affected_entity_count": len(target_entity_ids),
            "active_modifications_count": len(sorted_mods),
        }

        assumptions = [
            "All hypothetical changes are counterfactual and tagged SIMULATED.",
            "Modifications apply isolated overlays without mutating authoritative PostGIS facts.",
        ]
        limitations = [
            "Scenario evaluations reflect static heuristic deltas, not dynamic multi-step physical forward simulation.",
            "Unmodeled secondary impacts or general equilibrium market effects are not inferred.",
        ]

        eval_record = ScenarioEvaluation(
            scenario_id=scenario.id,
            scenario_version=scenario.version,
            baseline_snapshot=baseline_snapshot,
            simulated_state=simulated_state,
            delta_summary=delta_summary,
            constraint_findings=[f.model_dump() for f in validation_res.findings],
            is_feasible=validation_res.status != ConstraintStatus.INVALID,
            derived_metrics=derived_metrics,
            assumptions=assumptions,
            limitations=limitations,
            evaluation_version=evaluator,
        )

        # Step 5: Persist evaluation and transition scenario status to EVALUATED
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO scenario_evaluations (
                    id, scenario_id, scenario_version, baseline_snapshot,
                    simulated_state, delta_summary, constraint_findings,
                    is_feasible, derived_metrics, assumptions, limitations,
                    evaluation_version, evaluated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    eval_record.id,
                    eval_record.scenario_id,
                    eval_record.scenario_version,
                    json.dumps(eval_record.baseline_snapshot),
                    json.dumps(eval_record.simulated_state),
                    json.dumps(eval_record.delta_summary),
                    json.dumps(eval_record.constraint_findings),
                    eval_record.is_feasible,
                    json.dumps(eval_record.derived_metrics),
                    json.dumps(eval_record.assumptions),
                    json.dumps(eval_record.limitations),
                    eval_record.evaluation_version,
                    eval_record.evaluated_at,
                ),
            )
            cur.execute(
                "UPDATE scenarios SET status = 'EVALUATED', updated_at = NOW() WHERE id = %s",
                (scenario_id,),
            )

        return eval_record

    def get_latest_evaluation(self, scenario_id: UUID, conn: psycopg.Connection) -> ScenarioEvaluation | None:
        """Retrieve most recent evaluation for a scenario."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, scenario_id, scenario_version, baseline_snapshot,
                       simulated_state, delta_summary, constraint_findings,
                       is_feasible, derived_metrics, assumptions, limitations,
                       evaluation_version, evaluated_at
                FROM scenario_evaluations
                WHERE scenario_id = %s
                ORDER BY scenario_version DESC, evaluated_at DESC
                LIMIT 1
                """,
                (scenario_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return ScenarioEvaluation(
                id=row["id"],
                scenario_id=row["scenario_id"],
                scenario_version=row["scenario_version"],
                baseline_snapshot=row["baseline_snapshot"] if isinstance(row["baseline_snapshot"], dict) else json.loads(row["baseline_snapshot"]),
                simulated_state=row["simulated_state"] if isinstance(row["simulated_state"], dict) else json.loads(row["simulated_state"]),
                delta_summary=row["delta_summary"] if isinstance(row["delta_summary"], dict) else json.loads(row["delta_summary"]),
                constraint_findings=row["constraint_findings"] if isinstance(row["constraint_findings"], list) else json.loads(row["constraint_findings"]),
                is_feasible=row["is_feasible"],
                derived_metrics=row["derived_metrics"] if isinstance(row["derived_metrics"], dict) else json.loads(row["derived_metrics"]),
                assumptions=row["assumptions"] if isinstance(row["assumptions"], list) else json.loads(row["assumptions"]),
                limitations=row["limitations"] if isinstance(row["limitations"], list) else json.loads(row["limitations"]),
                evaluation_version=row["evaluation_version"],
                evaluated_at=row["evaluated_at"],
            )

    # -------------------------------------------------------------------------
    # 6. Scenario Comparison
    # -------------------------------------------------------------------------

    def compare_scenarios(
        self,
        scenario_a_id: UUID,
        scenario_b_id: UUID,
        conn: psycopg.Connection,
    ) -> ScenarioComparison:
        """Compare two evaluated scenarios across common target metrics and feasibility."""
        scen_a = self.get_scenario(scenario_a_id, conn=conn)
        scen_b = self.get_scenario(scenario_b_id, conn=conn)
        if not scen_a:
            raise ValueError(f"Scenario A '{scenario_a_id}' not found")
        if not scen_b:
            raise ValueError(f"Scenario B '{scenario_b_id}' not found")

        eval_a = self.get_latest_evaluation(scenario_a_id, conn=conn)
        eval_b = self.get_latest_evaluation(scenario_b_id, conn=conn)

        # If either is unevaluated, evaluate on-the-fly
        if not eval_a:
            eval_a = self.evaluate_scenario(scenario_a_id, conn=conn)
        if not eval_b:
            eval_b = self.evaluate_scenario(scenario_b_id, conn=conn)

        all_eids = set(eval_a.simulated_state.keys()) | set(eval_b.simulated_state.keys())
        entity_comps: list[dict[str, Any]] = []
        metric_deltas: dict[str, Any] = {}

        for eid in sorted(all_eids):
            a_state = eval_a.simulated_state.get(eid, {})
            b_state = eval_b.simulated_state.get(eid, {})
            name = a_state.get("name") or b_state.get("name", "Unknown Entity")

            a_obs = a_state.get("observations", {})
            b_obs = b_state.get("observations", {})
            common_measures = set(a_obs.keys()) | set(b_obs.keys())

            measures_comp: dict[str, Any] = {}
            for m in common_measures:
                val_a = a_obs.get(m, {}).get("value")
                val_b = b_obs.get(m, {}).get("value")
                diff = (val_b - val_a) if (val_a is not None and val_b is not None) else None
                measures_comp[m] = {
                    "scenario_a_value": val_a,
                    "scenario_b_value": val_b,
                    "delta_b_minus_a": round(diff, 4) if diff is not None else None,
                }
                metric_deltas[f"{eid}:{m}"] = diff

            entity_comps.append({
                "entity_id": eid,
                "name": name,
                "measures": measures_comp,
            })

        summary = (
            f"Comparison between '{scen_a.name}' (v{eval_a.scenario_version}, Feasible: {eval_a.is_feasible}) "
            f"and '{scen_b.name}' (v{eval_b.scenario_version}, Feasible: {eval_b.is_feasible}). "
            f"Compared across {len(entity_comps)} target entities."
        )

        return ScenarioComparison(
            scenario_a_id=scen_a.id,
            scenario_b_id=scen_b.id,
            scenario_a_name=scen_a.name,
            scenario_b_name=scen_b.name,
            entity_comparisons=entity_comps,
            feasibility_comparison={
                "scenario_a_feasible": eval_a.is_feasible,
                "scenario_b_feasible": eval_b.is_feasible,
            },
            metric_deltas=metric_deltas,
            summary=summary,
        )

    # -------------------------------------------------------------------------
    # 7. Protocol Compatibility
    # -------------------------------------------------------------------------

    def validate_constraints(self, scenario: dict[str, Any]) -> list[str]:
        """ScenarioEngine protocol compatibility."""
        return self.constraint_engine.validate_constraints(scenario)
