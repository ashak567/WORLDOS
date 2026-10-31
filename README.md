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

## Local assistant

The assistant uses the local Ollama service and the CPU Whisper `tiny` model. It does not send audio or questions to a cloud model. Start Ollama and download the default text model once:

```powershell
ollama serve
ollama pull llama3.2:3b
docker compose up --build
```

The API container downloads the Whisper `tiny` model the first time local transcription is used and keeps it in the `worldos-model-cache` Docker volume. The assistant accepts microphone recordings up to 5 MB; typed questions remain available if microphone access or a local speech service is unavailable. Change `WORLDOS_OLLAMA_MODEL` in `.env` to use a different model already installed in Ollama.

See [WORLDOS_ARCHITECTURE.md](WORLDOS_ARCHITECTURE.md) for the durable boundaries and [WORLDOS_PROGRESS.md](WORLDOS_PROGRESS.md) for the concrete checkpoint.

