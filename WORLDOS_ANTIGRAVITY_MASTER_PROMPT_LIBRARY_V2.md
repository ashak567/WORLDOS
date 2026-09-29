# WORLDOS — Antigravity master prompt library

## 0. Non-negotiable operating rules

Use these rules in every WORLDOS task:

```
You are continuing work on WORLDOS, an evidence-first world-model platform.

Do not turn this into a GEV clone, a dashboard-only product, a globe-first demo, or an AI chat wrapper.

The source of truth is PostgreSQL + PostGIS. DuckDB is a read-only derived analytical boundary. React/Cesium is a presentation layer only. AI may explain deterministic, evidence-backed results later; it must never become the data authority. Agents come last.

Every persisted claim must be traceable through:
Entity / Observation / Event / Relationship
→ Evidence
→ Provenance
→ registered Source
→ explicit Geometry and/or TimeInterval where applicable
→ Confidence.

Do not auto-merge entities on normalized names alone. Use publisher identifiers first. Name-only collisions must remain unresolved or be queued for review.

Before editing:
1. Inspect the repository, current branch, current commit, docs, and tests.
2. Preserve completed work.
3. Trace callers before changing shared model or ingestion code.
4. Make the smallest root-cause change.
5. Add or update one meaningful test for non-trivial behavior.
6. Run relevant tests/builds.
7. Update WORLDOS_ARCHITECTURE.md and WORLDOS_PROGRESS.md.
8. Commit on main only after verification.
9. Do not push unless explicitly asked.
```

## 0A. WORLDOS architectural constitution — additive rules

These rules extend the non-negotiable operating rules above. They do not replace any existing rule.

```text
WORLDOS is an evidence-first real-world intelligence platform built around a canonical World Model.

The World Model is the architectural center of gravity.

Do not build isolated feature silos such as:
- aircraft feature → aircraft-specific database
- satellite feature → satellite-specific database
- weather feature → weather-specific database
- travel feature → travel-specific database

Instead, new capabilities must map their data into the existing WORLDOS model and reuse the existing engines whenever possible.

The canonical flow is:

SOURCE
→ INGESTION
→ NORMALIZATION
→ WORLD MODEL
→ ENTITY RESOLUTION / DATA FUSION
→ EVIDENCE + PROVENANCE
→ INTELLIGENCE ENGINES
→ CONTEXT
→ DETERMINISTIC ANALYSIS
→ REASONING
→ PRESENTATION

A feature may bypass an engine only when an explicit architecture decision documents why.

The following engine boundaries are first-class architectural concepts:

CORE ENGINES
1. World Model Engine
2. Source Intelligence / Source Registry Engine
3. Data Ingestion Engine
4. Data Fusion / Entity Resolution Engine
5. Evidence & Provenance Engine
6. Data Quality & Freshness Engine
7. Spatial Intelligence Engine
8. Temporal Intelligence Engine
9. Relationship / Knowledge Graph Engine
10. Context Engine
11. Deterministic Analytics Engine
12. Constraint Engine
13. Decision Support Engine
14. Event / Alert Engine
15. Anomaly Detection Engine
16. Scenario Engine
17. Simulation Engine
18. Prediction Engine
19. Multimodal Evidence Engine
20. Evaluation Engine
21. Intelligence / Reasoning Engine

PRESENTATION / PLATFORM
22. API Platform
23. Frontend / World Interface
24. Observability / Operations
25. Security / Privacy / Governance

LAST-LAYER
26. Agent Engine

Not every engine must be fully implemented immediately.

However, every engine boundary must have:
- a documented purpose,
- explicit inputs,
- explicit outputs,
- ownership of logic,
- dependency boundaries,
- persistence expectations where applicable,
- API/interface contract,
- test expectations,
- lifecycle/status.

Do not introduce a heavyweight infrastructure component merely because an engine exists conceptually.

The implementation may begin with a simple PostgreSQL-backed or in-process implementation and evolve later.

The architecture must remain extensible without prematurely adding:
- Kafka
- Kubernetes
- Airflow
- Temporal
- Neo4j
- a vector database
- distributed compute
- custom ML infrastructure
- multi-agent frameworks

unless a measured requirement justifies it.

WORLDOS truth classes must remain explicit:

OBSERVED
- directly obtained from a registered source.

DERIVED
- deterministically calculated from known observations/data.

INFERRED
- a reasoned conclusion that is not directly observed.

PREDICTED
- a forward-looking model output.

SIMULATED
- a result produced under an explicit hypothetical scenario.

These classes must never be silently conflated.

Claims and derived facts must retain:
- inputs,
- method,
- time scope,
- source/evidence references,
- assumptions,
- confidence,
- model/version where applicable.

The LLM is not the World Model and is not a source of truth.

The reasoning layer may interpret deterministic WORLDOS results and supplied evidence, but it must not silently manufacture facts.

Agents are the final orchestration layer and must never become the foundation.

Before adding a new feature, ask:

1. Which WORLDOS entity/observation/event/relationship does this represent?
2. Which existing engine should own this behavior?
3. Which source(s) provide the evidence?
4. How is freshness represented?
5. How is provenance represented?
6. What is observed versus derived/inferred/predicted/simulated?
7. What deterministic computation can be done before AI?
8. What existing engine/API can be reused?
9. Does this create a new data silo?
10. What test proves the behavior?

If a new feature creates a parallel model, storage system, source path, or reasoning path, stop and document the architectural justification before proceeding.
```

## 0B. Engine registry contract

Maintain a durable WORLDOS engine registry in the repository.

