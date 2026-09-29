---
name: worldos-source-adapters
description: Standards and contracts for implementing data source ingestion adapters, rate limiting, payload hashing, and evidence registration in WORLDOS.
---

# WORLDOS Source Ingestion Adapters & ETL Architecture

In WORLDOS, external data enters exclusively through strongly-typed, registered **Source Adapters**. Direct ad-hoc insertion of external payloads into database tables is prohibited.

---

## 1. The Source Adapter Contract

Every source adapter must inherit from an abstract base adapter and implement the standard lifecycle:

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
import hashlib
import json
from pydantic import BaseModel

class IngestionResult(BaseModel):
    source_id: str
    records_fetched: int
    records_valid: int
    records_errored: int
    evidence_ids: List[str]
    duration_ms: float

class BaseSourceAdapter(ABC):
    @property
    @abstractmethod
    def source_id(self) -> str:
        """Unique registered string ID, e.g. 'world_bank_wdi', 'usgs_earthquakes'."""
        pass

    @property
    @abstractmethod
    def default_epistemic_tier(self) -> str:
        """Usually OBSERVED."""
        pass

    @abstractmethod
    async def fetch_raw(self, **kwargs) -> Any:
        """Fetch raw data over HTTP/filesystem with timeout, backoff, and rate limiting."""
        pass

    @abstractmethod
    def parse_and_validate(self, raw_data: Any) -> List[BaseModel]:
        """Convert raw payload into canonical WORLDOS Pydantic models."""
        pass

    def compute_evidence_hash(self, raw_record: Dict[str, Any]) -> str:
        """Deterministic SHA-256 hash of canonical JSON representation."""
        canonical_bytes = json.dumps(raw_record, sort_keys=True, default=str).encode('utf-8')
        return hashlib.sha256(canonical_bytes).hexdigest()

    @abstractmethod
    async def ingest(self, **kwargs) -> IngestionResult:
        """Full pipeline: fetch -> hash evidence -> validate -> persist -> reconcile."""
        pass
```

---

## 2. Ingestion Rules

1. **Idempotence**: Running an adapter multiple times on the same input must not produce duplicate entities or corrupted state. Use `ON CONFLICT DO NOTHING` or upsert semantics based on publisher identifiers and evidence hashes.
2. **Immutable Raw Evidence**: Store the raw record (or a pointer to S3/GCS/filesystem object storage) along with its SHA-256 hash. This guarantees cryptographic reproducibility.
3. **Resilience & Backoff**: External network requests must use `httpx.AsyncClient` with:
   - Configurable timeout (default 10s connect, 30s read).
   - Exponential backoff with jitter on HTTP 429 and 5xx errors.
   - Respect for `Retry-After` headers.
4. **Schema Enforcement**: Unrecognized fields must either be captured in a `properties: Dict[str, Any]` jsonb bag or rejected. Key domain attributes (`coordinates`, `timestamp`, `identifier`) must be strictly validated.

---

## 3. Anti-Patterns to Avoid

- **Anti-Pattern 1: Unhandled Schema Drift**: If an API provider changes a date format from ISO-8601 to unix epoch, failing silently or inserting `None` without alerting.
- **Anti-Pattern 2: Discarding the Raw Payload**: Parsing an API response into Python variables and immediately throwing away the raw JSON so future audits cannot verify what was received.
- **Anti-Pattern 3: Ingestion directly in HTTP request handlers**: Running long-running multi-minute data pulls synchronously inside a user-facing REST endpoint instead of a background task or worker.
