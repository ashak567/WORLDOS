# WORLDOS Engine Registry

This registry is the durable record of all 26 first-class engine boundaries within WORLDOS, governed by the WORLDOS Architectural Constitution (`WORLDOS_ANTIGRAVITY_MASTER_PROMPT_LIBRARY_V2.md`).

---

## Status Classification
- **`SPECIFIED`**: Engine boundary, inputs, outputs, and contracts documented; no code yet.
- **`INTERFACE_ONLY`**: Abstract base classes or Pydantic/Protocol interfaces defined; no concrete implementation.
- **`PARTIALLY_IMPLEMENTED`**: Initial implementation exists but lacks full contract coverage or automated tests.
- **`IMPLEMENTED`**: Fully functional implementation conforming to architectural contracts.
- **`VERIFIED`**: Proven end-to-end with container-backed integration tests and deterministic invariants.
- **`DEPRECATED`**: Obsolete or superseded implementation.

---

## Core Engines (1 – 21)

### 1. World Model Engine
- **Purpose**: Authoritative entity, observation, event, relationship, and geometry representation.
- **Status**: `VERIFIED`
- **Inputs**: Validated `WorldBundle` payloads from Ingestion / Fusion.
- **Outputs**: Canonical `Entity`, `Observation`, `Event`, `Relationship`, `Geometry`, `TimeInterval`.
- **Dependencies**: PostgreSQL 16, PostGIS 3.4.
- **Persistence**: Relational tables (`entities`, `entity_identifiers`, `geometries`, `observations`, `events`, `relationships`, `time_intervals`).
- **Interface / API**: `backend/app/domain.py` Pydantic models; `WorldRepository` methods in `backend/app/storage.py`.
- **Evidence Requirements**: Every persisted state must reference a registered `source_id` and immutable `evidence_id`.
- **Test Contract**: `backend/tests/test_container_integration.py` validates CRUD and relational integrity.
- **Current Implementation**: Fully operational in Docker container stack on port 5432.
- **Next Milestone**: Support for versioned entity attribute histories and UUIDv7 indexing.

### 2. Source Intelligence / Source Registry Engine
- **Purpose**: Authoritative catalog of registered external data providers, licenses, publisher identities, and refresh policies.
- **Status**: `PARTIALLY_IMPLEMENTED`
- **Inputs**: Source registration metadata (slug, name, publisher, license, homepage, refresh policy).
- **Outputs**: Unique `source_id` (UUID), registered metadata record.
- **Dependencies**: PostGIS `sources` table.
- **Persistence**: `sources` table in PostgreSQL.
- **Interface / API**: `Source` model; `WorldRepository._connection()`.
- **Evidence Requirements**: Immutable record of source registration.
- **Test Contract**: Verified via adapter integration tests for World Bank, Natural Earth, USGS.
- **Current Implementation**: `sources` table tracks registered slugs (`world-bank`, `natural-earth`, `usgs-earthquakes`).
- **Next Milestone**: Add ingestion run lifecycle tracking, rate-limit policies, and source health metadata.

### 3. Data Ingestion Engine
- **Purpose**: Strongly-typed adapters that fetch, normalize, and hash external payloads into atomic `WorldBundle` units.
- **Status**: `IMPLEMENTED`
- **Inputs**: Raw external data (HTTP JSON, GeoJSON, CSV, REST APIs).
- **Outputs**: Validated `WorldBundle` structures ready for atomic persistence.
- **Dependencies**: `httpx`, `pydantic`, `WorldRepository`.
- **Persistence**: PostGIS operational tables via atomic transactions.
- **Interface / API**: Source adapter modules in `backend/app/ingestion/`.
- **Evidence Requirements**: Every ingested item must produce an immutable `Evidence` record with a SHA-256 payload hash.
- **Test Contract**: `test_world_bank_vertical_slice.py` and `test_container_integration.py`.
- **Current Implementation**: World Bank (`SP.POP.TOTL`), Natural Earth Admin 0 Boundaries, USGS Earthquake Hazards.
- **Next Milestone**: Standardize on `BaseSourceAdapter` abstract base class with backoff and retry decorators.