Recommended document:

`WORLDOS_ENGINE_REGISTRY.md`

Each engine entry must contain:

```text
Engine
Purpose
Status
Inputs
Outputs
Dependencies
Persistence
API/interface
Evidence/provenance requirements
Test contract
Current implementation
Next milestone
```

Use statuses such as:

- SPECIFIED
- INTERFACE_ONLY
- PARTIALLY_IMPLEMENTED
- IMPLEMENTED
- VERIFIED
- DEPRECATED

Do not mark an engine IMPLEMENTED merely because an interface or placeholder exists.

A capability is VERIFIED only when meaningful deterministic behavior and its tests have been demonstrated.

## 0C. World Model contract

The canonical World Model must be capable of representing at least:

- Entity
- EntityIdentifier
- Geometry
- TimeInterval
- Observation
- Event
- Relationship
- Source
- Evidence
- Provenance
- Confidence
- Claim/Derivation metadata where needed

Future domain data must fit these primitives or receive an explicit architecture decision.

Examples:

Aircraft:
- Entity
- position Geometry
- Observation
- flight/route Relationship
- source Evidence
- timestamp/TimeInterval

Satellite:
- Entity
- orbital/position Observation
- sensor metadata
- coverage/observation opportunity Relationship
- time interval
- source Evidence

Infrastructure:
- Entity
- Geometry
- attributes
- Relationships
- source Evidence

Do not create domain-specific truth models that duplicate these concepts without justification.

## 0D. Claim and derivation contract

Whenever WORLDOS produces a non-source fact, preserve its derivation.

A derived result should conceptually carry:

```text
Claim
├── truth_class
├── inputs
├── method
├── time_scope
├── spatial_scope
├── source/evidence references
├── assumptions
├── confidence
└── computation/model version
```

Examples:

```text
Observed:
India population = X in 2023

Derived:
India population increased Y% between 2022 and 2023

Inferred:
The observed series is consistent with accelerating growth

Predicted:
Model estimates X under specified assumptions

Simulated:
Scenario output under explicitly changed constraints
```

Never label a derived/inferred/predicted/simulated result as an observed source fact.

## 0E. Data quality and freshness contract

WORLDOS must treat data quality as part of intelligence, not as an afterthought.

Track, where applicable:

- source health
- freshness
- retrieval time
- observation time
- coverage
- completeness
- schema validity
- duplicate rate
- reconciliation status
- parsing failures
- partial-result state
- source version/release
- license/usage metadata

Do not allow stale or partial data to silently appear equivalent to fresh authoritative data.

Query and reasoning layers should be able to expose relevant freshness/quality metadata.

## 0F. Source intelligence contract

The Source Registry should eventually answer:

- What sources exist?
- What does each source cover?
- Which entity/data types can it provide?
- What geographic coverage does it have?
- What temporal coverage does it have?
- How fresh is it?
- What identifier system does it use?
- What license/usage terms apply?
- What confidence/quality metadata exists?
- Is the source currently healthy?
- When was it last successfully ingested?

Do not build a giant source marketplace or scheduler prematurely.

Start with explicit tables, metadata, and commands.

## 0G. Context Engine contract

WORLDOS must eventually construct a reusable World Context rather than forcing every feature or LLM call to independently gather data.

A World Context may contain:

```text
Location
Time
User intent
Constraints
Entities
Observations
Events
Relationships
Infrastructure
Environment
Transport
Historical context
Spatial relationships
Evidence
Freshness / quality
Confidence
```

The Context Engine must:
- identify relevant world scope,
- gather deterministic data through existing engines,
- preserve evidence references,
- preserve time/spatial scope,
- expose assumptions,
- avoid silently inventing missing context.

The reasoning layer consumes context; it should not become the context builder itself.

## 0H. Event, alert, and change-detection contract

Separate:

Observation
→ Change Detection
→ Event/Anomaly
→ Rule/Condition
→ Alert/Notification

Do not collapse these into one generic AI feature.

Examples include:
- entity entering/leaving a region,
- significant sourced change,
- source freshness failure,
- anomaly according to a stated deterministic method,
- event intersecting infrastructure.

Every generated event/alert must identify:
- trigger,
- input observations,
- method/rule,
- time,
- spatial scope where applicable,
- evidence,
- confidence.

## 0I. Constraint and decision-support contract

WORLDOS must support explicit constraints before AI recommendation.

Represent constraints such as:

- budget
- time
- distance
- location
- availability
- capacity
- required/forbidden attributes
- user-specified preferences
- scenario variables

The flow should be:

```text
USER CONSTRAINTS
→ WORLD CONTEXT
→ DETERMINISTIC FILTERING / ANALYSIS
→ EVIDENCE
→ CANDIDATE OPTIONS
→ OPTIONAL AI EXPLANATION
```

Do not let an LLM invent prices, availability, distances, or constraints.

## 0J. Multimodal evidence contract

Future text, documents, images, video metadata, maps, satellite imagery, and other media may become evidence sources.

Do not implement all of this now.

Define a future-compatible boundary so multimodal evidence can enter through:

```text
Media / Document / Image / Video / Imagery
→ Evidence normalization
→ extraction metadata
→ provenance
→ confidence
→ World Model observation/claim
```

Image-derived or model-derived observations must retain their extraction method/model metadata and must not automatically become authoritative source facts.

## 0K. Cost, quota, and resource-budget contract

For external APIs and expensive model/data operations, WORLDOS should eventually track:

