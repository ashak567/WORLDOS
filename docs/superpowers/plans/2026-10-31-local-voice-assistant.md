# WORLDOS Local Voice Assistant and Travel Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Each task ends with its checks before proceeding.

**Goal:** Restore truthful live context first, then add a local, evidence-bound voice assistant to WORLDOS, with photo trip planning as a later optional skill.

**Architecture:** Keep deterministic WORLDOS queries as the source of facts and use the existing `EvidenceBoundReasoner` contract only to explain their results. Add local transcription and Ollama behind a narrow FastAPI assistant boundary, then a browser push-to-talk panel. Deliver travel separately after free data sources and attribution are verified.

**Tech Stack:** Python/FastAPI, Pydantic, existing pytest suite, React/TypeScript/Vite, existing map and route APIs, local Ollama, local speech recognition, browser speech synthesis.

**Spec:** `docs/superpowers/specs/2026-10-31-local-voice-assistant-design.md`

## Global Constraints

- No paid provider or per-request cloud service is required for v1.
- Audio and prompts stay local; there is no silent cloud fallback.
- The assistant may only use allowlisted read-only WORLDOS data tools and safe map-view actions.
- It must provide sources and retrieval times, report stale or unavailable feeds, and abstain when evidence is inadequate.
- Do not retain full conversations; saved low-sensitivity preferences require explicit user action.
- Travel is a secondary skill and must label traffic live, estimated, or unavailable according to evidence.
- Keep existing patterns and dependencies where they fit; do not restructure the large `main.py` as part of this feature.

---

## File map

- `backend/app/ingestion/satellites.py`: normalize timezone-aware timestamps at the shared satellite conversion boundary.
- `backend/app/ingestion/live_context.py`: parse and validate the existing public news and monthly climate feeds.
- `backend/tests/test_satellites.py`, `backend/tests/test_live_context.py`: offline regression checks with small provider-response fixtures.
- `backend/app/assistant.py`: local reasoner and transcription adapters, request validation, tool allowlist, evidence envelope, and no-cloud failure behavior.
- `backend/app/main.py`: register assistant request/response and bounded raw-audio endpoints, reusing existing WORLDOS query functions.
- `backend/app/config.py` and `backend/.env.example`: local Ollama/transcription settings and safe defaults; do not store secrets in source.
- `backend/tests/test_assistant.py`: tool rejection, evidence requirements, unavailable services, and text-only behavior.
- `frontend/src/api.ts`: typed assistant request and response API calls.
- `frontend/src/components/AssistantPanel.tsx`: push-to-talk UI, editable transcript, answer/citations, mic errors, and stop-speaking control.
- `frontend/src/App.tsx`, `frontend/src/components/HudBar.tsx`, `frontend/src/styles.css`: mount the panel and provide accessible HUD entry point and styling.
- No frontend test runner is installed. Verify panel behavior in the local browser unless a test runner is separately approved and added.
- Travel-stage files are selected only after source/licensing review; no provider or package is preselected by this plan.

## Stage 0: restore trustworthy local signals

### Task 1: Reproduce and fix satellite time normalization

**Files:** Modify `backend/app/ingestion/satellites.py`; create `backend/tests/test_satellites.py`.

**Interfaces:** Keep `satellite_to_api_state(record: SatelliteRecord) -> dict[str, Any]` unchanged. Normalize `record.epoch` and `record.elements_epoch` to UTC before age subtraction; naive values are interpreted as UTC, aware values are converted to UTC.

- [ ] Add a regression test with a naive element epoch and UTC-aware observation epoch; assert age in hours is calculated and never raises `TypeError`.
- [ ] Add a test with both timestamps aware but using different offsets; assert the UTC-normalized age.
- [ ] Run `python -m unittest discover -s tests -p test_satellites.py -v` in the backend container and confirm the failing case reproduces the reported exception.
- [ ] Apply normalization once at the shared API-state conversion boundary and rerun the focused test.
- [ ] Run `python -m unittest discover -s tests -p test_satellites.py -v` and `python -m unittest discover -s tests -p test_multidomain_ingestion.py -v` in the backend container.

### Task 2: Make news and climate adapters match their real response formats

