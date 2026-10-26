# WORLDOS progress

## Checkpoint: Event / Alert Engine Deepening (Engine 14)

**Date:** 2026-10-26
**Branch:** `main`
**Status:** implemented; live container integration and contract tests passed (71/71), frontend production build passed

### Completed

- **Database Migration (`db/init/008_alerts.sql`):**
  - Created relational tables: `alert_rules`, `alert_evaluations`, and `alerts` with strict foreign key constraints (`ON DELETE CASCADE` / `RESTRICT`).
  - Added indexes on `event_kind`, `status`, `event_id`, `rule_id`, and `created_at DESC` for performant spatial-temporal lookups.
  - Enforced check constraints on comparison operators (`>`, `>=`, `<`, `<=`, `==`, `!=`), severity tiers (`INFO`, `WARNING`, `CRITICAL`), lifecycle states, and unique deduplication keys.
- **Typed Alert Domain Models (`backend/app/domain.py`):**
  - Implemented `AlertSeverity` (`INFO`, `WARNING`, `CRITICAL`), `AlertLifecycleStatus` (`RECEIVED`, `VALIDATED`, `EVALUATED`, `ALERTED`, `SUPPRESSED`, `FAILED`), and `AlertStatus` (`active`, `acknowledged`, `resolved`).
  - Implemented `AlertRule` with validation for metric fields, finite thresholds, bounding box coordinate ranges, positive temporal windows, and cluster counts.
  - Implemented `AlertEvaluation` capturing exact rule matches, count of alerts generated, suppression rationale, and execution timestamps.
  - Implemented `Alert` with immutable evidence citations (`evidence_id`), structured context summaries, deduplication keys, and operator lifecycle fields.
- **Deterministic Event / Alert Engine Core (`backend/app/alerts.py`):**
  - *Rule Validation*: Rejects empty metrics, unsupported operators, infinite thresholds, negative cooldowns, inverted bounding boxes, and invalid cluster parameters.
  - *Deterministic Operator Evaluation*: Supports floating-point comparisons with $10^{-9}$ numerical tolerance.
  - *PostGIS Spatial Scope Matching*: Evaluates WGS 84 bounding boxes, entity containment (`ST_Contains`), and arbitrary GeoJSON polygons.
  - *Temporal Windows & Clustering*: PostGIS-backed queries calculating qualifying event frequency across sliding time windows and spatial envelopes.
  - *Lifecycle State Machine*: Formally tracks transition through `RECEIVED` -> `VALIDATED` -> `EVALUATED` -> (`ALERTED` | `SUPPRESSED`) | `FAILED`.
  - *Deduplication & Cooldown*: Idempotent deduplication keys (`rule_id:event_id`) and cooldown suppression window prevents alert flooding.
  - *Evidence Lineage & Epistemic Guardrails*: Every alert cites underlying source evidence, publisher locators, observed metrics, and explicitly disclaims unmodeled secondary impacts (e.g. tsunami or structural damage).
- **Authoritative Ingestion & Storage Integration (`backend/app/storage.py`):**
  - Extended `WorldRepository` with `create_alert_rule`, `get_alert_rule`, `list_alert_rules`, `update_alert_rule`, `delete_alert_rule`, `evaluate_event_alerts`, `list_alerts`, `get_alert`, `acknowledge_alert`, `resolve_alert`, and `list_alert_evaluations`.
  - Automated post-ingestion alert evaluation in `ingest_usgs_earthquake` with decoupled error handling ensuring event persistence survives evaluation failures.
- **FastAPI Endpoint Contracts (`backend/app/main.py`):**
  - Added rule endpoints: `GET /alerts/rules`, `POST /alerts/rules` (HTTP 201), `GET /alerts/rules/{id}`, `PATCH /alerts/rules/{id}`, `DELETE /alerts/rules/{id}`.
  - Added evaluation endpoints: `POST /alerts/events/{id}/evaluate`, `GET /alerts/evaluations`.
  - Added alert lifecycle endpoints: `GET /alerts`, `GET /alerts/{id}`, `POST /alerts/{id}/acknowledge`, `POST /alerts/{id}/resolve`.
- **Verification Evidence:**
  - 7 unit tests in `backend/tests/test_alerts.py` covering rule validation, comparison operators, spatial bounding box checks, cluster logic, and lifecycle enums.
  - 8 container-backed integration tests in `backend/tests/test_container_integration.py` verifying rule CRUD, seismic threshold alerts, PostGIS spatial bbox filtering, sub-threshold rejection, cooldown suppression, acknowledgment/resolution lifecycle transitions, REST API endpoints, and persistence survival on evaluation failure.
  - Complete container test suite passed: **71 tests passed in 83.48s** (`Ran 71 tests in 83.476s, OK`).
  - Frontend production build verified (`npm --prefix frontend run build` built cleanly in 12.45s).

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

### Not claimed as complete

- External notification dispatchers (e.g. SMTP email, Webhooks, SMS, Slack integration) are decoupled and deferred as external integration work.
- Multi-hazard secondary cascade modeling (e.g. tsunami simulation or infrastructure damage estimation) requires validated physical models and remains behind deferred contracts.

### Next task

Engine 13: Decision Support Engine — multi-criteria trade-off ranking based on deterministic evidence and scenario constraints.
