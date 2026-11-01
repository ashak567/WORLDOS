# ADR 0003: ElevenLabs hosted assistant

## Status
Accepted

## Context

The local Ollama and Whisper path made voice assistance depend on laptop CPU, memory, and model downloads. The user chose ElevenLabs for both assistant intelligence and voice.

## Decision

- Use an authenticated ElevenLabs conversational agent for speech recognition, reasoning, text, and spoken responses.
- Keep the API key on the WORLDOS API and return only a short-lived WebRTC token to the browser.
- Give the agent two client tools: fetch a bounded, sourced map context on demand and change visibility of allowlisted map layers.
- Limit agent conversations upstream to 10 per day and five minutes each; also limit session-token requests in the API.
- Remove local Ollama and Whisper requirements from the assistant path.

## Consequences

- Voice and chat are processed by ElevenLabs. Scoped map context is shared only when the agent invokes its tool.
- Voice sessions consume the account's plan quota. The agent is capped at 10 conversations per day and five minutes per session; WORLDOS allows six session-token requests per client address per hour per API process.
- The API key and agent ID must be configured for local Compose and the deployed API service. No speech or agent conversation is started as part of setup.