- request cost
- quota
- rate limits
- source priority
- cacheability
- retry policy
- fallback source
- request budget

Do not implement a distributed cost platform prematurely.

Begin with explicit configuration and telemetry where necessary.

Never add an external dependency whose expected cost/limit behavior is unknown.

## 0L. Evaluation contract

WORLDOS must have an Evaluation Engine/discipline that measures correctness before advanced AI or agents.

Evaluate, where relevant:

- entity-resolution accuracy
- spatial-query correctness
- temporal-query correctness
- source attribution
- evidence completeness
- freshness handling
- deterministic analytics
- prediction validation/calibration
- simulation reproducibility
- AI evidence/citation compliance
- regression behavior

Every major engine should have a testable contract.

Do not use "the output looked right" as a verification method.

## 0M. No feature-silo rule

Before creating a new table, service, API, source adapter, cache, model, or frontend state store for a feature, verify whether an existing WORLDOS primitive/engine already represents the requirement.

If yes:
- reuse it.

If no:
- propose the smallest new reusable primitive/engine.

If a feature-specific silo is still necessary:
- document why,
- document its relationship to the World Model,
- document migration/replacement boundaries,
- add tests.

## 0N. Infrastructure proportionality rule

Architecture must be ambitious, but infrastructure must remain proportional to measured need.

Prefer:

- PostgreSQL/PostGIS before a second operational database
- DuckDB before distributed analytical infrastructure
- explicit commands before orchestration platforms
- simple background execution before distributed queues
- modular interfaces before microservices
- deterministic algorithms before ML
- evidence-bound AI before agents

Introduce complexity only when:
- a measurable bottleneck exists,
- a reliability requirement exists,
- a security requirement exists,
- a scale requirement exists,
- or a clear architectural need exists.

## 0O. Skill and tooling governance

When using Antigravity skills:

- prefer workspace-local `.agents/skills/` for WORLDOS-specific rules,
- use global skills only for genuinely reusable workstation-wide behavior,
- load skills progressively,
- keep skills narrowly scoped,
- inspect third-party skill sources before installation,
- do not blindly install bulk skill collections,
- avoid machine-specific absolute paths,
- request only the tools a skill needs,
- document important installed skills/extensions.

The current Antigravity convention is:

```text
<workspace-root>/.agents/skills/<skill-folder>/SKILL.md
```

Antigravity supports progressive skill discovery/activation, so do not turn one WORLDOS skill into an enormous "do everything" instruction set. Use focused skills with clear triggering descriptions.

## 1. Master continuation prompt — use this first

```
Continue WORLDOS from the existing repository.

Repository:
C:\Users\ASUS\Documents\Codex\2026-09-29\continuing-from-worldos-chatgpt-conversation-6ab0f13d\work\WORLDOS

Start by inspecting:
- git status and recent commits
- WORLDOS_ARCHITECTURE.md
- WORLDOS_PROGRESS.md
- compose.yaml
- db/init/
- backend/app/
- backend/tests/
- frontend/src/

Current known checkpoint:
- Branch: main
- HEAD: 359ee6a — Reconcile country geometry across public sources
- Working tree should be clean
- Do not assume the remote has a main branch; do not push.

Already implemented:
- PostgreSQL/PostGIS world-model schema
- Entity / Source / Evidence / Provenance / Geometry / TimeInterval / Observation / Event / Relationship models
- EntityIdentifier reconciliation using explicit ISO-3 identifiers
- World Bank total-population ingestion
- Natural Earth country-boundary ingestion
- FastAPI deterministic query endpoints
- React/Cesium API-driven geometry presentation
- Postgres-to-DuckDB export command
- Local unit tests and frontend production build

The immediate task is to prove the existing vertical slice in containers:
1. Check whether Docker is available and running.
2. Start the PostGIS + API stack without deleting data volumes.
3. Ingest World Bank population and Natural Earth geometry for several ISO-3 countries.
4. Verify that one country resolves to one canonical entity across both sources.
5. Verify observation, geometry, context, spatial, and population-change endpoints.
6. Run the DuckDB export and inspect its resulting observation count.
7. Add container-backed integration tests for this exact flow.
8. Update progress/architecture docs only for confirmed results.
9. Commit the verified checkpoint to main.

Do not add AI, agents, prediction, simulation, anomaly detection, dashboards, authentication, scheduling, or deployment work in this task.
```

## 2. Prompt: run the existing real vertical slice

```
Verify WORLDOS’s existing public-data vertical slice end-to-end.

First inspect the existing database state and Docker volumes. Do not delete or reset anything automatically.

When Docker is available:
1. Start PostGIS and the FastAPI service using the existing compose configuration.
2. Ingest these sources for India:
   - World Bank population: POST /ingest/world-bank/population/IND?year=2023
   - Natural Earth boundary: POST /ingest/natural-earth/country/IND
3. Repeat for at least two additional ISO-3 countries, such as BRA and JPN.
4. Confirm each country has:
   - one canonical entity,
   - World Bank observation evidence,
   - Natural Earth polygon geometry evidence,
   - explicit ISO-3 entity identifiers,
   - no name-based duplicate entity.
5. Verify:
   - GET /observations
   - GET /geometries
   - GET /entities/{entity_id}/context
   - GET /spatial/entities using a point inside or near a country
   - GET /analytics/population/{entity_id}/change
6. Export the Postgres data to DuckDB with python -m app.export and verify the exported row count.
7. Record exact test evidence in WORLDOS_PROGRESS.md.
8. Add integration tests that fail if source reconciliation creates duplicate country entities.
9. Commit only after all checks pass.

If Docker is unavailable, do not fake successful integration. Report the exact blocker and complete any safe non-container tests only.
```

