# WORLDOS progress

## Checkpoint: Deterministic Decision Support Engine (Engine 13)

**Date:** 2026-10-26
**Branch:** `main`
**Status:** implemented; live container integration and contract tests passed (90/90), frontend production build passed

### Completed

- **Database Migration (`db/init/009_decisions.sql`):**
  - Created relational table: `decisions` tracking evaluation runs, input request, full results trace, alternatives count, feasible count, top alternative ID, top score, and evaluation timestamps.
  - Added indexes on `evaluated_at DESC` and `objective` for reproducible audit lookups.
- **Typed Decision Support Domain Models (`backend/app/domain.py`):**
  - Implemented `CriterionDirection` (`MAXIMIZE`, `MINIMIZE`, `TARGET_RANGE`) and `MissingDataPolicy` (`EXCLUDE`, `NEUTRAL_SCORE`, `PENALIZE_MIN`).
  - Implemented `DecisionCriterion` with validation for non-empty identifiers, finite non-negative weights, target range bounds, and hard constraint thresholds.
  - Implemented `DecisionAlternative` representing candidate options with optional entity links (`entity_id`), user attributes, or scenario proposals.
  - Implemented `CriterionScoreBreakdown` providing full calculation trace: raw values, normalized scores, normalized weights, weighted contributions, truth classes, units, and evidence links.
  - Implemented `RankedAlternative` and `InfeasibleAlternative` segregating feasible ranked candidates from candidates blocked by hard constraints.
  - Implemented `SensitivityVariation` capturing weight perturbation factors, rank changes, and top-choice stability.
  - Implemented `DecisionRequest` and `DecisionResult` supporting reproducible evaluations.
- **Deterministic Decision Support Core (`backend/app/decisions.py`):**
  - *Hard-Constraint Feasibility Gate*: Enforces hard constraints prior to scoring. Infeasible alternatives are completely excluded from ranking with explicit blocking reasons; high soft scores cannot compensate for hard constraint violations.
  - *Scenario Proposal Integration*: Evaluates proposed modifications through the Constraint Engine (Engine 12) to ensure candidates obey physical, temporal, and topological constraints.
  - *Deterministic Normalization*: Supports `maximize` ($\frac{x - x_{\min}}{x_{\max} - x_{\min}}$), `minimize` ($\frac{x_{\max} - x}{x_{\max} - x_{\min}}$), and `target_range` (bounded linear decay outside $[target_{\min}, target_{\max}]$). Handles identical bounds ($x_{\max} == x_{\min}$) safely as 1.0.
  - *Explicit Weight Normalization*: Normalizes user weights to $\sum w = 1.0$. Explicitly detects zero total weight and deterministically falls back to equal weights ($1/N$) with audit disclosures.
  - *Missing Data vs. Zero Distinction*: Preserves genuine empirical zero (`raw_value = 0.0`, `is_missing = False`) versus unknown/missing data (`raw_value = None`, `is_missing = True`). Applies configured policies (`EXCLUDE`, `NEUTRAL_SCORE` = 0.5, `PENALIZE_MIN` = 0.0) without corrupting raw facts.
  - *Deterministic Tie-Breaking & Reproducibility*: Multi-tier sorting (overall score desc -> primary criterion score desc -> alternative name asc -> alternative ID asc) guarantees identical rankings across repeated evaluations.
  - *Explainable Trade-Off Analysis*: Generates pairwise score deltas, relative advantages, and comparative trade-offs between top alternatives.
  - *Bounded Sensitivity Analysis*: Perturbs criterion weights by $\pm \delta$ to identify ranking instability or top-choice flips.
  - *Operational Non-Mutation*: Strictly read-only against authoritative world-state facts; decision runs never mutate `entities`, `observations`, `geometries`, or `evidence`.
- **Authoritative Storage & Repository Integration (`backend/app/storage.py`):**
  - Integrated `DecisionEngine` into `WorldRepository`.
  - Added repository methods: `evaluate_decision`, `persist_decision`, `get_decision`, `list_decisions`, and `run_decision_sensitivity`.
  - Authoritative entity observation lookup linking real World Bank population figures and cited evidence IDs to candidate alternatives.
- **FastAPI Endpoint Contracts (`backend/app/main.py`):**
  - Added evaluation endpoint: `POST /decisions/evaluate` (evaluates request and returns `DecisionResult`).
  - Added discovery endpoint: `GET /decisions` (lists historical runs with pagination).
  - Added audit endpoint: `GET /decisions/{id}` (returns complete decision record and calculation trace).
  - Added sensitivity endpoint: `POST /decisions/{id}/sensitivity` (evaluates bounded weight sensitivity).
- **Verification Evidence:**
  - 15 unit tests in `backend/tests/test_decisions.py` covering request validation, criterion directions, hard-constraint exclusion, soft-preference ranking, weight normalization, zero-sum fallback, missing data policies, unknown vs zero distinction, tie-breaking, trade-off analysis, and sensitivity analysis.
  - 4 container-backed integration tests in `backend/tests/test_container_integration.py` verifying real country entity resolution, non-mutation of world state, decision persistence and retrieval, and REST API endpoints.
  - Complete container test suite passed: **90 tests passed in 97.74s** (`Ran 90 tests in 97.738s, OK`).
  - Frontend production build verified (`npm --prefix frontend run build` built cleanly in 12.14s).

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

### Roadmap Ordering Note

Engine 13 was previously skipped while Engine 14 (Event / Alert Engine) was prioritized and deepened. Engine 13 has now been fully implemented and verified, closing the roadmap gap without altering or misrepresenting historical progress.

### Not claimed as complete

- AI narrative explanation layer is deferred; the core MCDA ranking remains 100% deterministic and evidence-grounded.
- Non-linear utility curves and pairwise AHP preference matrices are intentionally deferred; linear min-max and target-range utility functions provide full determinism.

### Next task

Engine 16: Scenario Engine / Engine 17: Simulation Engine — sandboxed scenario parameterization and forward state evolution without mutating operational world state.
