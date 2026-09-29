---
name: modern-python-fastapi
description: Best practices for modern Python (3.11+), Pydantic v2 data modeling, FastAPI routing, strict type safety, and ruff linting based on Trail of Bits and Microsoft engineering standards.
---

# Modern Python & FastAPI Architecture Playbook

This skill outlines code style, architectural conventions, and performance patterns for the WORLDOS backend service based on Microsoft and Trail of Bits official guidelines.

---

## 1. Modern Python Standards (3.11+)

- **Package & Dependency Management**:
  - Prefer `pyproject.toml` (PEP 518/621) as the single source of truth.
  - Use `uv` or `pip` with pinned requirements for reproducible builds.
  - Linting and Formatting: Use `ruff` (`ruff check .`, `ruff format .`). Replace flake8, black, isort, and bandit with high-performance ruff rules.
- **Strict Typing**:
  - All functions must have complete type annotations on arguments and return types.
  - Use modern built-in generics (`list[str]`, `dict[str, Any]`, `tuple[int, ...]`) instead of `typing.List`, `typing.Dict`.
  - Use `typing.Annotated` for dependency injection and metadata validation.
  - Avoid `Any` wherever possible; use `Union`, `TypeVar`, or concrete Pydantic models.

---

## 2. Pydantic v2 Data Modeling & Contracts

- **Immutable & Strict Config**:
  ```python
  from pydantic import BaseModel, ConfigDict, Field
  from datetime import datetime
  from uuid import UUID

  class WorldOSBaseModel(BaseModel):
      model_config = ConfigDict(
          populate_by_name=True,
          extra="forbid",            # Strict validation against unexpected injection
          validate_assignment=True,
          from_attributes=True       # Seamless ORM integration
      )

  class EntityCreateContract(WorldOSBaseModel):
      name: str = Field(..., min_length=1, max_length=256)
      entity_type: str = Field(..., pattern=r"^[a-z0-9_]+$")
      publisher_id: str
      confidence: float = Field(default=1.0, ge=0.0, le=1.0)
  ```
- **Serialization**:
  - Use `model.model_dump()` and `model.model_dump_json()` (never deprecated v1 `.dict()` or `.json()`).
  - Use `field_validator` and `model_validator(mode='before'|'after')` with explicit typing.

---

## 3. FastAPI Routing & Dependency Injection (Microsoft Standards)

- **Router Architecture**:
  - Keep route handlers thin. Handlers parse input, invoke engines/services, and return response contracts.
  - Modular routers under `backend/app/api/v1/routes/`:
    ```python
    from fastapi import APIRouter, Depends, HTTPException, status, Query
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.db.session import get_db

    router = APIRouter(prefix="/entities", tags=["Entities"])

    @router.get("/{entity_id}", response_model=EntityResponse)
    async def get_entity(
        entity_id: UUID,
        db: AsyncSession = Depends(get_db)
    ) -> EntityResponse:
        entity = await entity_engine.fetch_by_id(db, entity_id)
        if not entity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Entity {entity_id} not found"
            )
        return entity
    ```
- **Error Handling**:
  - Register global exception handlers for `DomainException`, `EntityConflictException`, and validation errors.
  - Return standardized RFC 7807 Problem Details JSON format:
    ```json
    {
      "type": "https://worldos.org/errors/entity-not-found",
      "title": "Entity Not Found",
      "status": 404,
      "detail": "Entity 4a8b... not found in registry",
      "instance": "/api/v1/entities/4a8b..."
    }
    ```
- **Pagination**:
  - Enforce cursor-based or keyset pagination (`limit`, `cursor`) for large datasets. Avoid unconstrained `OFFSET` on large PostGIS tables.

---

## 4. Async Best Practices

- Never call synchronous blocking I/O (e.g. `requests.get()`, `time.sleep()`, synchronous database drivers) inside an `async def` route.
- Use `httpx.AsyncClient` for HTTP calls and `asyncpg` / `create_async_engine` for database queries.
- For CPU-intensive operations (e.g., massive geometry simplification), use `asyncio.to_thread(worker_fn)`.

---

## 5. Anti-Patterns to Avoid

- **Anti-Pattern 1: Leaking ORM models directly to API output**: Returning SQLAlchemy objects directly from routes without converting through Pydantic contracts.
- **Anti-Pattern 2: Mixing Sync and Async Database Sessions**: Using synchronous `sessionmaker` inside an asynchronous event loop, blocking the worker thread.
- **Anti-Pattern 3: Loose Pydantic schemas**: Allowing `extra = "allow"` on sensitive mutation endpoints, enabling mass assignment vulnerabilities.
