# ADR 0002: Reliable Live Feed Caching and Position Linkage

## Status
Accepted

## Context

Aircraft positions depend on authenticated OpenSky requests, which can time out independently of credential validity. Satellite positions are propagated from CelesTrak orbital elements, but an in-memory cache disappears on service restart. Historical position queries also need to link each observation to the geometry produced by the same evidence and timestamp.

## Decision

- Report OpenSky connection and server failures separately from authentication failures.
- Cache the latest successful CelesTrak active catalog in PostgreSQL and serve it as stale data when the provider is unavailable.
- Match position observations to geometry using entity, evidence, geometry kind, and observation time.
- Batch aircraft and satellite map markers with Cesium billboard collections.

## Consequences

### Positive

- Temporary provider outages no longer masquerade as bad credentials, and a service restart can still serve a previously retrieved satellite catalog.
- Historical positions remain tied to their own evidence and observed time.
- High-volume aircraft and satellite markers use fewer Cesium objects.

### Negative

- A first deployment with an unavailable CelesTrak provider has no catalog to serve until one successful retrieval is cached.
- Cached satellite elements can become stale during provider outages; the API reports feed freshness so clients can label it.
- The active CelesTrak group is not a complete historical or inactive satellite catalog.
