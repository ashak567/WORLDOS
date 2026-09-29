# WORLDOS

WORLDOS is an evidence-first world model: it stores source data as entities, observations, events, relationships, geometries, and time intervals before it exposes maps, models, or AI explanations.

## First vertical slice

The first slice ingests an actual public World Bank population series and country metadata, persists its evidence and provenance in PostgreSQL/PostGIS, and exposes deterministic temporal, spatial, context, and analytics queries through FastAPI. The React/Cesium client consumes those queries; it is not the system of record.

```powershell
docker compose up --build
```

Then run an ingestion (the database needs to be running):

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/ingest/world-bank/population/IND
```

The API documentation is at `http://localhost:8000/docs`; the client is at `http://localhost:5173` when started from `frontend`.

See [WORLDOS_ARCHITECTURE.md](WORLDOS_ARCHITECTURE.md) for the durable boundaries and [WORLDOS_PROGRESS.md](WORLDOS_PROGRESS.md) for the concrete checkpoint.

