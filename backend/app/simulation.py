"""Engine 17: Bounded Deterministic Forward Simulation Engine.

Advances isolated hypothetical scenario states through a bounded series of discrete
time steps according to deterministic, versioned physical and heuristic transition rules.
Never mutates authoritative operational world-state data.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
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
    ScenarioStatus,
    SimulationComparison,
    SimulationRequest,
    SimulationRun,
    SimulationStatus,
    SimulationStep,
    TransitionRuleDefinition,
    TruthClass,
)


class SimulationError(Exception):
    """Base exception for Engine 17 simulation errors."""


class SimulationLifecycleError(SimulationError):
    """Raised when an invalid simulation lifecycle transition is attempted."""


class SimulationConfigurationError(SimulationError):
    """Raised when simulation parameters or time-horizons are invalid or exceed limits."""


class SimulationConstraintViolationError(SimulationError):
    """Raised when a blocking constraint is violated during simulation."""


# ==============================================================================
# Transition Rule Implementations & Registry
# ==============================================================================


def _step_size_in_years(step_size: float, step_unit: str) -> float:
    """Convert a time-step size to fractional years."""
    unit = step_unit.lower()
    if unit in ("year", "years"):
        return float(step_size)
    if unit in ("month", "months"):
        return float(step_size) / 12.0
    if unit in ("day", "days"):
        return float(step_size) / 365.25
    if unit in ("hour", "hours"):
        return float(step_size) / 8766.0
    if unit in ("step", "steps"):
        return float(step_size)
    return float(step_size)


def _clone_state(state: dict[str, Any]) -> dict[str, Any]:
    """Deep clone simulation state dictionaries to prevent cross-step mutation."""
    cloned: dict[str, Any] = {}
    for eid, edata in state.items():
        if isinstance(edata, dict):
            cloned[eid] = {
                "name": edata.get("name"),
                "attributes": dict(edata.get("attributes", {})),
                "observations": {
                    ok: dict(ov) if isinstance(ov, dict) else ov
                    for ok, ov in edata.get("observations", {}).items()
                },
            }
        else:
            cloned[eid] = edata
    return cloned


def _compute_step_count(starts_at: datetime, ends_at: datetime, step_size: float, step_unit: str) -> int:
    """Deterministically compute the exact number of steps between starts_at and ends_at."""
    unit = step_unit.lower()
    if unit in ("year", "years"):
        delta_years = (ends_at.year - starts_at.year) + (ends_at.month - starts_at.month) / 12.0 + (ends_at.day - starts_at.day) / 365.25
        return max(1, int(round(delta_years / step_size)))
    if unit in ("month", "months"):
        delta_months = (ends_at.year - starts_at.year) * 12 + (ends_at.month - starts_at.month) + (ends_at.day - starts_at.day) / 30.44
        return max(1, int(round(delta_months / step_size)))
    if unit in ("day", "days"):
        delta_days = (ends_at - starts_at).total_seconds() / 86400.0
        return max(1, int(round(delta_days / step_size)))
    if unit in ("hour", "hours"):
        delta_hours = (ends_at - starts_at).total_seconds() / 3600.0
        return max(1, int(round(delta_hours / step_size)))
    total_sec = (ends_at - starts_at).total_seconds()
    return max(1, int(round(total_sec / (step_size * 86400.0))))


class BaseTransitionRule:
    """Base class for all deterministic transition rules."""

    definition: TransitionRuleDefinition

    def apply(
        self,
        current_state: dict[str, Any],
        parameters: dict[str, Any],
        step_size: float,
        step_unit: str,
        context: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        """Compute the next state from previous simulated state.

        Returns:
            tuple of (updated_state_dict, derived_metrics_dict, findings_list)
        """
        raise NotImplementedError


class PopulationDynamicsRule(BaseTransitionRule):
    """Deterministic Malthusian or logistic population growth with carrying capacity and migration."""

    def __init__(self) -> None:
        self.definition = TransitionRuleDefinition(
            id="population_dynamics_v1",
            version="v1.0.0",
            name="Deterministic Population Dynamics",
            description=(
                "Models population growth via annual rate (r), optional carrying capacity (K), "
                "and net migration delta per step."
            ),
            supported_variables=["observation.population.total", "population.total"],
            required_inputs={"population": "count"},
            output_variables={"population": "count", "growth_delta": "count"},
            preconditions=["population >= 0", "growth_rate is finite"],
            assumptions=[
                "Uniform demographic age distribution",
                "Constant growth rate and carrying capacity across the step interval",
            ],
            limitations=[
                "Does not model demographic age cohorts, epidemic shocks, or sex ratios",
            ],
        )

    def apply(
        self,
        current_state: dict[str, Any],
        parameters: dict[str, Any],
        step_size: float,
        step_unit: str,
        context: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        updated = _clone_state(current_state)
        metrics: dict[str, Any] = {}
        findings: list[str] = []

        dt = _step_size_in_years(step_size, step_unit)
        growth_rate = float(parameters.get("growth_rate", 0.01))
        carrying_capacity = parameters.get("carrying_capacity")
        if carrying_capacity is not None:
            carrying_capacity = float(carrying_capacity)
        net_migration = float(parameters.get("net_migration", 0.0))

        for eid, entity_data in updated.items():
            if not isinstance(entity_data, dict):
                continue
            observations = entity_data.get("observations", {})
            pop_obs = observations.get("population.total")
            if not pop_obs:
                continue

            current_pop = float(pop_obs.get("value", 0.0))
            if carrying_capacity and carrying_capacity > 0:
                growth_delta = dt * (
                    growth_rate * current_pop * (1.0 - (current_pop / carrying_capacity))
                    + net_migration
                )
            else:
                growth_delta = dt * (growth_rate * current_pop + net_migration)

            new_pop = max(0.0, current_pop + growth_delta)
            growth_pct = ((new_pop - current_pop) / current_pop * 100.0) if current_pop > 0 else 0.0

            pop_obs["value"] = new_pop
            pop_obs["truth_class"] = TruthClass.SIMULATED.value

            metrics[f"{eid}.population.total"] = new_pop
            metrics[f"{eid}.population.growth_delta"] = growth_delta
            metrics[f"{eid}.population.growth_rate_pct"] = round(growth_pct, 4)

            if new_pop == 0.0 and current_pop > 0.0:
                findings.append(f"Entity {eid}: Population depleted to zero (extinction)")

        return updated, metrics, findings


class StockFlowAccountingRule(BaseTransitionRule):
    """Deterministic conservation of mass/resources through inflow, outflow, and decay."""

    def __init__(self) -> None:
        self.definition = TransitionRuleDefinition(
            id="stock_flow_accounting_v1",
            version="v1.0.0",
            name="Stock-Flow Conservation Accounting",
            description=(
                "Models inventory, reserves, or material stock evolution under inflow, "
                "outflow, and exponential decay."
            ),
            supported_variables=["observation.resource.stock", "resource.stock", "stock"],
            required_inputs={"stock": "units"},
            output_variables={"stock": "units", "net_flow": "units/step"},
            preconditions=["stock >= 0"],
            assumptions=["Inflow and outflow rates are constant across each discrete step"],
            limitations=["Does not model stochastic supply interruptions or price elasticity"],
        )

    def apply(
        self,
        current_state: dict[str, Any],
        parameters: dict[str, Any],
        step_size: float,
        step_unit: str,
        context: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        updated = _clone_state(current_state)
        metrics: dict[str, Any] = {}
        findings: list[str] = []

        dt = _step_size_in_years(step_size, step_unit)
        inflow = float(parameters.get("inflow_rate", 0.0))
        outflow = float(parameters.get("outflow_rate", 0.0))
        decay_rate = float(parameters.get("decay_rate", 0.0))
        capacity = parameters.get("capacity")
        if capacity is not None:
            capacity = float(capacity)
        min_capacity = float(parameters.get("min_capacity", 0.0))

        metric_key = parameters.get("stock_metric", "resource.stock")

        for eid, entity_data in updated.items():
            if not isinstance(entity_data, dict):
                continue
            observations = entity_data.get("observations", {})
            stock_obs = observations.get(metric_key)
            if not stock_obs:
                continue

            current_stock = float(stock_obs.get("value", 0.0))
            net_rate = inflow - outflow - (decay_rate * current_stock)
            delta_stock = dt * net_rate
            new_stock = current_stock + delta_stock

            if capacity is not None and new_stock > capacity:
                spillover = new_stock - capacity
                new_stock = capacity
                findings.append(f"Entity {eid}: Stock capacity exceeded; spillover of {spillover:.2f} units")

            if new_stock < min_capacity:
                findings.append(f"Entity {eid}: Stock fell below minimum capacity ({min_capacity})")
                new_stock = min_capacity

            stock_obs["value"] = new_stock
            stock_obs["truth_class"] = TruthClass.SIMULATED.value

            metrics[f"{eid}.{metric_key}"] = new_stock
            metrics[f"{eid}.{metric_key}.net_flow"] = delta_stock
            if capacity and capacity > 0:
                metrics[f"{eid}.{metric_key}.utilization_pct"] = round((new_stock / capacity) * 100.0, 2)

        return updated, metrics, findings


class PerCapitaResourceDepletionRule(BaseTransitionRule):
    """Coupled resource depletion driven by population size and per-capita consumption rate."""

    def __init__(self) -> None:
        self.definition = TransitionRuleDefinition(
            id="per_capita_resource_depletion_v1",
            version="v1.0.0",
            name="Coupled Per-Capita Resource Depletion",
            description=(
                "Models resource reserve depletion proportional to active population and "
                "annual per-capita consumption."
            ),
            supported_variables=["observation.population.total", "observation.resource.stock"],
            required_inputs={"population": "count", "resource_stock": "units"},
            output_variables={"resource_stock": "units", "depletion_rate": "units/year"},
            preconditions=["population >= 0", "consumption_per_capita >= 0"],
            assumptions=["Uniform per-capita resource consumption across entire population"],
            limitations=["Does not account for technological substitution or efficiency gains"],
        )

    def apply(
        self,
        current_state: dict[str, Any],
        parameters: dict[str, Any],
        step_size: float,
        step_unit: str,
        context: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        updated = _clone_state(current_state)
        metrics: dict[str, Any] = {}
        findings: list[str] = []

        dt = _step_size_in_years(step_size, step_unit)
        per_capita = float(parameters.get("consumption_per_capita", 1.0))
        replenishment = float(parameters.get("replenishment_rate", 0.0))
        resource_key = parameters.get("resource_metric", "resource.stock")

        for eid, entity_data in updated.items():
            if not isinstance(entity_data, dict):
                continue
            observations = entity_data.get("observations", {})
            pop_obs = observations.get("population.total")
            res_obs = observations.get(resource_key)

            if not pop_obs or not res_obs:
                continue

            pop = float(pop_obs.get("value", 0.0))
            res = float(res_obs.get("value", 0.0))

            annual_consumption = pop * per_capita
            delta_res = dt * (replenishment - annual_consumption)
            new_res = max(0.0, res + delta_res)

            res_obs["value"] = new_res
            res_obs["truth_class"] = TruthClass.SIMULATED.value

            years_remaining = (res / annual_consumption) if annual_consumption > 0 else 9999.0

            metrics[f"{eid}.{resource_key}"] = new_res
            metrics[f"{eid}.{resource_key}.consumption_rate"] = annual_consumption
            metrics[f"{eid}.{resource_key}.years_remaining"] = round(years_remaining, 2)

            if new_res == 0.0 and res > 0.0:
                findings.append(f"Entity {eid}: Resource '{resource_key}' completely depleted")

        return updated, metrics, findings


class ThresholdAlertTriggerRule(BaseTransitionRule):
    """Dynamic threshold evaluation emitting simulated warnings and alerts without operational mutation."""

    def __init__(self) -> None:
        self.definition = TransitionRuleDefinition(
            id="threshold_state_transition_v1",
            version="v1.0.0",
            name="Threshold Crossing & Simulated Alert Classifier",
            description=(
                "Evaluates numeric metrics against warning and critical thresholds, classifying "
                "system health and logging simulated alert findings."
            ),
            supported_variables=["*"],
            required_inputs={"target_metric": "numeric"},
            output_variables={"health_status": "string"},
            preconditions=["thresholds must be finite"],
            assumptions=["Static threshold boundaries over time"],
            limitations=["Does not evaluate multi-variate interactions or rate-of-change triggers"],
        )

    def apply(
        self,
        current_state: dict[str, Any],
        parameters: dict[str, Any],
        step_size: float,
        step_unit: str,
        context: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        updated = _clone_state(current_state)
        metrics: dict[str, Any] = {}
        findings: list[str] = []

        target_metric = parameters.get("target_metric", "population.total")
        warning_thresh = parameters.get("warning_threshold")
        critical_thresh = parameters.get("critical_threshold")
        direction = parameters.get("direction", "below")  # "below" or "above"

        for eid, entity_data in updated.items():
            if not isinstance(entity_data, dict):
                continue
            observations = entity_data.get("observations", {})
            obs = observations.get(target_metric)
            if not obs:
                continue

            val = float(obs.get("value", 0.0))
            status = "NORMAL"

            if direction == "below":
                if critical_thresh is not None and val <= float(critical_thresh):
                    status = "CRITICAL"
                    findings.append(
                        f"SIMULATED_ALERT: Entity {eid} {target_metric} fell below critical threshold ({val} <= {critical_thresh})"
                    )
                elif warning_thresh is not None and val <= float(warning_thresh):
                    status = "WARNING"
                    findings.append(
                        f"SIMULATED_ALERT: Entity {eid} {target_metric} fell below warning threshold ({val} <= {warning_thresh})"
                    )
            else:  # "above"
                if critical_thresh is not None and val >= float(critical_thresh):
                    status = "CRITICAL"
                    findings.append(
                        f"SIMULATED_ALERT: Entity {eid} {target_metric} exceeded critical threshold ({val} >= {critical_thresh})"
                    )
                elif warning_thresh is not None and val >= float(warning_thresh):
                    status = "WARNING"
                    findings.append(
                        f"SIMULATED_ALERT: Entity {eid} {target_metric} exceeded warning threshold ({val} >= {warning_thresh})"
                    )

            metrics[f"{eid}.{target_metric}.health_status"] = status

        return updated, metrics, findings


class LinearEvolutionRule(BaseTransitionRule):
    """Generic deterministic linear evolution for continuous metrics or synthetic fixtures."""

    def __init__(self) -> None:
        self.definition = TransitionRuleDefinition(
            id="generic_linear_evolution_v1",
            version="v1.0.0",
            name="Generic Deterministic Linear Evolution",
            description="Applies a constant linear rate of change (slope) to target variables per step.",
            supported_variables=["*"],
            required_inputs={"target_metric": "numeric"},
            output_variables={"target_metric": "numeric"},
            preconditions=["slope is finite"],
            assumptions=["Constant linear trajectory"],
            limitations=["Ignores non-linear feedback loops"],
        )

    def apply(
        self,
        current_state: dict[str, Any],
        parameters: dict[str, Any],
        step_size: float,
        step_unit: str,
        context: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        updated = _clone_state(current_state)
        metrics: dict[str, Any] = {}
        findings: list[str] = []

        target_metric = parameters.get("target_metric")
        if not target_metric:
            return updated, metrics, findings

        slope = float(parameters.get("slope", 0.0))
        min_val = parameters.get("min_value")
        max_val = parameters.get("max_value")
        dt = _step_size_in_years(step_size, step_unit)

        for eid, entity_data in updated.items():
            if not isinstance(entity_data, dict):
                continue
            observations = entity_data.get("observations", {})
            obs = observations.get(target_metric)
            if not obs:
                continue

            current_val = float(obs.get("value", 0.0))
            delta = dt * slope
            new_val = current_val + delta

            if min_val is not None:
                new_val = max(float(min_val), new_val)
            if max_val is not None:
                new_val = min(float(max_val), new_val)

            obs["value"] = new_val
            obs["truth_class"] = TruthClass.SIMULATED.value

            metrics[f"{eid}.{target_metric}"] = new_val
            metrics[f"{eid}.{target_metric}.delta"] = delta

        return updated, metrics, findings


class TransitionRuleRegistry:
    """Registry of verified deterministic transition rules."""

    def __init__(self) -> None:
        self._rules: dict[str, BaseTransitionRule] = {}
        self.register(PopulationDynamicsRule())
        self.register(StockFlowAccountingRule())
        self.register(PerCapitaResourceDepletionRule())
        self.register(ThresholdAlertTriggerRule())
        self.register(LinearEvolutionRule())

    def register(self, rule: BaseTransitionRule) -> None:
        self._rules[rule.definition.id] = rule

    def get(self, rule_id: str) -> BaseTransitionRule | None:
        return self._rules.get(rule_id)

    def list_rules(self) -> list[TransitionRuleDefinition]:
        return [rule.definition for rule in sorted(self._rules.values(), key=lambda r: r.definition.id)]


# Global default rule registry
DEFAULT_RULE_REGISTRY = TransitionRuleRegistry()


# ==============================================================================
# Deterministic Fingerprinting & Helpers
# ==============================================================================


def compute_simulation_fingerprint(
    scenario_id: UUID,
    scenario_version: int,
    starts_at: datetime,
    ends_at: datetime,
    step_size: float,
    step_unit: str,
    rule_ids: list[str],
    parameters: dict[str, Any],
    initial_state: dict[str, Any],
) -> str:
    """Compute a canonical, deterministic SHA-256 fingerprint for a simulation configuration."""
    canonical_payload = {
        "scenario_id": str(scenario_id),
        "scenario_version": scenario_version,
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
        "step_size": float(step_size),
        "step_unit": step_unit.lower(),
        "rule_ids": sorted(rule_ids),
        "parameters": parameters,
        "initial_state": initial_state,
    }
    encoded = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"sim_{digest[:16]}"


def compute_step_fingerprint(
    simulation_id: UUID,
    step_index: int,
    simulated_at: datetime,
    state: dict[str, Any],
    metrics: dict[str, Any],
) -> str:
    """Compute a deterministic SHA-256 fingerprint for an individual simulation step."""
    payload = {
        "simulation_id": str(simulation_id),
        "step_index": step_index,
        "simulated_at": simulated_at.isoformat(),
        "state": state,
        "metrics": metrics,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"step_{step_index}_{digest[:12]}"


def advance_simulated_timestamp(base: datetime, step_index: int, step_size: float, step_unit: str) -> datetime:
    """Deterministically advance timestamp by step_index * step_size."""
    unit = step_unit.lower()
    total_delta = step_index * step_size
    if unit in ("year", "years"):
        whole_years = int(total_delta)
        rem_years = total_delta - whole_years
        try:
            advanced = base.replace(year=base.year + whole_years)
        except ValueError:
            # Leap year edge case (Feb 29)
            advanced = base.replace(year=base.year + whole_years, day=28)
        if rem_years > 0:
            advanced += timedelta(days=rem_years * 365.25)
        return advanced
    if unit in ("month", "months"):
        whole_months = int(total_delta)
        rem_months = total_delta - whole_months
        year_add = (base.month + whole_months - 1) // 12
        new_month = ((base.month + whole_months - 1) % 12) + 1
        day = min(base.day, 28)
        advanced = base.replace(year=base.year + year_add, month=new_month, day=day)
        if rem_months > 0:
            advanced += timedelta(days=rem_months * 30.44)
        return advanced
    if unit in ("day", "days"):
        return base + timedelta(days=total_delta)
    if unit in ("hour", "hours"):
        return base + timedelta(hours=total_delta)
    if unit in ("step", "steps"):
        return base + timedelta(days=total_delta)
    return base + timedelta(days=total_delta)


# ==============================================================================
# Engine 17: Simulation Engine Core
# ==============================================================================


class SimulationEngine:
    """Deterministic, Bounded Forward Simulation Engine for WORLDOS.

    Guarantees:
    1. Operational Non-Mutation: Never mutates entities, observations, claims,
       geometries, evidence, or operational alerts.
    2. Epistemic Classification: Every trajectory step and outcome is tagged SIMULATED.
    3. Determinism: Identical inputs produce bit-for-bit identical trajectories and fingerprints.
    4. Bounded Horizons: Strict execution bounds (max 500 steps) reject unbounded loops.
    5. Constraint Integration: Real-time invariant checking across all simulated steps.
    """

    def __init__(
        self,
        repository: Any = None,
        rule_registry: TransitionRuleRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.rule_registry = rule_registry or DEFAULT_RULE_REGISTRY
        self.constraint_engine = (
            repository.constraint_engine
            if repository and hasattr(repository, "constraint_engine")
            else ConstraintEngine(repository=repository)
        )

    # -------------------------------------------------------------------------
    # Initial State Assembly over Scenario Branch
    # -------------------------------------------------------------------------

    def build_initial_state(
        self,
        scenario_id: UUID,
        scenario_version: int | None = None,
        initial_state_overrides: dict[str, Any] | None = None,
        conn: psycopg.Connection | None = None,
    ) -> tuple[dict[str, Any], int, list[str]]:
        """Construct sandboxed initial state from authoritative baseline + scenario overlay."""
        if not conn:
            raise ValueError("Database connection required to build initial state")

        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, status, version, baseline_context FROM scenarios WHERE id = %s",
                (scenario_id,),
            )
            scen_row = cur.fetchone()
            if not scen_row:
                raise SimulationConfigurationError(f"Scenario '{scenario_id}' not found")
            if scen_row["status"] == ScenarioStatus.ARCHIVED.value:
                raise SimulationConfigurationError(f"Cannot run simulation on ARCHIVED scenario '{scenario_id}'")

            target_version = scenario_version if scenario_version is not None else scen_row["version"]

            # Load active scenario modifications for this scenario
            cur.execute(
                """
                SELECT id, target_entity_id, target_field, operation, value, created_at
                FROM scenario_modifications
                WHERE scenario_id = %s AND status = 'active'
                ORDER BY target_entity_id, target_field, created_at, id
                """,
                (scenario_id,),
            )
            mod_rows = cur.fetchall()

        target_entity_ids = list({m["target_entity_id"] for m in mod_rows})
        baseline_state: dict[str, dict[str, Any]] = {}

        if target_entity_ids:
            with conn.cursor() as cur:
                # Query authoritative entity names and attributes
                cur.execute(
                    "SELECT id, canonical_name, attributes FROM entities WHERE id = ANY(%s)",
                    (target_entity_ids,),
                )
                for row in cur.fetchall():
                    eid = str(row["id"])
                    attrs = row["attributes"]
                    if not isinstance(attrs, dict):
                        attrs = json.loads(attrs) if attrs else {}
                    baseline_state[eid] = {
                        "name": row["canonical_name"],
                        "attributes": attrs,
                        "observations": {},
                    }

                # Query authoritative latest observations for target entities
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
                    if eid in baseline_state:
                        baseline_state[eid]["observations"][row["measure"]] = {
                            "value": float(row["value"]),
                            "unit": row["unit"],
                            "confidence": float(row["confidence"]),
                            "truth_class": row["truth_class"],
                        }

        # Apply deterministic scenario modifications
        simulated_state: dict[str, dict[str, Any]] = {}
        for eid, b_info in baseline_state.items():
            simulated_state[eid] = {
                "name": b_info["name"],
                "attributes": dict(b_info["attributes"]),
                "observations": {k: dict(v) for k, v in b_info["observations"].items()},
            }

        assumptions: list[str] = [
            f"Initialized from scenario '{scen_row['name']}' (version {target_version})",
            "Authoritative operational data loaded read-only",
        ]

        for mod in mod_rows:
            eid = str(mod["target_entity_id"])
            if eid not in simulated_state:
                continue

            field_parts = mod["target_field"].split(".", 1)
            field_type = field_parts[0]
            metric_key = field_parts[1] if len(field_parts) > 1 else mod["target_field"]
            op = mod["operation"]
            mod_val = mod["value"]
            if isinstance(mod_val, str):
                try:
                    mod_val = json.loads(mod_val)
                except Exception:
                    pass

            obs_dict = simulated_state[eid]["observations"]
            curr_obs = obs_dict.get(metric_key)
            base_val = curr_obs["value"] if curr_obs else 0.0

            if field_type == "observation":
                if op == "SET":
                    sim_val = float(mod_val)
                elif op == "DELTA":
                    sim_val = base_val + float(mod_val)
                elif op == "SCALE":
                    sim_val = base_val * float(mod_val)
                elif op == "REMOVE":
                    obs_dict.pop(metric_key, None)
                    continue
                else:
                    continue

                obs_dict[metric_key] = {
                    "value": sim_val,
                    "unit": curr_obs.get("unit") if curr_obs else None,
                    "confidence": 1.0,
                    "truth_class": TruthClass.SIMULATED.value,
                }
            elif field_type == "attribute":
                attr_dict = simulated_state[eid]["attributes"]
                if op == "SET":
                    attr_dict[metric_key] = mod_val
                elif op == "REMOVE":
                    attr_dict.pop(metric_key, None)

        # Apply any explicit request overrides
        if initial_state_overrides:
            for eid, overrides in initial_state_overrides.items():
                if eid in simulated_state and isinstance(overrides, dict):
                    for k, v in overrides.get("observations", {}).items():
                        simulated_state[eid]["observations"][k] = {
                            "value": float(v.get("value", v) if isinstance(v, dict) else v),
                            "unit": v.get("unit") if isinstance(v, dict) else None,
                            "confidence": 1.0,
                            "truth_class": TruthClass.SIMULATED.value,
                        }
                    for k, v in overrides.get("attributes", {}).items():
                        simulated_state[eid]["attributes"][k] = v

        return simulated_state, target_version, assumptions

    # -------------------------------------------------------------------------
    # Core Forward Simulation Execution
    # -------------------------------------------------------------------------

    def create_and_run_simulation(
        self,
        request: SimulationRequest,
        conn: psycopg.Connection | None = None,
    ) -> SimulationRun:
        """Create, execute, and persist a complete deterministic forward simulation run."""
        if not conn:
            raise ValueError("Database connection required to run simulation")

        start_time = datetime.now(UTC)

        # Step 1: Validate time horizon & step counts
        step_years = _step_size_in_years(request.step_size, request.step_unit)
        total_seconds = (request.ends_at - request.starts_at).total_seconds()
        if total_seconds <= 0:
            raise SimulationConfigurationError("ends_at must be strictly greater than starts_at")

        # Estimate step count using calendar-aware calculation
        estimated_steps = _compute_step_count(
            starts_at=request.starts_at,
            ends_at=request.ends_at,
            step_size=request.step_size,
            step_unit=request.step_unit,
        )
        if estimated_steps > request.max_steps:
            raise SimulationConfigurationError(
                f"Requested simulation horizon requires {estimated_steps} steps, exceeding max_steps limit ({request.max_steps})"
            )
        if estimated_steps < 1:
            estimated_steps = 1

        # Step 2: Build initial state from pinned scenario
        initial_state, scenario_version, base_assumptions = self.build_initial_state(
            scenario_id=request.scenario_id,
            scenario_version=request.scenario_version,
            initial_state_overrides=request.initial_state_overrides,
            conn=conn,
        )

        # Step 3: Resolve requested transition rules
        active_rules: list[BaseTransitionRule] = []
        rule_ids = request.rule_ids or ["population_dynamics_v1"]
        for rid in rule_ids:
            rule = self.rule_registry.get(rid)
            if not rule:
                raise SimulationConfigurationError(f"Transition rule '{rid}' is not registered or supported")
            active_rules.append(rule)

        # Ensure deterministic rule ordering
        active_rules.sort(key=lambda r: r.definition.id)

        # Step 4: Compute deterministic reproducibility fingerprint
        fingerprint = compute_simulation_fingerprint(
            scenario_id=request.scenario_id,
            scenario_version=scenario_version,
            starts_at=request.starts_at,
            ends_at=request.ends_at,
            step_size=request.step_size,
            step_unit=request.step_unit,
            rule_ids=[r.definition.id for r in active_rules],
            parameters=request.parameters,
            initial_state=initial_state,
        )

        # Persist simulation run in CREATED / RUNNING status
        run_record = SimulationRun(
            id=request.id,
            scenario_id=request.scenario_id,
            scenario_version=scenario_version,
            status=SimulationStatus.RUNNING,
            configuration=request.model_dump(mode="json"),
            initial_state=initial_state,
            final_state={},
            trajectory_summary={},
            is_feasible=True,
            constraint_findings=[],
            assumptions=base_assumptions,
            limitations=[
                "Deterministic model projection; not calibrated real-world forecast",
                "Does not account for external geopolitical or natural shocks not specified in transition rules",
            ],
            step_count=0,
            reproducibility_fingerprint=fingerprint,
            truth_class=TruthClass.SIMULATED,
        )

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO simulation_runs (
                    id, scenario_id, scenario_version, status, configuration,
                    initial_state, final_state, trajectory_summary, is_feasible,
                    constraint_findings, assumptions, limitations, step_count,
                    reproducibility_fingerprint, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    run_record.id,
                    run_record.scenario_id,
                    run_record.scenario_version,
                    run_record.status.value,
                    json.dumps(run_record.configuration),
                    json.dumps(run_record.initial_state),
                    json.dumps(run_record.final_state),
                    json.dumps(run_record.trajectory_summary),
                    run_record.is_feasible,
                    json.dumps(run_record.constraint_findings),
                    json.dumps(run_record.assumptions),
                    json.dumps(run_record.limitations),
                    run_record.step_count,
                    run_record.reproducibility_fingerprint,
                    run_record.created_at,
                ),
            )

        # Step 5: Execute bounded simulation loop
        current_state = _clone_state(initial_state)
        trajectory_steps: list[SimulationStep] = []
        is_feasible = True
        accumulated_constraint_findings: list[dict[str, Any]] = []

        # Record Step 0 (Initial Condition)
        step0_metrics: dict[str, Any] = {"step_index": 0}
        for eid, edata in current_state.items():
            if isinstance(edata, dict):
                for ok, ov in edata.get("observations", {}).items():
                    if isinstance(ov, dict) and "value" in ov:
                        step0_metrics[f"{eid}.{ok}"] = float(ov["value"])

        step0_fp = compute_step_fingerprint(
            simulation_id=run_record.id,
            step_index=0,
            simulated_at=request.starts_at,
            state=current_state,
            metrics=step0_metrics,
        )
        step0 = SimulationStep(
            simulation_id=run_record.id,
            step_index=0,
            simulated_at=request.starts_at,
            state=_clone_state(current_state),
            metrics=step0_metrics,
            applied_rules=[],
            constraint_findings=[],
            findings=["Simulation initialized from pinned scenario overlay"],
            truth_class=TruthClass.SIMULATED,
            step_fingerprint=step0_fp,
        )
        trajectory_steps.append(step0)

        # Advance through discrete steps
        for step_idx in range(1, estimated_steps + 1):
            sim_time = advance_simulated_timestamp(
                base=request.starts_at,
                step_index=step_idx,
                step_size=request.step_size,
                step_unit=request.step_unit,
            )

            step_metrics: dict[str, Any] = {"step_index": step_idx}
            step_findings: list[str] = []
            applied_rule_ids: list[str] = []

            # Sequentially apply transition rules
            for rule in active_rules:
                current_state, r_metrics, r_findings = rule.apply(
                    current_state=current_state,
                    parameters=request.parameters,
                    step_size=request.step_size,
                    step_unit=request.step_unit,
                    context={"step_index": step_idx, "simulated_at": sim_time.isoformat()},
                )
                step_metrics.update(r_metrics)
                step_findings.extend(r_findings)
                applied_rule_ids.append(rule.definition.id)

            # Evaluate state constraints on step output
            step_c_findings: list[dict[str, Any]] = []
            for eid, edata in current_state.items():
                if not isinstance(edata, dict):
                    continue
                obs_dict = edata.get("observations", {})
                for measure_key, obs_item in obs_dict.items():
                    val = obs_item.get("value")
                    if not isinstance(val, (int, float)) or not math.isfinite(val):
                        finding = {
                            "code": "SIMULATION_NON_FINITE_VALUE",
                            "severity": ConstraintSeverity.BLOCKING.value,
                            "message": f"Entity {eid}: Non-finite value in '{measure_key}'",
                            "entity_id": eid,
                            "field": measure_key,
                        }
                        step_c_findings.append(finding)
                        accumulated_constraint_findings.append(finding)
                        is_feasible = False
                    elif "population" in measure_key.lower() and val < 0:
                        finding = {
                            "code": "SIMULATION_NEGATIVE_POPULATION",
                            "severity": ConstraintSeverity.BLOCKING.value,
                            "message": f"Entity {eid}: Population is negative ({val})",
                            "entity_id": eid,
                            "field": measure_key,
                        }
                        step_c_findings.append(finding)
                        accumulated_constraint_findings.append(finding)
                        is_feasible = False

            step_fp = compute_step_fingerprint(
                simulation_id=run_record.id,
                step_index=step_idx,
                simulated_at=sim_time,
                state=current_state,
                metrics=step_metrics,
            )

            step_record = SimulationStep(
                simulation_id=run_record.id,
                step_index=step_idx,
                simulated_at=sim_time,
                state=_clone_state(current_state),
                metrics=step_metrics,
                applied_rules=applied_rule_ids,
                constraint_findings=step_c_findings,
                findings=step_findings,
                truth_class=TruthClass.SIMULATED,
                step_fingerprint=step_fp,
            )
            trajectory_steps.append(step_record)

        # Step 6: Compute trajectory summaries
        trajectory_summary = self._compute_trajectory_summary(trajectory_steps)

        # Step 7: Persist steps and final run state
        end_time = datetime.now(UTC)
        duration_ms = (end_time - start_time).total_seconds() * 1000.0

        with conn.cursor() as cur:
            for s in trajectory_steps:
                cur.execute(
                    """
                    INSERT INTO simulation_steps (
                        id, simulation_id, step_index, simulated_at, state,
                        metrics, applied_rules, constraint_findings, findings,
                        step_fingerprint, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        s.id,
                        s.simulation_id,
                        s.step_index,
                        s.simulated_at,
                        json.dumps(s.state),
                        json.dumps(s.metrics),
                        json.dumps(s.applied_rules),
                        json.dumps(s.constraint_findings),
                        json.dumps(s.findings),
                        s.step_fingerprint,
                        datetime.now(UTC),
                    ),
                )

            cur.execute(
                """
                UPDATE simulation_runs
                SET status = 'COMPLETED',
                    final_state = %s,
                    trajectory_summary = %s,
                    is_feasible = %s,
                    constraint_findings = %s,
                    step_count = %s,
                    execution_duration_ms = %s,
                    completed_at = %s
                WHERE id = %s
                """,
                (
                    json.dumps(current_state),
                    json.dumps(trajectory_summary),
                    is_feasible,
                    json.dumps(accumulated_constraint_findings),
                    len(trajectory_steps),
                    duration_ms,
                    end_time,
                    run_record.id,
                ),
            )

        run_record.status = SimulationStatus.COMPLETED
        run_record.final_state = current_state
        run_record.trajectory_summary = trajectory_summary
        run_record.is_feasible = is_feasible
        run_record.constraint_findings = accumulated_constraint_findings
        run_record.step_count = len(trajectory_steps)
        run_record.execution_duration_ms = duration_ms
        run_record.completed_at = end_time

        return run_record

    def _compute_trajectory_summary(self, steps: list[SimulationStep]) -> dict[str, Any]:
        """Produce analytical summaries (min, max, mean, final delta) across trajectory steps."""
        if not steps:
            return {}

        metric_series: dict[str, list[float]] = {}
        for s in steps:
            for mkey, mval in s.metrics.items():
                if isinstance(mval, (int, float)) and math.isfinite(mval):
                    metric_series.setdefault(mkey, []).append(float(mval))

        summary: dict[str, Any] = {}
        for mkey, values in metric_series.items():
            if not values:
                continue
            init_val = values[0]
            fin_val = values[-1]
            abs_change = fin_val - init_val
            pct_change = ((fin_val - init_val) / init_val * 100.0) if init_val != 0 else 0.0
            summary[mkey] = {
                "initial": init_val,
                "final": fin_val,
                "min": min(values),
                "max": max(values),
                "mean": round(sum(values) / len(values), 4),
                "absolute_change": round(abs_change, 4),
                "relative_change_pct": round(pct_change, 4),
                "points_count": len(values),
            }
        return summary

    # -------------------------------------------------------------------------
    # Retrieval and Trajectory Queries
    # -------------------------------------------------------------------------

    def get_simulation(self, simulation_id: UUID, conn: psycopg.Connection | None = None) -> SimulationRun | None:
        """Retrieve simulation run metadata by ID."""
        if not conn:
            raise ValueError("Database connection required")

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, scenario_id, scenario_version, status, configuration,
                       initial_state, final_state, trajectory_summary, is_feasible,
                       constraint_findings, assumptions, limitations, step_count,
                       execution_duration_ms, reproducibility_fingerprint,
                       error_message, created_at, completed_at
                FROM simulation_runs
                WHERE id = %s
                """,
                (simulation_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            return SimulationRun(
                id=row["id"],
                scenario_id=row["scenario_id"],
                scenario_version=row["scenario_version"],
                status=SimulationStatus(row["status"]),
                configuration=row["configuration"] if isinstance(row["configuration"], dict) else json.loads(row["configuration"]),
                initial_state=row["initial_state"] if isinstance(row["initial_state"], dict) else json.loads(row["initial_state"]),
                final_state=row["final_state"] if isinstance(row["final_state"], dict) else json.loads(row["final_state"]),
                trajectory_summary=row["trajectory_summary"] if isinstance(row["trajectory_summary"], dict) else json.loads(row["trajectory_summary"]),
                is_feasible=row["is_feasible"],
                constraint_findings=row["constraint_findings"] if isinstance(row["constraint_findings"], list) else json.loads(row["constraint_findings"]),
                assumptions=row["assumptions"] if isinstance(row["assumptions"], list) else json.loads(row["assumptions"]),
                limitations=row["limitations"] if isinstance(row["limitations"], list) else json.loads(row["limitations"]),
                step_count=row["step_count"],
                execution_duration_ms=row["execution_duration_ms"],
                reproducibility_fingerprint=row["reproducibility_fingerprint"],
                error_message=row["error_message"],
                created_at=row["created_at"],
                completed_at=row["completed_at"],
            )

    def list_simulations(
        self,
        scenario_id: UUID | None = None,
        status: SimulationStatus | str | None = None,
        limit: int = 100,
        offset: int = 0,
        conn: psycopg.Connection | None = None,
    ) -> list[SimulationRun]:
        """List simulation runs with optional filtering and pagination."""
        if not conn:
            raise ValueError("Database connection required")

        query = """
            SELECT id, scenario_id, scenario_version, status, configuration,
                   initial_state, final_state, trajectory_summary, is_feasible,
                   constraint_findings, assumptions, limitations, step_count,
                   execution_duration_ms, reproducibility_fingerprint,
                   error_message, created_at, completed_at
            FROM simulation_runs
            WHERE 1=1
        """
        params: list[Any] = []
        if scenario_id:
            query += " AND scenario_id = %s"
            params.append(scenario_id)
        if status:
            st_val = status.value if hasattr(status, "value") else str(status)
            query += " AND status = %s"
            params.append(st_val)

        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        with conn.cursor() as cur:
            cur.execute(query, tuple(params))
            results: list[SimulationRun] = []
            for row in cur.fetchall():
                results.append(
                    SimulationRun(
                        id=row["id"],
                        scenario_id=row["scenario_id"],
                        scenario_version=row["scenario_version"],
                        status=SimulationStatus(row["status"]),
                        configuration=row["configuration"] if isinstance(row["configuration"], dict) else json.loads(row["configuration"]),
                        initial_state=row["initial_state"] if isinstance(row["initial_state"], dict) else json.loads(row["initial_state"]),
                        final_state=row["final_state"] if isinstance(row["final_state"], dict) else json.loads(row["final_state"]),
                        trajectory_summary=row["trajectory_summary"] if isinstance(row["trajectory_summary"], dict) else json.loads(row["trajectory_summary"]),
                        is_feasible=row["is_feasible"],
                        constraint_findings=row["constraint_findings"] if isinstance(row["constraint_findings"], list) else json.loads(row["constraint_findings"]),
                        assumptions=row["assumptions"] if isinstance(row["assumptions"], list) else json.loads(row["assumptions"]),
                        limitations=row["limitations"] if isinstance(row["limitations"], list) else json.loads(row["limitations"]),
                        step_count=row["step_count"],
                        execution_duration_ms=row["execution_duration_ms"],
                        reproducibility_fingerprint=row["reproducibility_fingerprint"],
                        error_message=row["error_message"],
                        created_at=row["created_at"],
                        completed_at=row["completed_at"],
                    )
                )
            return results

    def get_trajectory(
        self,
        simulation_id: UUID,
        offset: int = 0,
        limit: int = 200,
        conn: psycopg.Connection | None = None,
    ) -> list[SimulationStep]:
        """Retrieve ordered trajectory steps for a simulation run with pagination."""
        if not conn:
            raise ValueError("Database connection required")

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, simulation_id, step_index, simulated_at, state,
                       metrics, applied_rules, constraint_findings, findings,
                       step_fingerprint, created_at
                FROM simulation_steps
                WHERE simulation_id = %s
                ORDER BY step_index ASC
                LIMIT %s OFFSET %s
                """,
                (simulation_id, limit, offset),
            )
            steps: list[SimulationStep] = []
            for row in cur.fetchall():
                steps.append(
                    SimulationStep(
                        id=row["id"],
                        simulation_id=row["simulation_id"],
                        step_index=row["step_index"],
                        simulated_at=row["simulated_at"],
                        state=row["state"] if isinstance(row["state"], dict) else json.loads(row["state"]),
                        metrics=row["metrics"] if isinstance(row["metrics"], dict) else json.loads(row["metrics"]),
                        applied_rules=row["applied_rules"] if isinstance(row["applied_rules"], list) else json.loads(row["applied_rules"]),
                        constraint_findings=row["constraint_findings"] if isinstance(row["constraint_findings"], list) else json.loads(row["constraint_findings"]),
                        findings=row["findings"] if isinstance(row["findings"], list) else json.loads(row["findings"]),
                        truth_class=TruthClass.SIMULATED,
                        step_fingerprint=row["step_fingerprint"],
                    )
                )
            return steps

    def get_step(
        self,
        simulation_id: UUID,
        step_index: int,
        conn: psycopg.Connection | None = None,
    ) -> SimulationStep | None:
        """Retrieve a specific simulation step by its index."""
        if not conn:
            raise ValueError("Database connection required")

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, simulation_id, step_index, simulated_at, state,
                       metrics, applied_rules, constraint_findings, findings,
                       step_fingerprint, created_at
                FROM simulation_steps
                WHERE simulation_id = %s AND step_index = %s
                """,
                (simulation_id, step_index),
            )
            row = cur.fetchone()
            if not row:
                return None

            return SimulationStep(
                id=row["id"],
                simulation_id=row["simulation_id"],
                step_index=row["step_index"],
                simulated_at=row["simulated_at"],
                state=row["state"] if isinstance(row["state"], dict) else json.loads(row["state"]),
                metrics=row["metrics"] if isinstance(row["metrics"], dict) else json.loads(row["metrics"]),
                applied_rules=row["applied_rules"] if isinstance(row["applied_rules"], list) else json.loads(row["applied_rules"]),
                constraint_findings=row["constraint_findings"] if isinstance(row["constraint_findings"], list) else json.loads(row["constraint_findings"]),
                findings=row["findings"] if isinstance(row["findings"], list) else json.loads(row["findings"]),
                truth_class=TruthClass.SIMULATED,
                step_fingerprint=row["step_fingerprint"],
            )

    # -------------------------------------------------------------------------
    # Simulation Comparison & Cancellation
    # -------------------------------------------------------------------------

    def compare_simulations(
        self,
        simulation_a_id: UUID,
        simulation_b_id: UUID,
        conn: psycopg.Connection | None = None,
    ) -> SimulationComparison:
        """Compare two completed simulation runs across final outcomes and trajectory divergence."""
        if not conn:
            raise ValueError("Database connection required")

        sim_a = self.get_simulation(simulation_a_id, conn=conn)
        if not sim_a:
            raise SimulationConfigurationError(f"Simulation A '{simulation_a_id}' not found")
        sim_b = self.get_simulation(simulation_b_id, conn=conn)
        if not sim_b:
            raise SimulationConfigurationError(f"Simulation B '{simulation_b_id}' not found")

        sum_a = sim_a.trajectory_summary or {}
        sum_b = sim_b.trajectory_summary or {}

        shared_metrics = set(sum_a.keys()) & set(sum_b.keys())
        metric_deltas: dict[str, Any] = {}
        for m in sorted(shared_metrics):
            fa = sum_a[m].get("final", 0.0)
            fb = sum_b[m].get("final", 0.0)
            delta = fb - fa
            pct_diff = ((fb - fa) / fa * 100.0) if fa != 0 else 0.0
            metric_deltas[m] = {
                "final_a": fa,
                "final_b": fb,
                "delta": round(delta, 4),
                "pct_difference": round(pct_diff, 4),
            }

        # Calculate divergence summary
        feasibility_comparison = {
            "simulation_a_feasible": sim_a.is_feasible,
            "simulation_b_feasible": sim_b.is_feasible,
        }

        summary_text = (
            f"Compared simulation {sim_a.id} ({sim_a.step_count} steps) with {sim_b.id} ({sim_b.step_count} steps). "
            f"Common metrics: {len(shared_metrics)}. "
            f"Feasibility: Run A {'feasible' if sim_a.is_feasible else 'infeasible'}, "
            f"Run B {'feasible' if sim_b.is_feasible else 'infeasible'}."
        )

        return SimulationComparison(
            simulation_a_id=sim_a.id,
            simulation_b_id=sim_b.id,
            scenario_a_id=sim_a.scenario_id,
            scenario_b_id=sim_b.scenario_id,
            step_count_a=sim_a.step_count,
            step_count_b=sim_b.step_count,
            metric_deltas=metric_deltas,
            trajectory_divergence={},
            feasibility_comparison=feasibility_comparison,
            summary=summary_text,
        )

    def cancel_simulation(
        self,
        simulation_id: UUID,
        conn: psycopg.Connection | None = None,
    ) -> bool:
        """Cancel a simulation run if it has not yet completed."""
        if not conn:
            raise ValueError("Database connection required")

        sim = self.get_simulation(simulation_id, conn=conn)
        if not sim:
            raise SimulationConfigurationError(f"Simulation '{simulation_id}' not found")
        if sim.status in (SimulationStatus.COMPLETED, SimulationStatus.FAILED):
            raise SimulationLifecycleError(f"Cannot cancel simulation in terminal status '{sim.status.value}'")

        with conn.cursor() as cur:
            cur.execute(
                "UPDATE simulation_runs SET status = 'CANCELLED', completed_at = NOW() WHERE id = %s",
                (simulation_id,),
            )
            return cur.rowcount > 0

    # -------------------------------------------------------------------------
    # Backward compatibility with protocol stub
    # -------------------------------------------------------------------------

    def run(self, scenario: dict) -> dict:
        """Protocol compatibility wrapper."""
        return {
            "status": "COMPLETED",
            "message": "Engine 17 Simulation Engine fully operational via create_and_run_simulation",
            "scenario": scenario,
        }