## 3. Prompt: add container-backed integration tests

```
Add the smallest meaningful container-backed integration test coverage for WORLDOS.

Scope:
- Existing World Bank + Natural Earth country ingestion
- Existing PostGIS persistence
- Existing ISO-3 entity reconciliation
- Existing spatial and temporal API queries
- Existing DuckDB export

Requirements:
- Reuse the current compose setup and existing FastAPI endpoints.
- Do not mock PostGIS for the integration path.
- Test at least one country that receives both a World Bank observation and a Natural Earth polygon.
- Assert that both sources link to one canonical entity.
- Assert geometry kind remains country_boundary and is not conflated with the World Bank representative_point.
- Assert evidence locators and provenance records exist.
- Assert a nearby spatial query returns the entity.
- Assert DuckDB receives the derived observations export.
- Keep fixtures tiny and deterministic where live-network use would make tests flaky.
- Keep live source checks separate from repeatable integration tests.
- Update progress documentation with exact test commands and results.
- Commit to main after tests pass.

Do not introduce a test framework or orchestration platform unless the current dependencies cannot support the required test.
```

## 4. Prompt: add the third real public source adapter

```
Add one third independent, real public-data source adapter to WORLDOS.

Before choosing the source:
1. Inspect the existing World Bank and Natural Earth adapters.
2. Choose a stable public source with a clear license, API or downloadable dataset, durable publisher identifiers, and evidence-friendly URLs.
3. Choose a data type that materially expands the model rather than duplicating population or country boundaries.

Preferred candidates:
- World Bank indicator other than total population, if it introduces a clearly typed observation and unit.
- GeoNames, only if its identifier/license/usage terms are verified.
- GADM or another boundary source only if license and source-role boundaries are compatible.
- A reputable public disaster/event feed only if it can demonstrate Event + TimeInterval + Evidence correctly.

Requirements:
- Register the Source with publisher, license, homepage, and refresh policy.
- Preserve raw source locator and content hash as Evidence.
- Record parsing and normalization steps as Provenance.
- Use explicit source identifiers for reconciliation.
- Do not merge by normalized name alone.
- Add a Pydantic contract and parser validation.
- Add deterministic unit tests using a minimal fixture.
- Add at least one live read-only adapter validation.
- Extend the existing API only when a new deterministic query is justified.
- Update architecture/progress docs and commit to main.

Do not add a new generic ingestion framework, scheduler, event bus, or agent system unless the new source truly requires it.
```

## 5. Prompt: strengthen source registry and ingestion contracts

```
Review and strengthen the WORLDOS source-registry and ingestion boundaries.

Current model:
- Sources are registered during ingestion.
- Evidence stores locator, retrieved time, and content hash.
- Provenance stores pipeline version and transformation metadata.
- EntityIdentifier enables safe cross-source reconciliation.

Implement only gaps that are necessary for safe repeatable ingestion.

Evaluate:
- source version or dataset release metadata,
- ingestion run identifier and status,
- idempotency boundaries,
- source fetch failure recording,
- schema validation failures,
- source freshness metadata,
- pagination and partial-result behavior.

Rules:
- Do not add a message broker, scheduler, worker platform, or orchestration service.
- Prefer tables/columns and small explicit commands over infrastructure.
- Do not erase or overwrite prior evidence silently.
- Make failed ingestion observable without making incomplete data authoritative.
- Add focused tests.
- Update architecture/progress docs and commit.
```

## 6. Prompt: build a proper entity-resolution review path

```
Improve WORLDOS entity resolution without weakening its conservative merge rule.

Current behavior:
- Explicit matching ISO-3 identifiers reconcile World Bank and Natural Earth country data.
- Name-only matches are intentionally not auto-merged.

Task:
Design and implement the smallest human-reviewable workflow for uncertain cross-source matches.

Requirements:
- Keep automatic merges restricted to compatible, explicit identifiers.
- Store candidate matches, match reason, score/confidence, source entities, and review state.
- Do not modify canonical entity links until an approved action occurs.
- Make review actions auditable through evidence/provenance or an explicit resolution record.
- Expose a typed backend query for pending review candidates.
- Do not build a full admin UI unless a minimal API is insufficient.
- Add tests proving a similar-name collision cannot silently merge.
- Update docs and commit to main.

Do not add machine learning, embeddings, LLM matching, or a graph database in this task.
```

## 7. Prompt: deepen temporal intelligence correctly

```
Extend WORLDOS temporal intelligence using the existing TimeInterval model.

First inspect all consumers of TimeInterval, observations, events, relationships, and geometry validity.

Implement only deterministic capabilities that are needed now, such as:
- interval overlap queries,
- valid-at / valid-during queries,
- precision-aware filtering for year/month/day/instant facts,
- temporal geometry selection,
- temporal relationship retrieval.

Requirements:
- Do not treat a year observation as an exact instant without retaining year precision.
- Preserve source-provided temporal ambiguity.
- Use Postgres range and timestamp capabilities where appropriate.
- Add targeted tests for overlap, boundary conditions, and precision.
- Extend FastAPI only for a useful deterministic query.
- Update docs and commit.

Do not add forecasting, causal inference, simulation, or AI reasoning in this task.
```

## 8. Prompt: deepen spatial intelligence correctly

