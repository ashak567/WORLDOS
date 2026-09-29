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

- **Temporal engine:** filters `TimeInterval.starts_at` and records precision rather than treating a year as an unscoped timestamp.
- **Spatial engine:** PostGIS `ST_DWithin` and `ST_Contains` run against evidence-backed geometry. Country points, boundary polygons, and event epicenters remain distinct geometry kinds.
- **Context engine:** returns one entity with observations, relationships, and their evidence locators.
- **Knowledge graph:** `relationships` is a normal relational edge table with evidence and temporal validity. It can later be projected into a graph index without splitting truth ownership.
- **Deterministic analytics:** window functions compute population changes from observations. DuckDB is available only for a versioned analytical export.

## Deliberately deferred interfaces

Scenario constraints, prediction, simulation, anomaly detection, and evidence-bound AI reasoning are contracts in `backend/app/interfaces.py`, not fake implementations. An implementation must accept a deterministic input/result and return cited evidence IDs, assumptions, and a model/version. Agents come after those capability contracts and may only call them.

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

`docker compose up --build` starts PostGIS and FastAPI. Call `POST /ingest/world-bank/population/IND?year=2023`, `POST /ingest/natural-earth/country/IND`, and `POST /ingest/usgs/earthquake/us6000m0xm`; countries reconcile through ISO-3 while earthquakes resolve through USGS event IDs and spatial containment. Use `/observations`, `/events`, `/geometries`, `/spatial/entities`, `/entities/{id}/context`, `/claims`, and `/analytics/population/{id}/growth`. The React/Cesium client reads the deterministic data and displays the fetched geometry with its evidence-backed context.

## Decisions and consequences

PostGIS is chosen over a globe-centric document store because spatial predicates, relationships, temporal joins, and provenance need transactionally consistent joins. DuckDB is kept outside the write path to retain its fast local analytical workflow without creating two truth stores. Source IDs, not normalized names, control automatic fusion; this creates more review work but prevents misleading false merges.