### 4. Data Fusion / Entity Resolution Engine
- **Purpose**: Cross-source entity reconciliation prioritizing publisher identifiers, strictly prohibiting name-only auto-merging.
- **Status**: `VERIFIED`
- **Inputs**: External identifiers, entity candidate names, spatial geometries.
- **Outputs**: Canonical entity ID matching existing entities or creating a new isolated entity.
- **Dependencies**: PostGIS `entity_identifiers` table, B-Tree index on `(scheme, value)`.
- **Persistence**: `entity_identifiers` mapping table.
- **Interface / API**: `backend/app/fusion.py`, `WorldRepository.ingest()`.
- **Evidence Requirements**: Source identity scheme, value, and confidence must accompany resolution.
- **Test Contract**: False-merge prevention verified in `test_container_integration.py::test_false_merge_prevented_without_matching_publisher_identifier`.
- **Current Implementation**: Resolves ISO-3 codes across World Bank and Natural Earth; isolates USGS events.
- **Next Milestone**: Implement an explicit `review_queue` table for uncertain matches requiring human review.

### 5. Evidence & Provenance Engine
- **Purpose**: Complete audit trail tracking raw data locators, retrieval timestamps, cryptographic hashes, pipeline versions, and transformation parameters.
- **Status**: `VERIFIED`
- **Inputs**: Ingestion metadata, raw content bytes.
- **Outputs**: `evidence_id`, `provenance_id` foreign keys attached to all claims.
- **Dependencies**: PostGIS `evidence` and `provenance` tables.
- **Persistence**: Relational foreign-keyed tables with `ON DELETE RESTRICT`.
- **Interface / API**: `Evidence` and `Provenance` models in `backend/app/domain.py`.
- **Evidence Requirements**: Non-null `source_id`, `locator`, and `retrieved_at`.
- **Test Contract**: Provenance traversal verified in `test_world_bank_vertical_slice.py`.
- **Current Implementation**: Operational; all observations, events, and relationships link to evidence.
- **Next Milestone**: Add cryptographic signature verification for high-integrity public feeds.

### 6. Data Quality & Freshness Engine
- **Purpose**: Track observation latency, completeness, schema validity, and source degradation.
- **Status**: `SPECIFIED`
- **Inputs**: Observation timestamps, ingestion attempt logs, schema validation metrics.
- **Outputs**: Freshness scores, quality alerts, degradation indicators.
- **Dependencies**: PostGIS, Source Registry.
- **Persistence**: Planned `source_runs` and `data_quality_metrics` tables.
- **Interface / API**: Planned `GET /api/v1/sources/{source_slug}/health`.
- **Evidence Requirements**: Quality assessments must cite observed run statistics.
- **Test Contract**: Deterministic scoring based on `now() - observed_at`.
- **Current Implementation**: Conceptual; basic timestamps recorded.
- **Next Milestone**: Implement ingestion run log and source freshness endpoint.

### 7. Spatial Intelligence Engine
- **Purpose**: Deterministic geospatial operations, topological containment, proximity joins, spatial intersections, and CRS normalization in WGS 84 (SRID 4326).
- **Status**: `VERIFIED`
- **Inputs**: GeoJSON, coordinates, geometries, distance radii, entity IDs.
- **Outputs**: Containing entities, intersecting geometries, nearest neighbors with evidence citations.
- **Dependencies**: PostGIS 3.4, GEOS, Shapely.
- **Persistence**: `geometries` table with GiST indexing on `geometry` and `valid_during`, foreign key to `evidence(id)`.
- **Interface / API**: `WorldRepository.near()`, `WorldRepository.containing_geometries()`, `WorldRepository.spatial_intersections()`, `GET /spatial/entities`, `GET /spatial/containing`, `GET /spatial/intersections/{entity_id}`.
- **Evidence Requirements**: Every geometry cites `source_id`, `evidence_id`, confidence, and validity interval.
- **Test Contract**: Verified in `test_container_integration.py::test_postgis_containment_and_distance_queries` and `test_spatial_containment_and_intersections_with_evidence`.
- **Current Implementation**: Fully operational in container PostGIS with evidence attribution.
- **Next Milestone**: Add polygon clipping, antimeridian normalization, and buffered spatial cluster queries.

