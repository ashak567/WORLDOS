# WORLDOS architecture

**Status:** accepted foundation · **Date:** 2026-09-29

## Purpose and non-negotiables

WORLDOS is a world model, not a globe application. A conclusion may be presented only after its deterministic inputs, time scope, spatial scope, source evidence, transformation, and confidence are addressable. The 3D client and any AI are consumers of this evidence-backed substrate.

## System of record and boundaries

| Boundary | Responsibility | Does not do |
| --- | --- | --- |
| PostgreSQL + PostGIS | authoritative writes, topology-aware geometry, spatial/temporal filtering, provenance joins | ad-hoc OLAP ownership |
| DuckDB + Spatial | read-only analysis of a versioned export from Postgres | ingesting or serving authoritative facts |
| Source adapters | fetch, validate, normalize one publisher contract | silently merge entities from different publishers |
| Fusion | match publisher IDs first; queue uncertain name matches | auto-merge name-only collisions |
| FastAPI | typed writes and deterministic query surfaces | direct client database access |
| React + Cesium | render returned contexts and evidence links | create facts, perform entity resolution, or replace analytics |
| AI reasoning | explain deterministic result with evidence IDs | write unverified claims into the model |
| Agents | run bounded workflows over the above interfaces | become a parallel source of truth |

## Canonical model

`Entity` is a persistent thing (`place`, `organization`, `person`, `asset`, `concept`). `Observation` is a measured value about an entity. `Event` is an occurrence. `Relationship` is an evidence-backed directed edge between entities. All meaningful assertions carry `Confidence`; every fact must be traceable through `Provenance` to `Evidence` and a registered `Source`.

`Geometry` belongs to an entity and has an SRID 4326 shape, validity interval, source, and confidence. `TimeInterval` gives observations, events, and relationships an explicit temporal extent and precision. A representative point is deliberately distinct from a boundary polygon. `EntityIdentifier` attaches publisher keys to a canonical entity; it lets World Bank and Natural Earth reconcile only on the explicit `iso_3166_1_alpha_3` scheme.

The initial schema is in `db/init/001_world_model.sql`; typed API schemas are in `backend/app/domain.py`.

## Ingestion and source registry

Each adapter owns a publisher-specific parsing contract and registers a `Source` with publisher, license, home page, and refresh policy. Ingestion writes a `WorldBundle` atomically:

```text
public response -> Source -> Entity + Geometry -> TimeInterval
                -> Evidence(content hash, locator, retrieved time)
                -> Provenance(pipeline/version/transformation) -> Observation
```

The first adapter is World Bank indicator `SP.POP.TOTL`. It uses the publisher's country API for country metadata and its World Development Indicators endpoint for annual population. Natural Earth Admin 0 is the second adapter and contributes country polygons through the same ISO-3 identifier. The third adapter is the USGS Earthquake Hazards Program, contributing physical seismic events, epicenter point geometries, magnitude observations, and topological `occurred_in` relationships evaluated via PostGIS `ST_Contains` against country boundaries. Stable UUIDv5 values make a re-run idempotent for a country/year or event fact. Null source values are skipped and that transformation is recorded.

## Query engines

