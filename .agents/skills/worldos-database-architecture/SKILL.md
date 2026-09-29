---
name: worldos-database-architecture
description: Architectural separation and guidelines for PostgreSQL/PostGIS (operational world-state source of truth) and DuckDB (in-process columnar analytics read boundary).
---

# WORLDOS Database Architecture: Operational vs Analytical Dual-Engine

WORLDOS deliberately employs a dual-database architecture. Each database has a strictly defined domain boundary.

```
┌────────────────────────────────────────────────────────┐
│             PostgreSQL + PostGIS (Port 5432)            │
│  - Authoritative operational world-state               │
│  - Entity registry & identity resolution               │
│  - Raw evidence & immutable provenance graph           │
│  - Spatial topology (GiST, ST_Contains, ST_Intersects) │
│  - ACID transactional integrity                        │
└───────────────────────────┬────────────────────────────┘
                            │ Snapshot ETL / CDC
                            ▼
┌────────────────────────────────────────────────────────┐
│                  DuckDB Read Boundary                  │
│  - In-process columnar analytical query engine         │
│  - Parquet snapshot scanning & temporal aggregates    │
│  - Complex statistical rollups & OLAP metrics          │
│  - Zero locks on operational PostGIS tables            │
└────────────────────────────────────────────────────────┘
```

---

## 1. Boundary Rules

### Rule 1: Never Write Operational State to DuckDB
DuckDB is an analytical read boundary. It receives transformed snapshots, Parquet exports, or read-only analytical queries. It must **never** be used as the transactional system of record for live entity mutations.

### Rule 2: Never Run Heavy Analytical Scans on Live PostGIS
Do not execute multi-million row aggregate scans, complex window functions, or historical time-series back-tests directly on production transactional tables during active ingestion. Route analytical queries through DuckDB over partitioned Parquet or read replicas.

### Rule 3: Do Not Collapse the Databases
Do not attempt to replace PostGIS with DuckDB (DuckDB lacks multi-client ACID transactional concurrency and robust topological locking) or replace DuckDB with raw PostgreSQL (PostgreSQL is row-oriented and suffers high CPU/IO overhead on wide-column analytical scans).

---

## 2. PostgreSQL / PostGIS Best Practices (Supabase Guidelines)

- **Connection Management**:
  - Use connection pooling (SQLAlchemy `QueuePool` with sensible `pool_size=10`, `max_overflow=20`, `pool_recycle=3600`).
  - Use `asyncpg` with async FastAPI routes for non-blocking I/O.
- **Index Hygiene**:
  - Primary keys: UUIDv4 or UUIDv7.
  - Foreign keys: Always add standard B-Tree index on foreign key columns (`source_id`, `entity_id`, `evidence_id`).
  - Geometries: Always add GiST index (`CREATE INDEX ... USING GIST (geom)`).
  - Time ranges: GiST or BRIN indexes for continuous time-series observations (`observed_at`).
  - Jsonb: GIN index on `jsonb_path_ops` for dynamic property lookups.
- **Migrations**:
  - Write idempotent, declarative SQL migrations.
  - Never run destructive migrations (`DROP TABLE`, `ALTER COLUMN ... DROP`) in production without explicit multi-phase deprecation.
  - Test rollback steps for every migration.

---

## 3. DuckDB Analytical Patterns

- **In-Memory & File-Based Queries**:
  ```python
  import duckdb

  con = duckdb.connect(database=":memory:")
  # Direct query over Parquet files or PostgreSQL export:
  con.execute("""
      SELECT
          entity_type,
          count(*) AS total_entities,
          avg(confidence) AS avg_confidence,
          min(observed_at) AS earliest,
          max(observed_at) AS latest
      FROM read_parquet('data/snapshots/observations_*.parquet')
      GROUP BY entity_type
  """)
  df = con.df()
  ```
- **Spatial Extension in DuckDB**:
  Install and load the spatial extension when running vector analytics on Parquet:
  ```sql
  INSTALL spatial;
  LOAD spatial;
  SELECT ST_Area(geom) FROM read_parquet('data/polygons.parquet');
  ```
- **Read-Only Safety**:
  Always open DuckDB connections with `read_only=True` when accessing shared analytical snapshot files to prevent file locking conflicts.

---

## 4. Anti-Patterns to Avoid

- **Anti-Pattern 1: Transactional Writes into DuckDB**: Trying to manage active user sessions, ingestion locks, or live entity updates in a `.duckdb` file.
- **Anti-Pattern 2: N+1 Spatial Queries in PostgreSQL**: Looping over 10,000 points in Python and running individual `SELECT ST_Contains(...)` queries instead of a single spatial join query.
- **Anti-Pattern 3: Unbounded Memory in DuckDB**: Not setting `SET max_memory = '4GB'` when executing analytical aggregation queries in memory-constrained container environments.