### 8. Temporal Intelligence Engine
- **Purpose**: Bi-temporal and valid-time modeling with precision tiers (`instant`, `day`, `month`, `year`).
- **Status**: `VERIFIED`
- **Inputs**: Start timestamps, optional end timestamps, precision strings, `valid_at` target dates.
- **Outputs**: Validated `TimeInterval` records, temporal slice filters, point-in-time and interval overlap matches.
- **Dependencies**: PostgreSQL timestamp with time zone (`timestamptz`), `tstzrange`.
- **Persistence**: `time_intervals` table with composite index `(starts_at, ends_at)`, `geometries(valid_during)` with GiST range index.
- **Interface / API**: `TimeInterval` model; `ordered` model validator; `valid_at`, `start`, `end`, and `precision` parameters in `WorldRepository.observations()`, `events()`, `geometries()`.
- **Evidence Requirements**: Start timestamp cannot exceed end timestamp.
- **Test Contract**: Verified in `test_world_bank_vertical_slice.py::test_time_interval_ordering_and_precision_validation` and `test_container_integration.py::test_temporal_point_in_time_and_interval_overlap_queries`.
- **Current Implementation**: Fully operational; supports point-in-time and interval overlap queries across observations, events, and geometries.
- **Next Milestone**: Historical world-state rewind and temporal timeline playback.

### 9. Relationship / Knowledge Graph Engine
- **Purpose**: Directed entity-to-entity and event-to-entity topological and semantic graphs without a heavyweight graph DB.
- **Status**: `VERIFIED`
- **Inputs**: `subject_entity_id`, typed `predicate` (`VALID_PREDICATES`), `object_entity_id`, time interval, evidence.
- **Outputs**: Directed graph edges, 1-hop and 2-hop neighborhood graphs (`nodes`, `edges`, `node_count`, `edge_count`).
- **Dependencies**: PostGIS `relationships` table.
- **Persistence**: Relational `relationships` table with B-tree indexes on subject and object.
- **Interface / API**: `Relationship` model; `WorldRepository.relationships()`, `record_relationship()`, `entity_graph()`; `GET /relationships`, `POST /relationships`, `GET /relationships/graph/{entity_id}`.
- **Evidence Requirements**: Every relationship must cite an `evidence_id`, confidence score, and optional time interval.
- **Test Contract**: Verified in `test_world_bank_vertical_slice.py::test_relationship_distinct_entities_validation` and `test_container_integration.py::test_relationship_predicates_and_graph_traversal`.
- **Current Implementation**: Fully operational; supports verified typed predicates and deterministic 1-hop / 2-hop neighborhood traversals directly on PostGIS relational tables.
- **Next Milestone**: Multi-predicate path-finding and cycles detection.

### 10. Context Engine
- **Purpose**: Assemble a coherent, evidence-backed spatio-temporal slice (entities, observations, events, geometries, relationships, claims, evidence) for a given scope.
- **Status**: `VERIFIED`
- **Inputs**: Bounding box coordinates (`min_lon`, `min_lat`, `max_lon`, `max_lat`), temporal scope (`valid_at`, `start`, `end`, `precision`), `entity_ids`, `entity_kind`, or single `entity_id`.
- **Outputs**: Typed `WorldContext` bundle composing entities, geometries, observations, events, relationships, claims, and deduplicated `EvidenceCitation` records.
- **Dependencies**: PostGIS 3.4 (`ST_MakeEnvelope`, `ST_Intersects`), PostgreSQL b-tree/GiST indexes, `WorldRepository`.
- **Persistence**: In-memory ephemeral view over authoritative relational tables.
- **Interface / API**: `WorldRepository.scoped_context()`, `WorldRepository.context()`, `GET /context`, `GET /entities/{entity_id}/context`.
- **Evidence Requirements**: Every included observation, event, geometry, relationship, and claim must retain its underlying evidence ID and locator; deduplicated citations must cite source slug, name, and retrieval timestamp.
- **Test Contract**: Verified in `test_world_bank_vertical_slice.py` (bounding box validation, temporal scope validation, model assembly) and `test_container_integration.py` (spatial bounding box filtering, temporal precision/point-in-time/interval overlap, evidence deduplication, empty scope, API error handling, and backward compatibility).
- **Current Implementation**: Fully operational in container stack for multi-entity spatial and temporal query slices.
- **Next Milestone**: Automated context caching with change-data-capture (CDC) invalidation and temporal replay diff streams.

