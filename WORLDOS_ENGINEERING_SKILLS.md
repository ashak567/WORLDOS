# WORLDOS Engineering Skills Manifest

This manifest documents the agent skills curated, audited, and configured for the WORLDOS engineering environment.

In accordance with WORLDOS architecture and security requirements, all third-party skills were reviewed from the live [VoltAgent Awesome Agent Skills](https://github.com/VoltAgent/awesome-agent-skills) catalog. Vendor-locking, unmaintained, or purely generative "AI slop" skills were rejected. High-value engineering practices from official maintainers (Supabase, DuckDB, Trail of Bits, Microsoft, TestMu AI, Sentry) and core WORLDOS domain constraints have been formalized into project-local skills in `.agents/skills/`.

---

## 1. Skill Catalog by Category

### CORE

| Skill | Source Repository | Original Maintainer | Purpose | Subsystem Supported | Scope | Security Review | Why Needed | Mandatory / Optional |
|---|---|---|---|---|---|---|---|---|
| `worldos-engineering` | Project-Local (`.agents/skills/`) | WORLDOS Core Architecture Team | Enforces 20 core engineering rules: intelligence-first, evidence-first, database boundaries, epistemic classification, and "agents last" rule. | System-wide / All Engines | Workspace | Verified / Safe | Establishes non-negotiable architectural boundaries and prevents degradation into a travel app, map clone, or AI wrapper. | **Mandatory** |
| `worldos-git-adr-discipline` | Project-Local (`.agents/skills/`) | WORLDOS Core Architecture Team | Enforces conventional commits, Architecture Decision Records (ADRs), change management, and review checklists. | All Subsystems & Documentation | Workspace | Verified / Safe | Ensures architectural evolution is auditable and prevents regressions across complex multi-engine subsystems. | **Mandatory** |
| `birdview` / `ddd` | `NeoLabHQ/context-engineering-kit`, `Qiuner/birdview` | NeoLabHQ, Qiuner | Domain-Driven Design (aggregates, bounded contexts) and constraint-first architectural planning. | Core Architecture & Engine Design | Reference / Global | Audited / Safe | Guides decoupling of domain logic from database and transport layers. | Optional |

### DATA

| Skill | Source Repository | Original Maintainer | Purpose | Subsystem Supported | Scope | Security Review | Why Needed | Mandatory / Optional |
|---|---|---|---|---|---|---|---|---|
| `worldos-database-architecture` | Project-Local (`.agents/skills/`) | WORLDOS Core Architecture Team | Governs dual-database separation: PostgreSQL/PostGIS (operational world-state) and DuckDB (read-only analytical boundary). | Database Layer (`backend/app/db/`) | Workspace | Verified / Safe | Prevents collapsing operational and analytical boundaries or running heavy OLAP scans on live PostGIS. | **Mandatory** |
| `worldos-source-adapters` | Project-Local (`.agents/skills/`) | WORLDOS Ingestion Team | Base adapter contract, raw payload SHA-256 hashing, rate limiting, and evidence registration. | Ingestion Pipeline (`backend/app/adapters/`) | Workspace | Verified / Safe | Standardizes all incoming real-world data pipelines and guarantees cryptographic provenance. | **Mandatory** |
| `worldos-provenance-fusion` | Project-Local (`.agents/skills/`) | WORLDOS Intelligence Team | Entity resolution hierarchy (publisher IDs first), multi-source confidence fusion, and epistemic tagging. | Fusion & Resolution Engines | Workspace | Verified / Safe | Prohibits auto-merging entities on fuzzy names alone and formalizes confidence scoring. | **Mandatory** |
| `postgres-best-practices` | `supabase/postgres-best-practices` | Supabase Engineering | Index optimization, query execution plans, connection pool sizing, and migration hygiene. | PostgreSQL Database | Reference / Global | Audited / Safe | Prevents slow unindexed queries and unsafe schema mutations in production PostgreSQL. | Recommended |
| `duckdb-analytics` | `duckdb/query`, `duckdb/attach-db` | DuckDB Foundation | High-performance Parquet scanning, columnar memory tuning, and analytical SQL. | Analytical Read Boundary | Reference / Global | Audited / Safe | Optimizes offline analytics, time-series rollups, and Parquet exports without locking operational tables. | Recommended |

### GEOSPATIAL

| Skill | Source Repository | Original Maintainer | Purpose | Subsystem Supported | Scope | Security Review | Why Needed | Mandatory / Optional |
|---|---|---|---|---|---|---|---|---|
| `worldos-spatial-engineering` | Project-Local (`.agents/skills/`) | WORLDOS Geospatial Team | PostGIS spatial SQL, WGS 84 (SRID 4326), `(lon, lat)` coordinate ordering, GiST spatial indexing, and topological predicates (`ST_Contains`, `ST_Intersects`, `ST_DWithin`). | Spatial Engine & PostGIS Layer | Workspace | Verified / Safe | Guarantees mathematically deterministic spatial containment and proximity calculations. | **Mandatory** |

### BACKEND

| Skill | Source Repository | Original Maintainer | Purpose | Subsystem Supported | Scope | Security Review | Why Needed | Mandatory / Optional |
|---|---|---|---|---|---|---|---|---|
| `modern-python-fastapi` | Project-Local (`.agents/skills/`) | Microsoft & Trail of Bits (Adapted) | Modern Python 3.11+, Pydantic v2 data contracts, FastAPI modular routing, strict type safety, RFC 7807 problem details, and asyncpg. | Backend API & Engines (`backend/app/`) | Workspace | Verified / Safe | Enforces strict data validation, non-blocking asynchronous I/O, and structured API contracts. | **Mandatory** |

### FRONTEND

| Skill | Source Repository | Original Maintainer | Purpose | Subsystem Supported | Scope | Security Review | Why Needed | Mandatory / Optional |
|---|---|---|---|---|---|---|---|---|
| `worldos-presentation-boundary` | Project-Local (`.agents/skills/`) | WORLDOS Frontend Team | React 18, TypeScript strict mode, state management, and strict constraint that CesiumJS is purely a presentation renderer, never the intelligence engine. | Frontend Client (`frontend/`) | Workspace | Verified / Safe | Enforces that UI components display provenance badges and audits without executing world-truth logic in the browser. | **Mandatory** |

### TESTING

| Skill | Source Repository | Original Maintainer | Purpose | Subsystem Supported | Scope | Security Review | Why Needed | Mandatory / Optional |
|---|---|---|---|---|---|---|---|---|
| `worldos-testing` | Project-Local (`.agents/skills/`) | TestMu AI & Trail of Bits (Adapted) | Pytest test suites, deterministic fixtures, property-based testing (Hypothesis), contract testing, and container-backed integration tests. | Test Suites (`tests/`) | Workspace | Verified / Safe | Eliminates test flakiness, verifies spatial invariants across random inputs, and tests against real PostGIS containers. | **Mandatory** |

### SECURITY

| Skill | Source Repository | Original Maintainer | Purpose | Subsystem Supported | Scope | Security Review | Why Needed | Mandatory / Optional |
|---|---|---|---|---|---|---|---|---|
| `worldos-security-threat-model` | Project-Local (`.agents/skills/`) | Trail of Bits (Adapted) | Threat modeling, SSRF prevention in source adapters, private IP blocklists, secure defaults, Pydantic `SecretStr`, and defense-in-depth. | Ingestion, API, Infrastructure | Workspace | Verified / Safe | Protects internal networks and metadata services when adapters fetch data from external endpoints. | **Mandatory** |

### OBSERVABILITY

| Skill | Source Repository | Original Maintainer | Purpose | Subsystem Supported | Scope | Security Review | Why Needed | Mandatory / Optional |
|---|---|---|---|---|---|---|---|---|
| `worldos-observability-metrics` | Project-Local (`.agents/skills/`) | Sentry & Cloud Observability Standards | Structured JSON logging, health probes (`/health/live`, `/health/ready`), Prometheus/OpenTelemetry metrics, and error tracing. | Backend API & Monitoring | Workspace | Verified / Safe | Provides real-time visibility into ingestion latency, spatial query performance, and connection pool health. | **Mandatory** |

### AI / REASONING

| Skill | Source Repository | Original Maintainer | Purpose | Subsystem Supported | Scope | Security Review | Why Needed | Mandatory / Optional |
|---|---|---|---|---|---|---|---|---|
| `grounded-reasoning-contracts` | Core Architectural Pattern | WORLDOS Architecture Team | Constrains downstream LLM inference to citing deterministic WORLDOS evidence IDs; strictly forbids hallucinating world-state or computing coordinates. | Context & Reasoning Layer | Workspace / Future | Verified / Safe | Ensures AI is an explanation and reasoning client, never the data authority. | **Mandatory** (When AI layer is reached) |

### FUTURE / OPTIONAL

| Skill | Source Repository | Original Maintainer | Purpose | Subsystem Supported | Scope | Security Review | Why Needed | Mandatory / Optional |
|---|---|---|---|---|---|---|---|---|
| `orbital-mechanics-spg4` | Future Domain Plugin | Astrodynamics Standards | SGP4 satellite propagation and ephemeris computation. | Satellite Ingestion Engine | Planned | Pending Audit | Future satellite tracking without LLM guessing. | Optional |
| `aviation-adsb-telemetry` | Future Domain Plugin | ADS-B Standards | Aircraft kinematic state vector parsing and dead-reckoning. | Aviation Ingestion Engine | Planned | Pending Audit | Future real-time flight ingestion. | Optional |

---

## 2. Progressive Disclosure Skill Loading Strategy

To avoid context window bloat and conflicting guidance, skills must **NOT** all be loaded simultaneously. Agents must activate skills dynamically according to the active engineering task:

```
┌────────────────────────────────────────────────────────┐
│                      Task Trigger                      │
└───────────┬────────────────────────────────┬───────────┘
            │                                │
            ▼ Database / Migration Task      ▼ Spatial / GIS Task
┌──────────────────────────────┐ ┌──────────────────────────────┐
│ • worldos-engineering        │ │ • worldos-engineering        │
│ • worldos-database-architect │ │ • worldos-spatial-engineeri  │
│ • worldos-testing            │ │ • worldos-testing            │
│ • (supabase/postgres-best)   │ │                              │
└──────────────────────────────┘ └──────────────────────────────┘
            │                                │
            ▼ Ingestion / Fusion Task        ▼ Backend / API Task
┌──────────────────────────────┐ ┌──────────────────────────────┐
│ • worldos-engineering        │ │ • worldos-engineering        │
│ • worldos-source-adapters    │ │ • modern-python-fastapi      │
│ • worldos-provenance-fusion  │ │ • worldos-security-threat    │
│ • worldos-security-threat    │ │ • worldos-testing            │
│ • worldos-testing            │ │ • worldos-observability-met  │
└──────────────────────────────┘ └──────────────────────────────┘
            │                                │
            ▼ Frontend / UI Task             ▼ Security / Audit Task
┌──────────────────────────────┐ ┌──────────────────────────────┐
│ • worldos-engineering        │ │ • worldos-engineering        │
│ • worldos-presentation-bound │ │ • worldos-security-threat    │
│ • modern-python-fastapi      │ │ • worldos-source-adapters    │
│   (for API contracts)        │ │ • worldos-git-adr-discipline │
└──────────────────────────────┘ └──────────────────────────────┘
```
