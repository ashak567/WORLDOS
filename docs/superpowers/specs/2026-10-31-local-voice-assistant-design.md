# WORLDOS Local Voice Assistant and Travel Skill

## Status

Draft for user review. This document records the approved product direction; implementation has not started.

## Purpose

Add a conversational voice assistant to WORLDOS, with travel planning as a secondary skill. The assistant should feel natural and lightly witty while keeping claims tied to WORLDOS data, sources, and freshness.

The intended platform is the existing Windows-accessible React and FastAPI application. Atticus Mac is MIT-licensed, but its repository is a macOS 26+ desktop app built around Swift, Apple speech and native Mac controls. It is not a drop-in library or service for WORLDOS. WORLDOS will adapt the interaction and safety ideas rather than package the full Mac application. See the [Atticus README](https://github.com/SaarthurR/atticus-mac/blob/main/README.md) and [license](https://github.com/SaarthurR/atticus-mac/blob/main/LICENSE).

## User experience

- Add a push-to-talk entry point to the WORLDOS HUD and a compact assistant panel.
- Show the recognized words before the assistant invokes tools, with an edit option.
- Display each answer and read it aloud. Text remains available if microphone or speech support is unavailable.
- Use a warm, conversational voice with occasional understated humor. Do not force jokes, claim human feelings or experiences, or joke about emergencies, disasters, or casualties.
- Let the user explicitly save or remove low-sensitivity preferences such as preferred travel pace or photo interests. Do not retain full conversations by default.

## Architecture

1. The browser records speech after an explicit user action and submits it to the local WORLDOS API.
2. A local speech-recognition runtime transcribes it. Use a small local Whisper model as the first candidate; benchmark CPU performance before choosing its model size. Do not silently fall back to cloud transcription.
3. A new assistant endpoint in FastAPI gathers relevant information through existing typed WORLDOS query and routing surfaces. The model runs through Ollama, which is installed on the user's PC and will need to be started and configured.
4. Model requests use a narrow, explicit tool list. Initial tools can read current map context, source status, selected entity details, and route results, and can change map focus or layer visibility. They cannot mutate stored WORLDOS facts, run shell commands, send messages, or make purchases.
5. The answer returns as structured text with evidence IDs, source names, retrieval times, and stale/unavailable state. The browser displays it and uses local speech synthesis to read it.

The implementation follows the existing `EvidenceBoundReasoner` contract in `backend/app/interfaces.py`. The model explains deterministic query results; it does not become a second source of truth. For requests with no adequate evidence, it says what is missing and asks a targeted follow-up or abstains.

## Travel skill

Travel is a named, optional skill, not the main assistant mode. Its first useful version should:

- Ask for destination, time, travel mode, and relevant preferences such as photography interests.
- Rank candidate photo locations using sourced place and geographic data plus deterministic factors such as viewpoint, sun angle, and available weather.
- Offer route alternatives and explain the trade-offs.
- Label traffic as live only when a current, attributable traffic source supports it. Otherwise label it estimated or unavailable; do not invent traffic observations.

The current WORLDOS route planner focuses on strategic aviation and maritime routes. The photo-trip skill therefore needs its own pedestrian/driving route capability. Source coverage, usage limits, and attribution must be checked before choosing free place, routing, weather, and traffic providers. No paid provider is required for the initial design.

## Rollout

### Stage 0: restore trustworthy local signals

Fix the satellite timezone failure and the unavailable news/climate adapters seen in the local run. The assistant must represent unavailable feeds accurately and must not imply those feeds are working.

### Stage 1: local voice assistant

Add local speech transcription, Ollama-backed reasoning, the assistant panel, evidence-bound answers, source freshness, safe map-view actions, and explicit opt-in preferences. Keep all reasoning and speech services local by default.

### Stage 2: travel skill

Add place discovery, photo-time and weather context, walking/driving routes, and traffic status behind the same assistant boundary. Use deterministic scoring for recommendations and have the model explain the results.

## Failure and safety behavior

- If Ollama, local transcription, or WORLDOS sources are unavailable, show the specific unavailable state and preserve typed input where possible.
- Never send audio or prompts to a cloud model as an automatic fallback.
- Validate any structured tool request against the server's allowlist before running it.
- Keep personal preferences separate from canonical WORLDOS entities and observations.
- Attribute each externally sourced recommendation and preserve its freshness timestamp.

## Verification plan

- Unit checks for tool allowlisting, evidence citation requirements, and refusal to invent live traffic when its source is unavailable.
- Local integration checks for transcription, Ollama timeouts, source failures, and text-only fallback.
- Browser checks for microphone permission denial, transcript correction, keyboard access, and stopping speech playback.
- Travel checks for deterministic ranking from the same inputs and correct labels for live, estimated, and unavailable traffic.

## Known trade-offs

- Local inference avoids per-request API charges and keeps audio local, but answer quality and latency depend on installed models and PC hardware.
- The local speech model requires an initial download and uses CPU/GPU resources.
- Public free geographic feeds may have uneven coverage, limits, or stale traffic data; the UI must expose those limits.