### 11. Deterministic Analytics Engine
- **Purpose**: High-performance in-process columnar metrics, Hive-partitioned Parquet snapshots, multi-entity spatial rollups, temporal aggregations, evidence freshness auditing, and reproducible benchmarks.
- **Status**: `VERIFIED`
- **Inputs**: Operational PostGIS data, partitioned Parquet snapshots in `data/snapshots/{snapshot_id}/`.
- **Outputs**: Spatial summary rollups, multi-entity temporal trends, evidence coverage/freshness metrics, spatial slice comparisons, derived claims with `TruthClass.DERIVED`, analytical benchmark telemetry.
- **Dependencies**: DuckDB, `psycopg`, Parquet.
- **Persistence**: Hive-partitioned Parquet files organized by `year={year}/entity_type={entity_type}/` under `data/snapshots/{snapshot_id}/`, metadata in `manifest.json`, and database run tracking in `snapshot_runs` table.
- **Interface / API**: `backend/app/analytics.py` (`DuckDbSpatialAnalytics`), `backend/app/snapshots.py` (`SnapshotManager`, `SnapshotCatalog`), `backend/app/benchmarks.py` (`AnalyticalBenchmarkSuite`), REST endpoints: `POST /analytics/snapshots/export`, `GET /analytics/snapshots`, `GET /analytics/snapshots/{id}`, `GET /analytics/snapshots/{id}/validate`, `GET /analytics/rollups/spatial`, `GET /analytics/rollups/temporal`, `GET /analytics/coverage`, `GET /analytics/compare`, `GET /analytics/benchmarks`, and `POST /analytics/population/{id}/growth`.
- **Evidence Requirements**: Read-only replica queries; zero mutation of operational world state; strict evidence citation lineage and input tracing preserved in derived claims.
- **Test Contract**: Verified in `test_analytics_and_snapshots.py` (5 unit tests: partition naming, temporal bucketing, unknown values, catalog discovery, staleness, validation, and spatial rollups) and `test_container_integration.py` (snapshot export lifecycle, PostgreSQL `snapshot_runs` tracking, DuckDB multi-entity rollups, analytical benchmarks, and FastAPI endpoints).
- **Current Implementation**: Fully operational in container stack; DuckDB executes analytical rollups over partitioned Parquet files with zero locks on operational PostGIS tables.
- **Next Milestone**: Decision Support Engine (Engine 13) and Event Alert Engine (Engine 14) thresholds.

### 12. Constraint Engine
- **Purpose**: Deterministic validation layer enforcing physical coordinate invariants, PostGIS geometry topology, spatial consistency, temporal ordering, entity relationships, truth classes, evidence completeness, and scenario modifications.
- **Status**: `VERIFIED`
- **Inputs**: `WorldBundle`, `Entity`, `Geometry`, `Observation`, `Relationship`, `Claim`, `TimeInterval`, `BoundingBox`, and `ScenarioProposal`.
- **Outputs**: Typed `ConstraintValidationResult` with `status` (`VALID`, `VALID_WITH_WARNINGS`, `INVALID`), `findings` (`ConstraintFinding`), and severity counters (`blocking_count`, `warning_count`, `review_required_count`).
- **Dependencies**: PostGIS 3.4 (`ST_IsValid`, `ST_IsValidReason`, `ST_Contains`, `ST_Intersects`, `ST_Disjoint`), `psycopg`, `pydantic`.
- **Persistence**: Pre-persistence gate in `WorldRepository.ingest()`; dry-run ephemeral evaluation via REST endpoint. Does not mutate database during validation.
- **Interface / API**: `backend/app/constraints.py` (`ConstraintEngine`, `ConstraintViolationError`), `WorldRepository.validate_bundle()`, `WorldRepository.validate_scenario()`, REST endpoints: `POST /constraints/validate`, `GET /constraints/rules`, and protocol compatibility `ScenarioEngine.validate_constraints(scenario: dict) -> list[str]`.
- **Evidence Requirements**: Every finding preserves underlying evidence references without fabricating evidence. Distinguishes missing evidence (`WARNING`) from invalid references (`BLOCKING`).
- **Test Contract**: Verified by 15 unit tests in `backend/tests/test_constraints.py` (coordinates, non-finite values, polygon closure, antimeridian wrapping, temporal intervals, anti-reflexivity, truth class invariants, derived claims, scenario proposals) and 4 container-backed integration tests in `backend/tests/test_container_integration.py` (authoritative PostGIS topology, spatial containment consistency, pre-persistence ingestion blocking with rollback, and dry-run validation REST endpoints).
- **Current Implementation**: Fully operational in container stack; protects `WorldRepository.ingest()` from dirty writes; provides deterministic dry-run evaluation.
- **Next Milestone**: Implement cross-temporal velocity constraints (maximum rate of change between successive observations) and polygon simplification checks.

