"""Stable, evidence-first contracts shared by ingestion and query code."""
from __future__ import annotations

import math
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl, model_validator


class TruthClass(str, Enum):
    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"
    INFERRED = "INFERRED"
    PREDICTED = "PREDICTED"
    SIMULATED = "SIMULATED"


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


class EntityIdentifier(BaseModel):
    """A publisher identifier used for safe cross-source entity reconciliation."""

    source_id: UUID
    source_key: str
    scheme: str
    value: str
    confidence: Confidence


class Geometry(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    entity_id: UUID
    geojson: dict[str, Any]
    geometry_kind: str
    source_id: UUID
    evidence_id: UUID | None = None
    confidence: Confidence
    valid_during: TimeInterval | None = None


class Observation(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    subject_entity_id: UUID
    measure: str
    value: float
    unit: str
    truth_class: Literal["OBSERVED"] = "OBSERVED"
    time_interval_id: UUID
    evidence_id: UUID
    provenance_id: UUID
    confidence: Confidence
    attributes: dict[str, Any] = Field(default_factory=dict)


class Claim(BaseModel):
    """A factual, analytical, or model assertion with explicit truth class and derivation lineage."""

    id: UUID = Field(default_factory=uuid4)
    subject_entity_id: UUID
    claim_type: str
    truth_class: TruthClass
    value: Any
    unit: str | None = None
    time_interval_id: UUID | None = None
    spatial_scope: dict[str, Any] | None = None
    method: str
    computation_version: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[UUID] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    confidence: Confidence
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_derivation_contract(self) -> "Claim":
        if self.truth_class == TruthClass.DERIVED:
            if not self.inputs:
                raise ValueError("Derived claims must preserve explicit inputs (e.g. input_entity_ids or observation_ids)")
            if not self.method or not self.computation_version:
                raise ValueError("Derived claims must record method and computation_version")
        elif self.truth_class in (TruthClass.PREDICTED, TruthClass.SIMULATED):
            if not self.assumptions:
                raise ValueError(f"{self.truth_class.value} claims must document explicit assumptions")
            if not self.method:
                raise ValueError(f"{self.truth_class.value} claims must specify predictive or simulation method")
        return self



class Event(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    kind: str
    subject_entity_id: UUID | None = None
    time_interval_id: UUID
    evidence_id: UUID
    confidence: Confidence
    attributes: dict[str, Any] = Field(default_factory=dict)


VALID_PREDICATES: set[str] = {
    "located_in",
    "connected_to",
    "near",
    "affects",
    "observed_by",
    "occurred_in",
    "adjacent_to",
    "belongs_to",
    "part_of",
    "intersects",
    "covers",
}


class Relationship(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    subject_entity_id: UUID
    predicate: str
    object_entity_id: UUID
    time_interval_id: UUID | None = None
    evidence_id: UUID
    confidence: Confidence
    attributes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_distinct_entities(self) -> "Relationship":
        if self.subject_entity_id == self.object_entity_id:
            raise ValueError("subject_entity_id and object_entity_id must be distinct")
        return self


class WorldBundle(BaseModel):
    """The smallest atomic write: facts plus their source trail."""

    source: Source
    entity: Entity
    evidence: Evidence
    provenance: Provenance
    identifiers: list[EntityIdentifier] = Field(default_factory=list)
    time_interval: TimeInterval | None = None
    observation: Observation | None = None
    geometry: Geometry | None = None
    event: Event | None = None
    relationships: list[Relationship] = Field(default_factory=list)

    @model_validator(mode="after")
    def has_evidence_backed_fact(self) -> "WorldBundle":
        if not self.observation and not self.geometry and not self.event and not self.relationships:
            raise ValueError("a bundle must contain an observation, geometry, event, or relationship")
        if (self.observation or self.event) and not self.time_interval:
            raise ValueError("an observation or event requires a time interval")
        return self


class IngestionRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    pipeline_version: str
    status: Literal["started", "completed", "failed", "partial"]
    started_at: datetime
    completed_at: datetime | None = None
    records_fetched: int = 0
    records_persisted: int = 0
    records_failed: int = 0
    error_message: str | None = None
    freshness_observed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceHealth(BaseModel):
    source_slug: str
    source_name: str
    publisher: str
    last_run_status: str | None = None
    last_successful_ingest: datetime | None = None
    freshness_observed_at: datetime | None = None
    total_runs: int = 0
    total_records_persisted: int = 0
    is_healthy: bool = True


class EntityResolutionReview(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    candidate_entity_id: UUID
    target_entity_id: UUID
    match_reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    status: Literal["pending", "approved", "rejected"] = "pending"
    created_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    resolution_notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BoundingBox(BaseModel):
    min_longitude: float = Field(ge=-180, le=180)
    min_latitude: float = Field(ge=-90, le=90)
    max_longitude: float = Field(ge=-180, le=180)
    max_latitude: float = Field(ge=-90, le=90)

    @model_validator(mode="after")
    def validate_bounds(self) -> "BoundingBox":
        if self.min_longitude > self.max_longitude:
            raise ValueError("min_longitude must not exceed max_longitude")
        if self.min_latitude > self.max_latitude:
            raise ValueError("min_latitude must not exceed max_latitude")
        return self


class SpatialScope(BaseModel):
    bounding_box: BoundingBox | None = None
    filter_type: Literal["intersects", "contains", "within"] = "intersects"


class TemporalScope(BaseModel):
    valid_at: datetime | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    precision: Literal["instant", "day", "month", "year", "unknown"] | None = None

    @model_validator(mode="after")
    def validate_interval(self) -> "TemporalScope":
        if self.starts_at and self.ends_at and self.starts_at > self.ends_at:
            raise ValueError("starts_at must not exceed ends_at")
        return self


class ContextQueryScope(BaseModel):
    spatial: SpatialScope | None = None
    temporal: TemporalScope | None = None
    entity_ids: list[UUID] | None = None
    entity_kind: str | None = None
    limit: int = 100


class EvidenceCitation(BaseModel):
    evidence_id: UUID
    source_id: UUID
    source_slug: str
    source_name: str
    locator: str
    retrieved_at: datetime
    content_hash: str | None = None
    excerpt: str | None = None


class WorldContext(BaseModel):
    query_scope: ContextQueryScope
    entities: list[dict[str, Any]] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    geometries: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[EvidenceCitation] = Field(default_factory=list)
    assumptions_or_limitations: list[str] = Field(default_factory=list)


class SnapshotManifest(BaseModel):
    snapshot_id: UUID = Field(default_factory=uuid4)
    schema_version: str = "worldos-snapshot-v1"
    status: Literal["in_progress", "completed", "failed"] = "in_progress"
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    datasets: list[str] = Field(default_factory=lambda: ["observations", "entities", "geometries", "events"])
    total_records: int = 0
    row_counts: dict[str, int] = Field(default_factory=dict)
    partition_counts: dict[str, int] = Field(default_factory=dict)
    min_year: int | None = None
    max_year: int | None = None
    storage_path: str = ""
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SpatialRollupItem(BaseModel):
    entity_id: UUID | str
    entity_canonical_name: str
    entity_type: str
    measure: str
    year: str | int | None
    observation_count: int
    total_value: float
    mean_value: float
    min_value: float
    max_value: float
    evidence_count: int
    has_data: bool


class TemporalTrendItem(BaseModel):
    entity_id: UUID | str
    entity_canonical_name: str
    measure: str
    earliest_year: str | int | None
    latest_year: str | int | None
    earliest_value: float | None
    latest_value: float | None
    percentage_change: float | None
    observation_count: int
    series: list[dict[str, Any]] = Field(default_factory=list)
    evidence_ids: list[UUID | str] = Field(default_factory=list)


class CoverageSummary(BaseModel):
    total_observations: int
    total_entities: int
    total_evidence_citations: int
    distinct_sources: int
    source_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    earliest_observation: str | None = None
    latest_observation: str | None = None
    entities_with_observations: int = 0
    entities_with_geometry: int = 0


class SpatialSliceComparison(BaseModel):
    measure: str
    year: str | int | None
    entity_a: dict[str, Any]
    entity_b: dict[str, Any]
    absolute_difference: float | None
    ratio: float | None
    larger_entity: str | None


class ConstraintSeverity(str, Enum):
    BLOCKING = "BLOCKING"
    WARNING = "WARNING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class ConstraintCategory(str, Enum):
    PHYSICAL_COORDINATES = "PHYSICAL_COORDINATES"
    SPATIAL_CONSISTENCY = "SPATIAL_CONSISTENCY"
    TEMPORAL_CONSISTENCY = "TEMPORAL_CONSISTENCY"
    ENTITY_RELATIONSHIP = "ENTITY_RELATIONSHIP"
    CLAIM_EVIDENCE = "CLAIM_EVIDENCE"
    SCENARIO_PROPOSAL = "SCENARIO_PROPOSAL"


class ConstraintStatus(str, Enum):
    VALID = "VALID"
    VALID_WITH_WARNINGS = "VALID_WITH_WARNINGS"
    INVALID = "INVALID"


class ConstraintFinding(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    code: str
    category: ConstraintCategory
    severity: ConstraintSeverity
    message: str
    field: str | None = None
    actual_value: Any | None = None
    expected_value: Any | None = None
    evidence_ids: list[UUID] = Field(default_factory=list)
    blocks_persistence: bool = False

    @model_validator(mode="after")
    def sync_blocking(self) -> "ConstraintFinding":
        if self.severity == ConstraintSeverity.BLOCKING:
            self.blocks_persistence = True
        return self


class ConstraintValidationResult(BaseModel):
    status: ConstraintStatus
    findings: list[ConstraintFinding] = Field(default_factory=list)
    total_findings: int = 0
    blocking_count: int = 0
    warning_count: int = 0
    review_required_count: int = 0
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_findings(cls, findings: list[ConstraintFinding]) -> "ConstraintValidationResult":
        blocking = sum(1 for f in findings if f.severity == ConstraintSeverity.BLOCKING)
        warning = sum(1 for f in findings if f.severity == ConstraintSeverity.WARNING)
        review = sum(1 for f in findings if f.severity == ConstraintSeverity.REVIEW_REQUIRED)

        if blocking > 0:
            status = ConstraintStatus.INVALID
        elif warning > 0 or review > 0:
            status = ConstraintStatus.VALID_WITH_WARNINGS
        else:
            status = ConstraintStatus.VALID

        return cls(
            status=status,
            findings=findings,
            total_findings=len(findings),
            blocking_count=blocking,
            warning_count=warning,
            review_required_count=review,
        )


class ScenarioProposal(BaseModel):
    """Reusable specification for proposed scenario modifications validated prior to application."""

    scenario_id: UUID = Field(default_factory=uuid4)
    name: str
    description: str | None = None
    target_entity_ids: list[UUID] = Field(default_factory=list)
    proposed_observations: list[Observation] = Field(default_factory=list)
    proposed_geometries: list[Geometry] = Field(default_factory=list)
    proposed_relationships: list[Relationship] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)


class AlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertLifecycleStatus(str, Enum):
    RECEIVED = "RECEIVED"
    VALIDATED = "VALIDATED"
    EVALUATED = "EVALUATED"
    ALERTED = "ALERTED"
    SUPPRESSED = "SUPPRESSED"
    FAILED = "FAILED"


class AlertStatus(str, Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertComparisonOperator(str, Enum):
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    EQ = "=="
    NEQ = "!="


class AlertRule(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str | None = None
    event_kind: str
    operator: Literal[">", ">=", "<", "<=", "==", "!="]
    metric_field: str
    threshold: float
    severity: AlertSeverity = AlertSeverity.WARNING
    spatial_scope: dict[str, Any] | None = None
    temporal_window_seconds: int | None = None
    cluster_threshold: int | None = None
    cooldown_seconds: int = Field(default=300, ge=0)
    is_enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_rule(self) -> "AlertRule":
        if not self.metric_field or not self.metric_field.strip():
            raise ValueError("metric_field cannot be empty")
        if math.isnan(self.threshold) or math.isinf(self.threshold):
            raise ValueError("threshold must be a finite number")
        if self.cluster_threshold is not None:
            if self.cluster_threshold < 1:
                raise ValueError("cluster_threshold must be >= 1")
            if not self.temporal_window_seconds or self.temporal_window_seconds <= 0:
                raise ValueError("cluster_threshold requires a positive temporal_window_seconds")
        if self.spatial_scope:
            scope_type = self.spatial_scope.get("type")
            if scope_type == "bbox":
                min_lon = self.spatial_scope.get("min_lon")
                max_lon = self.spatial_scope.get("max_lon")
                min_lat = self.spatial_scope.get("min_lat")
                max_lat = self.spatial_scope.get("max_lat")
                if None in (min_lon, max_lon, min_lat, max_lat):
                    raise ValueError("spatial_scope bbox requires min_lon, max_lon, min_lat, max_lat")
                if min_lon < -180 or max_lon > 180 or min_lon > max_lon:
                    raise ValueError(f"Invalid longitude bounds: [{min_lon}, {max_lon}]")
                if min_lat < -90 or max_lat > 90 or min_lat > max_lat:
                    raise ValueError(f"Invalid latitude bounds: [{min_lat}, {max_lat}]")
        return self


class AlertEvaluation(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    event_id: UUID
    status: AlertLifecycleStatus
    matched_rule_ids: list[UUID] = Field(default_factory=list)
    alerts_generated: int = 0
    reason: str | None = None
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class Alert(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    rule_id: UUID
    event_id: UUID
    severity: AlertSeverity
    title: str
    message: str
    dedup_key: str
    status: AlertStatus = AlertStatus.ACTIVE
    evidence_id: UUID
    context_summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    resolved_at: datetime | None = None
    resolution_notes: str | None = None
