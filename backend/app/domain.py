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


# ==============================================================================
# Engine 13: Deterministic Decision Support Models
# ==============================================================================


class CriterionDirection(str, Enum):
    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"
    TARGET_RANGE = "target_range"


class MissingDataPolicy(str, Enum):
    EXCLUDE = "exclude"
    NEUTRAL_SCORE = "neutral_score"
    PENALIZE_MIN = "penalize_min"


class DecisionCriterion(BaseModel):
    id: str
    name: str
    metric_field: str
    direction: CriterionDirection = CriterionDirection.MAXIMIZE
    weight: float = Field(default=1.0, ge=0.0)
    target_min: float | None = None
    target_max: float | None = None
    hard_constraint_min: float | None = None
    hard_constraint_max: float | None = None
    required: bool = False
    unit: str | None = None

    @model_validator(mode="after")
    def validate_criterion(self) -> "DecisionCriterion":
        if not self.id or not self.id.strip():
            raise ValueError("criterion id cannot be empty")
        if not self.name or not self.name.strip():
            raise ValueError("criterion name cannot be empty")
        if not self.metric_field or not self.metric_field.strip():
            raise ValueError("criterion metric_field cannot be empty")
        if math.isnan(self.weight) or math.isinf(self.weight) or self.weight < 0:
            raise ValueError("criterion weight must be a finite non-negative number")
        if self.direction == CriterionDirection.TARGET_RANGE:
            if self.target_min is None or self.target_max is None:
                raise ValueError("direction 'target_range' requires both target_min and target_max")
            if self.target_min > self.target_max:
                raise ValueError(f"target_min ({self.target_min}) must not exceed target_max ({self.target_max})")
        if self.hard_constraint_min is not None and self.hard_constraint_max is not None:
            if self.hard_constraint_min > self.hard_constraint_max:
                raise ValueError(
                    f"hard_constraint_min ({self.hard_constraint_min}) must not exceed hard_constraint_max ({self.hard_constraint_max})"
                )
        return self


class DecisionAlternative(BaseModel):
    id: str
    name: str
    entity_id: UUID | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    scenario_proposal: ScenarioProposal | None = None


class CriterionScoreBreakdown(BaseModel):
    criterion_id: str
    criterion_name: str
    raw_value: float | None = None
    unit: str | None = None
    is_missing: bool = False
    normalized_score: float
    weight: float
    normalized_weight: float
    weighted_contribution: float
    evidence_id: UUID | None = None
    truth_class: TruthClass | None = None
    notes: str | None = None


class RankedAlternative(BaseModel):
    alternative_id: str
    name: str
    entity_id: UUID | None = None
    rank: int
    overall_score: float
    criteria_breakdown: dict[str, CriterionScoreBreakdown] = Field(default_factory=dict)
    missing_criteria: list[str] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class InfeasibleAlternative(BaseModel):
    alternative_id: str
    name: str
    entity_id: UUID | None = None
    blocking_reasons: list[str] = Field(default_factory=list)
    constraint_findings: list[dict[str, Any]] = Field(default_factory=list)


class SensitivityVariation(BaseModel):
    criterion_id: str
    criterion_name: str
    original_weight: float
    varied_weight: float
    top_alternative_id: str
    top_alternative_name: str
    top_alternative_score: float
    rank_changed: bool
    new_rankings: list[dict[str, Any]] = Field(default_factory=list)


class DecisionRequest(BaseModel):
    decision_id: UUID = Field(default_factory=uuid4)
    objective: str
    scope: dict[str, Any] = Field(default_factory=dict)
    criteria: list[DecisionCriterion] = Field(default_factory=list)
    alternatives: list[DecisionAlternative] = Field(default_factory=list)
    missing_data_policy: MissingDataPolicy = MissingDataPolicy.NEUTRAL_SCORE
    enforce_constraints: bool = True
    persist: bool = True

    @model_validator(mode="after")
    def validate_request(self) -> "DecisionRequest":
        if not self.objective or not self.objective.strip():
            raise ValueError("objective cannot be empty")
        if not self.alternatives:
            raise ValueError("at least one alternative must be provided")
        if not self.criteria:
            raise ValueError("at least one criterion must be provided")
        return self


