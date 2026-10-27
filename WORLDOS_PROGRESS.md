# WORLDOS progress

## Checkpoint: Deterministic Evidence-Aware Anomaly Detection Engine (Engine 15)

**Date:** 2026-10-27
**Branch:** `main`
**Status:** implemented; live container integration and contract tests passing, frontend production build passed

### Completed

- **Database Migration (`db/init/012_anomalies.sql`):**
  - Created relational tables `anomaly_runs` and `anomaly_findings`.
  - Added indexes on `entity_id`, `metric`, `observed_at`, `severity`, `status`, `detection_method`, `run_id`, and `created_at`.
  - Enforced unique constraint on `fingerprint` for idempotent execution and deduplication.
- **Typed Anomaly Domain Models (`backend/app/domain.py`):**
  - Implemented `AnomalySeverity` (`INFO`, `WARNING`, `HIGH`, `CRITICAL`).
  - Implemented `FindingLifecycleStatus` (`NEW`, `ACTIVE`, `RESOLVED`, `SUPPRESSED`).
  - Implemented `DetectionMethod` (`ROBUST_ZSCORE_MAD`, `TEMPORAL_CHANGE`, `PEER_GROUP_DEVIATION`, `SPATIAL_DEVIATION`, `MULTIVARIATE_MAHALANOBIS`).
  - Implemented `DetectionMethodDefinition` declaring method metadata, supported scopes, parameters, default thresholds, assumptions, and limitations.
  - Implemented `AnomalyDetectionRequest` with input bounds and temporal ordering validation.
  - Implemented `AnomalyFinding` preserving observed value, expected value, deviation, normalized anomaly score, data reliability, evidence references, explanations, limitations, and fingerprints.
  - Implemented `AnomalyRun` with execution metadata, observations count, findings count, summary statistics, and data quality exclusions.
- **Deterministic Detection Algorithms (`backend/app/anomalies.py`):**
  - *Method A: Robust Z-Score via MAD*: Computes median and MAD scaled by 0.6745. Implemented target leakage prevention (evaluating strictly against preceding points) and zero-dispersion handling for constant series without division by zero.
  - *Method B: Temporal Change Detection*: Computes step-to-step percentage and absolute shifts, handling zero baselines and rejecting false percentage calculations.
  - *Method C: Peer Group Cross-Sectional Deviation*: Evaluates entities against contemporaneous peer cohorts of the same entity kind.
  - *Method D: Spatial Neighborhood Deviation*: Integrates PostGIS geometry coordinates to evaluate observations against spatial neighbors within distance radius.
  - *Method E: Multivariate Mahalanobis*: Registered specification and interface for aligned multi-metric distance.
- **Data Quality, Epistemics & Deduplication:**
  - Strict non-mutation guarantee: Authoritative operational tables (`entities`, `observations`, `geometries`, `evidence`, `alerts`, etc.) are verified not to have added, modified, or deleted rows during anomaly detection.
  - Epistemic classification: All anomaly findings carry `TruthClass.DERIVED` and cite underlying observation `evidence_ids`.
  - Canonical SHA-256 fingerprinting for deduplication and lifecycle tracking (`suppress`, `resolve`).
- **Storage & REST API Integration (`backend/app/storage.py`, `backend/app/main.py`):**
  - Added `AnomalyEngine` delegate methods to `WorldRepository`.
  - Implemented endpoints: `GET /anomalies/methods`, `POST /anomalies/detect`, `GET /anomalies/runs`, `GET /anomalies/runs/{id}`, `GET /anomalies/findings`, `GET /anomalies/findings/{id}`, `POST /anomalies/findings/{id}/suppress`, `POST /anomalies/findings/{id}/resolve`.
- **Frontend Integration (`frontend/src/api.ts`):**
  - Added `AnomalyFindingSummary` type and `anomalyFindings` fetcher.
  - Verified frontend production build passed cleanly in 16.46s.

## Checkpoint: Bounded Deterministic Forward Simulation Engine (Engine 17)

**Date:** 2026-10-27
**Branch:** `main`
**Status:** implemented; live container integration and contract tests passing, frontend production build passed

### Completed

- **Database Migration (`db/init/011_simulations.sql`):**
  - Created relational tables: `simulation_runs` and `simulation_steps`.
  - Configured check constraints, foreign keys with `ON DELETE CASCADE` referencing scenarios and runs, and composite uniqueness constraint `UNIQUE(simulation_id, step_index)` on simulation steps.
  - Added indexes on `(scenario_id, scenario_version)`, `status`, `created_at DESC`, and `(simulation_id, step_index ASC)`.
- **Typed Simulation Domain Models (`backend/app/domain.py`):**
  - Implemented `SimulationStatus` (`CREATED`, `VALIDATED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`).
  - Implemented `SimulationRequest` with boundary validations (`ends_at > starts_at`, `step_size > 0`, `max_steps <= 500`).
  - Implemented `TransitionRuleDefinition` declaring supported variables, required inputs, output units, preconditions, assumptions, and limitations.
  - Implemented `SimulationStep` with step index, simulated timestamp, state snapshot, step metrics, applied rules, constraint findings, step findings, and deterministic step fingerprint.
  - Implemented `SimulationRun` tracking pinned scenario version, configuration, initial state, final state, trajectory summary, constraint feasibility (`is_feasible: bool`), assumptions, execution duration, and reproducibility fingerprint.
  - Implemented `SimulationComparison` comparing two completed simulation runs across final outcomes, metric deltas ($B - A$), and feasibility.