**Files:** Modify `backend/app/ingestion/live_context.py`; create `backend/tests/test_live_context.py`.

**Interfaces:** Preserve `fetch_global_news(now=None)` and `fetch_global_climate(now=None)` return contracts and `LiveContextFeedError` behavior.

- [ ] Capture representative, sanitized response bodies from the named public endpoints or their official documented formats; save minimal fixtures with no credentials.
- [ ] Add parser tests for a valid news response, empty news result, valid monthly climate rows, and malformed/unavailable responses.
- [ ] Run `python -m unittest discover -s tests -p test_live_context.py -v` in the backend container and confirm parser failures before changing production parsing.
- [ ] Parse the documented provider shape, validate required fields and timestamps, and preserve explicit unavailable status on invalid data.
- [ ] Run `python -m unittest discover -s tests -p test_live_context.py -v` and `python -m unittest discover -s tests -p test_multidomain_ingestion.py -v` in the backend container.
- [ ] With the local API available, verify `/live/context` reports each feed's actual status, retrieved time, and record count. Do not label an unavailable feed fresh.

## Stage 1: local voice assistant

### Task 3: Select a local transcription runtime using a repeatable benchmark

**Files:** Create `backend/app/assistant.py` and `backend/tests/test_assistant.py`; modify `backend/app/main.py`, `backend/app/config.py`, `backend/pyproject.toml`, and `backend/Dockerfile` only for the measured local runtime and its setup.

**Interfaces:** `POST /assistant/transcribe` accepts a raw, bounded browser audio body with an allowlisted audio content type and returns `{text: str, language: str | None, service_status: str}`. It must not make network requests after model installation.

- [ ] Compare a small local Whisper candidate on the target Windows PC using the same short sample, measuring install footprint, model download size, CPU latency, and compatibility with the current Docker deployment.
- [ ] Select the smallest candidate that produces usable transcription at acceptable latency; document the chosen model and one-time download command in the existing setup documentation.
- [ ] Add tests for accepted audio types, oversized request rejection, empty audio, and explicit model-unavailable response.
- [ ] Enforce the audio size/duration limit before decoding, implement transcription with the measured runtime, and verify inference performs no network access.
- [ ] Run `python -m unittest discover -s tests -p test_assistant.py -v` in the backend container.
- [ ] Do not add a cloud speech API or automatic cloud fallback. If no candidate fits current deployment, keep typed assistant input and report voice unavailable.

### Task 4: Add the local evidence-bound assistant service

**Files:** Create `backend/app/assistant.py`; modify `backend/app/main.py`, `backend/app/config.py`, `backend/.env.example`; create `backend/tests/test_assistant.py`.

**Interfaces:** Add `POST /assistant/answer` taking `{question: str, context: AssistantContext | None}` and returning `{answer: str, evidence: EvidenceItem[], actions: AssistantAction[], service_status: str}`. `EvidenceItem` contains `evidence_id`, `source_name`, `retrieved_at`, and `freshness`; `AssistantAction` is a validated `focus_entity` or `set_layer_visibility` instruction. Keep `EvidenceBoundReasoner.answer(question, deterministic_result, evidence_ids)` as the reasoning contract.

- [ ] Write tests that reject unknown tool names and arguments, require cited evidence IDs to exist in the deterministic result, and return an explicit unavailable response when Ollama is unreachable.
- [ ] Write tests proving that tools cannot mutate canonical entities, invoke shell commands, send messages, or buy anything.
- [ ] Implement only allowlisted readers for current map context, source status, selected entity details, and route results; allow only safe map focus/layer visibility actions through validated response instructions.
- [ ] Configure Ollama through a local URL/model setting with bounded timeouts. Validate local-only defaults and do not log raw audio or full prompts.
- [ ] Return concise abstention text if no relevant evidence is available; pass source freshness through without allowing the model to rewrite it.
- [ ] Run `python -m unittest discover -s tests -p test_assistant.py -v`, then the backend suite in the backend container.

### Task 5: Add browser push-to-talk and text-first fallback

**Files:** Create `frontend/src/components/AssistantPanel.tsx`; modify `frontend/src/api.ts`, `frontend/src/App.tsx`, `frontend/src/components/HudBar.tsx`, `frontend/src/styles.css`.