### 13. Decision Support Engine
- **Purpose**: Deterministic, evidence-linked Multi-Criteria Decision Analysis (MCDA), comparing candidate alternatives, evaluating hard constraints (feasibility gates), scoring soft preferences (weighted ranking), handling missing data policies, producing trade-off explanations, and performing bounded weight sensitivity analysis without mutating operational world state.
- **Status**: `VERIFIED`
- **Inputs**: `DecisionRequest` specifying objective, candidate `DecisionAlternative` items (with entity IDs, attributes, or scenario proposals), `DecisionCriterion` definitions (directions: `maximize`, `minimize`, `target_range`; weights; hard constraints; target ranges), and `MissingDataPolicy` (`EXCLUDE`, `NEUTRAL_SCORE`, `PENALIZE_MIN`).
- **Outputs**: `DecisionResult` providing deterministic ranks, overall scores, normalized scores, per-criterion weighted contributions, feasibility findings for excluded alternatives, trade-off comparisons, audit trails, and cited evidence IDs.
- **Dependencies**: PostgreSQL 16 / PostGIS 3.4, `WorldRepository`, `ConstraintEngine`, `pydantic`.
- **Persistence**: Relational `decisions` table in PostgreSQL storing input request, scope, evaluated result JSON, top alternative, top score, and evaluation timestamp.
- **Interface / API**: `backend/app/decisions.py` (`DecisionEngine`), `backend/app/domain.py` (`DecisionRequest`, `DecisionResult`, `DecisionCriterion`, `DecisionAlternative`, `CriterionScoreBreakdown`, `RankedAlternative`, `InfeasibleAlternative`, `SensitivityVariation`, `CriterionDirection`, `MissingDataPolicy`), `backend/app/interfaces.py` (`DecisionSupportEngine`), `WorldRepository` methods (`evaluate_decision`, `persist_decision`, `get_decision`, `list_decisions`, `run_decision_sensitivity`), and REST endpoints: `POST /decisions/evaluate`, `GET /decisions`, `GET /decisions/{id}`, `POST /decisions/{id}/sensitivity`.
- **Evidence Requirements**: All source-derived criterion values preserve underlying `evidence_id`, source locators, truth classes, temporal validity, and confidence metadata; missing data is explicitly distinguished from genuine zero values.
- **Test Contract**: Verified by 15 unit tests in `backend/tests/test_decisions.py` (request validation, criterion directions, hard-constraint exclusion, soft-preference ranking, weight normalization and equal weight fallback, missing data policies, genuine zero vs unknown distinction, deterministic tie-breaking and reproducibility, trade-off analysis, and bounded sensitivity analysis) and 4 container-backed integration tests in `backend/tests/test_container_integration.py` (authoritative entity observation resolution, non-mutation of world state, decision persistence and retrieval, and REST API endpoints). Total test suite of 90 tests passing (100%).
- **Current Implementation**: Fully operational in container stack; integrated with PostgreSQL/PostGIS authoritative data, with audit persistence and non-mutating evaluations. Note on roadmap ordering: Engine 13 was previously skipped while Engine 14 was deepened; it is now fully implemented and verified.
- **Next Milestone**: Integration with Scenario Engine (Engine 16) for what-if alternative simulation and Pareto frontier visualization.


