---
name: worldos-testing
description: Guidelines and patterns for deterministic testing, pytest suites, property-based testing, contract testing, and container-backed integration tests in WORLDOS.
---

# WORLDOS Testing & Verification Playbook

WORLDOS models physical reality. Erroneous calculations, broken spatial containment, or corrupt provenance can invalidate the entire world model. Robust, deterministic testing is non-negotiable.

---

## 1. The Testing Pyramid in WORLDOS

1. **Unit & Mathematical Invariant Tests (Fast, In-Memory)**:
   - Geometry math (distance, projection, clipping).
   - Entity resolution heuristics (scoring, publisher ID collision).
   - Confidence decay algorithms.
   - Pydantic validation contracts.
   - Run in milliseconds without network or database dependencies.
2. **Container-Backed Integration Tests**:
   - Real PostgreSQL + PostGIS container (`worldos-postgres`).
   - Verifies real SQL execution, GiST indexes, `ST_Contains`, `ST_Intersects`, and migrations.
   - DuckDB in-process analytical reading.
3. **End-to-End Adapter Pipeline Tests**:
   - Tests full adapter fetch $\to$ parse $\to$ evidence hash $\to$ DB upsert pipeline with mocked HTTP responses (`respx` or recorded VCR cassettes).

---

## 2. Deterministic Testing Standards

- **Zero Flakiness**: Tests must produce identical results regardless of execution order, time of day, or machine architecture.
- **Frozen Time**: When testing time-dependent logic (e.g. observation expiry, temporal decay), use `freezegun` or inject explicit `datetime` fixtures.
- **Mocking External APIs**:
  - Never call live external APIs (World Bank, USGS) in CI or automated test suites.
  - Use `respx` or `unittest.mock` to return fixed, recorded JSON fixtures.
- **Randomness Control**:
  - If generating test coordinates or IDs, use explicit random seeds (`random.seed(42)`).

---

## 3. Property-Based Testing (Trail of Bits Guidelines)

Use `hypothesis` for verifying geometric and algorithmic invariants across generated input spaces:

```python
from hypothesis import given, strategies as st
from shapely.geometry import Point, box

@given(
    lon=st.floats(min_value=-180.0, max_value=180.0),
    lat=st.floats(min_value=-90.0, max_value=90.0)
)
def test_point_within_world_bounds(lon: float, lat: float):
    pt = Point(lon, lat)
    world_bbox = box(-180.0, -90.0, 180.0, 90.0)
    assert world_bbox.covers(pt)

@given(
    c1=st.floats(min_value=0.0, max_value=1.0),
    c2=st.floats(min_value=0.0, max_value=1.0)
)
def test_fused_confidence_bounded(c1: float, c2: float):
    fused = 1.0 - (1.0 - c1) * (1.0 - c2)
    assert 0.0 <= fused <= 1.0
    assert fused >= max(c1, c2)
```

---

## 4. Pytest Fixture Patterns (TestMu AI Guidelines)

- Use `conftest.py` with scoped fixtures (`session`, `module`, `function`).
- Database isolation:
  - Run tests inside database transactions that rollback on teardown (`yield session; await session.rollback()`), or run against dedicated ephemeral test databases.
- Example fixture:
  ```python
  import pytest
  from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
  from sqlalchemy.orm import sessionmaker

  @pytest.fixture(scope="function")
  async def db_session():
      engine = create_async_engine("postgresql+asyncpg://postgres:postgres@localhost:5432/worldos_test")
      async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
      async with async_session() as session:
          yield session
          await session.rollback()
      await engine.dispose()
  ```

---

## 5. Anti-Patterns to Avoid

- **Anti-Pattern 1: Live Network Requests in Tests**: Running `pytest` when internet access is down and having tests fail because `api.worldbank.org` was unreachable.
- **Anti-Pattern 2: Non-deterministic Sleep**: Using `time.sleep(2)` to wait for asynchronous workers instead of polling with `asyncio.wait_for()` on an event.
- **Anti-Pattern 3: State Bleed Between Tests**: Tests relying on records inserted by previous tests rather than clean fixture setup.