**Interfaces:** Frontend API calls `transcribeAssistantAudio(audio: Blob): Promise<Transcript>` and `answerAssistant(question: string, context?: AssistantContext): Promise<AssistantAnswer>`. The panel receives current selected item, visible layers, and map context through props; it emits only server-validated map-view actions to existing app state handlers.

- [ ] Build the panel with push-to-talk, editable transcript, send/cancel, visible answer and evidence, explicit mic permission/error text, and stop-speaking control.
- [ ] Record only during a user-started push-to-talk action with `MediaRecorder`, send the blob to `/assistant/transcribe`, and display the editable transcript. Keep a typed question field available when microphone or local speech is unavailable.
- [ ] Speak the answer with native `speechSynthesis`; text and citations remain visible if synthesis is unsupported or stopped.
- [ ] Keep the microphone action user initiated; do not record in the background. Provide keyboard operation, focus management, and accessible labels/status announcements.
- [ ] Mount the panel from the HUD without adding a second assistant state store; persist no conversation by default.
- [ ] Verify mic-denied, transcript-edit, text-only, Ollama-timeout, citation-display, keyboard, and stop-speaking flows in the local browser.
- [ ] Run the frontend production build and existing frontend checks, if present.

### Task 6: Add explicit opt-in preference storage

**Files:** Modify `frontend/src/components/AssistantPanel.tsx`; test the preference allowlist in that module's browser interaction.

**Interfaces:** Keep an allowlisted `TravelPreferences` object in browser `localStorage`; include it only when the user explicitly saves preferences and accepts the save prompt. No server-side preference or conversation endpoint is added.

- [ ] Define the small allowlist (travel pace, photography interests) and validate values and lengths before storing.
- [ ] Show the exact values to be saved, require a save action, and provide a clear per-item removal action.
- [ ] Verify a fresh browser profile has no preferences and clearing a saved item removes it from subsequent assistant requests.

## Stage 2: optional travel skill (separate implementation approval)

### Task 7: Verify free data sources and define honest coverage

**Files:** Add `docs/superpowers/research/` source/attribution notes before implementation; provider code and config are chosen only after this review.

- [ ] For candidate place, pedestrian/driving route, weather, and traffic sources, record official endpoint, free-use limits, attribution text, redistribution rules, coverage, and whether traffic is truly live.
- [ ] Reject sources whose terms do not permit the planned use or whose current traffic observations cannot be distinguished from estimates.
- [ ] Present the source matrix and obtain approval before adding provider dependencies or keys.

### Task 8: Implement deterministic photo-trip recommendations

**Files:** Add a focused travel module under `backend/app/` and tests; extend the assistant allowlist and panel only after Task 7 approval.

**Interfaces:** `plan_photo_trip(destination, time_window, travel_mode, preferences) -> TravelPlan` returns ranked sourced places, deterministic score factors, route alternatives, weather context, traffic status (`live | estimated | unavailable`), citations, and retrieval times.

- [ ] Add deterministic ranking tests proving identical inputs and source data produce identical rankings and that unavailable sources never produce live labels.
- [ ] Implement place and route retrieval only through approved free sources, with attribution and explicit failure/staleness states.
- [ ] Calculate photo timing factors only from available time/location inputs; expose missing factors rather than filling them with guesses.
- [ ] Let the model explain the deterministic travel result without changing scores, source labels, or traffic status.
- [ ] Run focused backend and browser checks for ranking stability, source outage, and live/estimated/unavailable labels.

## Self-review against the spec

- Voice UX, local-only speech, editable transcript, typed fallback, natural but restrained humor, citations, freshness, safe tools, explicit preferences, and no chat retention map to Tasks 3–6.
- Stage 0 satellite and news/climate reliability maps to Tasks 1–2.
- Travel destination, photo location ranking, route options, weather, traffic freshness, attribution, and free-provider review map to Tasks 7–8.
- The plan deliberately leaves provider selection contingent on official terms and current coverage; this is required by the spec and avoids an unverified licensing decision.
- No implementation or tests have been run as part of writing this plan.