- **Temporal engine:** bi-temporal and valid-time modeling with precision tiers (`instant`, `day`, `month`, `year`). Supports point-in-time (`valid_at`), interval overlap (`[start, end]`), and temporal precision queries backed by GiST indexing on `geometries(valid_during)` (`tstzrange`) and composite B-tree indexing on `time_intervals(starts_at, ends_at)`.
- **Spatial engine:** PostGIS `ST_DWithin`, `ST_Contains`, and `ST_Intersects` run against evidence-backed geometry with direct `evidence_id` foreign key lineage. Point-in-polygon containment (`/spatial/containing`) and topological intersection (`/spatial/intersections/{id}`) preserve geometry kind, confidence, source, and evidence locators.
- **Context engine:** assembles coherent, evidence-backed spatio-temporal slices across multiple entities within defined geographic bounding boxes (`ST_MakeEnvelope`) and temporal windows (`valid_at`, intervals). Returns typed `WorldContext` models composing entities, geometries, observations, events, relationships, claims, and deduplicated evidence citations while maintaining backward compatibility with single-entity context queries (`/entities/{id}/context`).
- **Knowledge graph:** directed entity-to-entity and event-to-entity edges in the `relationships` table with explicit typed predicates (`located_in`, `connected_to`, `near`, `affects`, `observed_by`, etc.), temporal intervals, and evidence lineage. Executes deterministic 1-hop and 2-hop neighborhood traversals (`/relationships/graph/{id}`) directly on PostGIS without a separate graph database.
- **Deterministic analytics:** in-process columnar analytics engine powered by DuckDB over Hive-partitioned Parquet snapshots (`data/snapshots/{snapshot_id}/`). Preserves strict operational vs analytical dual-engine separation with zero locks on transactional PostGIS tables. Partitions datasets by calendar year (`year=YYYY`, `year=unknown`) and entity type (`entity_type=...`). Exposes atomic non-blocking snapshot export (`SnapshotManager`), metadata and catalog discovery (`SnapshotCatalog`), snapshot validation, multi-entity spatial rollups, temporal aggregation series, evidence coverage/freshness auditing, and reproducible benchmark workloads (`AnalyticalBenchmarkSuite`).
- **Constraint engine (Engine 12):** deterministic validation layer evaluating physical invariants, spatial boundaries, temporal ordering, entity relationships, truth classes, evidence completeness, and scenario modifications. Implements explicit severity tiers (`BLOCKING`, `WARNING`, `REVIEW_REQUIRED`) and status derivations (`VALID`, `VALID_WITH_WARNINGS`, `INVALID`). Validates incoming `WorldBundle` payloads before persistence in `WorldRepository.ingest()`, raising `ConstraintViolationError` on blocking violations to prevent data corruption. Uses PostGIS `ST_IsValid` / `ST_IsValidReason` for authoritative topology and spatial relation checks (`ST_Contains`, `ST_Intersects`, `ST_Disjoint`). Exposes dry-run validation via `POST /constraints/validate` and policy registry via `GET /constraints/rules`.
- **Event / alert engine (Engine 14):** deterministic condition-based alerting on incoming world events. Evaluates events against registered rules across structural constraints, numeric comparison operators (`>`, `>=`, `<`, `<=`, `==`, `!=`), PostGIS spatial bounding box and polygon scopes (`ST_Contains`, `ST_Intersects`, `ST_MakeEnvelope`), temporal sliding windows, and cluster thresholds. Manages a formal event lifecycle: `RECEIVED` (accepted for processing), `VALIDATED` (structural and constraint checks passed), `EVALUATED` (matching rules evaluated), `ALERTED` (condition triggered and alert generated), `SUPPRESSED` (cooldown or deduplication policy prevented duplicate alert), and `FAILED` (processing failed with recorded reason). Preserves immutable evidence lineage (`evidence_id`), observed coordinates, metric values, and explicit disclaimers regarding unmodeled secondary impacts. Supports full operator lifecycle (`active` -> `acknowledged` -> `resolved`). Exposes REST surfaces (`/alerts/rules`, `/alerts/events/{id}/evaluate`, `/alerts`). External notification dispatch is decoupled as deferred work.
- **Decision support engine (Engine 13):** evidence-linked Multi-Criteria Decision Analysis (MCDA) comparing candidate alternatives, evaluating hard constraints (feasibility gates), scoring soft preferences (weighted ranking), handling missing-data policies without conflating unknown values with zero, and calculating trade-off explanations and bounded weight sensitivity analysis. Operates strictly read-only against authoritative PostgreSQL/PostGIS world-state data, with zero mutation of operational tables (`entities`, `observations`, `geometries`, `evidence`). Feasible and infeasible alternatives are strictly segregated; failing alternatives are excluded from ranking with explicit blocking reasons. Normalizes values via deterministic min-max and target-range functions. Preserves full calculation trace and evidence citations in PostgreSQL `decisions` table. Exposes REST surfaces (`POST /decisions/evaluate`, `GET /decisions`, `GET /decisions/{id}`, `POST /decisions/{id}/sensitivity`).
- **Scenario engine (Engine 16):** deterministic, isolated counterfactual state branches and what-if parameter modeling. Operates strictly read-only against operational world-state data (`entities`, `observations`, `geometries`, `evidence`, `claims`, `alerts`), guaranteeing zero mutation of authoritative truth. Hypothetical modifications are expressed via supported operations (`SET`, `DELTA`, `SCALE`, `REMOVE`) on structured targets (`observation.<measure>`, `attribute.<key>`, `parameter.<name>`). Enforces a strict formal lifecycle (`DRAFT` -> `VALIDATED` -> `EVALUATED` -> `ARCHIVED`): modifications may only be added/removed in draft state; material changes invalidate prior evaluations and increment version; modifications are validated against the Constraint Engine (Engine 12) before evaluation. Evaluates scenarios through a deterministic overlay applied in documented precedence order (`target_entity_id`, `target_field`, `created_at`, `id`) over baseline facts. All hypothetical modifications, simulated states, and delta summaries are explicitly tagged with `TruthClass.SIMULATED`. Supports versioned branching (`branch_scenario`) and cross-scenario feasibility/metric comparison (`compare_scenarios`). Exposes REST surfaces (`POST /scenarios`, `GET /scenarios`, `GET /scenarios/{id}`, `POST /scenarios/{id}/modifications`, `GET /scenarios/{id}/modifications`, `DELETE /scenarios/{id}/modifications/{mod_id}`, `POST /scenarios/{id}/validate`, `POST /scenarios/{id}/evaluate`, `GET /scenarios/{id}/evaluation`, `POST /scenarios/{id}/branch`, `GET /scenarios/{a}/compare/{b}`, `POST /scenarios/{id}/archive`).
- **Simulation engine (Engine 17):** bounded, deterministic forward simulation engine that advances isolated hypothetical scenario states through discrete time steps according to versioned physical and heuristic transition rules. Operates strictly read-only against authoritative PostgreSQL/PostGIS operational data (`entities`, `observations`, `geometries`, `evidence`, `claims`, `alerts`), guaranteeing zero mutation of authoritative truth. Features a deterministic rule registry (`population_dynamics_v1`, `stock_flow_accounting_v1`, `per_capita_resource_depletion_v1`, `threshold_state_transition_v1`, `generic_linear_evolution_v1`) executing in stable order without caller-supplied arbitrary code. Enforces strict execution safeguards (bounded horizons up to 500 steps, calendar-aware step size progression across hours, days, months, and years, deep state isolation). Integrates the Constraint Engine (Engine 12) for real-time invariant checking across all simulated steps (`is_feasible: bool`). Computes bit-for-bit reproducible SHA-256 fingerprints across pinned scenario versions and configuration parameters. Every trajectory step, output metric, and summary is tagged with `TruthClass.SIMULATED`. Supports cross-simulation comparison (`compare_simulations`), step-level trajectory inspection, and run cancellation. Persists runs and steps in PostgreSQL via migration `011_simulations.sql`. Exposes REST surfaces (`GET /simulations/rules`, `POST /simulations`, `GET /simulations`, `GET /simulations/{id}`, `GET /simulations/{id}/trajectory`, `GET /simulations/{id}/steps/{step_index}`, `GET /simulations/{a}/compare/{b}`, `POST /simulations/{id}/cancel`).