```
Extend WORLDOS spatial intelligence on the PostGIS source-of-truth layer.

Current state:
- Representative country points come from World Bank metadata.
- Country boundary polygons come from Natural Earth.
- Both remain separate geometry kinds with independent evidence.

Implement one justified spatial capability, such as:
- geometry valid-at query,
- boundary containment,
- intersection between sourced geometries,
- geometry-quality filtering,
- country polygon lookup by point,
- spatial query result including geometry evidence.

Requirements:
- Use PostGIS; do not duplicate geospatial truth in frontend code.
- Never substitute a representative point for a polygon or imply they are equivalent.
- Include geometry kind, source, confidence, and evidence in results.
- Use appropriate spatial indexes.
- Add integration tests against real PostGIS.
- Update docs and commit.

Do not add tiles, vector databases, custom globe rendering logic, or a second spatial store.
```

## 9. Prompt: mature the DuckDB analytical boundary

```
Improve the WORLDOS Postgres-to-DuckDB analytical boundary.

Current state:
- PostgreSQL/PostGIS remains authoritative.
- backend/app/export.py writes observations into a DuckDB file.
- DuckDB is derived, replaceable, and must never accept authoritative writes.

Task:
Make exported analytical snapshots reproducible and inspectable.

Requirements:
- Add snapshot metadata: source Postgres export timestamp, export version, row counts, and source schema/version information.
- Prefer a versioned output filename or a manifest over in-place ambiguity.
- Preserve enough fields for deterministic population and spatial analysis.
- Keep all writes one-way: Postgres → DuckDB.
- Add a small command or API-independent verifier that checks snapshot metadata and row counts.
- Add tests using minimal data or a temporary DuckDB file.
- Update documentation with export/replay commands.
- Commit to main.

Do not make DuckDB a live write store, a cache with hidden freshness rules, or a replacement for PostGIS.
```

## 10. Prompt: improve the React/Cesium presentation layer

```
Improve the existing React/Cesium presentation layer without turning WORLDOS into a globe-first demo.

First inspect frontend/src/App.tsx and frontend/src/api.ts.

Current role of the frontend:
- Fetch deterministic observations and sourced geometry from the API.
- Render geometry in Cesium.
- Link users to evidence.
- Never create, merge, or infer facts.

Choose one focused improvement:
- entity selection and evidence/context panel,
- source/geometry-kind/confidence labels,
- temporal observation selection,
- query-state and error handling,
- clear distinction between representative points and boundary polygons,
- map interaction that calls a deterministic spatial endpoint.

Requirements:
- Reuse existing API patterns.
- Do not hardcode World Bank or Natural Earth records in the UI.
- Display evidence locator/source information for shown facts.
- Preserve accessible labels and keyboard basics.
- Keep Cesium bundle work limited to a measured need.
- Run npm run build.
- Update docs only if API behavior changes.
- Commit to main.

Do not add fake “AI insights,” analytics cards with invented data, login flows, or a new visual-design framework.
```

## 11. Prompt: deterministic analytics before prediction

```
Extend WORLDOS deterministic analytics before considering prediction.

Use existing observations, time intervals, geometry, evidence, provenance, and DuckDB export boundaries.

Implement one evidence-backed analytic capability, for example:
- population growth rate with explicit period,
- comparison of two country time series,
- outlier flag based on a stated deterministic method,
- source coverage/freshness analysis,
- spatial aggregate over sourced country polygons.

Requirements:
- Return the exact input scope, time window, method, source evidence, and assumptions.
- Keep calculations reproducible in SQL or DuckDB.
- Store no calculated fact as source truth unless its provenance states it is derived.
- Add tests covering numeric edge cases and missing data.
- Expose a typed FastAPI response only if it is broadly useful.
- Update docs and commit.

Do not call an LLM, claim prediction, or add a simulation interface implementation.
```

## 12. Prompt: scenario, prediction, simulation, anomaly — only after prerequisites

```
Assess whether WORLDOS is ready to implement one of its currently interface-only capabilities:
ScenarioEngine, PredictionEngine, SimulationEngine, or AnomalyEngine.

First provide a short evidence-based readiness assessment:
- Which deterministic datasets exist?
- Which variables, time coverage, geometry coverage, and source confidence exist?
- Are input constraints explicit?
- Are outputs testable against known historical or synthetic cases?
- Can every result carry evidence, assumptions, model version, and uncertainty?

If readiness is insufficient:
- Do not implement a fake version.
- Add only the smallest missing deterministic prerequisite, if it is clearly scoped.

If readiness is sufficient for exactly one capability:
- Implement the smallest deterministic version.
- Make all inputs, constraints, outputs, uncertainty, and provenance explicit.
- Add tests that would fail for unsupported assumptions.
- Keep AI/agents out of the write path.
- Update docs and commit.

Never label a heuristic as a prediction or a simulation unless its model and validation are explicit.
```

## 13. Prompt: AI reasoning layer — much later

```
Do not implement AI reasoning until the requested deterministic query, evidence, provenance, and confidence surfaces already exist.

When ready, add an evidence-bound explanation layer only.

Requirements:
- AI input must be a deterministic query result plus its source evidence IDs/locators.
- AI output must cite only supplied evidence IDs.
- The AI cannot write observations, events, entities, relationships, or provenance records as truth.
- The AI cannot silently run arbitrary database queries.
- Return clear uncertainty and “insufficient evidence” outcomes.
- Log model/version/prompt-template metadata separately from factual provenance.
- Add tests for unsupported claims, missing evidence, and citation validation.
- Keep agents out of scope.
- Update docs and commit.

Do not build a generic chat bot or a free-form “ask the world” interface first.
```

