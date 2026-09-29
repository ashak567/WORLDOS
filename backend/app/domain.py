"""Stable, evidence-first contracts shared by ingestion and query code."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl, model_validator


class Confidence(BaseModel):
    value: float = Field(ge=0, le=1)
    method: str = "source_asserted"


class TimeInterval(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    starts_at: datetime
    ends_at: datetime | None = None
    precision: Literal["instant", "day", "month", "year", "unknown"]

    @model_validator(mode="after")
    def ordered(self) -> "TimeInterval":
        if self.ends_at and self.ends_at < self.starts_at:
            raise ValueError("ends_at must not precede starts_at")
        return self


class Source(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    slug: str
    name: str
    publisher: str
    license: str | None = None
    homepage: HttpUrl | None = None
    refresh_policy: str = "manual"


class Evidence(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    locator: str
    retrieved_at: datetime
    content_hash: str | None = None
    excerpt: str | None = None


class Provenance(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    evidence_id: UUID
    pipeline_version: str
    transformation: dict[str, Any] = Field(default_factory=dict)


class Entity(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    kind: Literal["place", "organization", "person", "asset", "concept", "other"]
    canonical_name: str
    source_id: UUID | None = None
    source_key: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    confidence: Confidence


class Geometry(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    entity_id: UUID
    geojson: dict[str, Any]
    geometry_kind: str
    source_id: UUID
    confidence: Confidence
    valid_during: TimeInterval | None = None


class Observation(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    subject_entity_id: UUID
    measure: str
    value: float
    unit: str
    time_interval_id: UUID
    evidence_id: UUID
    provenance_id: UUID
    confidence: Confidence
    attributes: dict[str, Any] = Field(default_factory=dict)


class Event(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    kind: str
    subject_entity_id: UUID | None = None
    time_interval_id: UUID
    evidence_id: UUID
    confidence: Confidence
    attributes: dict[str, Any] = Field(default_factory=dict)


class Relationship(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    subject_entity_id: UUID
    predicate: str
    object_entity_id: UUID
    time_interval_id: UUID | None = None
    evidence_id: UUID
    confidence: Confidence
    attributes: dict[str, Any] = Field(default_factory=dict)


class WorldBundle(BaseModel):
    """The smallest atomic write: facts plus their source trail."""

    source: Source
    entity: Entity
    time_interval: TimeInterval
    evidence: Evidence
    provenance: Provenance
    observation: Observation
    geometry: Geometry | None = None