## Deliberately deferred interfaces

Prediction, anomaly detection, and evidence-bound AI reasoning are contracts in `backend/app/interfaces.py`, not fake implementations. Scenario proposal dry-run validation is supported by Engine 12's `validate_scenario_proposal` and `ScenarioEngine.validate_constraints` without mutating authoritative world state. An implementation must accept a deterministic input/result and return cited evidence IDs, assumptions, and a model/version. Agents come after those capability contracts and may only call them.


## Truth classes and claim contract

WORLDOS strictly segregates empirical source facts from computed or modeled assertions. Every assertion carries an explicit `TruthClass`:

- **OBSERVED:** Direct empirical measurement from a verified source (e.g. World Bank census, USGS seismograph). Strictly enforced on the `observations` table via a PostgreSQL check constraint (`CHECK (truth_class = 'OBSERVED')`) and Pydantic validator. An observation cannot be created with a derived or predicted truth class.
- **DERIVED:** Deterministically computed from observed facts (e.g., percentage growth rate, density, anomaly scores). Preserves explicit `inputs`, `method`, `computation_version`, and underlying `evidence_ids`.
- **INFERRED:** Rule-based or probabilistic derivations consistent with observed data.
- **PREDICTED:** Future or unobserved state projections under documented `assumptions` and model specifications.
- **SIMULATED:** Counterfactual or hypothetical projections under explicitly altered constraints.

All non-observation assertions reside in the `claims` table and preserve full lineage back to the empirical inputs and evidence IDs that produced them.

## Source lifecycle, health, and reviewable entity resolution

Ingestion runs are tracked in `ingestion_runs` with start/completion timestamps, records counts, error messages, and observed freshness. Source operational health is exposed via `/sources/health`.

Entity reconciliation follows a strict conservative rule: entities are auto-merged only when matching explicit publisher keys (`entity_identifiers`). Name-only collisions are never silently merged; they are recorded as `pending` entries in `entity_resolution_reviews` for audit and manual review (`/resolution/reviews`).

## Operational path

`docker compose up --build` starts PostGIS and FastAPI. Call `POST /ingest/world-bank/population/IND?year=2023`, `POST /ingest/natural-earth/country/IND`, and `POST /ingest/usgs/earthquake/us6000m0xm`; countries reconcile through ISO-3 while earthquakes resolve through USGS event IDs and spatial containment. Use `/observations`, `/events`, `/geometries`, `/spatial/entities`, `/spatial/containing`, `/relationships`, `/context`, `/entities/{id}/context`, `/claims`, `/analytics/snapshots`, `/analytics/snapshots/export`, `/analytics/rollups/spatial`, `/analytics/rollups/temporal`, `/analytics/coverage`, `/analytics/compare`, `/analytics/benchmarks`, and `/analytics/population/{id}/growth`. The React/Cesium client reads the deterministic data and displays the fetched geometry with its evidence-backed context.

## Decisions and consequences

PostGIS is chosen over a globe-centric document store because spatial predicates, relationships, temporal joins, and provenance need transactionally consistent joins. DuckDB is kept outside the write path to retain its fast local analytical workflow without creating two truth stores. Source IDs, not normalized names, control automatic fusion; this creates more review work but prevents misleading false merges.
