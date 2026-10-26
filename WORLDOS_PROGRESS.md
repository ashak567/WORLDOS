# WORLDOS progress

## Checkpoint: World Context Engine multi-entity spatial and temporal context assembly

**Date:** 2026-09-29
**Branch:** `main`
**Status:** implemented; live container integration and contract tests passed (27/27), unit tests passed (9/9), frontend production build passed

### Completed

- **Spatially Scoped Context (Prompt 19 & Engine 10):**
  - Added `BoundingBox` and `SpatialScope` models with coordinate validation: bounds $[-180, 180]$ and $[-90, 90]$, ensuring `min_lon <= max_lon` and `min_lat <= max_lat`.
  - Implemented spatial filtering directly via PostGIS `ST_Intersects` and `ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)` accelerated by existing GiST spatial indexes.
  - Preserves geometry kinds (`country_boundary`, `city_point`, `point`, `epicenter`); representative points are never conflated with polygon boundaries.
- **Temporally Scoped Context:**
  - Added `TemporalScope` model with interval validation (`starts_at <= ends_at`) and precision tiers (`instant`, `day`, `month`, `year`, `unknown`).
  - Evaluates point-in-time (`valid_at`), interval overlap (`[start, end]`), and temporal precision filtering natively in SQL.
  - Preserves year-level data semantics without flattening into artificial timestamps.
- **Multi-Entity Context Assembly:**
  - Implemented `WorldRepository.scoped_context()` assembling a deterministic world context across entities, geometries, observations, events, relationships, claims, and evidence citations.
  - All facts are queried from PostgreSQL/PostGIS operational world-state tables without duplicating engine logic or creating a secondary truth store.
- **Evidence Lineage & Provenance:**
  - Every returned observation, event, geometry, relationship, and claim retains its underlying `evidence_id` and `evidence_locator`.
  - Missing evidence is represented explicitly (`None`); no artificial citations or false provenance claims are invented.
  - Populates a deduplicated list of `EvidenceCitation` records with source slug, name, locator, and retrieval timestamps.
- **Deterministic Response Contract:**
  - Defined typed `WorldContext` and `ContextQueryScope` Pydantic models.
  - Returns query scope, spatial bounds (if supplied), temporal scope (if supplied), deduplicated entities, observations, events, geometries, relationships, claims, evidence citations, and documented assumptions/limitations.
  - Output is strictly deterministic and stable across repeated queries on unchanged data.
- **API Endpoints & Backward Compatibility:**
  - Added FastAPI endpoint `GET /context` supporting optional bounding box coordinates (`min_lon`, `min_lat`, `max_lon`, `max_lat`), temporal parameters (`valid_at`, `start`, `end`, `precision`), `entity_id`, `entity_ids`, `entity_kind`, and `limit`.
  - Parameter validation returns clear HTTP 400 errors for partial bounding boxes, inverted bounding boxes, or inverted temporal intervals.
  - Preserved 100% backward compatibility for single-entity context queries via `GET /entities/{entity_id}/context`.
- **Entity Ingestion Idempotency Fix:**
  - Enhanced `WorldRepository.ingest()` to check existing entities by primary key `id` before inserting, ensuring seamless reuse of entity instances across multiple fact bundles without primary key collisions.
- **Engine Registry Upgrade:**
  - Promoted Context Engine (Engine 10) status from `PARTIALLY_IMPLEMENTED` to `VERIFIED` in `WORLDOS_ENGINE_REGISTRY.md`.
- **Verification Evidence:**
  - Expanded unit test suite in `backend/tests/test_world_bank_vertical_slice.py` to 9 tests (100% pass rate).
  - Expanded container integration test suite in `backend/tests/test_container_integration.py` to 27 tests covering spatial bounding box filtering, temporal precision, point-in-time matching, interval overlap, evidence deduplication, empty scope handling, API parameter validation, and backward compatibility. All 27 tests pass against the live PostGIS container stack.
  - Verified frontend production build passes cleanly (`npm --prefix frontend run build` completed with 0 errors).

### Previous Checkpoints Reused

1. `b719013 — Build evidence-first WORLDOS foundation`
2. `359ee6a — Reconcile country geometry across public sources`
3. `2edf163 — PostGIS container stack, multi-country ingestion, USGS earthquake adapter`
4. `963f33b — WORLDOS engineering discipline and project skills`
5. `afb22ff — Engine registry, ingestion lifecycle, source health, resolution reviews, and claim/truth-class formalization`
6. `46f7007 — Deepen temporal interval queries, spatial containment evidence, and knowledge graph traversal`

### Not claimed as complete

- Advanced modeling engines (Simulation, Prediction, Scenario, Anomaly Detection) remain pure specification/interface boundaries pending further multi-source data depth.
- Agent engine remains deferred behind deterministic query and evaluation prerequisites.

### Next task

Step 13: Deterministic Analytics & Snapshot Automation (Prompt 9 & Engine 11 deepening) — automated DuckDB snapshot rotation and analytical rollups over versioned Parquet data exports without operational database locks.
