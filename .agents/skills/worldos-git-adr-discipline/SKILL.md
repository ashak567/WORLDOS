---
name: worldos-git-adr-discipline
description: Standards for Git commit hygiene, Pull Request reviews, change management, and Architecture Decision Records (ADRs) in WORLDOS.
---

# WORLDOS Git Hygiene & Architecture Decision Records (ADRs)

To maintain long-term architectural integrity across complex spatial, temporal, and fusion engines, WORLDOS requires strict version control discipline and documented decision-making.

---

## 1. Commit Message Discipline (Conventional Commits)

Commit messages must be concise, structured, and informative:

```
<type>(<scope>): <short description>

[optional body explaining WHY, not just WHAT]

[optional issue/ticket reference]
```

### Allowed Types:
- `feat`: A new user-facing or API feature / engine capability.
- `fix`: A bug fix in an engine, adapter, or model.
- `refactor`: Code change that neither fixes a bug nor adds a feature.
- `test`: Adding or correcting tests.
- `docs`: Documentation, ADRs, or README updates.
- `chore`: Tooling, dependency, or configuration updates.

### Examples:
- `feat(spatial): add ST_Contains topological containment query for earthquake events`
- `fix(fusion): resolve pytz timezone issue in DuckDB analytical snapshot`
- `docs(adr): document dual-database boundary between PostGIS and DuckDB`

---

## 2. Architecture Decision Records (ADRs)

Any non-trivial architectural change (e.g. changing database engines, adopting a new serialization format, introducing a new epistemic tier, altering entity resolution precedence) must be documented in `docs/adr/NNNN-title.md`.

### ADR Template:
```markdown
# ADR 0001: Separation of Operational PostGIS and Analytical DuckDB

## Status
Accepted

## Context
WORLDOS requires high-throughput spatial indexing and transactional entity mutations alongside fast columnar rollups and historical time-series queries. Running heavy analytical aggregate queries directly against active PostGIS tables causes table locks and degradations in live ingestion performance.

## Decision
We maintain PostgreSQL + PostGIS as the operational source of truth and system of record. We export periodic Parquet snapshots and use DuckDB as an in-process, read-only analytical boundary for fast OLAP rollups and offline metrics.

## Consequences
### Positive:
- Operational writes and spatial topology queries remain responsive.
- Analytical queries run at columnar speed with vector instructions.
### Negative:
- Requires a snapshot synchronization pipeline from PostGIS to Parquet.
- Analytical data has a small bounded latency (snapshot lag).
```

---

## 3. Code Review & Change Checklist

Before merging any Pull Request:
1. **Architectural Conformance**: Does this preserve engine boundaries? Does it avoid turning WORLDOS into a globe-first or map-centric app?
2. **Provenance & Evidence**: Are external claims accompanied by source identifiers, timestamps, and confidence scores?
3. **Deterministic Tests**: Are unit and integration tests included? Do they pass cleanly in Docker containers?
4. **No Secrets**: Are credentials or internal endpoints accidentally committed?
5. **No Regressions**: Does `pytest` pass with 100% success?
