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

## Assistant

The voice and chat assistant uses an authenticated ElevenLabs agent for speech recognition, reasoning, and spoken answers. Its API key stays in the Git-ignored root `.env.local`; Docker Compose passes it only to the API container. The agent can request a bounded, sourced summary of the current map and can toggle only allowlisted map layers. It has a 10-conversation daily limit, a 5-minute session limit, and WORLDOS issues at most six session tokens per client address per hour.

Starting a conversation sends voice and text to ElevenLabs. WORLDOS map context is sent only when the agent calls its map-context tool. This avoids running local Ollama and Whisper models on the laptop. Update the agent's name, prompt, model, and voice in ElevenLabs; keep `WORLDOS_ELEVENLABS_AGENT_ID` and `ELEVENLABS_API_KEY` in `.env.local` for local Compose runs and in the API host's private environment for deployment.

See [WORLDOS_ARCHITECTURE.md](WORLDOS_ARCHITECTURE.md) for the durable boundaries and [WORLDOS_PROGRESS.md](WORLDOS_PROGRESS.md) for the concrete checkpoint.

