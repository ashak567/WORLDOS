---
name: worldos-observability-metrics
description: Guidelines for structured logging, performance metrics, distributed tracing, health checks, and error monitoring in WORLDOS based on Sentry and modern cloud observability standards.
---

# WORLDOS Observability, Metrics & Telemetry Playbook

In WORLDOS, deterministic intelligence requires observability across ingestion pipelines, spatial query latency, database health, and memory usage.

---

## 1. Structured Logging Standards

- **JSON Output**: In production, logs must be output as single-line JSON strings to stdout/stderr.
- **Mandatory Context Fields**:
  - `timestamp`: ISO-8601 UTC string.
  - `level`: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.
  - `service`: `worldos-backend` / `worldos-worker`.
  - `correlation_id` / `request_id`: Traces execution across HTTP requests and background tasks.
  - `source_id`: When executing ingestion adapters.
  - `duration_ms`: For database queries, external HTTP calls, and engine operations.
- **No Sensitive Data**: Never log passwords, API tokens, raw Authorization headers, or PII.

```python
import structlog

logger = structlog.get_logger()

# Example log call:
logger.info(
    "ingestion_batch_completed",
    source_id="usgs_earthquakes",
    records_processed=42,
    duration_ms=318.5,
    epistemic_tier="OBSERVED"
)
```

---

## 2. Health Checks & Readiness Probes

FastAPI must expose standardized health endpoints for container orchestration:
- `/health/live`: Fast liveness probe (checks process is alive and event loop is responsive). Returns HTTP 200 immediately.
- `/health/ready`: Readiness probe. Validates:
  1. PostgreSQL connection can execute `SELECT 1`.
  2. PostGIS extension is loaded (`SELECT PostGIS_Version()`).
  3. Analytical snapshot storage directory is readable/writable.
  Returns HTTP 200 if ready; HTTP 503 Service Unavailable if any dependency fails.

---

## 3. Key Metrics to Measure

| Metric Name | Type | Labels | Description |
|---|---|---|---|
| `worldos_ingestion_duration_seconds` | Histogram | `source_id`, `status` | Duration of source adapter ingestion runs. |
| `worldos_records_ingested_total` | Counter | `source_id`, `epistemic_tier` | Total raw records ingested. |
| `worldos_spatial_query_duration_seconds` | Histogram | `operation` (`contains`, `intersects`, `dwithin`) | PostGIS spatial query latency. |
| `worldos_entity_conflicts_total` | Counter | `entity_type`, `resolution_status` | Conflicts detected during entity resolution. |
| `worldos_db_pool_active_connections` | Gauge | `database` (`postgres`) | Active connections in connection pool. |

---

## 4. Anti-Patterns to Avoid

- **Anti-Pattern 1: Unstructured Print Statements**: Using `print("done!")` in backend code instead of structured loggers.
- **Anti-Pattern 2: Shallow Health Checks**: A `/health` endpoint that returns `{"status": "ok"}` hardcoded without actually testing the database connection.
- **Anti-Pattern 3: Unhandled Ingestion Failures**: Swallowing exceptions in adapter loops with `except Exception: pass` without logging error metrics or traces.
