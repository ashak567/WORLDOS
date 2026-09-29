---
name: worldos-engineering
description: Foundational engineering rules, data boundaries, and architectural discipline for WORLDOS. Enforces evidence-first principles, operational vs analytical database separation, and strict provenance.
---

# WORLDOS Core Engineering Rules & Architecture Discipline

WORLDOS is an AI-powered real-world intelligence platform that models reality from deterministic evidence, spatial topology, temporal dynamics, and verified entity relationships.

It is **NOT**:
- A travel app
- A map or navigation app
- A satellite tracker
- An OSINT-only platform
- A "God's Eye View" (GEV) clone
- A globe-first visualization demo
- An LLM chat wrapper

---

## The 20 Fundamental Engineering Rules

### 1. Intelligence Platform Primacy
WORLDOS exists to ingest, reconcile, analyze, and reason about physical world state across time and space. Presentation, visualizations, and dashboards are clients of the intelligence engine, never the engine itself.

### 2. Never Turn WORLDOS into a Globe-First Application
The core engine operates completely headlessly and deterministically. A 3D globe or 2D map is merely one projection of the world model state. Core logic, tests, and data engines must never depend on UI visualization components or 3D rendering loops.

### 3. Never Copy God's Eye View (GEV) Architecture Wholesale
GEV architectures often prioritize cinematic visual presentation, centralized monolithic state, or ungrounded mock streams. WORLDOS builds from verified primitives: registered sources, raw observations, evidence, entity resolution, and topological relationships.

### 4. Cesium is Visualization, Not the Intelligence Core
CesiumJS / Resium are rendering clients. They consume GeoJSON, CZML, or REST/WebSocket streams produced by the backend engines. Never place ingestion, entity resolution, data fusion, or coordinate geometry validation inside the Cesium client layer.

### 5. PostgreSQL / PostGIS is the Operational World-State Source of Truth
All transactional entity mutations, current live states, canonical entity identity registries, spatial topology relationships (ST_Contains, ST_Intersects, ST_DWithin), and authoritative provenance graphs reside in PostgreSQL with PostGIS.

### 6. DuckDB is for Analytical Workloads
DuckDB is an in-process, columnar read boundary. It is used to generate time-series rollups, historical analytical aggregates, Parquet exports, and high-performance analytical queries without placing heavy analytical scan locks on the transactional PostGIS database. Never collapse PostgreSQL and DuckDB into a single database without formal architectural justification.

### 7. Evidence and Provenance are Mandatory
Every externally sourced claim, entity state, or observed value must cite:
- `source_id`: Explicit registered source identifier.
- `evidence_id`: Reference to the immutable raw record or cryptographic hash.
- `observed_at` / `valid_from` / `valid_until`: Temporal anchors.
- `confidence`: Confidence score in $[0.0, 1.0]$.
Silent mutation of world-state without provenance is strictly prohibited.

### 8. Strict Epistemological Taxonomy
Every state assertion in WORLDOS must be classified into exactly one epistemological tier:
- `OBSERVED`: Directly witnessed and extracted from a registered source without transformation.
- `DERIVED`: Mathematically or topologically computed from observed data via deterministic rules (e.g., spatial containment, density, aggregate counts).
- `INFERRED`: Probabilistically deduced through heuristics or fusion algorithms.
- `PREDICTED`: Projected into a future time horizon based on historical or physical models.
- `SIMULATED`: Generated within a synthetic or scenario sandbox.

### 9. Deterministic Computation Over LLM Guessing
Spatial queries, distance calculations, coordinate conversions, statistical metrics, graph connectivity, and containment tests must be computed deterministically with PostGIS, GEOS, Shapely, DuckDB, or NetworkX. Never ask an LLM to calculate geographic distances, spatial containment, or numerical aggregations.

### 10. LLMs Reason Over WORLDOS Data, Never Fabricate Truth
LLMs are inference and synthesis tools that operate downstream of deterministic engines. An LLM may synthesize a situation report, explain an anomaly, or formulate a structured query, but it must cite deterministic WORLDOS evidence IDs. It is never the authoritative data store.

