# WORLDOS progress

## Checkpoint: Deterministic Scenario Engine (Engine 16)

**Date:** 2026-10-26
**Branch:** `main`
**Status:** implemented; live container integration and contract tests passed (108/108), frontend production build passed

### Completed

- **Database Migration (`db/init/010_scenarios.sql`):**
  - Created relational tables: `scenarios`, `scenario_modifications`, and `scenario_evaluations`.
  - Configured check constraints, foreign keys with `ON DELETE CASCADE` on modifications/evaluations, and indexes on `parent_scenario_id`, `status`, and `target_entity_id`.
  - Added scenario versioning and audit timestamps.
- **Typed Scenario Domain Models (`backend/app/domain.py`):**
  - Implemented `ScenarioStatus` (`DRAFT`, `VALIDATED`, `EVALUATED`, `ARCHIVED`).
  - Implemented `ScenarioOperationType` (`SET`, `DELTA`, `SCALE`, `REMOVE`) on structured targets (`observation.<measure>`, `attribute.<key>`, `parameter.<name>`).
  - Implemented `ScenarioModification` with validation for non-empty identifiers, finite values, and temporal intervals.
  - Implemented `Scenario` with default `TruthClass.SIMULATED`, version tracking, parent scenario pointer, and baseline context.
  - Implemented `ScenarioEvaluation` storing baseline snapshot, isolated simulated state overlay, delta summaries, constraint validation findings, feasibility status, derived metrics, and reproducibility assumptions.
  - Implemented `ScenarioComparison` comparing two evaluated scenarios across common target metrics, cross-branch deltas, and feasibility.
- **Deterministic Scenario Engine Core (`backend/app/scenarios.py`):**
  - *Operational Non-Mutation*: Authoritative tables (`entities`, `observations`, `geometries`, `evidence`, `claims`, `alerts`) are NEVER mutated. All scenario queries against world facts are strictly read-only.
  - *Lifecycle State Machine*: Enforces strict transitions (`DRAFT` -> `VALIDATED` -> `EVALUATED` -> `ARCHIVED`). Modifications are restricted to draft state; material edits increment version and automatically drop status back to `DRAFT`. Archived scenarios reject mutations.
  - *Constraint Engine Pre-Evaluation Validation*: Integrates Engine 12 to validate modifications against numeric bounds, non-negativity (e.g. population >= 0), and target integrity. Scenarios with blocking findings remain `DRAFT` and cannot be evaluated.
  - *Deterministic Modification Overlay*: Applies modifications in deterministic sort order `(target_entity_id, target_field, created_at, id)`. Successive modifications accumulate deterministically over simulated state.
  - *Epistemic Classification*: Every hypothetical parameter, modified observation, attribute, and delta record is explicitly tagged with `TruthClass.SIMULATED`.
  - *Versioned Branching*: `branch_scenario` clones active parent modifications to a new child scenario with `version = 1`, preserving parent references (`parent_scenario_id`, `parent_scenario_version`) and audit history without overwriting prior evaluations.
  - *Scenario Comparison*: `compare_scenarios` evaluates and aligns metric values across branches, computing absolute deltas ($B - A$) and feasibility comparisons.
- **Repository Integration (`backend/app/storage.py`):**
  - Integrated `ScenarioEngine` into `WorldRepository`.
  - Added repository methods: `create_scenario`, `get_scenario`, `list_scenarios`, `archive_scenario`, `add_scenario_modification`, `list_scenario_modifications`, `remove_scenario_modification`, `branch_scenario`, `validate_scenario`, `evaluate_scenario`, `get_latest_scenario_evaluation`, and `compare_scenarios`.
- **FastAPI REST Endpoint Contracts (`backend/app/main.py`):**
  - `POST /scenarios`: creates scenario in `DRAFT` status.
  - `GET /scenarios`: lists scenarios with optional `status` and `parent_id` filters.
  - `GET /scenarios/{id}`: retrieves scenario metadata and version.
  - `POST /scenarios/{id}/modifications`: adds a modification, incrementing version.
  - `GET /scenarios/{id}/modifications`: lists active modifications.
  - `DELETE /scenarios/{id}/modifications/{mod_id}`: removes a modification.
  - `POST /scenarios/{id}/validate`: validates modifications against Constraint Engine.
  - `POST /scenarios/{id}/evaluate`: evaluates scenario and produces isolated overlay.
  - `GET /scenarios/{id}/evaluation`: retrieves latest evaluation record.
  - `POST /scenarios/{id}/branch`: branches a child scenario.
  - `GET /scenarios/{a}/compare/{b}`: compares two scenarios.
  - `POST /scenarios/{id}/archive`: archives a scenario.
- **Verification Evidence:**
  - 13 unit tests in `backend/tests/test_scenarios.py` verifying model defaults, supported operations, non-empty targets, deterministic overlay calculations, conflicting modification ordering, lifecycle rejection, reproducibility, and comparison deltas.
  - 5 container-backed integration tests in `backend/tests/test_container_integration.py` verifying CRUD lifecycle, real database operational non-mutation (verifying row counts of `entities`, `observations`, `geometries`, `evidence`, `provenance`, and `entity_identifiers` remain 100% identical before and after scenario operations), isolated overlays with `TruthClass.SIMULATED`, versioned branching, cross-scenario comparison, and REST API endpoints.
  - Complete container test suite passed: **108 tests passed in 120.73s** (`Ran 108 tests in 120.725s, OK`).
  - Frontend production build verified (`npm --prefix frontend run build` built cleanly in 12.10s).

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

### Not claimed as complete

- Multi-step forward physical simulation with dynamic differential equations is deferred to Engine 17 (Simulation Engine); the Scenario Engine focuses on deterministic parameter overlays, counterfactual state definitions, and comparative branch evaluation.
- Unrestricted arbitrary SQL mutations or JSON table patching are prohibited by design; only safe, strongly-typed domain modification operations (`SET`, `DELTA`, `SCALE`, `REMOVE`) on supported fields are allowed.

### Next task

Engine 17: Simulation Engine — multi-step forward state evolution, physical/heuristic transition rules, and temporal trajectory modeling over sandboxed scenario branches.
