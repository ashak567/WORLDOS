# ADR 0001: Local Evidence-Bound Assistant

## Status
Accepted

## Context

WORLDOS needs a conversational interface that can explain the current map and accept voice input without turning model output into an unverified data source. The project is intended to run locally on student hardware and should not require paid AI APIs or retain conversations by default.

## Decision

- Run language reasoning through a locally hosted Ollama model and transcription through local Whisper. Do not send prompts or recordings to a cloud model or speech provider.
- Build the assistant's map context from WORLDOS records on the server, bound by the selected entity or visible map area. Keep source IDs and retrieval times alongside answers.
- Treat model output as explanation only. Accept only validated map-view actions from a small allowlist; the assistant cannot mutate canonical records or invoke arbitrary tools.
- Record audio only after a user starts push-to-talk. Keep typed input available, speak responses with browser-native speech synthesis, and do not persist conversations by default.
- Store optional travel preferences in browser storage only after the user explicitly saves them.

## Consequences

### Positive

- Prompts and voice recordings stay on the user's local machine, with no per-request AI API charge.
- Answers can be checked against the same evidence and freshness metadata used by the map.
- The model cannot change source records or perform arbitrary actions.

### Negative

- Reasoning and transcription require locally installed models and enough memory/compute; an unavailable or slow model leaves typed, evidence-backed responses available where possible.
- The assistant is not available from a cloud deployment unless its local-model boundary is redesigned or the model runs on a separately provisioned host.
- Travel recommendations remain explanatory and map-scoped until approved, sourced routing and place providers are implemented.