class DecisionResult(BaseModel):
    decision_id: UUID
    objective: str
    scope: dict[str, Any] = Field(default_factory=dict)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: str = "completed"
    alternatives_count: int = 0
    feasible_count: int = 0
    infeasible_count: int = 0
    missing_data_policy: MissingDataPolicy
    feasible_alternatives: list[RankedAlternative] = Field(default_factory=list)
    infeasible_alternatives: list[InfeasibleAlternative] = Field(default_factory=list)
    criteria: list[DecisionCriterion] = Field(default_factory=list)
    normalized_weights: dict[str, float] = Field(default_factory=dict)
    trade_off_analysis: dict[str, Any] = Field(default_factory=dict)
    ranking_limitations: list[str] = Field(default_factory=list)
    evidence_citations: list[dict[str, Any]] = Field(default_factory=list)


# ==============================================================================
# Engine 16: Scenario Engine Models
# ==============================================================================


class ScenarioStatus(str, Enum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    EVALUATED = "EVALUATED"
    ARCHIVED = "ARCHIVED"


class ScenarioOperationType(str, Enum):
    SET = "SET"
    DELTA = "DELTA"
    SCALE = "SCALE"
    REMOVE = "REMOVE"


class ScenarioModification(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    scenario_id: UUID
    target_entity_id: UUID
    target_field: str
    operation: ScenarioOperationType = ScenarioOperationType.SET
    value: Any
    unit: str | None = None
    effective_interval: TimeInterval | None = None
    rationale: str | None = None
    evidence_references: list[UUID] = Field(default_factory=list)
    status: Literal["active", "superseded", "invalid"] = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_modification(self) -> "ScenarioModification":
        if not self.target_field or not self.target_field.strip():
            raise ValueError("target_field cannot be empty")
        if self.operation in (ScenarioOperationType.DELTA, ScenarioOperationType.SCALE):
            if not isinstance(self.value, (int, float)) or not math.isfinite(self.value):
                raise ValueError(f"Operation {self.operation.value} requires a finite numeric value")
            if self.operation == ScenarioOperationType.SCALE and self.value < 0:
                raise ValueError("Operation SCALE requires non-negative factor")
        return self


class Scenario(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str | None = None
    status: ScenarioStatus = ScenarioStatus.DRAFT
    version: int = Field(default=1, ge=1)
    parent_scenario_id: UUID | None = None
    parent_scenario_version: int | None = None
    baseline_context: dict[str, Any] = Field(default_factory=dict)
    truth_class: TruthClass = TruthClass.SIMULATED
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_scenario(self) -> "Scenario":
        if not self.name or not self.name.strip():
            raise ValueError("Scenario name cannot be empty")
        return self


class ScenarioEvaluation(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    scenario_id: UUID
    scenario_version: int
    baseline_snapshot: dict[str, Any] = Field(default_factory=dict)
    simulated_state: dict[str, Any] = Field(default_factory=dict)
    delta_summary: dict[str, Any] = Field(default_factory=dict)
    constraint_findings: list[dict[str, Any]] = Field(default_factory=list)
    is_feasible: bool = True
    derived_metrics: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evaluation_version: str = "v1.0.0"
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ScenarioComparison(BaseModel):
    scenario_a_id: UUID
    scenario_b_id: UUID
    scenario_a_name: str
    scenario_b_name: str
    compared_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    entity_comparisons: list[dict[str, Any]] = Field(default_factory=list)
    feasibility_comparison: dict[str, Any] = Field(default_factory=dict)
    metric_deltas: dict[str, Any] = Field(default_factory=dict)
    summary: str


# ==============================================================================
# Engine 17: Simulation Engine Models
# ==============================================================================


class SimulationStatus(str, Enum):
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SimulationRequest(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    scenario_id: UUID
    scenario_version: int | None = None
    starts_at: datetime
    ends_at: datetime
    step_size: float = Field(default=1.0, gt=0)
    step_unit: Literal["hour", "day", "month", "year", "step"] = "year"
    max_steps: int = Field(default=100, ge=1, le=500)
    parameters: dict[str, Any] = Field(default_factory=dict)
    initial_state_overrides: dict[str, Any] = Field(default_factory=dict)
    rule_ids: list[str] = Field(default_factory=list)
    requested_metrics: list[str] = Field(default_factory=list)
    branch_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_simulation_request(self) -> "SimulationRequest":
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be strictly greater than starts_at")
        if self.step_size <= 0:
            raise ValueError("step_size must be positive")
        if self.max_steps < 1 or self.max_steps > 500:
            raise ValueError("max_steps must be between 1 and 500")
        return self


class TransitionRuleDefinition(BaseModel):
    id: str
    version: str = "v1.0.0"
    name: str
    description: str
    supported_variables: list[str] = Field(default_factory=list)
    required_inputs: dict[str, str] = Field(default_factory=dict)
    output_variables: dict[str, str] = Field(default_factory=dict)
    preconditions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class SimulationStep(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    simulation_id: UUID
    step_index: int = Field(ge=0)
    simulated_at: datetime
    state: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    applied_rules: list[str] = Field(default_factory=list)
    constraint_findings: list[dict[str, Any]] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    truth_class: TruthClass = TruthClass.SIMULATED
    step_fingerprint: str = ""


class SimulationRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    scenario_id: UUID
    scenario_version: int
    status: SimulationStatus = SimulationStatus.CREATED
    configuration: dict[str, Any] = Field(default_factory=dict)
    initial_state: dict[str, Any] = Field(default_factory=dict)
    final_state: dict[str, Any] = Field(default_factory=dict)
    trajectory_summary: dict[str, Any] = Field(default_factory=dict)
    is_feasible: bool = True
    constraint_findings: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    step_count: int = 0
    execution_duration_ms: float | None = None
    reproducibility_fingerprint: str = ""
    truth_class: TruthClass = TruthClass.SIMULATED
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


class SimulationComparison(BaseModel):
    simulation_a_id: UUID
    simulation_b_id: UUID
    scenario_a_id: UUID
    scenario_b_id: UUID
    compared_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    step_count_a: int
    step_count_b: int
    metric_deltas: dict[str, Any] = Field(default_factory=dict)
    trajectory_divergence: dict[str, Any] = Field(default_factory=dict)
    feasibility_comparison: dict[str, bool] = Field(default_factory=dict)
    summary: str


# ==============================================================================
# Engine 15: Anomaly Detection Models
# ==============================================================================


class AnomalySeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FindingLifecycleStatus(str, Enum):
    NEW = "NEW"
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"
    SUPPRESSED = "SUPPRESSED"


class DetectionMethod(str, Enum):
    ROBUST_ZSCORE_MAD = "robust_zscore_mad"
    TEMPORAL_CHANGE = "temporal_change"
    PEER_GROUP_DEVIATION = "peer_group_deviation"
    SPATIAL_DEVIATION = "spatial_deviation"
    MULTIVARIATE_MAHALANOBIS = "multivariate_mahalanobis"


class DetectionMethodDefinition(BaseModel):
    method: DetectionMethod
    name: str
    version: str = "v1.0.0"
    description: str
    supported_scopes: list[str] = Field(default_factory=list)
    required_parameters: list[str] = Field(default_factory=list)
    default_threshold: float
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class AnomalyDetectionRequest(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    entity_ids: list[UUID] | None = None
    metric: str
    detection_methods: list[DetectionMethod] = Field(
        default_factory=lambda: [DetectionMethod.ROBUST_ZSCORE_MAD, DetectionMethod.TEMPORAL_CHANGE]
    )
    baseline_config: dict[str, Any] = Field(default_factory=dict)
    threshold: float | None = None
    min_observations: int = Field(default=3, ge=2)
    spatial_scope: dict[str, Any] | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    severity_thresholds: dict[str, float] | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    evaluate_as_alert: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_request(self) -> "AnomalyDetectionRequest":
        if not self.metric or not self.metric.strip():
            raise ValueError("metric cannot be empty")
        if self.starts_at and self.ends_at and self.ends_at < self.starts_at:
            raise ValueError("ends_at must not precede starts_at")
        if self.threshold is not None:
            if not math.isfinite(self.threshold) or self.threshold <= 0:
                raise ValueError("threshold must be a positive finite number")
        return self


class AnomalyFinding(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID | None = None
    entity_id: UUID
    entity_name: str
    observation_id: UUID | None = None
    metric: str
    unit: str
    observed_value: float
    observed_at: datetime
    expected_value: float | None = None
    deviation: float
    deviation_magnitude: float
    anomaly_score: float
    detection_method: DetectionMethod | str
    method_version: str = "v1.0.0"
    threshold_applied: float
    severity: AnomalySeverity = AnomalySeverity.WARNING
    status: FindingLifecycleStatus = FindingLifecycleStatus.NEW
    data_reliability: float = Field(default=1.0, ge=0.0, le=1.0)
    baseline_observation_count: int = 0
    baseline_window: dict[str, Any] = Field(default_factory=dict)
    baseline_summary: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[UUID] = Field(default_factory=list)
    truth_class: TruthClass = TruthClass.DERIVED
    explanation: str
    limitations: list[str] = Field(default_factory=list)
    data_quality_warnings: list[str] = Field(default_factory=list)
    fingerprint: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AnomalyRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    status: str = "RUNNING"
    request: AnomalyDetectionRequest
    observations_evaluated: int = 0
    findings_count: int = 0
    findings: list[AnomalyFinding] = Field(default_factory=list)
    summary_statistics: dict[str, Any] = Field(default_factory=dict)
    exclusions_and_warnings: list[str] = Field(default_factory=list)
    execution_duration_ms: float | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


# ==============================================================================
# Engine 18: Prediction Engine Domain Models
# ==============================================================================


class PredictionMethod(str, Enum):
    NAIVE_BASELINE = "naive_baseline"
    SEASONAL_NAIVE = "seasonal_naive"
    MOVING_AVERAGE = "moving_average"
    LINEAR_TREND = "linear_trend"
    AUTO_SELECT = "auto_select"


class PredictionStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class PredictionMethodDefinition(BaseModel):
    method: PredictionMethod
    name: str
    version: str = "v1.0.0"
    description: str
    required_parameters: list[str] = Field(default_factory=list)
    min_observations: int = 3
    supports_prediction_intervals: bool = True
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class PredictionRequest(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    entity_id: UUID
    metric: str
    horizon: int = Field(default=5, ge=1, le=100)
    step_size: int = Field(default=1, ge=1)
    step_unit: Literal["year", "month", "day", "hour"] = "year"
    method: PredictionMethod = PredictionMethod.LINEAR_TREND
    method_params: dict[str, Any] = Field(default_factory=dict)
    min_observations: int = Field(default=3, ge=2)
    confidence_level: float = Field(default=0.95, ge=0.50, le=0.999)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    scenario_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_request(self) -> "PredictionRequest":
        if not self.metric or not self.metric.strip():
            raise ValueError("metric cannot be empty")
        if self.starts_at and self.ends_at and self.ends_at < self.starts_at:
            raise ValueError("ends_at must not precede starts_at")
        if self.horizon < 1 or self.horizon > 100:
            raise ValueError("horizon must be between 1 and 100")
        if self.confidence_level < 0.50 or self.confidence_level >= 1.0:
            raise ValueError("confidence_level must be between 0.50 and 0.999")
        return self


class PredictionPoint(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID | None = None
    step_index: int
    entity_id: UUID
    metric: str
    unit: str
    forecast_timestamp: datetime
    predicted_value: float
    lower_bound: float | None = None
    upper_bound: float | None = None
    confidence_level: float | None = None
    method: PredictionMethod | str
    method_version: str = "v1.0.0"
    truth_class: TruthClass = TruthClass.PREDICTED
    evidence_ids: list[UUID] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    data_quality_warnings: list[str] = Field(default_factory=list)
    fingerprint: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PredictionEvaluation(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    metric: str
    evaluation_window: dict[str, Any] = Field(default_factory=dict)
    matched_points_count: int = 0
    mae: float
    rmse: float
    mase: float | None = None
    bias: float = 0.0
    interval_coverage: float | None = None
    baseline_comparison: dict[str, Any] = Field(default_factory=dict)
    evaluation_method: str = "walk_forward"
    method_version: str = "v1.0.0"
    limitations: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PredictionRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    status: PredictionStatus = PredictionStatus.CREATED
    request: PredictionRequest
    selected_method: PredictionMethod
    method_version: str = "v1.0.0"
    entity_id: UUID
    metric: str
    unit: str = ""
    observations_count: int = 0
    trajectory_points_count: int = 0
    trajectory: list[PredictionPoint] = Field(default_factory=list)
    historical_summary: dict[str, Any] = Field(default_factory=dict)
    model_parameters: dict[str, Any] = Field(default_factory=dict)
    evaluation: PredictionEvaluation | None = None
    quality_warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    reproducibility_fingerprint: str = ""
    execution_duration_ms: float | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


class BacktestRequest(BaseModel):
    entity_id: UUID
    metric: str
    method: PredictionMethod = PredictionMethod.LINEAR_TREND
    method_params: dict[str, Any] = Field(default_factory=dict)
    eval_horizon: int = Field(default=3, ge=1, le=20)
    min_train_size: int = Field(default=3, ge=2)
    step_size: int = Field(default=1, ge=1)
    step_unit: Literal["year", "month", "day", "hour"] = "year"
    confidence_level: float = Field(default=0.95, ge=0.50, le=0.999)


class BacktestResult(BaseModel):
    entity_id: UUID
    metric: str
    method: PredictionMethod
    origins_evaluated: int
    total_evaluations: int
    mae: float
    rmse: float
    mase: float | None = None
    bias: float = 0.0
    interval_coverage: float | None = None
    baseline_comparison: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