### 14. Event / Alert Engine
- **Purpose**: Deterministic condition-based alerting on incoming world events, spatial-temporal correlation, PostGIS geometry filtering, clustering thresholds, deduplication/cooldown enforcement, and evidence-linked alert records.
- **Status**: `VERIFIED`
- **Inputs**: Sourced `Event` records, `AlertRule` definitions, PostGIS geometries, temporal sliding windows.
- **Outputs**: `AlertEvaluation` records tracking lifecycle states (`RECEIVED`, `VALIDATED`, `EVALUATED`, `ALERTED`, `SUPPRESSED`, `FAILED`), deterministic `Alert` records citing evidence IDs, cooldown suppression logs.
- **Dependencies**: PostGIS 3.4 (`ST_Contains`, `ST_Intersects`, `ST_MakeEnvelope`), `psycopg`, `pydantic`.
- **Persistence**: Relational tables in PostgreSQL (`events`, `alert_rules`, `alert_evaluations`, `alerts`).
- **Interface / API**: `backend/app/alerts.py` (`AlertEngine`), `backend/app/domain.py` (`AlertRule`, `AlertEvaluation`, `Alert`, `AlertSeverity`, `AlertStatus`, `AlertLifecycleStatus`), `WorldRepository` methods (`create_alert_rule`, `get_alert_rule`, `list_alert_rules`, `update_alert_rule`, `delete_alert_rule`, `evaluate_event_alerts`, `list_alerts`, `get_alert`, `acknowledge_alert`, `resolve_alert`), and REST endpoints: `GET /alerts/rules`, `POST /alerts/rules`, `GET /alerts/rules/{id}`, `PATCH /alerts/rules/{id}`, `DELETE /alerts/rules/{id}`, `POST /alerts/events/{id}/evaluate`, `GET /alerts/evaluations`, `GET /alerts`, `GET /alerts/{id}`, `POST /alerts/{id}/acknowledge`, `POST /alerts/{id}/resolve`.
- **Evidence Requirements**: Every triggered alert preserves the immutable `evidence_id` of the underlying event; preserves context summary with observed coordinates, metric values, and operator thresholds; explicitly disclaims unmodeled secondary impacts.
- **Test Contract**: Verified by 7 unit tests in `backend/tests/test_alerts.py` (rule validation, comparison operators, spatial bounding box checks, cluster logic, lifecycle states) and 8 container-backed integration tests in `backend/tests/test_container_integration.py` (CRUD operations, seismic threshold alerting, PostGIS spatial bounding box rejection, sub-threshold rejection, idempotency/cooldown deduplication, acknowledgment/resolution lifecycle transitions, REST API endpoints, and persistence survival on evaluation failure). Total test suite of 71 container tests passing.
- **Current Implementation**: Fully operational in container stack; automated post-ingestion evaluation in USGS earthquake pipeline; decoupled alert records from external notification dispatch.
- **Next Milestone**: External notification delivery channels (webhooks, email dispatchers) as deferred async tasks.

### 15. Anomaly Detection Engine
- **Purpose**: Deterministic statistical outlier and change-point detection on historical observation series.
- **Status**: `INTERFACE_ONLY`
- **Inputs**: Time-series observation values (`list[float]`), significance thresholds.
- **Outputs**: Indices of anomalous observations (`list[int]`).
- **Dependencies**: `interfaces.py`, `numpy`/`duckdb`.
- **Persistence**: Ephemeral / derived observation tags.
- **Interface / API**: `AnomalyEngine.detect(series: list[float]) -> list[int]`.
- **Evidence Requirements**: Detected anomalies must cite the underlying series evidence IDs.
- **Test Contract**: Verification against synthetic standard normal distribution with injected outliers.
- **Current Implementation**: Protocol defined in `backend/app/interfaces.py`.
- **Next Milestone**: Implement z-score and IQR-based anomaly detection over DuckDB series.

### 16. Scenario Engine
- **Purpose**: Sandboxed scenario definitions allowing hypothetical state changes without contaminating operational truth.
- **Status**: `INTERFACE_ONLY`
- **Inputs**: Baseline world state, scenario delta parameters.
- **Outputs**: Sandboxed scenario state tagged `SIMULATED`.
- **Dependencies**: `interfaces.py`.
- **Persistence**: In-memory or isolated scenario database branch.
- **Interface / API**: `ScenarioEngine.run(scenario: dict) -> dict`.
- **Evidence Requirements**: All outputs must carry epistemic tier `SIMULATED`.
- **Test Contract**: Verify operational tables are unmodified after scenario execution.
- **Current Implementation**: Protocol defined in `backend/app/interfaces.py`.
- **Next Milestone**: Implement delta overlay pattern over DuckDB analytical snapshots.

