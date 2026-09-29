# WORLDOS progress

## Checkpoint: reconciled country geometry + analytical export

**Date:** 2026-09-29
**Branch:** `main`
**Status:** implemented; local contract tests passed

### Completed

- Postgres/PostGIS schema for source, entity, entity identifier, geometry, time interval, evidence, provenance, observation, event, and relationship facts.
- A source-aware, idempotent write boundary; spatial, temporal, context, and deterministic population-change queries.
- World Bank public-data adapter for `SP.POP.TOTL` and country metadata, with stable IDs, evidence locator/hash, and recorded transformation.
- Conservative entity-resolution rule: only matching publisher identifiers auto-merge.
- DuckDB Spatial analytical boundary and future scenario/prediction/simulation/anomaly/AI contracts.
- FastAPI endpoints and typed Pydantic contracts.
- Natural Earth Admin 0 country-polygon adapter, reconciled with World Bank through explicit ISO-3 identifiers rather than names.
- React/Cesium presentation shell that displays deterministic observations, fetched source geometry, and evidence links.
- Explicit Postgres-to-DuckDB analytical snapshot export command: `python -m app.export`.
- Contract test covering the public-data mapping and false-merge guard.
- Verified the World Bank adapter against the live 2023 India record (`1,438,069,596`).
- Verified the Natural Earth adapter against the live India `Polygon` feature and retained the hash of the fetched collection as evidence.

### Not claimed as complete

- No asynchronous job runner, source scheduling, or production deployment configuration.
- No implemented prediction, simulation, anomaly, AI, or agent behavior. Interfaces exist to prevent these from bypassing provenance later.
- The local Docker daemon was unavailable, so the PostGIS container integration path is documented but not yet run in this checkout.

### Next task

Start the PostGIS stack, ingest World Bank and Natural Earth for several ISO-3 countries, and add container-backed integration tests covering source reconciliation, polygon spatial queries, and DuckDB snapshot export. Then add a third independent source adapter before considering model behavior.