- **Deterministic Transition Rule Framework (`backend/app/simulation.py`):**
  - Implemented `TransitionRuleRegistry` for strongly-typed, registered rule discovery without executing caller-supplied arbitrary code.
  - Registered 5 verified deterministic transition rules:
    - `population_dynamics_v1`: annual growth rate ($r$), optional carrying capacity ($K$), and net migration delta per step.
    - `stock_flow_accounting_v1`: conservation of mass/resources through inflow, outflow, decay rate, and capacity boundaries.
    - `per_capita_resource_depletion_v1`: coupled multi-variable resource depletion driven by population size and annual per-capita consumption rate.
    - `threshold_state_transition_v1`: dynamic threshold evaluation emitting simulated warnings and alerts (`SIMULATED_ALERT`) without mutating operational alerts.
    - `generic_linear_evolution_v1`: constant linear slope with optional min/max bounds for synthetic fixtures.
- **Engine 17 Simulation Engine Core (`backend/app/simulation.py`):**
  - *Operational Non-Mutation*: Authoritative tables (`entities`, `observations`, `geometries`, `evidence`, `claims`, `alerts`) are NEVER mutated. Queries against baseline facts are strictly read-only.
  - *Deep State Isolation*: Implemented `_clone_state` ensuring every trajectory step and intermediate rule application operates on an isolated snapshot, preventing cross-step mutation.
  - *Calendar-Aware Discrete Stepping*: Implemented `_compute_step_count` and `advance_simulated_timestamp` handling leap years and calendar intervals for hours, days, months, and years.
  - *Bounded Horizons*: Enforces strict execution limits (`max_steps <= 500`), rejecting unbounded loops.
  - *Constraint Invariant Integration*: Evaluates each step state using the Constraint Engine (Engine 12) for non-finite values and negative population bounds. Infeasible states are flagged with `is_feasible = False` and persisted without silent failure.
  - *Epistemic Classification*: Every simulated state, trajectory step, derived metric, and delta summary carries `TruthClass.SIMULATED`.
  - *Reproducibility*: Computes canonical SHA-256 fingerprints over canonical JSON of `(scenario_id, scenario_version, starts_at, ends_at, step_size, step_unit, rule_ids, parameters, initial_state)`.
  - *Scenario Branch Pinning*: Simulations reference pinned scenario versions; subsequent modifications to the scenario do not alter or invalidate existing simulation runs.
  - *Analytical Trajectory Summaries*: Aggregates min, max, mean, absolute change, and relative percentage change across time series.
  - *Simulation Comparison*: `compare_simulations` aligns final metrics and computes divergence between compatible runs.
- **Repository Integration (`backend/app/storage.py`):**
  - Integrated `SimulationEngine` into `WorldRepository`.
  - Added repository methods: `create_and_run_simulation`, `get_simulation`, `list_simulations`, `get_simulation_trajectory`, `get_simulation_step`, `compare_simulations`, `cancel_simulation`, and `list_simulation_rules`.
- **FastAPI REST Endpoint Contracts (`backend/app/main.py`):**
  - `GET /simulations/rules`: lists registered transition rules.
  - `POST /simulations`: executes a forward simulation over a pinned scenario.
  - `GET /simulations`: lists simulation runs with scenario and status filters.
  - `GET /simulations/{id}`: retrieves simulation run metadata.
  - `GET /simulations/{id}/trajectory`: retrieves ordered trajectory steps with pagination.
  - `GET /simulations/{id}/steps/{step_index}`: retrieves a specific trajectory step.
  - `GET /simulations/{a}/compare/{b}`: compares two simulation runs.
  - `POST /simulations/{id}/cancel`: cancels an active or queued run.
- **Verification Evidence:**
  - 12 unit tests in `backend/tests/test_simulation.py` verifying domain bounds, transition rule dynamics, stock-flow conservation, coupled depletion, threshold warnings, deterministic fingerprinting, calendar stepping, and rule registry discovery.
  - 5 container-backed integration tests in `backend/tests/test_container_integration.py` verifying real PostgreSQL execution, operational non-mutation (verifying row counts of `entities`, `observations`, `geometries`, `evidence`, `provenance`, `entity_identifiers`, and `alerts` remain 100% identical before and after simulation), bit-for-bit reproducibility, scenario version pinning, cross-simulation comparison deltas, constraint infeasibility handling, and REST API endpoints.

### Previous Checkpoints Reused

1. `b719013 — Build evidence-first WORLDOS foundation`
2. `359ee6a — Reconcile country geometry across public sources`
3. `2edf163 — PostGIS container stack, multi-country ingestion, USGS earthquake adapter`
4. `963f33b — WORLDOS engineering discipline and project skills`
5. `afb22ff — Engine registry, ingestion lifecycle, source health, resolution reviews, and claim/truth-class formalization`
6. `46f7007 — Deepen temporal interval queries, spatial containment evidence, and knowledge graph traversal`
7. `6873fbb — World Context Engine multi-entity spatial and temporal context assembly`
8. `5347b1c — Deepen DuckDB analytical engine with Parquet snapshot automation, spatial rollups, and benchmark suite`
9. `f88fe35 — Deterministic constraint engine for spatial, temporal, relationship, and evidence validation`
10. `72c50be — Event / alert engine deepening with spatial-temporal correlation and evidence-linked alerting`
11. `165bd82 — feat(decisions): implement deterministic decision support engine with MCDA ranking and sensitivity analysis`
12. `526bb20 — feat(scenarios): implement deterministic scenario engine with isolated overlays and versioned branching`

### Not claimed as complete

- Empirical statistical calibration, machine-learned parameter estimation, and backtested historical forecasting are deferred to Engine 18 (Prediction Engine); transition models in Engine 17 are structural/heuristic simulations under explicit user parameters.
- High-resolution partial differential spatial mesh fluid/climate simulations are deferred.

### Next task

Engine 18: Prediction Engine — forward-looking projection beyond observed time horizons with explicit model assumptions, confidence intervals, and evidence citations.