## 14. Prompt: agent layer — last

```
Assess whether WORLDOS is ready for an agent layer.

Agents are only permitted after:
- deterministic query APIs are stable,
- source ingestion is auditable,
- entity reconciliation has review safeguards,
- AI explanations are evidence-bound,
- scenario/prediction/simulation capabilities are real and tested where needed.

If not ready, report which prerequisite blocks agents and implement no agent behavior.

If ready, build one bounded workflow agent only:
- explicit allowed tools,
- no direct database writes,
- evidence-required outputs,
- human confirmation before external effects,
- deterministic workflow logs,
- clear stop conditions,
- tests for permission and evidence failures.

Do not create a general autonomous agent platform, background task swarm, or self-modifying workflow system.
```

## 15. Prompt: documentation, checkpoint, and commit

```
Finish the current WORLDOS task cleanly.

Before committing:
1. Run relevant backend tests.
2. Run relevant frontend build if frontend changed.
3. Run container integration tests if the task touched persistence, ingestion, spatial behavior, or API contracts and Docker is available.
4. Check git diff for unrelated/generated files.
5. Ensure no source data, secrets, local database files, node_modules, build outputs, or generated package metadata are committed.
6. Update WORLDOS_ARCHITECTURE.md only for durable design changes.
7. Update WORLDOS_PROGRESS.md with:
   - exact completed behavior,
   - exact verified checks,
   - known limits,
   - single next task.
8. Commit to main using a concise conventional message.
9. Do not push unless explicitly requested.

Final report must state:
- exact commit hash,
- exact verified tests/builds,
- exact unverified limitation,
- next continuation task.
```

## 16. Prompt: establish and audit the WORLDOS engine registry

```text
Audit WORLDOS against the architectural constitution and create/update WORLDOS_ENGINE_REGISTRY.md.

Do not rebuild existing implementation.

First inspect:
- WORLDOS_ARCHITECTURE.md
- WORLDOS_PROGRESS.md
- current schema/models
- backend modules
- frontend boundaries
- tests
- existing APIs
- existing ingestion/source code

Create a registry covering:

CORE
- World Model
- Source Intelligence / Source Registry
- Data Ingestion
- Data Fusion / Entity Resolution
- Evidence & Provenance
- Data Quality & Freshness
- Spatial Intelligence
- Temporal Intelligence
- Relationship / Knowledge Graph
- Context
- Deterministic Analytics
- Constraint
- Decision Support
- Event / Alert
- Anomaly Detection
- Scenario
- Simulation
- Prediction
- Multimodal Evidence
- Evaluation
- Intelligence / Reasoning

PLATFORM
- API
- Frontend / World Interface
- Observability
- Security / Privacy / Governance

LAST
- Agent Engine

For every engine record:
- purpose
- current status
- inputs
- outputs
- dependencies
- persistence
- interface/API
- evidence requirements
- test contract
- current implementation
- next milestone

Do not mark an engine implemented just because a placeholder exists.

Do not add new infrastructure merely to populate the registry.

Update WORLDOS_ARCHITECTURE.md only where durable architectural clarification is necessary.

Commit only after verification.
```

## 17. Prompt: audit WORLDOS for feature silos

```text
Perform an architecture-conformance audit for feature silos.

Search the repository for:
- duplicated domain models
- feature-specific databases
- direct frontend data ingestion
- feature-specific source registries
- duplicated entity-resolution logic
- duplicated spatial logic
- duplicated temporal logic
- facts created outside the World Model
- LLM paths that bypass deterministic APIs/evidence
- hidden caches that can become stale truth
- hardcoded external source facts

For every issue:
- identify the file/module
- explain the architectural conflict
- determine whether a refactor is necessary now
- avoid speculative rewrites

If a refactor is necessary, make the smallest safe change.

Do not turn this into a broad rewrite.

Add regression tests where behavior changes.

Update WORLDOS_ENGINE_REGISTRY.md and WORLDOS_PROGRESS.md only when justified.

Commit after verification.
```

## 18. Prompt: implement source health, freshness, and quality metadata

```text
Strengthen WORLDOS source-quality and freshness handling.

Inspect the existing Source, Evidence, Provenance, ingestion-run, and observation models first.

Implement only the smallest reusable model/API needed to represent:
- retrieval time
- observation time
- source release/version where available
- freshness state
- source health
- partial-result state
- validation/parsing failure state
- coverage/completeness metadata where practical

Do not create a scheduler or distributed monitoring system.

Rules:
- incomplete ingestion must not silently become authoritative
- failed ingestion must remain observable
- old evidence must remain historical rather than being overwritten
- source freshness must not be confused with observation time
- source health must not alter factual truth

Add deterministic tests.

Expose a typed query only if it is broadly useful.

Commit after verification.
```

## 19. Prompt: deepen the World Context Engine

```text
Design and implement the smallest real WORLDOS Context Engine capability.

The Context Engine must gather deterministic world state from existing engines rather than duplicating their logic.

A context should be capable of representing:
- location
- time
- user intent
- constraints
- entities
- observations
- events
- relationships
- spatial scope
- temporal scope
- evidence
- freshness/quality
- confidence

Start with one deterministic context query, such as:
"build context for a supplied point and time window."

The result must identify:
- exact spatial scope
- exact temporal scope
- included entities
- included observations/events
- source/evidence references
- freshness
- assumptions

Do not call an LLM.

Do not build a generic chat interface.

Do not add a second data store.

Add contract tests proving that context construction is deterministic and evidence-linked.

Commit after verification.
```