### 17. Simulation Engine
- **Purpose**: Multi-step forward state evolution according to physical and heuristic models.
- **Status**: `INTERFACE_ONLY`
- **Inputs**: Scenario state, time step count, transition rules.
- **Outputs**: Time-stamped trajectory of simulated entity states.
- **Dependencies**: `interfaces.py`.
- **Persistence**: Sandboxed simulation run logs.
- **Interface / API**: `SimulationEngine.run(scenario: dict) -> dict`.
- **Evidence Requirements**: All generated values tagged `SIMULATED`.
- **Test Contract**: Conservation of mass/population invariants during simulation.
- **Current Implementation**: Protocol defined in `backend/app/interfaces.py`.
- **Next Milestone**: Define state transition interface.

### 18. Prediction Engine
- **Purpose**: Forward-looking projection beyond observed time horizons with explicit assumptions.
- **Status**: `INTERFACE_ONLY`
- **Inputs**: Target entity/metric, historical observation series, evidence IDs.
- **Outputs**: Predicted values tagged `PREDICTED`, confidence intervals, model assumptions.
- **Dependencies**: `interfaces.py`, Deterministic Analytics.
- **Persistence**: Derived observation records with truth class `PREDICTED`.
- **Interface / API**: `PredictionEngine.predict(target: str, evidence_ids: list[str]) -> dict`.
- **Evidence Requirements**: Must cite all input evidence IDs and model version.
- **Test Contract**: Prediction output must never be tagged `OBSERVED`.
- **Current Implementation**: Protocol defined in `backend/app/interfaces.py`.
- **Next Milestone**: Implement linear and polynomial trend extrapolation citing evidence.

### 19. Multimodal Evidence Engine
- **Purpose**: Ingestion, hashing, and retrieval of raster satellite imagery, documents, and sensory media.
- **Status**: `SPECIFIED`
- **Inputs**: Image/document URLs, binary blobs.
- **Outputs**: Content-addressed storage hashes, bounding coordinates, acquisition timestamps.
- **Dependencies**: Object storage (S3/GCS/local filesystem), `Evidence` table.
- **Persistence**: `evidence` table with binary storage references.
- **Interface / API**: Planned `backend/app/engines/multimodal.py`.
- **Evidence Requirements**: SHA-256 cryptographic hash of raw media.
- **Test Contract**: Hash verification on media upload.
- **Current Implementation**: Locator strings stored in `evidence.locator`.
- **Next Milestone**: Integrate raster metadata schemas for Earth observation products.

### 20. Evaluation Engine
- **Purpose**: Continuous verification of deterministic invariants, spatial accuracy, and fusion correctness.
- **Status**: `PARTIALLY_IMPLEMENTED`
- **Inputs**: Test suites, reference benchmarks, world state assertions.
- **Outputs**: Pass/fail test reports, invariant violations.
- **Dependencies**: `unittest`, `pytest`, Docker container stack.
- **Persistence**: Test execution logs.
- **Interface / API**: Pytest test suites in `backend/tests/`.
- **Evidence Requirements**: Grounded in fixed recorded test fixtures.
- **Test Contract**: Zero external network dependency during evaluation runs.
- **Current Implementation**: 9 unit and container-backed integration tests executing in CI/container.
- **Next Milestone**: Add property-based testing suites via Hypothesis.

### 21. Intelligence / Reasoning Engine
- **Purpose**: Downstream LLM explanation and synthesis strictly grounded in deterministic query results.
- **Status**: `INTERFACE_ONLY`
- **Inputs**: User question, deterministic engine result, cited evidence IDs.
- **Outputs**: Synthesized natural language explanation citing exact evidence IDs.
- **Dependencies**: `interfaces.py`, LLM API client.
- **Persistence**: Ephemeral / query audit log.
- **Interface / API**: `EvidenceBoundReasoner.answer(...)` in `backend/app/interfaces.py`.
- **Evidence Requirements**: Prohibited from stating facts without back-referencing supplied evidence IDs.
- **Test Contract**: Verifier checks that all stated entity facts map to input evidence IDs.
- **Current Implementation**: Protocol defined in `backend/app/interfaces.py`.
- **Next Milestone**: Implement deterministic verification filter over LLM output.