### 11. AI Agents are a Final Orchestration Layer
Agents reside at the top of the processing stack, after:
$$\text{Data Sources} \to \text{Ingestion} \to \text{World Model} \to \text{Data Fusion} \to \text{Spatial} \to \text{Temporal} \to \text{Knowledge} \to \text{Evidence} \to \text{Analytics} \to \text{Context} \to \text{Reasoning} \to \text{Agents}$$
Never invert this dependency chain. Agents consume context and invoke engine tools; they do not serve as the storage or ingestion foundation.

### 12. Engines Expose Clear Contracts and Interfaces
Each subsystem (Ingestion, Resolution, Spatial, Temporal, Knowledge Graph, Analytics) must expose strongly-typed interfaces (Pydantic v2 schemas, abstract base classes, or clean service contracts). Engines must not directly reach into each other's internal storage representations.

### 13. Source Adapters for All Ingestion
Every external data provider (World Bank, USGS, Copernicus, Flight Radar, OpenStreetMap) must have a dedicated source adapter that:
- Normalizes raw incoming payloads into canonical WORLDOS domain schemas.
- Records raw ingestion payloads and provenance metadata.
- Handles rate-limiting, retries, and schema validation failures deterministically.

### 14. No Feature-Specific Data Silos
If a new data feed contains entities (e.g., airports, vessels, weather events), they must be mapped to the canonical `Entity`, `Observation`, `Event`, or `Relationship` schemas. Do not invent disconnected ad-hoc tables when the core world model can represent the domain.

### 15. Tests Must Accompany Core Engine Changes
No code touching data modeling, spatial topology, entity resolution, database migrations, or ingestion adapters may be merged without comprehensive unit and integration tests. Tests must verify deterministic behavior and edge cases (e.g., antimeridian wrapping, null coordinates, collision resolution).

### 16. Preserve Architectural Boundaries
Maintain clear directory separation:
- `backend/app/models/`: Domain schemas and data contracts.
- `backend/app/db/`: Database connection, session management, and migrations.
- `backend/app/engines/`: Deterministic domain engines (spatial, temporal, fusion, analytics).
- `backend/app/adapters/`: External data source ingestion clients.
- `backend/app/api/`: REST/WebSocket routing and presentation contracts.
- `frontend/src/`: UI components and presentation layers.

### 17. Never Silently Weaken Provenance or Confidence
When merging conflicting observations during entity resolution, never drop contradictory evidence or fabricate an average without recording the conflict. If confidence degrades due to stale or conflicting data, it must be explicitly reflected in the confidence score and logged.

### 18. Never Fabricate Real-World Data
Test fixtures must be clearly demarcated as synthetic or mocked. In production or live environments, mock data must never be intermingled with real world-state without being tagged as `SIMULATED`.

### 19. Strict Data Privacy and Authorized Access
Never ingest or store private, unauthorized, or confidential personal information. Ingestion pipelines must respect terms of service, robots.txt, and rate limits for all external providers.

### 20. Document Every Major Architectural Decision
All non-trivial architectural decisions, schema evolutions, or engine boundaries must be recorded in Architecture Decision Records (ADRs) and reflected in `WORLDOS_ARCHITECTURE.md` and `WORLDOS_PROGRESS.md`.

---

## Epistemological Code Convention

When writing Pydantic models or database records, always include:

```python
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any

class EpistemicTier(str, Enum):
    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"
    INFERRED = "INFERRED"
    PREDICTED = "PREDICTED"
    SIMULATED = "SIMULATED"

class ProvenanceRecord(BaseModel):
    source_id: str = Field(..., description="Registered unique source identifier")
    source_name: str
    observed_at: datetime
    fetched_at: datetime
    epistemic_tier: EpistemicTier = EpistemicTier.OBSERVED
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_hash: Optional[str] = None
    raw_payload_ref: Optional[str] = None
```