## 20. Prompt: formalize claims and derivations

```text
Review WORLDOS for places where derived values are represented as if they were observations.

Introduce the smallest reusable claim/derivation metadata needed to distinguish:

OBSERVED
DERIVED
INFERRED
PREDICTED
SIMULATED

For derived outputs, preserve:
- inputs
- method
- time scope
- spatial scope
- assumptions
- evidence references
- confidence
- computation/model version

Do not rewrite every existing record unnecessarily.

Prioritize the paths that will feed analytics, reasoning, prediction, or simulation.

Add tests proving that a derived value cannot be silently labeled as a source observation.

Update the architecture documentation.

Commit after verification.
```

## 21. Prompt: build the relationship / knowledge graph boundary without a graph database

```text
Strengthen WORLDOS relationships as a reusable knowledge-graph boundary.

Do not install Neo4j or another graph database in this task.

Use the existing PostgreSQL relationship model.

Support explicit relationships such as:
- located_in
- connected_to
- near
- affects
- observed_by
- route
- belongs_to
- intersects
- covers
- adjacent_to

Requirements:
- typed relationship semantics
- source/evidence references
- temporal validity where applicable
- confidence where applicable
- deterministic traversal/query boundaries
- tests for relationship integrity

Do not build a generic graph UI.

Do not create domain-specific relationship silos.

The goal is to make PostgreSQL relationships capable of supporting future knowledge-graph reasoning without prematurely introducing another database.

Commit after verification.
```

## 22. Prompt: establish the constraint and decision-support boundary

```text
Define the smallest reusable WORLDOS Constraint Engine and Decision Support boundary.

Constraints may include:
- budget
- time
- distance
- location
- availability
- capacity
- required attributes
- forbidden attributes
- user preferences

Implement only deterministic filtering/evaluation.

The flow must be:

CONSTRAINTS
→ WORLD CONTEXT
→ DETERMINISTIC FILTERING
→ CANDIDATE OPTIONS
→ EVIDENCE

Do not use an LLM to invent:
- prices
- availability
- distances
- travel times
- capacities
- source facts

Any optional recommendation text must come later as an explanation over deterministic candidates.

Add typed models and tests.

Do not build a travel-specific engine.

The engine must remain reusable for travel, infrastructure, real estate, resource planning, and other WORLDOS domains.

Commit after verification.
```

## 23. Prompt: establish event, change-detection, and alert boundaries

```text
Design the smallest reusable event/change-detection boundary.

Keep these concepts separate:

OBSERVATION
→ CHANGE DETECTION
→ EVENT / ANOMALY
→ RULE / CONDITION
→ ALERT

Implement one deterministic example using existing data.

Every generated event/alert must preserve:
- trigger
- input observations
- method/rule
- timestamp/time interval
- spatial scope where applicable
- evidence
- confidence

Do not use an LLM.

Do not build a notification platform.

Do not add streaming infrastructure.

The implementation should be synchronous or command-driven unless existing scale requirements justify otherwise.

Add tests for repeated observations, missing observations, and boundary conditions.

Commit after verification.
```

## 24. Prompt: establish multimodal evidence interfaces without implementing the whole stack

```text
Design the future multimodal evidence boundary.

Do not build a full computer-vision or media-processing platform.

Inspect the existing Evidence and Provenance models.

Define how WORLDOS could represent evidence originating from:
- documents
- images
- video metadata
- maps
- satellite imagery
- OCR
- extracted media metadata

The design must preserve:
- source
- locator
- retrieval time
- extraction method
- model/version where applicable
- confidence
- provenance
- relation to the resulting observation/claim

If a minimal schema extension is necessary, implement only that extension.

Do not add a vector database.

Do not add an image database.

Do not automatically convert model-generated observations into authoritative facts.

Add tests for provenance metadata.

Commit only if the boundary produces real reusable value.
```

## 25. Prompt: establish API/resource budgeting boundaries

```text
Audit WORLDOS for external API/resource-cost risks.

Identify:
- paid APIs
- rate-limited sources
- expensive AI/model calls
- high-volume geospatial queries
- external data downloads

Design the smallest reusable request-budget metadata/configuration needed.

Track where appropriate:
- source
- request type
- quota/rate limit
- estimated cost
- retry policy
- fallback source
- cacheability

Do not build a billing platform.

Do not add distributed queues.

Do not introduce a cache unless there is a measured need.

The result must make it possible to prevent an uncontrolled request loop or expensive recursive workflow later.

Add tests for budget enforcement where implemented.

Commit after verification.
```

## 26. Prompt: build the WORLDOS evaluation discipline

```text
Establish the WORLDOS Evaluation Engine/discipline.

The goal is to prove correctness, not merely that code executes.

Start with deterministic evaluation of:
- entity resolution
- spatial queries
- temporal queries
- evidence attribution
- freshness handling
- analytics
- DuckDB export
- context construction

For each evaluation:
- define input
- expected result
- actual result
- evidence expectations
- acceptable tolerance where numeric
- failure condition

Create small deterministic fixtures.

Do not use LLM-as-judge as the only evaluator.

Do not create a generic benchmark platform.

Add regression tests for every evaluation that catches a real architectural failure.

Later this framework may be extended to:
- prediction calibration
- simulation reproducibility
- AI citation compliance
- unsupported-claim detection

Commit after verification.
```

## 27. Prompt: audit Antigravity skills for WORLDOS