---

## Platform & Presentation (22 – 25)

### 22. API Platform
- **Purpose**: REST and WebSocket interfaces exposing deterministic world model capabilities.
- **Status**: `IMPLEMENTED`
- **Inputs**: HTTP requests.
- **Outputs**: RFC 7807 problem details or strongly-typed JSON responses.
- **Dependencies**: FastAPI, Uvicorn, Pydantic.
- **Persistence**: Stateless.
- **Interface / API**: `backend/app/main.py`.
- **Evidence Requirements**: Endpoints return `evidence_locator` and `confidence` fields.
- **Test Contract**: Verified via `test_world_bank_vertical_slice.py` and `test_container_integration.py`.
- **Current Implementation**: Operational on port 8000.
- **Next Milestone**: Standardize error schemas and add OpenAPI documentation tags.

### 23. Frontend / World Interface
- **Purpose**: Interactive React presentation layer rendering 3D Cesium globe and data tables.
- **Status**: `IMPLEMENTED`
- **Inputs**: Backend REST API streams.
- **Outputs**: Interactive WebGL 3D globe and HTML inspector cards.
- **Dependencies**: React 18, TypeScript, Vite, CesiumJS, Resium.
- **Persistence**: Browser localStorage for UI settings; all truth resides on backend.
- **Interface / API**: `frontend/src/App.tsx`.
- **Evidence Requirements**: UI displays Epistemic Badges and Evidence Drawers.
- **Test Contract**: `npm run build` production asset compilation.
- **Current Implementation**: Operational; renders country polygons and population series.
- **Next Milestone**: Add 3D visualization of seismic event points and relationship arcs.

### 24. Observability / Operations
- **Purpose**: Container health monitoring, structured logging, and query performance telemetry.
- **Status**: `PARTIALLY_IMPLEMENTED`
- **Inputs**: Application events, container probes.
- **Outputs**: Health status, structured logs.
- **Dependencies**: Docker Compose health checks, Uvicorn logging.
- **Persistence**: Container stdout/stderr logs.
- **Interface / API**: `GET /health` endpoint; Docker healthcheck.
- **Evidence Requirements**: Health checks test actual database connectivity.
- **Test Contract**: Verified by Docker healthy status.
- **Current Implementation**: Healthcheck endpoint operational; structured logging skill defined.
- **Next Milestone**: Add Prometheus `/metrics` endpoint and structured JSON logger.

### 25. Security / Privacy / Governance
- **Purpose**: Enforce secure defaults, SSRF protection in adapters, least-privilege DB access, and data privacy.
- **Status**: `PARTIALLY_IMPLEMENTED`
- **Inputs**: Outbound HTTP requests, database credentials.
- **Outputs**: Sanitized network calls, masked credentials.
- **Dependencies**: Pydantic `SecretStr`, adapter allowlists.
- **Persistence**: Configuration files (`.env`).
- **Interface / API**: Security standards in `.agents/skills/worldos-security-threat-model/SKILL.md`.
- **Evidence Requirements**: Audit trail for sensitive data access.
- **Test Contract**: SSRF URL validation test.
- **Current Implementation**: Container credentials isolated; security playbooks established.
- **Next Milestone**: Implement runtime URL validator in `BaseSourceAdapter`.

---

## Last Layer (26)

### 26. Agent Engine
- **Purpose**: Goal-directed autonomous workflow orchestration invoking validated WORLDOS engine tools.
- **Status**: `SPECIFIED` (Explicitly Last Layer)
- **Inputs**: User goals, task constraints, verified world context.
- **Outputs**: Multi-step plans, engine tool invocations, synthesized final report.
- **Dependencies**: All preceding 25 engines.
- **Persistence**: Task execution traces.
- **Interface / API**: Planned `backend/app/engines/agent.py`.
- **Evidence Requirements**: Agents may never mutate world state without verified source adapters and evidence hashing.
- **Test Contract**: Invariant testing of agent action boundaries.
- **Current Implementation**: Purely conceptual. Per architectural rules, implementation is deferred until all underlying data and reasoning engines are verified.
- **Next Milestone**: Architectural readiness gate (Prompt 28) prior to any agent code.