```text
Audit the currently installed Antigravity skills for WORLDOS.

Use the current Awesome Agent Skills catalog only as a discovery source.

Do not bulk-install the catalog.

For each candidate skill:
- identify original maintainer/source
- inspect the actual skill
- determine whether it is actively maintained
- identify tool permissions
- identify scripts/resources
- assess prompt-injection/tool-poisoning risk
- determine WORLDOS relevance

Prefer narrowly scoped skills for:
- architecture
- Python
- Pydantic
- FastAPI
- PostgreSQL/PostGIS
- DuckDB
- GIS
- testing
- security
- frontend/TypeScript
- observability
- documentation
- Git/code review

Keep WORLDOS-specific rules in:
.agents/skills/

Do not create a single giant skill.

Do not install an agent-framework skill merely because WORLDOS will eventually have agents.

Produce/update:
WORLDOS_ENGINEERING_SKILLS.md

Do not change application code in this task.

Commit only the skill-governance changes if they are repository-worthy.
```

## 28. Prompt: architecture readiness gate before advanced intelligence

```text
Before implementing prediction, simulation, anomaly detection, AI reasoning, or agents, perform a WORLDOS readiness gate.

Check:
- World Model integrity
- source registry
- ingestion repeatability
- entity-resolution safeguards
- evidence/provenance completeness
- spatial correctness
- temporal correctness
- context construction
- deterministic analytics
- data freshness/quality
- evaluation coverage
- API contracts
- security boundaries

For the requested advanced capability, explicitly state:
- available deterministic inputs
- geographic coverage
- temporal coverage
- confidence
- known gaps
- validation method
- evidence requirements
- expected failure modes

If readiness is insufficient:
- do not fake the capability
- implement only the smallest missing prerequisite

If readiness is sufficient:
- implement exactly one capability
- keep it deterministic where possible
- keep AI/agents outside the write path
- add validation and regression tests

Update WORLDOS_ENGINE_REGISTRY.md and WORLDOS_PROGRESS.md.

Commit after verification.
```

## 29. Prompt: final architecture-conformance review

```text
Perform a final architecture-conformance review before a major WORLDOS milestone.

Verify:

1. No feature has become a parallel source of truth.
2. PostgreSQL/PostGIS remains authoritative.
3. DuckDB remains derived/read-only.
4. Frontend does not create facts.
5. Source adapters remain evidence-producing.
6. Entity resolution remains conservative.
7. Observed/derived/inferred/predicted/simulated states remain distinct.
8. Context is assembled from deterministic WORLDOS engines.
9. Analytics are reproducible.
10. Evidence and provenance are preserved.
11. Data freshness/quality is visible where relevant.
12. AI does not become factual authority.
13. Agents remain out of scope unless the readiness gate passes.
14. No unjustified infrastructure has been introduced.
15. Tests cover the changed contracts.
16. Documentation matches the implementation.
17. WORLDOS_ENGINE_REGISTRY.md accurately reflects engine status.
18. WORLDOS_PROGRESS.md contains exactly one next continuation task.

Report:
- violations
- severity
- files
- recommended fix
- whether a fix is required before the milestone

Do not perform a broad rewrite automatically.

Commit only intentional fixes after verification.
```

## Suggested execution order — V2

```text
FOUNDATION / VERIFICATION
1. Container-backed end-to-end verification
2. Integration tests for ingestion + reconciliation + PostGIS + DuckDB export
3. Establish WORLDOS_ENGINE_REGISTRY.md
4. Architecture-conformance / feature-silo audit

DATA FOUNDATION
5. Third public source adapter
6. Source lifecycle / ingestion-run tracking
7. Source health / freshness / data-quality metadata
8. Reviewable uncertain entity-resolution workflow

WORLD MODEL / INTELLIGENCE SUBSTRATE
9. Formalize claim/derivation truth classes
10. Temporal and spatial query deepening
11. Relationship / knowledge-graph boundary
12. World Context Engine
13. Snapshot metadata and DuckDB analytical maturity

DETERMINISTIC INTELLIGENCE
14. Constraint Engine
15. Decision Support boundary
16. Event / change-detection / alert boundary
17. Deterministic analytics
18. Evaluation Engine / regression discipline

ADVANCED EVIDENCE
19. Multimodal evidence boundary
20. API/resource-budget controls

AI — ONLY AFTER DETERMINISTIC PREREQUISITES
21. Evidence-bound AI explanation layer

ADVANCED MODELING — ONLY WHEN DATA JUSTIFIES IT
22. Anomaly detection
23. Scenario engine
24. Simulation
25. Prediction

AGENTS — LAST
26. Agent readiness gate
27. One bounded evidence-required workflow agent only if every prerequisite is real

PLATFORM / MILESTONE
28. Frontend/Cesium improvements that expose deterministic WORLDOS capabilities
29. Security/privacy/governance hardening
30. Observability/performance hardening
31. Final architecture-conformance review
32. Documentation/checkpoint/commit

Do not interpret this list as a requirement to fully implement every engine before any vertical slice.

The architecture may remain interface-only for future engines.

A capability should move from SPECIFIED → INTERFACE_ONLY → PARTIALLY_IMPLEMENTED → IMPLEMENTED → VERIFIED only when evidence supports the status.
```

## V2 milestone rule

```text
A milestone is not complete because the UI looks complete.

A WORLDOS milestone is complete when:
- the relevant engine contract is explicit,
- deterministic behavior exists where claimed,
- evidence/provenance is preserved,
- tests verify the behavior,
- known limitations are documented,
- the engine registry reflects reality,
- progress contains one exact next task.
```
