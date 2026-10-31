from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4, uuid5

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from .domain import (
    Alert,
    AlertEvaluation,
    AlertLifecycleStatus,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    BoundingBox,
    Claim,
    Confidence,
    ConstraintCategory,
    ConstraintFinding,
    ConstraintSeverity,
    ConstraintStatus,
    ConstraintValidationResult,
    CoverageSummary,
    CriterionDirection,
    DecisionAlternative,
    DecisionCriterion,
    DecisionRequest,
    DecisionResult,
    Entity,
    EntityIdentifier,
    Event,
    Evidence,
    Geometry,
    Observation,
    Provenance,
    RankedAlternative,
    Relationship,
    Scenario,
    ScenarioComparison,
    ScenarioEvaluation,
    ScenarioModification,
    ScenarioOperationType,
    ScenarioProposal,
    ScenarioStatus,
    SensitivityVariation,
    SimulationComparison,
    SimulationRequest,
    SimulationRun,
    SimulationStatus,
    SimulationStep,
    SnapshotManifest,
    Source,
    SpatialRollupItem,
    SpatialSliceComparison,
    TemporalTrendItem,
    TimeInterval,
    TransitionRuleDefinition,
    TruthClass,
    WorldBundle,
    WorldContext,
    AnomalyDetectionRequest,
    AnomalyFinding,
    AnomalyRun,
    AnomalySeverity,
    DetectionMethod,
    DetectionMethodDefinition,
    FindingLifecycleStatus,
    BacktestRequest,
    BacktestResult,
    PredictionEvaluation,
    PredictionMethod,
    PredictionMethodDefinition,
    PredictionPoint,
    PredictionRequest,
    PredictionRun,
    PredictionStatus,
)
from .config import get_aisstream_settings, get_firms_settings, get_opensky_settings
from .assistant import (
    AssistantInputError,
    AssistantUnavailable,
    MAX_AUDIO_BYTES,
    OllamaEvidenceBoundReasoner,
    transcribe_local_audio,
    validated_layer_action,
)
from .alerts import AlertEngine
from .anomalies import (
    AnomalyConfigurationError,
    AnomalyDataQualityError,
    AnomalyLifecycleError,
)
from .analytics import DuckDbSpatialAnalytics
from .benchmarks import AnalyticalBenchmarkSuite
from .constraints import ConstraintEngine, ConstraintViolationError
from .export import export_observations
from .ingestion.natural_earth import fetch_country_boundary
from .ingestion.fires import fetch_live_firms_anomalies
from .ingestion.opensky import (
    AircraftStateRecord,
    OpenSkyAuthError,
    OpenSkyError,
    OpenSkyRateLimitError,
    fetch_aircraft_states,
)
from .ingestion.usgs import EarthquakeRecord, fetch_earthquake
from .ingestion.world_bank import fetch_country_point, fetch_population, retrieved_now
from .ingestion import (
    camera_to_world_bundle,
    fetch_maritime_vessels,
    fetch_current_satellites,
    fetch_satellite_ground_track,
    fetch_gdacs_alerts,
    fetch_open_natural_events,
    fetch_recent_earthquakes,
    infrastructure_to_world_bundle,
    load_authoritative_cameras,
    load_authoritative_infrastructure,
    maritime_vessel_bundle,
    SatelliteFeedError,
    LiveHazardFeedError,
    LiveContextFeedError,
    fetch_global_climate,
    fetch_global_news,
    satellite_to_api_state,
    satellite_to_world_bundle,
    thermal_anomaly_to_world_bundle,
)
from .prediction import (
    PredictionConfigurationError,
    PredictionDataQualityError,
)
from .scenarios import ScenarioLifecycleError
from .simulation import (
    SimulationConfigurationError,
    SimulationConstraintViolationError,
    SimulationLifecycleError,
)
from .snapshots import SnapshotCatalog, SnapshotManager
from .storage import WorldRepository

from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)


async def _scheduled_ingestion(
    name: str,
    ingest: Any,
    configured: Any,
    interval_seconds: int,
) -> None:
    await asyncio.sleep(30)
    while True:
        if configured():
            try:
                result = await asyncio.to_thread(ingest)
                if isinstance(result, dict):
                    fetched = result.get("records_fetched", 0)
                    persisted = result.get("records_persisted", 0)
                else:
                    fetched = getattr(result, "records_fetched", 0)
                    persisted = getattr(result, "records_persisted", 0)
                logger.info("Scheduled %s ingestion completed: fetched=%s persisted=%s", name, fetched, persisted)
            except Exception:
                logger.exception("Scheduled %s ingestion failed", name)
        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    tasks = [
        asyncio.create_task(_scheduled_ingestion("OpenSky", lambda: ingest_opensky_states(global_snapshot=True), lambda: get_opensky_settings().is_configured, 30 * 60)),
        asyncio.create_task(_scheduled_ingestion("AISStream", ingest_maritime_vessels, lambda: get_aisstream_settings().is_configured, 5 * 60)),
        asyncio.create_task(_scheduled_ingestion("NASA FIRMS", ingest_thermal_anomalies, lambda: get_firms_settings().is_configured, 15 * 60)),
    ]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="WORLDOS", version="0.1.0", description="Evidence-first world model API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("WORLDOS_CORS_ORIGINS", "*").split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def public_read_only_guard(request: Request, call_next):
    """Block unauthenticated database mutations when the API is publicly deployed."""
    if os.getenv("WORLDOS_PUBLIC_READ_ONLY", "false").strip().lower() == "true":
        safe_posts = {"/routing/plan", "/constraints/validate", "/assistant/answer"}
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not (
            request.method == "POST" and request.url.path in safe_posts
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": "Write operations are disabled on this public demo API."},
            )
    return await call_next(request)


@app.exception_handler(ConstraintViolationError)
def constraint_violation_handler(request, exc: ConstraintViolationError):
    return JSONResponse(
        status_code=422,
        content={
            "detail": str(exc),
            "validation": exc.result.model_dump(mode="json"),
        },
    )


@app.exception_handler(ScenarioLifecycleError)
def scenario_lifecycle_handler(request, exc: ScenarioLifecycleError):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


@app.exception_handler(SimulationLifecycleError)
def simulation_lifecycle_handler(request, exc: SimulationLifecycleError):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


@app.exception_handler(SimulationConfigurationError)
def simulation_configuration_handler(request, exc: SimulationConfigurationError):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


@app.exception_handler(SimulationConstraintViolationError)
def simulation_constraint_handler(request, exc: SimulationConstraintViolationError):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc)},
    )


@app.exception_handler(AnomalyConfigurationError)
def anomaly_configuration_handler(request, exc: AnomalyConfigurationError):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


@app.exception_handler(AnomalyLifecycleError)
def anomaly_lifecycle_handler(request, exc: AnomalyLifecycleError):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


@app.exception_handler(AnomalyDataQualityError)
def anomaly_data_quality_handler(request, exc: AnomalyDataQualityError):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc)},
    )


@app.exception_handler(PredictionConfigurationError)
def prediction_configuration_handler(request, exc: PredictionConfigurationError):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


@app.exception_handler(PredictionDataQualityError)
def prediction_data_quality_handler(request, exc: PredictionDataQualityError):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc)},
    )


NAMESPACE = UUID("b0dcd802-3c40-4b12-99d5-3707d5a07603")



def stable_id(*parts: str) -> UUID:
    return uuid5(NAMESPACE, ":".join(parts))


class IngestionResult(BaseModel):
    country_code: str
    observations_written: int
    observation_ids: list[UUID]
    run_id: UUID | None = None


class GeometryIngestionResult(BaseModel):
    country_code: str
    geometry_id: UUID
    run_id: UUID | None = None


class EarthquakeIngestionResult(BaseModel):
    event_id: str
    entity_id: UUID
    observation_id: UUID
    event_id_persisted: UUID
    containing_country_id: UUID | None = None
    relationships_written: int
    run_id: UUID | None = None


class OpenSkyIngestionResult(BaseModel):
    records_fetched: int
    records_persisted: int
    run_id: UUID | None = None
    freshness_observed_at: datetime | None = None
    credit_cost_estimate: int = 1


class AssistantMapBounds(BaseModel):
    min_lon: float = Field(ge=-180, le=180)
    min_lat: float = Field(ge=-90, le=90)
    max_lon: float = Field(ge=-180, le=180)
    max_lat: float = Field(ge=-90, le=90)

    @model_validator(mode="after")
    def validate_bounds(self) -> "AssistantMapBounds":
        if self.min_lon > self.max_lon or self.min_lat > self.max_lat:
            raise ValueError("Map bounds are invalid")
        return self


class AssistantTravelPreferences(BaseModel):
    model_config = {"extra": "forbid", "str_strip_whitespace": True}
    pace: Literal["relaxed", "balanced", "packed"] | None = None
    photo_interest: str | None = Field(default=None, max_length=120)


class AssistantAnswerRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1200)
    selected_entity_id: UUID | None = None
    map_bounds: AssistantMapBounds | None = None
    travel_preferences: AssistantTravelPreferences | None = None


class AssistantEvidenceItem(BaseModel):
    evidence_id: str
    source_name: str
    retrieved_at: str
    freshness: Literal["fresh", "stale", "unavailable", "unknown"] = "unknown"


class AssistantAction(BaseModel):
    type: Literal["set_layer_visibility"]
    layer_id: str
    visible: bool


class AssistantAnswerResponse(BaseModel):
    answer: str
    evidence: list[AssistantEvidenceItem] = Field(default_factory=list)
    actions: list[AssistantAction] = Field(default_factory=list)
    service_status: Literal["ready", "unavailable"]


def _compact_assistant_context(world_context: WorldContext) -> dict[str, Any]:
    """Keep only bounded, readable fields; never send large polygon coordinate arrays to the model."""
    data = world_context.model_dump(mode="json")

    def pick(rows: list[dict[str, Any]], keys: tuple[str, ...], limit: int = 30) -> list[dict[str, Any]]:
        return [{key: row[key] for key in keys if key in row} for row in rows[:limit]]

    point_geometries = []
    for row in data.get("geometries", [])[:30]:
        geometry = row.get("geometry") or {}
        point = geometry.get("coordinates") if geometry.get("type") == "Point" else None
        summary = {key: row[key] for key in ("id", "entity_id", "canonical_name", "geometry_kind", "evidence_id", "source_slug", "properties") if key in row}
        if point:
            summary["point"] = point
        point_geometries.append(summary)

    return {
        "query_scope": data.get("query_scope"),
        "entities": pick(data.get("entities", []), ("id", "canonical_name", "entity_kind", "attributes", "confidence")),
        "observations": pick(data.get("observations", []), ("id", "entity_id", "canonical_name", "measure", "value", "unit", "starts_at", "ends_at", "observed_at", "truth_class", "confidence", "evidence_id", "source_slug", "point", "coordinates", "properties")),
        "events": pick(data.get("events", []), ("id", "canonical_name", "title", "event_type", "kind", "category", "starts_at", "occurred_at", "truth_class", "evidence_id", "source_slug", "attributes", "properties", "coordinates", "point")),
        "geometries": point_geometries,
        "relationships": pick(data.get("relationships", []), ("id", "subject_entity_id", "predicate", "object_entity_id", "confidence", "evidence_id")),
        "claims": pick(data.get("claims", []), ("id", "entity_id", "claim_type", "truth_class", "content", "confidence", "evidence_references")),
        "evidence": pick(data.get("evidence", []), ("evidence_id", "source_slug", "source_name", "retrieved_at"), 60),
        "assumptions_or_limitations": data.get("assumptions_or_limitations", [])[:20],
    }



def world_bank_bundle(record, point, retrieved_at: datetime) -> WorldBundle:
    source_id = stable_id("source", "world-bank")
    entity_id = stable_id("entity", "world-bank", record.country_code)
    interval_id = stable_id("year", record.country_code, str(record.year))
    evidence_id = stable_id("evidence", "world-bank", record.locator)
    provenance_id = stable_id("provenance", "world-bank-population-v1", record.locator)
    observation_id = stable_id("observation", record.country_code, "population.total", str(record.year))
    source = Source(
        id=source_id,
        slug="world-bank",
        name="World Development Indicators",
        publisher="World Bank",
        license="CC BY 4.0",
        homepage="https://data.worldbank.org/",
        refresh_policy="manual, source-versioned ingestion",
    )
    entity = Entity(
        id=entity_id,
        kind="place",
        canonical_name=record.country_name,
        source_id=source_id,
        source_key=record.country_code,
        attributes={"iso3": record.country_code},
        confidence=Confidence(value=1, method="publisher_identifier"),
    )
    interval = TimeInterval(
        id=interval_id,
        starts_at=datetime(record.year, 1, 1, tzinfo=UTC),
        ends_at=datetime(record.year, 12, 31, 23, 59, 59, tzinfo=UTC),
        precision="year",
    )
    evidence = Evidence(id=evidence_id, source_id=source_id, locator=record.locator,
                        retrieved_at=retrieved_at, content_hash=record.content_hash)
    provenance = Provenance(id=provenance_id, evidence_id=evidence_id, pipeline_version="world-bank-population-v1",
                            transformation={"indicator": "SP.POP.TOTL", "null_values_skipped": True})
    geometry = None
    if point:
        geometry = Geometry(id=stable_id("geometry", "world-bank", record.country_code), entity_id=entity_id,
                            geojson={"type": "Point", "coordinates": [point.longitude, point.latitude]},
                            geometry_kind="representative_point", source_id=source_id,
                            evidence_id=evidence_id,
                            confidence=Confidence(value=0.9, method="source_metadata"))
    observation = Observation(id=observation_id, subject_entity_id=entity_id, measure="population.total",
                              value=record.population, unit="people", time_interval_id=interval_id,
                              evidence_id=evidence_id, provenance_id=provenance_id,
                              confidence=Confidence(value=1, method="publisher_asserted"),
                              attributes={"indicator": "SP.POP.TOTL"})
    identifier = EntityIdentifier(source_id=source_id, source_key=record.country_code,
                                  scheme="iso_3166_1_alpha_3", value=record.country_code,
                                  confidence=Confidence(value=1, method="publisher_identifier"))
    return WorldBundle(source=source, entity=entity, identifiers=[identifier], time_interval=interval, evidence=evidence,
                       provenance=provenance, observation=observation, geometry=geometry)


def natural_earth_bundle(boundary, retrieved_at: datetime) -> WorldBundle:
    source_id = stable_id("source", "natural-earth-admin-0")
    entity_id = stable_id("entity", "natural-earth", boundary.iso3)
    evidence_id = stable_id("evidence", "natural-earth-admin-0", boundary.locator)
    provenance_id = stable_id("provenance", "natural-earth-admin-0-v1", boundary.locator)
    source = Source(id=source_id, slug="natural-earth-admin-0", name="Natural Earth Admin 0 Countries",
                    publisher="Natural Earth", license="public domain", homepage="https://www.naturalearthdata.com/",
                    refresh_policy="manual, source-versioned ingestion")
    entity = Entity(id=entity_id, kind="place", canonical_name=boundary.name, source_id=source_id,
                    source_key=boundary.iso3, attributes={"iso3": boundary.iso3},
                    confidence=Confidence(value=1, method="publisher_identifier"))
    identifier = EntityIdentifier(source_id=source_id, source_key=boundary.iso3,
                                  scheme="iso_3166_1_alpha_3", value=boundary.iso3,
                                  confidence=Confidence(value=1, method="publisher_identifier"))
    evidence = Evidence(id=evidence_id, source_id=source_id, locator=boundary.locator,
                        retrieved_at=retrieved_at, content_hash=boundary.content_hash)
    provenance = Provenance(id=provenance_id, evidence_id=evidence_id, pipeline_version="natural-earth-admin-0-v1",
                            transformation={"feature_filter": "ISO_A3", "geometry": "publisher_polygon"})
    geometry = Geometry(id=stable_id("geometry", "natural-earth", boundary.iso3), entity_id=entity_id,
                        geojson=boundary.geometry, geometry_kind="country_boundary", source_id=source_id,
                        evidence_id=evidence_id,
                        confidence=Confidence(value=1, method="publisher_asserted"))
    return WorldBundle(source=source, entity=entity, identifiers=[identifier], evidence=evidence,
                       provenance=provenance, geometry=geometry)


def usgs_earthquake_bundle(
    record: EarthquakeRecord, retrieved_at: datetime, containing_entity_id: UUID | None = None
) -> WorldBundle:
    source_id = stable_id("source", "usgs-earthquakes")
    entity_id = stable_id("entity", "usgs", record.event_id)
    interval_id = stable_id("time", "usgs", record.event_id)
    evidence_id = stable_id("evidence", "usgs", record.locator)
    provenance_id = stable_id("provenance", "usgs-earthquake-v1", record.locator)
    observation_id = stable_id("observation", "usgs", record.event_id, "magnitude")
    event_id = stable_id("event", "usgs", record.event_id)

    source = Source(
        id=source_id,
        slug="usgs-earthquakes",
        name="USGS Earthquake Hazards Program",
        publisher="U.S. Geological Survey",
        license="public domain",
        homepage="https://earthquake.usgs.gov/",
        refresh_policy="event-driven, source-versioned ingestion",
    )
    entity = Entity(
        id=entity_id,
        kind="other",
        canonical_name=record.title,
        source_id=source_id,
        source_key=record.event_id,
        attributes={"event_id": record.event_id, "place": record.place, "depth_km": record.depth_km},
        confidence=Confidence(value=1.0, method="publisher_identifier"),
    )
    identifier = EntityIdentifier(
        source_id=source_id,
        source_key=record.event_id,
        scheme="usgs_event_id",
        value=record.event_id,
        confidence=Confidence(value=1.0, method="publisher_identifier"),
    )
    interval = TimeInterval(
        id=interval_id,
        starts_at=record.time,
        ends_at=record.time,
        precision="instant",
    )
    evidence = Evidence(
        id=evidence_id,
        source_id=source_id,
        locator=record.locator,
        retrieved_at=retrieved_at,
        content_hash=record.content_hash,
    )
    provenance = Provenance(
        id=provenance_id,
        evidence_id=evidence_id,
        pipeline_version="usgs-earthquake-v1",
        transformation={"publisher_event_id": record.event_id, "measure": "earthquake.magnitude"},
    )
    geometry = Geometry(
        id=stable_id("geometry", "usgs", record.event_id),
        entity_id=entity_id,
        geojson={"type": "Point", "coordinates": [record.longitude, record.latitude]},
        geometry_kind="epicenter",
        source_id=source_id,
        evidence_id=evidence_id,
        valid_during=interval,
        confidence=Confidence(value=1.0, method="publisher_asserted"),
    )
    observation = Observation(
        id=observation_id,
        subject_entity_id=entity_id,
        measure="earthquake.magnitude",
        value=record.mag,
        unit="magnitude",
        time_interval_id=interval_id,
        evidence_id=evidence_id,
        provenance_id=provenance_id,
        confidence=Confidence(value=1.0, method="publisher_asserted"),
        attributes={"place": record.place},
    )
    event = Event(
        id=event_id,
        kind="earthquake",
        subject_entity_id=entity_id,
        time_interval_id=interval_id,
        evidence_id=evidence_id,
        confidence=Confidence(value=1.0, method="publisher_asserted"),
        attributes={"title": record.title, "place": record.place, "depth_km": record.depth_km, "mag": record.mag},
    )
    relationships = []
    if containing_entity_id:
        relationships.append(
            Relationship(
                id=stable_id("relationship", "usgs-occurred-in", record.event_id, str(containing_entity_id)),
                subject_entity_id=entity_id,
                predicate="occurred_in",
                object_entity_id=containing_entity_id,
                time_interval_id=interval_id,
                evidence_id=evidence_id,
                confidence=Confidence(value=0.95, method="postgis_st_contains"),
                attributes={"method": "ST_Contains"},
            )
        )
    return WorldBundle(
        source=source,
        entity=entity,
        identifiers=[identifier],
        time_interval=interval,
        evidence=evidence,
        provenance=provenance,
        observation=observation,
        geometry=geometry,
        event=event,
        relationships=relationships,
    )


def opensky_aircraft_bundle(record: AircraftStateRecord, retrieved_at: datetime) -> WorldBundle:
    source_id = stable_id("source", "opensky-network")
    entity_id = stable_id("entity", "aircraft", record.icao24)
    time_str = record.observation_time.isoformat()
    interval_id = stable_id("time", "aircraft", record.icao24, time_str)
    evidence_id = stable_id("evidence", "opensky-network", record.locator)
    provenance_id = stable_id("provenance", "opensky-state-vector-v1", record.locator)
    observation_id = stable_id("observation", "aircraft", record.icao24, time_str)
    geometry_id = stable_id("geometry", "aircraft", record.icao24, time_str)

    source = Source(
        id=source_id,
        slug="opensky-network",
        name="OpenSky Network",
        publisher="OpenSky Network Association",
        license="OpenSky Terms of Use (Non-commercial / Academic)",
        homepage="https://opensky-network.org/",
        refresh_policy="credit-budgeted, authenticated state-vector ingestion",
    )
    canonical_name = record.callsign if record.callsign else f"ICAO24:{record.icao24.upper()}"
    entity = Entity(
        id=entity_id,
        kind="asset",
        canonical_name=canonical_name,
        source_id=source_id,
        source_key=record.icao24,
        attributes={
            "icao24": record.icao24,
            "callsign": record.callsign,
            "origin_country": record.origin_country,
            "category": record.category,
        },
        confidence=Confidence(value=1.0, method="transponder_broadcast"),
    )
    identifiers = [
        EntityIdentifier(
            source_id=source_id,
            source_key=record.icao24,
            scheme="icao24",
            value=record.icao24,
            confidence=Confidence(value=1.0, method="transponder_broadcast"),
        )
    ]
    if record.callsign:
        identifiers.append(
            EntityIdentifier(
                source_id=source_id,
                source_key=record.icao24,
                scheme="callsign",
                value=record.callsign,
                confidence=Confidence(value=0.9, method="transponder_broadcast"),
            )
        )
    interval = TimeInterval(
        id=interval_id,
        starts_at=record.observation_time,
        ends_at=record.observation_time,
        precision="instant",
    )
    evidence = Evidence(
        id=evidence_id,
        source_id=source_id,
        locator=record.locator,
        retrieved_at=retrieved_at,
        content_hash=record.content_hash,
    )
    provenance = Provenance(
        id=provenance_id,
        evidence_id=evidence_id,
        pipeline_version="opensky-state-vector-v1",
        transformation={"measure": "aircraft.state", "transponder_source": record.position_source},
    )
    geometry = Geometry(
        id=geometry_id,
        entity_id=entity_id,
        geojson={"type": "Point", "coordinates": [record.longitude, record.latitude]},
        geometry_kind="position",
        source_id=source_id,
        evidence_id=evidence_id,
        valid_during=interval,
        confidence=Confidence(value=1.0, method="transponder_asserted"),
    )
    observation = Observation(
        id=observation_id,
        subject_entity_id=entity_id,
        measure="aircraft.state",
        value=record.baro_altitude if record.baro_altitude is not None else 0.0,
        unit="meters",
        time_interval_id=interval_id,
        evidence_id=evidence_id,
        provenance_id=provenance_id,
        confidence=Confidence(value=1.0, method="source_asserted"),
        attributes={
            "icao24": record.icao24,
            "callsign": record.callsign,
            "origin_country": record.origin_country,
            "baro_altitude": record.baro_altitude,
            "geo_altitude": record.geo_altitude,
            "velocity": record.velocity,
            "true_track": record.true_track,
            "vertical_rate": record.vertical_rate,
            "on_ground": record.on_ground,
            "squawk": record.squawk,
            "position_source": record.position_source,
            "category": record.category,
        },
    )
    return WorldBundle(
        source=source,
        entity=entity,
        identifiers=identifiers,
        time_interval=interval,
        evidence=evidence,
        provenance=provenance,
        observation=observation,
        geometry=geometry,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "system_of_record": "postgresql-postgis"}


@app.post("/ingest/world-bank/population/{country_code}", response_model=IngestionResult)
def ingest_world_bank_population(country_code: str, year: int | None = Query(default=None, ge=1960, le=2100)) -> IngestionResult:
    country_code = country_code.upper()
    repo = WorldRepository()
    source_id = stable_id("source", "world-bank")
    run_id = repo.record_ingestion_run(
        source_id=source_id,
        pipeline_version="world-bank-population-v1",
        status="started",
        metadata={"country_code": country_code, "year": year},
    )
    try:
        records = fetch_population(country_code, year=year)
        if not records:
            repo.finish_ingestion_run(
                run_id,
                status="failed",
                records_fetched=0,
                records_persisted=0,
                records_failed=1,
                error_message="World Bank returned no population observations",
            )
            raise HTTPException(status_code=404, detail="World Bank returned no population observations")
        point, now = fetch_country_point(country_code), retrieved_now()
        ids = [repo.ingest(world_bank_bundle(record, point, now)) for record in records]
        latest_year = max(record.year for record in records)
        freshness_dt = datetime(latest_year, 12, 31, 23, 59, 59, tzinfo=UTC)
        repo.finish_ingestion_run(
            run_id,
            status="completed",
            records_fetched=len(records),
            records_persisted=len(ids),
            records_failed=0,
            freshness_observed_at=freshness_dt,
        )
        return IngestionResult(country_code=country_code, observations_written=len(ids), observation_ids=ids, run_id=run_id)
    except HTTPException:
        raise
    except Exception as exc:
        repo.finish_ingestion_run(
            run_id,
            status="failed",
            records_fetched=0,
            records_persisted=0,
            records_failed=1,
            error_message=str(exc),
        )
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc


@app.post("/ingest/natural-earth/country/{country_code}", response_model=GeometryIngestionResult)
def ingest_natural_earth_country(country_code: str) -> GeometryIngestionResult:
    country_code = country_code.upper()
    repo = WorldRepository()
    source_id = stable_id("source", "natural-earth-admin-0")
    run_id = repo.record_ingestion_run(
        source_id=source_id,
        pipeline_version="natural-earth-admin-0-v1",
        status="started",
        metadata={"country_code": country_code},
    )
    try:
        boundary = fetch_country_boundary(country_code)
        now = retrieved_now()
        geometry_id = repo.ingest(natural_earth_bundle(boundary, now))
        repo.finish_ingestion_run(
            run_id,
            status="completed",
            records_fetched=1,
            records_persisted=1,
            records_failed=0,
            freshness_observed_at=now,
        )
        return GeometryIngestionResult(country_code=country_code, geometry_id=geometry_id, run_id=run_id)
    except LookupError as error:
        repo.finish_ingestion_run(
            run_id,
            status="failed",
            records_fetched=0,
            records_persisted=0,
            records_failed=1,
            error_message=str(error),
        )
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as exc:
        repo.finish_ingestion_run(
            run_id,
            status="failed",
            records_fetched=0,
            records_persisted=0,
            records_failed=1,
            error_message=str(exc),
        )
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc


@app.post("/ingest/usgs/earthquake/{event_id}", response_model=EarthquakeIngestionResult)
def ingest_usgs_earthquake(event_id: str) -> EarthquakeIngestionResult:
    repo = WorldRepository()
    source_id = stable_id("source", "usgs-earthquakes")
    run_id = repo.record_ingestion_run(
        source_id=source_id,
        pipeline_version="usgs-earthquake-v1",
        status="started",
        metadata={"event_id": event_id},
    )
    try:
        record = fetch_earthquake(event_id)
    except Exception as error:
        repo.finish_ingestion_run(
            run_id,
            status="failed",
            records_fetched=0,
            records_persisted=0,
            records_failed=1,
            error_message=str(error),
        )
        raise HTTPException(status_code=404, detail=f"USGS earthquake {event_id} not found: {error}") from error

    try:
        containing_country = repo.find_containing_entity(record.longitude, record.latitude)
        containing_id = containing_country["id"] if containing_country else None
        now = retrieved_now()
        bundle = usgs_earthquake_bundle(record, now, containing_entity_id=containing_id)
        repo.ingest(bundle)
        try:
            repo.evaluate_event_alerts(bundle.event.id)
        except Exception:
            pass  # Event persistence must survive alert evaluation or dispatch failure
        repo.finish_ingestion_run(
            run_id,
            status="completed",
            records_fetched=1,
            records_persisted=1 + (1 if containing_id else 0),
            records_failed=0,
            freshness_observed_at=record.time,
        )
        return EarthquakeIngestionResult(
            event_id=record.event_id,
            entity_id=bundle.entity.id,
            observation_id=bundle.observation.id,
            event_id_persisted=bundle.event.id,
            containing_country_id=containing_id,
            relationships_written=len(bundle.relationships),
            run_id=run_id,
        )
    except Exception as exc:
        repo.finish_ingestion_run(
            run_id,
            status="failed",
            records_fetched=1,
            records_persisted=0,
            records_failed=1,
            error_message=str(exc),
        )
        raise HTTPException(status_code=500, detail=f"Persistence failed: {exc}") from exc


@app.post("/ingest/opensky/states", response_model=OpenSkyIngestionResult)
def ingest_opensky_states(
    lamin: float | None = Query(default=None, description="Lower latitude bound"),
    lomin: float | None = Query(default=None, description="Lower longitude bound"),
    lamax: float | None = Query(default=None, description="Upper latitude bound"),
    lomax: float | None = Query(default=None, description="Upper longitude bound"),
    global_snapshot: bool = Query(default=True, description="Fetch global snapshot without bbox filter"),
) -> OpenSkyIngestionResult:
    if global_snapshot:
        lamin, lomin, lamax, lomax = None, None, None, None
        credit_cost = 4
    elif lamin is None or lomin is None or lamax is None or lomax is None:
        lamin, lomin, lamax, lomax = 26.0, 75.0, 30.0, 79.0
        credit_cost = 1
    else:
        area = abs(lamax - lamin) * abs(lomax - lomin)
        if area <= 25:
            credit_cost = 1
        elif area <= 100:
            credit_cost = 2
        elif area <= 400:
            credit_cost = 3
        else:
            credit_cost = 4

    repo = WorldRepository()
    source_id = stable_id("source", "opensky-network")
    source = Source(
        id=source_id,
        slug="opensky-network",
        name="OpenSky Network",
        publisher="OpenSky Network Association",
        license="OpenSky Terms of Use (Non-commercial / Academic)",
        homepage="https://opensky-network.org/",
        refresh_policy="credit-budgeted, authenticated state-vector ingestion",
    )
    repo.ensure_source(source)
    run_id = repo.record_ingestion_run(
        source_id=source_id,
        pipeline_version="opensky-state-vector-v1",
        status="started",
        metadata={"lamin": lamin, "lomin": lomin, "lamax": lamax, "lomax": lomax, "credit_cost_est": credit_cost, "global_snapshot": global_snapshot},
    )
    now = datetime.now(UTC)
    try:
        records = fetch_aircraft_states(lamin=lamin, lomin=lomin, lamax=lamax, lomax=lomax)
        persisted_count = 0
        latest_obs = None
        for r in records:
            bundle = opensky_aircraft_bundle(r, now)
            repo.ingest(bundle)
            persisted_count += 1
            if latest_obs is None or r.observation_time > latest_obs:
                latest_obs = r.observation_time

        repo.finish_ingestion_run(
            run_id,
            status="completed",
            records_fetched=len(records),
            records_persisted=persisted_count,
            records_failed=0,
            freshness_observed_at=latest_obs or now,
        )
        return OpenSkyIngestionResult(
            records_fetched=len(records),
            records_persisted=persisted_count,
            run_id=run_id,
            freshness_observed_at=latest_obs or now,
            credit_cost_estimate=credit_cost,
        )
    except OpenSkyAuthError as auth_err:
        repo.finish_ingestion_run(
            run_id,
            status="failed",
            records_fetched=0,
            records_persisted=0,
            records_failed=1,
            error_message=str(auth_err),
        )
        raise HTTPException(status_code=401, detail=str(auth_err)) from auth_err
    except OpenSkyRateLimitError as rate_err:
        repo.finish_ingestion_run(
            run_id,
            status="failed",
            records_fetched=0,
            records_persisted=0,
            records_failed=1,
            error_message=str(rate_err),
        )
        raise HTTPException(status_code=429, detail=str(rate_err)) from rate_err
    except Exception as exc:
        repo.finish_ingestion_run(
            run_id,
            status="failed",
            records_fetched=0,
            records_persisted=0,
            records_failed=1,
            error_message=str(exc),
        )
        raise HTTPException(status_code=500, detail=f"OpenSky ingestion failed: {exc}") from exc


@app.get("/aircraft/states")
def list_aircraft_states(
    min_lon: float | None = Query(default=None),
    min_lat: float | None = Query(default=None),
    max_lon: float | None = Query(default=None),
    max_lat: float | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=20000),
):
    min_lon_v = _clean_param(min_lon)
    min_lat_v = _clean_param(min_lat)
    max_lon_v = _clean_param(max_lon)
    max_lat_v = _clean_param(max_lat)
    limit_v = _clean_param(limit, 500)

    min_lon_f = float(min_lon_v) if min_lon_v is not None else None
    min_lat_f = float(min_lat_v) if min_lat_v is not None else None
    max_lon_f = float(max_lon_v) if max_lon_v is not None else None
    max_lat_f = float(max_lat_v) if max_lat_v is not None else None

    return WorldRepository().aircraft_states(
        min_lon=min_lon_f,
        min_lat=min_lat_f,
        max_lon=max_lon_f,
        max_lat=max_lat_f,
        limit=limit_v,
    )


@app.get("/aircraft/states/{icao24}/track")
def get_aircraft_track(icao24: str, limit: int = Query(default=100, ge=1, le=500)):
    """Retrieve ordered historical observation track for a specific aircraft."""
    return WorldRepository().aircraft_track(icao24=icao24, limit=limit)


@app.get("/maritime/vessels")
def list_maritime_vessels(
    min_lon: float | None = Query(default=None),
    min_lat: float | None = Query(default=None),
    max_lon: float | None = Query(default=None),
    max_lat: float | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
):
    min_lon_v = _clean_param(min_lon)
    min_lat_v = _clean_param(min_lat)
    max_lon_v = _clean_param(max_lon)
    max_lat_v = _clean_param(max_lat)
    limit_v = _clean_param(limit, 200)

    return WorldRepository().maritime_vessels(
        min_lon=float(min_lon_v) if min_lon_v is not None else None,
        min_lat=float(min_lat_v) if min_lat_v is not None else None,
        max_lon=float(max_lon_v) if max_lon_v is not None else None,
        max_lat=float(max_lat_v) if max_lat_v is not None else None,
        limit=limit_v,
    )


@app.post("/ingest/maritime/vessels")
def ingest_maritime_vessels() -> dict[str, Any]:
    repo = WorldRepository()
    records = fetch_maritime_vessels()
    now = datetime.now(UTC)
    persisted = 0
    for r in records:
        bundle = maritime_vessel_bundle(r, now)
        repo.ingest(bundle)
        persisted += 1
    return {"status": "completed", "records_fetched": len(records), "records_persisted": persisted}


@app.get("/space/satellites")
def list_satellites(limit: int = Query(default=20_000, ge=1, le=20_000)):
    try:
        records = fetch_current_satellites(limit=_clean_param(limit, 20_000))
    except SatelliteFeedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return [satellite_to_api_state(record) for record in records]


@app.get("/space/satellites/{norad_id}/ground-track")
def satellite_ground_track(norad_id: str, points: int = Query(default=72, ge=12, le=360)):
    try:
        return {"norad_id": norad_id, "points": fetch_satellite_ground_track(norad_id, points=points)}
    except SatelliteFeedError as exc:
        message = str(exc)
        status_code = 400 if message.startswith("Invalid") else 404 if "not in the active catalog" in message else 503
        raise HTTPException(status_code=status_code, detail=message) from exc


@app.post("/ingest/space/satellites")
def ingest_satellites(limit: int = Query(default=1_000, ge=1, le=20_000)) -> dict[str, Any]:
    repo = WorldRepository()
    try:
        records = fetch_current_satellites(limit=_clean_param(limit, 1_000))
    except SatelliteFeedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    now = datetime.now(UTC)
    persisted = 0
    for r in records:
        bundle = satellite_to_world_bundle(r, now)
        repo.ingest(bundle)
        persisted += 1
    return {"status": "completed", "records_fetched": len(records), "records_persisted": persisted}


@app.get("/cameras")
def list_cameras(
    min_lon: float | None = Query(default=None),
    min_lat: float | None = Query(default=None),
    max_lon: float | None = Query(default=None),
    max_lat: float | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    min_lon_v = _clean_param(min_lon)
    min_lat_v = _clean_param(min_lat)
    max_lon_v = _clean_param(max_lon)
    max_lat_v = _clean_param(max_lat)
    limit_v = _clean_param(limit, 100)

    records = WorldRepository().cameras(
        min_lon=float(min_lon_v) if min_lon_v is not None else None,
        min_lat=float(min_lat_v) if min_lat_v is not None else None,
        max_lon=float(max_lon_v) if max_lon_v is not None else None,
        max_lat=float(max_lat_v) if max_lat_v is not None else None,
        limit=limit_v,
    )
    for record in records:
        record["truth_class"] = "SIMULATED"
        record["value"] = None
        record["confidence"] = 0.25
        record["evidence_locator"] = None
        record["source_name"] = "WORLDOS curated camera examples"
        attributes = record.get("attributes") or {}
        attributes["status"] = "UNVERIFIED"
        attributes["truth_class"] = "SIMULATED"
        record["attributes"] = attributes
    return records


@app.post("/ingest/cameras")
def ingest_cameras() -> dict[str, Any]:
    repo = WorldRepository()
    records = load_authoritative_cameras()
    now = datetime.now(UTC)
    persisted = 0
    for r in records:
        bundle = camera_to_world_bundle(r, now)
        repo.ingest(bundle)
        persisted += 1
    return {"status": "completed", "records_fetched": len(records), "records_persisted": persisted}


@app.get("/events/thermal")
def list_thermal_anomalies(
    min_lon: float | None = Query(default=None),
    min_lat: float | None = Query(default=None),
    max_lon: float | None = Query(default=None),
    max_lat: float | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
):
    min_lon_v = _clean_param(min_lon)
    min_lat_v = _clean_param(min_lat)
    max_lon_v = _clean_param(max_lon)
    max_lat_v = _clean_param(max_lat)
    limit_v = _clean_param(limit, 200)

    return WorldRepository().thermal_anomalies(
        min_lon=float(min_lon_v) if min_lon_v is not None else None,
        min_lat=float(min_lat_v) if min_lat_v is not None else None,
        max_lon=float(max_lon_v) if max_lon_v is not None else None,
        max_lat=float(max_lat_v) if max_lat_v is not None else None,
        limit=limit_v,
    )


@app.post("/ingest/nasa-firms/fires")
def ingest_thermal_anomalies() -> dict[str, Any]:
    settings = get_firms_settings()
    if not settings.is_configured or settings.map_key is None:
        raise HTTPException(
            status_code=503,
            detail="NASA FIRMS requires a free NASA_FIRMS_MAP_KEY; use the NASA EONET Global Natural Events layer for keyless wildfire indicators.",
        )
    repo = WorldRepository()
    try:
        records = fetch_live_firms_anomalies(settings.map_key.get_secret_value(), max_records=500)
    except (OSError, TimeoutError, UnicodeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="NASA FIRMS feed is unavailable; verify the key and try again.") from exc
    now = datetime.now(UTC)
    persisted = 0
    for r in records:
        bundle = thermal_anomaly_to_world_bundle(r, now)
        repo.ingest(bundle)
        persisted += 1
    return {"status": "completed", "records_fetched": len(records), "records_persisted": persisted}


@app.get("/infrastructure")
def list_infrastructure(
    node_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    records = WorldRepository().infrastructure_nodes(
        node_type=node_type,
        limit=_clean_param(limit, 100),
    )
    for record in records:
        record["truth_class"] = "SIMULATED"
        record["value"] = None
        record["confidence"] = 0.25
        record["evidence_locator"] = None
        record["source_name"] = "WORLDOS curated infrastructure examples"
        attributes = record.get("attributes") or {}
        attributes["status"] = "UNVERIFIED"
        attributes["capabilities_status"] = "UNVERIFIED"
        attributes["truth_class"] = "SIMULATED"
        record["attributes"] = attributes
    return records


@app.post("/ingest/infrastructure")
def ingest_infrastructure() -> dict[str, Any]:
    repo = WorldRepository()
    records = load_authoritative_infrastructure()
    now = datetime.now(UTC)
    persisted = 0
    for r in records:
        bundle = infrastructure_to_world_bundle(r, now)
        repo.ingest(bundle)
        persisted += 1
    return {"status": "completed", "records_fetched": len(records), "records_persisted": persisted}


@app.get("/sources/health")
def source_health(source: str | None = None):
    return WorldRepository().source_health(source_slug=source)


@app.get("/ingestion/runs")
def ingestion_runs(source: str | None = None, limit: int = Query(default=50, ge=1, le=500)):
    return WorldRepository().ingestion_runs(source_slug=source, limit=limit)


class ReviewActionRequest(BaseModel):
    reviewed_by: str = Field(..., min_length=1)
    notes: str | None = None


@app.get("/resolution/reviews")
def list_resolution_reviews(status: str | None = Query(default=None, pattern=r"^(pending|approved|rejected)$")):
    return WorldRepository().resolution_reviews(status=status)


@app.post("/resolution/reviews/{review_id}/approve")
def approve_resolution_review(review_id: UUID, req: ReviewActionRequest):
    success = WorldRepository().approve_resolution_review(review_id, reviewed_by=req.reviewed_by, notes=req.notes)
    if not success:
        raise HTTPException(status_code=404, detail="Review not found or not in pending status")
    return {"status": "approved", "review_id": review_id}


@app.post("/resolution/reviews/{review_id}/reject")
def reject_resolution_review(review_id: UUID, req: ReviewActionRequest):
    success = WorldRepository().reject_resolution_review(review_id, reviewed_by=req.reviewed_by, notes=req.notes)
    if not success:
        raise HTTPException(status_code=404, detail="Review not found or not in pending status")
    return {"status": "rejected", "review_id": review_id}




@app.get("/observations")
def observations(
    measure: str | None = "population.total",
    start: datetime | None = None,
    end: datetime | None = None,
    valid_at: datetime | None = None,
    precision: str | None = None,
    entity_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    return WorldRepository().observations(
        measure=measure,
        start=start,
        end=end,
        valid_at=valid_at,
        precision=precision,
        entity_id=entity_id,
        limit=limit,
    )


@app.get("/events")
def events(
    kind: str | None = None,
    entity_id: UUID | None = None,
    valid_at: datetime | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    return WorldRepository().events(
        kind=kind,
        entity_id=entity_id,
        valid_at=valid_at,
        start=start,
        end=end,
        limit=limit,
    )


@app.get("/events/live")
def live_events():
    """Return current public earthquake and NASA EONET event indicators."""
    now = datetime.now(UTC)
    feeds: dict[str, Any] = {}
    earthquakes: list[dict[str, Any]] = []
    natural_events: list[dict[str, Any]] = []
    failures = 0

    for key, fetcher, target in (
        ("usgs", fetch_recent_earthquakes, earthquakes),
        ("nasa_eonet", fetch_open_natural_events, natural_events),
        ("gdacs", fetch_gdacs_alerts, natural_events),
    ):
        try:
            records, retrieved_at, status = fetcher(now)
            target.extend(records)
            feeds[key] = {"status": status, "retrieved_at": retrieved_at.isoformat(), "count": len(records)}
        except LiveHazardFeedError as exc:
            failures += 1
            feeds[key] = {"status": "unavailable", "error": str(exc), "count": 0}

    if failures == len(feeds):
        raise HTTPException(status_code=503, detail={"message": "Live event feeds are unavailable", "sources": feeds})
    return {"earthquakes": earthquakes, "natural_events": natural_events, "sources": feeds, "as_of": now.isoformat()}


@app.get("/context/live")
def live_context():
    """Return sourced news headlines and the latest monthly NASA climate anomaly."""
    now = datetime.now(UTC)
    result: dict[str, Any] = {"sources": {}, "as_of": now.isoformat()}
    failures = 0
    for key, fetcher in (("news", fetch_global_news), ("climate", fetch_global_climate)):
        try:
            data, retrieved_at, status = fetcher(now)
            result[key] = data
            result["sources"][key] = {"status": status, "retrieved_at": retrieved_at.isoformat(), "count": len(data) if isinstance(data, list) else 1}
        except LiveContextFeedError as exc:
            failures += 1
            result[key] = [] if key == "news" else None
            result["sources"][key] = {"status": "unavailable", "error": str(exc), "count": 0}
    if failures == 2:
        raise HTTPException(status_code=503, detail={"message": "Live context feeds are unavailable", "sources": result["sources"]})
    return result


@app.post("/assistant/transcribe")
async def assistant_transcribe(request: Request):
    """Transcribe a bounded user-started recording using the local Whisper model."""
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_AUDIO_BYTES:
                raise HTTPException(status_code=413, detail="Audio recording exceeds the 5 MB limit")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length header") from exc
    audio = bytearray()
    async for chunk in request.stream():
        audio.extend(chunk)
        if len(audio) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="Audio recording exceeds the 5 MB limit")
    try:
        transcript = await asyncio.to_thread(transcribe_local_audio, bytes(audio), content_type)
        return {**transcript, "service_status": "ready"}
    except AssistantInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AssistantUnavailable as exc:
        return {"text": "", "language": None, "service_status": "unavailable", "detail": str(exc)}


@app.post("/assistant/answer", response_model=AssistantAnswerResponse)
def assistant_answer(request: AssistantAnswerRequest) -> AssistantAnswerResponse:
    """Explain a bounded, deterministic map slice without treating the model as a data source."""
    actions = []
    action = validated_layer_action(request.question)
    if action:
        actions.append(AssistantAction.model_validate(action))

    if request.map_bounds or request.selected_entity_id:
        bbox = None
        if request.map_bounds:
            bbox = BoundingBox(
                min_longitude=request.map_bounds.min_lon,
                min_latitude=request.map_bounds.min_lat,
                max_longitude=request.map_bounds.max_lon,
                max_latitude=request.map_bounds.max_lat,
            )
        try:
            world_context = WorldRepository().scoped_context(
                bbox=bbox,
                entity_ids=[request.selected_entity_id] if request.selected_entity_id else None,
                limit=30,
            )
        except Exception:
            logger.exception("Could not assemble assistant map context")
            return AssistantAnswerResponse(
                answer="I can’t read the current WORLDOS map data right now. Please try again in a moment.",
                actions=actions,
                service_status="unavailable",
            )
        deterministic_result = _compact_assistant_context(world_context)
    else:
        deterministic_result = {
            "entities": [], "observations": [], "events": [], "geometries": [],
            "relationships": [], "claims": [], "evidence": [],
            "assumptions_or_limitations": ["No map bounds or selected entity were supplied."],
        }
    if request.travel_preferences:
        deterministic_result["user_preferences"] = request.travel_preferences.model_dump(exclude_none=True)

    evidence = [
        AssistantEvidenceItem(
            evidence_id=str(item["evidence_id"]),
            source_name=str(item["source_name"]),
            retrieved_at=str(item["retrieved_at"]),
            freshness="unknown",
        )
        for item in deterministic_result.get("evidence", [])
        if item.get("evidence_id") and item.get("source_name") and item.get("retrieved_at")
    ]
    if not evidence:
        answer = (
            "Done — I updated the map layer visibility."
            if actions
            else "I don’t have sourced records for this view yet. Select a map feature or zoom into an area, and I’ll summarize what WORLDOS can verify."
        )
        return AssistantAnswerResponse(answer=answer, evidence=[], actions=actions, service_status="ready")
    try:
        result = OllamaEvidenceBoundReasoner().answer(
            request.question,
            deterministic_result,
            [item.evidence_id for item in evidence],
        )
    except AssistantUnavailable:
        return AssistantAnswerResponse(
            answer="I couldn’t produce an answer tied to the available WORLDOS sources. Check that Ollama is running and try again; your question was not sent to a cloud service.",
            evidence=[],
            actions=actions,
            service_status="unavailable",
        )
    cited_ids = set(result["evidence_ids"])
    return AssistantAnswerResponse(
        answer=result["answer"],
        evidence=[item for item in evidence if item.evidence_id in cited_ids],
        actions=actions,
        service_status="ready",
    )


@app.get("/entities/{entity_id}/context")
def context(entity_id: UUID):
    result = WorldRepository().context(entity_id)
    if not result:
        raise HTTPException(status_code=404, detail="entity not found")
    return result


def _clean_param(val: Any, default: Any = None) -> Any:
    if hasattr(val, "default"):
        return val.default
    return val if val is not None else default


@app.get("/context", response_model=WorldContext)
def get_world_context(
    min_lon: float | None = Query(default=None, ge=-180, le=180),
    min_lat: float | None = Query(default=None, ge=-90, le=90),
    max_lon: float | None = Query(default=None, ge=-180, le=180),
    max_lat: float | None = Query(default=None, ge=-90, le=90),
    valid_at: datetime | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    precision: str | None = None,
    entity_id: UUID | None = None,
    entity_ids: str | None = Query(default=None, description="Comma-separated or individual entity UUIDs"),
    entity_kind: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    min_lon_v = _clean_param(min_lon)
    min_lat_v = _clean_param(min_lat)
    max_lon_v = _clean_param(max_lon)
    max_lat_v = _clean_param(max_lat)
    bbox_vals = [min_lon_v, min_lat_v, max_lon_v, max_lat_v]
    provided_count = sum(1 for v in bbox_vals if v is not None)
    if 0 < provided_count < 4:
        raise HTTPException(
            status_code=400,
            detail="Bounding box requires all four coordinates: min_lon, min_lat, max_lon, max_lat",
        )
    bbox: BoundingBox | None = None
    if provided_count == 4:
        min_lon_f, min_lat_f, max_lon_f, max_lat_f = float(min_lon_v), float(min_lat_v), float(max_lon_v), float(max_lat_v)
        if min_lon_f > max_lon_f:
            raise HTTPException(
                status_code=400,
                detail="Invalid bounding box: min_lon must be less than or equal to max_lon",
            )
        if min_lat_f > max_lat_f:
            raise HTTPException(
                status_code=400,
                detail="Invalid bounding box: min_lat must be less than or equal to max_lat",
            )
        bbox = BoundingBox(
            min_longitude=min_lon_f,
            min_latitude=min_lat_f,
            max_longitude=max_lon_f,
            max_latitude=max_lat_f,
        )

    start_v = _clean_param(start)
    end_v = _clean_param(end)
    valid_at_v = _clean_param(valid_at)
    precision_v = _clean_param(precision)

    if start_v and end_v and start_v > end_v:
        raise HTTPException(
            status_code=400,
            detail="Invalid temporal scope: start must be less than or equal to end",
        )
    if precision_v and precision_v not in {"instant", "day", "month", "year", "unknown"}:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid precision '{precision_v}'. Must be one of instant, day, month, year, unknown",
        )

    e_ids: list[UUID] = []
    entity_id_v = _clean_param(entity_id)
    if entity_id_v:
        e_ids.append(UUID(str(entity_id_v)))
    entity_ids_v = _clean_param(entity_ids)
    if entity_ids_v:
        for raw_id in str(entity_ids_v).split(","):
            raw_clean = raw_id.strip()
            if raw_clean:
                try:
                    e_ids.append(UUID(raw_clean))
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Invalid entity UUID: '{raw_clean}'")

    limit_v = _clean_param(limit, 100)
    entity_kind_v = _clean_param(entity_kind)

    return WorldRepository().scoped_context(
        bbox=bbox,
        valid_at=valid_at_v,
        start=start_v,
        end=end_v,
        precision=precision_v,
        entity_ids=e_ids if e_ids else None,
        entity_kind=entity_kind_v,
        limit=limit_v,
    )



@app.get("/spatial/entities")
def nearby_entities(longitude: float = Query(ge=-180, le=180), latitude: float = Query(ge=-90, le=90),
                    radius_km: float = Query(default=50, gt=0, le=20_000)):
    return WorldRepository().near(longitude, latitude, radius_km)


@app.get("/spatial/containing")
def containing_geometries(
    longitude: float = Query(ge=-180, le=180),
    latitude: float = Query(ge=-90, le=90),
    geometry_kind: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    return WorldRepository().containing_geometries(
        longitude=longitude,
        latitude=latitude,
        geometry_kind=geometry_kind,
        limit=limit,
    )


@app.get("/spatial/intersections/{entity_id}")
def spatial_intersections(
    entity_id: UUID,
    target_geometry_kind: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    return WorldRepository().spatial_intersections(
        entity_id=entity_id,
        target_geometry_kind=target_geometry_kind,
        limit=limit,
    )


@app.get("/geometries")
def geometries(
    entity_id: UUID | None = None,
    geometry_kind: str | None = None,
    valid_at: datetime | None = None,
    limit: int = Query(default=1000, ge=1, le=5000),
):
    return WorldRepository().geometries(
        entity_id=entity_id,
        geometry_kind=geometry_kind,
        valid_at=valid_at,
        limit=limit,
    )


@app.get("/relationships")
def relationships(
    subject_id: UUID | None = None,
    predicate: str | None = None,
    object_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    return WorldRepository().relationships(
        subject_entity_id=subject_id,
        predicate=predicate,
        object_entity_id=object_id,
        limit=limit,
    )


@app.post("/relationships", response_model=UUID)
def create_relationship(relationship: Relationship):
    return WorldRepository().record_relationship(relationship)


@app.get("/relationships/graph/{entity_id}")
def entity_graph(
    entity_id: UUID,
    depth: int = Query(default=1, ge=1, le=2),
    limit: int = Query(default=100, ge=1, le=500),
):
    result = WorldRepository().entity_graph(entity_id=entity_id, depth=depth, limit=limit)
    if not result or not result.get("nodes"):
        raise HTTPException(status_code=404, detail="entity not found")
    return result


@app.get("/claims")
def list_claims(
    subject_entity_id: UUID | None = None,
    truth_class: str | None = None,
    claim_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    return WorldRepository().claims(
        subject_entity_id=subject_entity_id,
        truth_class=truth_class,
        claim_type=claim_type,
        limit=limit,
    )


@app.post("/analytics/population/{entity_id}/growth")
def derive_population_growth(entity_id: UUID):
    import os
    from pathlib import Path
    repo = WorldRepository()
    db_url = repo.database_url
    duckdb_path = Path(os.environ.get("WORLDOS_DUCKDB_PATH", "/tmp/worldos-analytics.duckdb"))
    export_observations(db_url, duckdb_path)
    analytics = DuckDbSpatialAnalytics(duckdb_path)
    claim = analytics.derive_population_growth(entity_id)
    if not claim:
        raise HTTPException(status_code=400, detail="insufficient population observations to compute growth rate")
    claim_id = repo.record_claim(claim)
    return {"status": "derived", "claim_id": claim_id, "claim": claim.model_dump()}


@app.post("/analytics/snapshots/export")
def export_snapshot_endpoint(
    background: bool = Query(default=False),
    datasets: list[str] | None = Query(default=None),
    background_tasks: BackgroundTasks = None,  # type: ignore
):
    manager = SnapshotManager()
    datasets_v = _clean_param(datasets)
    background_v = bool(_clean_param(background, False))
    if background_v and background_tasks is not None:
        sid = uuid4()
        background_tasks.add_task(manager.export_snapshot, datasets=datasets_v, snapshot_id=sid)
        return {
            "status": "in_progress",
            "snapshot_id": sid,
            "message": "Snapshot export job started in background",
        }
    manifest = manager.export_snapshot(datasets=datasets_v)
    return manifest


@app.get("/analytics/snapshots")
def list_snapshots_endpoint(
    status: str | None = Query(default=None),
):
    status_v = _clean_param(status)
    catalog = SnapshotCatalog()
    return catalog.list_snapshots(status_filter=status_v)


@app.get("/analytics/snapshots/{snapshot_id}")
def get_snapshot_endpoint(snapshot_id: UUID):
    catalog = SnapshotCatalog()
    manifest = catalog.get_snapshot(snapshot_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return manifest


@app.get("/analytics/snapshots/{snapshot_id}/validate")
def validate_snapshot_endpoint(snapshot_id: UUID):
    catalog = SnapshotCatalog()
    res = catalog.validate_snapshot(snapshot_id)
    if not res.get("valid"):
        raise HTTPException(status_code=400, detail=res)
    return res


@app.get("/analytics/rollups/spatial")
def spatial_rollups_endpoint(
    snapshot_id: UUID | None = Query(default=None),
    measure: str = Query(default="population.total"),
    year: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
):
    snapshot_id_v = _clean_param(snapshot_id)
    measure_v = str(_clean_param(measure, "population.total"))
    year_v = _clean_param(year)
    entity_type_v = _clean_param(entity_type)

    catalog = SnapshotCatalog()
    if snapshot_id_v:
        manifest = catalog.get_snapshot(snapshot_id_v)
        if not manifest:
            raise HTTPException(status_code=404, detail="Specified snapshot not found")
        analytics = DuckDbSpatialAnalytics(manifest.storage_path)
    else:
        latest = catalog.get_latest_completed_snapshot()
        analytics = DuckDbSpatialAnalytics(latest.storage_path if latest else None)

    return analytics.spatial_summaries(measure=measure_v, year=year_v, entity_type=entity_type_v)


@app.get("/analytics/rollups/temporal")
def temporal_rollups_endpoint(
    snapshot_id: UUID | None = Query(default=None),
    measure: str = Query(default="population.total"),
    entity_ids: list[UUID] | None = Query(default=None),
):
    snapshot_id_v = _clean_param(snapshot_id)
    measure_v = str(_clean_param(measure, "population.total"))
    entity_ids_v = _clean_param(entity_ids)

    catalog = SnapshotCatalog()
    if snapshot_id_v:
        manifest = catalog.get_snapshot(snapshot_id_v)
        if not manifest:
            raise HTTPException(status_code=404, detail="Specified snapshot not found")
        analytics = DuckDbSpatialAnalytics(manifest.storage_path)
    else:
        latest = catalog.get_latest_completed_snapshot()
        analytics = DuckDbSpatialAnalytics(latest.storage_path if latest else None)

    return analytics.multi_entity_temporal_trends(
        entity_ids=[str(e) for e in entity_ids_v] if entity_ids_v else None,
        measure=measure_v,
    )


@app.get("/analytics/coverage")
def coverage_summary_endpoint(
    snapshot_id: UUID | None = Query(default=None),
):
    snapshot_id_v = _clean_param(snapshot_id)
    catalog = SnapshotCatalog()
    if snapshot_id_v:
        manifest = catalog.get_snapshot(snapshot_id_v)
        if not manifest:
            raise HTTPException(status_code=404, detail="Specified snapshot not found")
        analytics = DuckDbSpatialAnalytics(manifest.storage_path)
    else:
        latest = catalog.get_latest_completed_snapshot()
        analytics = DuckDbSpatialAnalytics(latest.storage_path if latest else None)

    return analytics.evidence_coverage_and_freshness()


@app.get("/analytics/compare")
def compare_spatial_slices_endpoint(
    entity_a_id: UUID = Query(...),
    entity_b_id: UUID = Query(...),
    snapshot_id: UUID | None = Query(default=None),
    measure: str = Query(default="population.total"),
    year: str | None = Query(default=None),
):
    entity_a_id_v = _clean_param(entity_a_id)
    entity_b_id_v = _clean_param(entity_b_id)
    snapshot_id_v = _clean_param(snapshot_id)
    measure_v = str(_clean_param(measure, "population.total"))
    year_v = _clean_param(year)

    catalog = SnapshotCatalog()
    if snapshot_id_v:
        manifest = catalog.get_snapshot(snapshot_id_v)
        if not manifest:
            raise HTTPException(status_code=404, detail="Specified snapshot not found")
        analytics = DuckDbSpatialAnalytics(manifest.storage_path)
    else:
        latest = catalog.get_latest_completed_snapshot()
        analytics = DuckDbSpatialAnalytics(latest.storage_path if latest else None)

    return analytics.compare_spatial_slices(
        entity_a_id=entity_a_id_v,
        entity_b_id=entity_b_id_v,
        measure=measure_v,
        year=year_v,
    )


@app.get("/analytics/benchmarks")
def run_benchmarks_endpoint(
    iterations: int = Query(default=3, ge=1, le=20),
):
    iterations_v = int(_clean_param(iterations, 3))
    catalog = SnapshotCatalog()
    latest = catalog.get_latest_completed_snapshot()
    if not latest:
        raise HTTPException(status_code=404, detail="No completed snapshot available to benchmark")
    suite = AnalyticalBenchmarkSuite(latest.storage_path)
    return suite.run_all(iterations=iterations_v)


# -----------------------------------------------------------------------------
# Engine 12: Constraint Engine Endpoints
# -----------------------------------------------------------------------------


class ValidationRequest(BaseModel):
    bundle: WorldBundle | None = None
    entity: Entity | None = None
    geometry: Geometry | None = None
    observation: Observation | None = None
    relationship: Relationship | None = None
    claim: Claim | None = None
    time_interval: TimeInterval | None = None
    bounding_box: BoundingBox | None = None
    scenario_proposal: ScenarioProposal | None = None


@app.post("/constraints/validate", response_model=ConstraintValidationResult)
def validate_constraints_endpoint(payload: ValidationRequest):
    """Deterministic, dry-run validation endpoint evaluating physical, spatial, temporal, entity, claim, and scenario constraints without state mutation."""
    findings: list[ConstraintFinding] = []
    repo = WorldRepository()

    with repo._connection() as conn:
        engine = repo.constraint_engine

        if payload.bundle:
            return engine.validate_bundle(payload.bundle, conn=conn)

        if payload.scenario_proposal:
            return engine.validate_scenario_proposal(payload.scenario_proposal, conn=conn)

        if payload.entity:
            findings.extend(engine.validate_entity(payload.entity, conn=conn))

        if payload.geometry:
            findings.extend(engine.validate_geometry(payload.geometry, conn=conn))

        if payload.observation:
            findings.extend(engine.validate_observation(payload.observation, conn=conn))

        if payload.relationship:
            findings.extend(engine.validate_relationship(payload.relationship, conn=conn))

        if payload.claim:
            findings.extend(engine.validate_claim(payload.claim, conn=conn))

        if payload.time_interval:
            findings.extend(engine.validate_temporal(payload.time_interval))

        if payload.bounding_box:
            findings.extend(engine.validate_bounding_box(payload.bounding_box))

    if not any([
        payload.bundle, payload.scenario_proposal, payload.entity, payload.geometry,
        payload.observation, payload.relationship, payload.claim, payload.time_interval,
        payload.bounding_box
    ]):
        raise HTTPException(
            status_code=422,
            detail="At least one validatable payload object must be provided (bundle, scenario_proposal, entity, geometry, observation, relationship, claim, time_interval, or bounding_box)"
        )

    return ConstraintValidationResult.from_findings(findings)


@app.get("/constraints/rules")
def list_constraint_rules():
    """Return active deterministic constraint categories, error codes, and policy tiers."""
    return {
        "engine": "Engine 12: Constraint Engine",
        "status": "IMPLEMENTED",
        "severity_tiers": {
            "BLOCKING": "Prohibits persistence or scenario application; deterministic invariant violation.",
            "WARNING": "Persistence permitted; highlights non-fatal advisories or incomplete evidence.",
            "REVIEW_REQUIRED": "Human resolution or conservative quarantine required before automated merge."
        },
        "categories": {
            "PHYSICAL_COORDINATES": [
                {"code": "COORD_NON_NUMERIC", "severity": "BLOCKING", "description": "Coordinates must be numeric."},
                {"code": "COORD_NON_FINITE", "severity": "BLOCKING", "description": "Coordinates must be finite (no NaN/Inf)."},
                {"code": "COORD_LON_OUT_OF_BOUNDS", "severity": "BLOCKING", "description": "Longitude must be in [-180, 180]."},
                {"code": "COORD_LAT_OUT_OF_BOUNDS", "severity": "BLOCKING", "description": "Latitude must be in [-90, 90]."},
                {"code": "BBOX_LATITUDE_INVERTED", "severity": "BLOCKING", "description": "min_latitude must be <= max_latitude."},
                {"code": "BBOX_LONGITUDE_INVERTED", "severity": "BLOCKING", "description": "min_longitude must be <= max_longitude unless anti-meridian."},
                {"code": "BBOX_ANTIMERIDIAN_SPAN", "severity": "WARNING", "description": "Bounding box spans the 180th anti-meridian."},
                {"code": "GEOM_INVALID_TOPOLOGY", "severity": "BLOCKING", "description": "PostGIS geometry topology failure (self-intersection, invalid rings)."},
                {"code": "GEOM_POLYGON_RING_NOT_CLOSED", "severity": "BLOCKING", "description": "Polygon ring first vertex must equal last vertex."}
            ],
            "SPATIAL_CONSISTENCY": [
                {"code": "SPATIAL_RELATION_CONTRADICTION", "severity": "BLOCKING", "description": "Entities asserted in spatial relationship are geographically disjoint."},
                {"code": "SPATIAL_RELATION_PARTIAL_OVERLAP", "severity": "WARNING", "description": "Entities partially overlap for strict containment predicate."},
                {"code": "SPATIAL_EVIDENCE_MISSING", "severity": "WARNING", "description": "Cannot verify spatial relationship due to missing geometry."}
            ],
            "TEMPORAL_CONSISTENCY": [
                {"code": "TEMPORAL_TIMEZONE_MISSING", "severity": "BLOCKING", "description": "Timestamps must be timezone-aware (UTC)."},
                {"code": "TEMPORAL_INVERTED", "severity": "BLOCKING", "description": "Interval starts_at must be <= ends_at."},
                {"code": "TEMPORAL_PRECISION_INVALID", "severity": "BLOCKING", "description": "Precision must be instant, day, month, year, or unknown."}
            ],
            "ENTITY_RELATIONSHIP": [
                {"code": "REL_SELF_RELATIONSHIP", "severity": "BLOCKING", "description": "Self-referencing relationships are prohibited."},
                {"code": "REL_INVALID_PREDICATE", "severity": "BLOCKING", "description": "Predicate must be in VALID_PREDICATES."},
                {"code": "ENTITY_RESOLUTION_UNVERIFIED_MATCH", "severity": "REVIEW_REQUIRED", "description": "Name matches existing entity without publisher identifier."}
            ],
            "CLAIM_EVIDENCE": [
                {"code": "TRUTH_CLASS_INVALID", "severity": "BLOCKING", "description": "Observations must be OBSERVED."},
                {"code": "CONFIDENCE_OUT_OF_BOUNDS", "severity": "BLOCKING", "description": "Confidence must be within [0.0, 1.0]."},
                {"code": "MEASURE_VALUE_NEGATIVE", "severity": "BLOCKING", "description": "Population values cannot be negative."},
                {"code": "DERIVED_CLAIM_INPUTS_MISSING", "severity": "BLOCKING", "description": "Derived claims must record explicit inputs."},
                {"code": "HYPOTHESIS_ASSUMPTIONS_MISSING", "severity": "BLOCKING", "description": "Predicted/simulated claims must document assumptions."}
            ],
            "SCENARIO_PROPOSAL": [
                {"code": "SCENARIO_NAME_EMPTY", "severity": "BLOCKING", "description": "Scenario must provide a valid name."},
                {"code": "SCENARIO_PARAMETER_NON_FINITE", "severity": "BLOCKING", "description": "Parameters must be finite numbers."},
                {"code": "SCENARIO_PARAMETER_NEGATIVE_POPULATION", "severity": "BLOCKING", "description": "Population parameter delta cannot be negative."}
            ]
        }
    }


# =============================================================================
# Alert Engine Endpoints (Engine 14)
# =============================================================================


class CreateAlertRuleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    event_kind: str = Field(min_length=1, max_length=100)
    operator: str = Field(pattern=r"^(>|>=|<|<=|==|!=)$")
    metric_field: str = Field(min_length=1, max_length=100)
    threshold: float
    severity: AlertSeverity = AlertSeverity.WARNING
    spatial_scope: dict[str, Any] | None = None
    temporal_window_seconds: int | None = Field(default=None, ge=1)
    cluster_threshold: int | None = Field(default=None, ge=1)
    cooldown_seconds: int = Field(default=300, ge=0)
    is_enabled: bool = True


CreateAlertRuleRequest.model_rebuild()


class UpdateAlertRuleRequest(BaseModel):
    is_enabled: bool | None = None
    threshold: float | None = None


class AcknowledgeAlertRequest(BaseModel):
    acknowledged_by: str = Field(default="operator", min_length=1, max_length=100)


class ResolveAlertRequest(BaseModel):
    resolution_notes: str = Field(default="Resolved by operator", min_length=1, max_length=500)


@app.get("/alerts/rules", response_model=list[AlertRule])
def list_alert_rules(
    event_kind: str | None = None,
    is_enabled: bool | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    event_kind = _clean_param(event_kind)
    is_enabled = _clean_param(is_enabled)
    limit = _clean_param(limit, 100)
    return WorldRepository().list_alert_rules(event_kind=event_kind, is_enabled=is_enabled, limit=limit)


@app.post("/alerts/rules", response_model=AlertRule, status_code=201)
def create_alert_rule(req: CreateAlertRuleRequest):
    repo = WorldRepository()
    rule = AlertRule(
        name=req.name,
        description=req.description,
        event_kind=req.event_kind,
        operator=req.operator,  # type: ignore[arg-type]
        metric_field=req.metric_field,
        threshold=req.threshold,
        severity=req.severity,
        spatial_scope=req.spatial_scope,
        temporal_window_seconds=req.temporal_window_seconds,
        cluster_threshold=req.cluster_threshold,
        cooldown_seconds=req.cooldown_seconds,
        is_enabled=req.is_enabled,
    )
    try:
        rule_id = repo.create_alert_rule(rule)
        created = repo.get_alert_rule(rule_id)
        if not created:
            raise HTTPException(status_code=500, detail="Failed to retrieve created alert rule")
        return created
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err)) from val_err


@app.get("/alerts/rules/{rule_id}", response_model=AlertRule)
def get_alert_rule(rule_id: UUID):
    rule = WorldRepository().get_alert_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found")
    return rule


@app.patch("/alerts/rules/{rule_id}", response_model=AlertRule)
def update_alert_rule(rule_id: UUID, req: UpdateAlertRuleRequest):
    repo = WorldRepository()
    if req.is_enabled is None and req.threshold is None:
        raise HTTPException(status_code=400, detail="Must provide is_enabled or threshold to update")
    updated = repo.update_alert_rule(rule_id, is_enabled=req.is_enabled, threshold=req.threshold)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found")
    rule = repo.get_alert_rule(rule_id)
    return rule


@app.delete("/alerts/rules/{rule_id}")
def delete_alert_rule(rule_id: UUID):
    deleted = WorldRepository().delete_alert_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found")
    return {"deleted": True, "rule_id": rule_id}


@app.post("/alerts/events/{event_id}/evaluate", response_model=AlertEvaluation)
def evaluate_event_alerts(event_id: UUID, rule_ids: list[UUID] | None = None):
    evaluation = WorldRepository().evaluate_event_alerts(event_id, rule_ids=rule_ids)
    return evaluation


@app.get("/alerts/evaluations")
def list_alert_evaluations(
    event_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    event_id = _clean_param(event_id)
    limit = _clean_param(limit, 100)
    return WorldRepository().list_alert_evaluations(event_id=event_id, limit=limit)


@app.get("/alerts")
def list_alerts(
    status: str | None = None,
    severity: str | None = None,
    event_id: UUID | None = None,
    rule_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    status = _clean_param(status)
    severity = _clean_param(severity)
    event_id = _clean_param(event_id)
    rule_id = _clean_param(rule_id)
    limit = _clean_param(limit, 100)
    return WorldRepository().list_alerts(
        status=status,
        severity=severity,
        event_id=event_id,
        rule_id=rule_id,
        limit=limit,
    )


@app.get("/alerts/{alert_id}")
def get_alert(alert_id: UUID):
    alert = WorldRepository().get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return alert


@app.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: UUID, req: AcknowledgeAlertRequest = AcknowledgeAlertRequest()):
    ack_by = _clean_param(req.acknowledged_by, "operator")
    acknowledged = WorldRepository().acknowledge_alert(alert_id, acknowledged_by=ack_by)
    if not acknowledged:
        raise HTTPException(status_code=404, detail=f"Active alert {alert_id} not found or already acknowledged/resolved")
    return {"acknowledged": True, "alert_id": alert_id}


@app.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: UUID, req: ResolveAlertRequest = ResolveAlertRequest()):
    notes = _clean_param(req.resolution_notes, "Resolved by operator")
    resolved = WorldRepository().resolve_alert(alert_id, resolution_notes=notes)
    if not resolved:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found or already resolved")
    return {"resolved": True, "alert_id": alert_id}


# =============================================================================
# Decision Support Engine Endpoints (Engine 13)
# =============================================================================


class DecisionSensitivityRequest(BaseModel):
    delta_pct: float = Field(default=0.20, gt=0.0, le=1.0)


@app.post("/decisions/evaluate", response_model=DecisionResult)
def evaluate_decision(req: DecisionRequest):
    try:
        repo = WorldRepository()
        return repo.evaluate_decision(req)
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err)) from val_err


@app.get("/decisions")
def list_decisions(limit: int = Query(default=100, ge=1, le=1000)):
    limit_v = _clean_param(limit, 100)
    return WorldRepository().list_decisions(limit=limit_v)


@app.get("/decisions/{decision_id}")
def get_decision(decision_id: UUID):
    record = WorldRepository().get_decision(decision_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")
    return record


@app.post("/decisions/{decision_id}/sensitivity", response_model=list[SensitivityVariation])
def run_decision_sensitivity(decision_id: UUID, req: DecisionSensitivityRequest = DecisionSensitivityRequest()):
    try:
        delta = _clean_param(req.delta_pct, 0.20)
        return WorldRepository().run_decision_sensitivity(decision_id, delta_pct=delta)
    except ValueError as err:
        status_code = 404 if "not found" in str(err).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(err)) from err


# =============================================================================
# Scenario Engine Endpoints (Engine 16)
# =============================================================================


class CreateScenarioRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="")
    baseline_reference: str = Field(default="operational_world_state")
    parent_scenario_id: UUID | None = None
    parent_version: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AddScenarioModificationRequest(BaseModel):
    target_entity_id: UUID
    target_field: str = Field(min_length=1, max_length=255)
    operation: ScenarioOperationType
    value: Any = None
    effective_time_start: datetime | None = None
    effective_time_end: datetime | None = None
    rationale: str = Field(default="")
    evidence_references: list[str] = Field(default_factory=list)


class BranchScenarioRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="")


class EvaluateScenarioRequest(BaseModel):
    evaluator: str = Field(default="deterministic_scenario_engine_v1")


@app.post("/scenarios", response_model=Scenario)
def create_scenario_endpoint(req: CreateScenarioRequest):
    repo = WorldRepository()
    scenario = Scenario(
        name=req.name,
        description=req.description,
        baseline_reference=req.baseline_reference,
        parent_scenario_id=req.parent_scenario_id,
        parent_version=req.parent_version,
        metadata=req.metadata,
    )
    scenario_id = repo.create_scenario(scenario)
    created = repo.get_scenario(scenario_id)
    if not created:
        raise HTTPException(status_code=500, detail="Failed to retrieve created scenario")
    return created


@app.get("/scenarios", response_model=list[Scenario])
def list_scenarios_endpoint(
    status: ScenarioStatus | str | None = None,
    parent_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    status_v = _clean_param(status)
    parent_v = _clean_param(parent_id)
    limit_v = _clean_param(limit, 100)
    return WorldRepository().list_scenarios(status=status_v, parent_id=parent_v, limit=limit_v)


@app.get("/scenarios/{scenario_id}", response_model=Scenario)
def get_scenario_endpoint(scenario_id: UUID):
    scenario = WorldRepository().get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")
    return scenario


@app.post("/scenarios/{scenario_id}/archive")
def archive_scenario_endpoint(scenario_id: UUID):
    repo = WorldRepository()
    scenario = repo.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")
    archived = repo.archive_scenario(scenario_id)
    return {"archived": archived, "scenario_id": scenario_id}


@app.post("/scenarios/{scenario_id}/modifications", response_model=ScenarioModification)
def add_scenario_modification_endpoint(scenario_id: UUID, req: AddScenarioModificationRequest):
    repo = WorldRepository()
    scenario = repo.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")

    mod = ScenarioModification(
        scenario_id=scenario_id,
        target_entity_id=req.target_entity_id,
        target_field=req.target_field,
        operation=req.operation,
        value=req.value,
        effective_time_start=req.effective_time_start,
        effective_time_end=req.effective_time_end,
        rationale=req.rationale,
        evidence_references=req.evidence_references,
    )
    try:
        mod_id = repo.add_scenario_modification(mod)
        mods = repo.list_scenario_modifications(scenario_id, is_active=True)
        created_mod = next((m for m in mods if m.id == mod_id), None)
        if not created_mod:
            raise HTTPException(status_code=500, detail="Failed to retrieve created modification")
        return created_mod
    except ScenarioLifecycleError as sle:
        raise HTTPException(status_code=400, detail=str(sle)) from sle
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve


@app.get("/scenarios/{scenario_id}/modifications", response_model=list[ScenarioModification])
def list_scenario_modifications_endpoint(scenario_id: UUID, is_active: bool = True):
    repo = WorldRepository()
    scenario = repo.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")
    return repo.list_scenario_modifications(scenario_id, is_active=is_active)


@app.delete("/scenarios/{scenario_id}/modifications/{mod_id}")
def remove_scenario_modification_endpoint(scenario_id: UUID, mod_id: UUID):
    repo = WorldRepository()
    scenario = repo.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")
    try:
        removed = repo.remove_scenario_modification(mod_id)
        if not removed:
            raise HTTPException(status_code=404, detail=f"Modification {mod_id} not found")
        return {"removed": True, "modification_id": mod_id}
    except ScenarioLifecycleError as sle:
        raise HTTPException(status_code=400, detail=str(sle)) from sle


@app.post("/scenarios/{scenario_id}/branch", response_model=Scenario)
def branch_scenario_endpoint(scenario_id: UUID, req: BranchScenarioRequest):
    repo = WorldRepository()
    scenario = repo.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Parent scenario {scenario_id} not found")
    try:
        return repo.branch_scenario(
            parent_id=scenario_id,
            new_name=req.name,
            new_description=req.description,
        )
    except ScenarioLifecycleError as sle:
        raise HTTPException(status_code=400, detail=str(sle)) from sle
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve


@app.post("/scenarios/{scenario_id}/validate", response_model=ConstraintValidationResult)
def validate_scenario_endpoint(scenario_id: UUID):
    repo = WorldRepository()
    scenario = repo.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")
    try:
        return repo.validate_scenario(scenario_id)
    except ScenarioLifecycleError as sle:
        raise HTTPException(status_code=400, detail=str(sle)) from sle


@app.post("/scenarios/{scenario_id}/evaluate", response_model=ScenarioEvaluation)
def evaluate_scenario_endpoint(scenario_id: UUID, req: EvaluateScenarioRequest = EvaluateScenarioRequest()):
    repo = WorldRepository()
    scenario = repo.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")
    try:
        evaluator_name = _clean_param(req.evaluator, "deterministic_scenario_engine_v1")
        return repo.evaluate_scenario(scenario_id, evaluator=evaluator_name)
    except ScenarioLifecycleError as sle:
        raise HTTPException(status_code=400, detail=str(sle)) from sle
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve


@app.get("/scenarios/{scenario_id}/evaluation", response_model=ScenarioEvaluation)
def get_scenario_evaluation_endpoint(scenario_id: UUID):
    repo = WorldRepository()
    scenario = repo.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")
    evaluation = repo.get_latest_scenario_evaluation(scenario_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail=f"No evaluation found for scenario {scenario_id}")
    return evaluation


@app.get("/scenarios/{scenario_a_id}/compare/{scenario_b_id}", response_model=ScenarioComparison)
def compare_scenarios_endpoint(scenario_a_id: UUID, scenario_b_id: UUID):
    repo = WorldRepository()
    scenario_a = repo.get_scenario(scenario_a_id)
    if not scenario_a:
        raise HTTPException(status_code=404, detail=f"Scenario A {scenario_a_id} not found")
    scenario_b = repo.get_scenario(scenario_b_id)
    if not scenario_b:
        raise HTTPException(status_code=404, detail=f"Scenario B {scenario_b_id} not found")
    try:
        return repo.compare_scenarios(scenario_a_id, scenario_b_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve


# ==============================================================================
# Engine 17: Simulation Engine Endpoints
# ==============================================================================


class CreateSimulationRequest(BaseModel):
    scenario_id: UUID
    scenario_version: int | None = None
    starts_at: datetime
    ends_at: datetime
    step_size: float = Field(default=1.0, gt=0)
    step_unit: Literal["hour", "day", "month", "year", "step"] = "year"
    max_steps: int = Field(default=100, ge=1, le=500)
    parameters: dict[str, Any] = Field(default_factory=dict)
    initial_state_overrides: dict[str, Any] = Field(default_factory=dict)
    rule_ids: list[str] = Field(default_factory=lambda: ["population_dynamics_v1"])
    requested_metrics: list[str] = Field(default_factory=list)
    branch_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@app.get("/simulations/rules", response_model=list[TransitionRuleDefinition])
def list_simulation_rules_endpoint():
    return WorldRepository().list_simulation_rules()


@app.post("/simulations", response_model=SimulationRun)
def create_simulation_endpoint(req: CreateSimulationRequest):
    repo = WorldRepository()
    sim_req = SimulationRequest(
        scenario_id=req.scenario_id,
        scenario_version=req.scenario_version,
        starts_at=req.starts_at,
        ends_at=req.ends_at,
        step_size=req.step_size,
        step_unit=req.step_unit,
        max_steps=req.max_steps,
        parameters=req.parameters,
        initial_state_overrides=req.initial_state_overrides,
        rule_ids=req.rule_ids,
        requested_metrics=req.requested_metrics,
        branch_id=req.branch_id,
        metadata=req.metadata,
    )
    return repo.create_and_run_simulation(sim_req)


@app.get("/simulations", response_model=list[SimulationRun])
def list_simulations_endpoint(
    scenario_id: UUID | None = None,
    status: SimulationStatus | str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    scen_v = _clean_param(scenario_id)
    status_v = _clean_param(status)
    limit_v = _clean_param(limit, 100)
    offset_v = _clean_param(offset, 0)
    return WorldRepository().list_simulations(
        scenario_id=scen_v, status=status_v, limit=limit_v, offset=offset_v
    )


@app.get("/simulations/{simulation_id}", response_model=SimulationRun)
def get_simulation_endpoint(simulation_id: UUID):
    sim = WorldRepository().get_simulation(simulation_id)
    if not sim:
        raise HTTPException(status_code=404, detail=f"Simulation {simulation_id} not found")
    return sim


@app.get("/simulations/{simulation_id}/trajectory", response_model=list[SimulationStep])
def get_simulation_trajectory_endpoint(
    simulation_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
):
    repo = WorldRepository()
    sim = repo.get_simulation(simulation_id)
    if not sim:
        raise HTTPException(status_code=404, detail=f"Simulation {simulation_id} not found")
    offset_v = _clean_param(offset, 0)
    limit_v = _clean_param(limit, 200)
    return repo.get_simulation_trajectory(simulation_id, offset=offset_v, limit=limit_v)


@app.get("/simulations/{simulation_id}/steps/{step_index}", response_model=SimulationStep)
def get_simulation_step_endpoint(simulation_id: UUID, step_index: int):
    repo = WorldRepository()
    sim = repo.get_simulation(simulation_id)
    if not sim:
        raise HTTPException(status_code=404, detail=f"Simulation {simulation_id} not found")
    step = repo.get_simulation_step(simulation_id, step_index=step_index)
    if not step:
        raise HTTPException(status_code=404, detail=f"Step {step_index} not found for simulation {simulation_id}")
    return step


@app.get("/simulations/{simulation_a_id}/compare/{simulation_b_id}", response_model=SimulationComparison)
def compare_simulations_endpoint(simulation_a_id: UUID, simulation_b_id: UUID):
    repo = WorldRepository()
    sim_a = repo.get_simulation(simulation_a_id)
    if not sim_a:
        raise HTTPException(status_code=404, detail=f"Simulation A {simulation_a_id} not found")
    sim_b = repo.get_simulation(simulation_b_id)
    if not sim_b:
        raise HTTPException(status_code=404, detail=f"Simulation B {simulation_b_id} not found")
    return repo.compare_simulations(simulation_a_id, simulation_b_id)


@app.post("/simulations/{simulation_id}/cancel")
def cancel_simulation_endpoint(simulation_id: UUID):
    repo = WorldRepository()
    sim = repo.get_simulation(simulation_id)
    if not sim:
        raise HTTPException(status_code=404, detail=f"Simulation {simulation_id} not found")
    try:
        cancelled = repo.cancel_simulation(simulation_id)
        return {"cancelled": cancelled, "simulation_id": simulation_id}
    except SimulationLifecycleError as sle:
        raise HTTPException(status_code=400, detail=str(sle)) from sle


# ==============================================================================
# Engine 15: Anomaly Detection Endpoints
# ==============================================================================


@app.get("/anomalies/methods", response_model=list[DetectionMethodDefinition])
def list_anomaly_methods_endpoint():
    """List registered anomaly detection methods and their configuration requirements."""
    return WorldRepository().list_anomaly_methods()


@app.post("/anomalies/detect", response_model=AnomalyRun)
def detect_anomalies_endpoint(request: AnomalyDetectionRequest):
    """Execute a deterministic anomaly detection run over authoritative observations."""
    repo = WorldRepository()
    try:
        return repo.detect_anomalies(request)
    except AnomalyConfigurationError as ace:
        raise HTTPException(status_code=400, detail=str(ace)) from ace
    except AnomalyDataQualityError as adqe:
        raise HTTPException(status_code=422, detail=str(adqe)) from adqe


@app.get("/anomalies/runs", response_model=list[AnomalyRun])
def list_anomaly_runs_endpoint(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List anomaly detection runs with pagination and optional status filter."""
    status_v = _clean_param(status)
    limit_v = _clean_param(limit, 50)
    offset_v = _clean_param(offset, 0)
    return WorldRepository().list_anomaly_runs(status=status_v, limit=limit_v, offset=offset_v)


@app.get("/anomalies/runs/{run_id}", response_model=AnomalyRun)
def get_anomaly_run_endpoint(run_id: UUID):
    """Retrieve an anomaly run and its associated findings."""
    run = WorldRepository().get_anomaly_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Anomaly run {run_id} not found")
    return run


@app.get("/anomalies/findings", response_model=list[AnomalyFinding])
def list_anomaly_findings_endpoint(
    entity_id: UUID | None = None,
    metric: str | None = None,
    severity: AnomalySeverity | str | None = None,
    status: FindingLifecycleStatus | str | None = None,
    detection_method: DetectionMethod | str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """List anomaly findings with structured filters and pagination."""
    eid_v = _clean_param(entity_id)
    met_v = _clean_param(metric)
    sev_v = _clean_param(severity)
    st_v = _clean_param(status)
    dm_v = _clean_param(detection_method)
    limit_v = _clean_param(limit, 100)
    offset_v = _clean_param(offset, 0)
    return WorldRepository().list_anomaly_findings(
        entity_id=eid_v,
        metric=met_v,
        severity=sev_v,
        status=st_v,
        detection_method=dm_v,
        limit=limit_v,
        offset=offset_v,
    )


@app.get("/anomalies/findings/{finding_id}", response_model=AnomalyFinding)
def get_anomaly_finding_endpoint(finding_id: UUID):
    """Retrieve an individual anomaly finding by its unique identifier."""
    finding = WorldRepository().get_anomaly_finding(finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail=f"Anomaly finding {finding_id} not found")
    return finding


class FindingActionRequest(BaseModel):
    notes: str | None = None


@app.post("/anomalies/findings/{finding_id}/suppress", response_model=AnomalyFinding)
def suppress_anomaly_finding_endpoint(finding_id: UUID, req: FindingActionRequest | None = None):
    """Suppress a finding to prevent repeated operational alert notifications."""
    repo = WorldRepository()
    try:
        notes = req.notes if req else None
        return repo.suppress_anomaly_finding(finding_id, notes=notes)
    except AnomalyLifecycleError as ale:
        if "not found" in str(ale).lower():
            raise HTTPException(status_code=404, detail=str(ale)) from ale
        raise HTTPException(status_code=400, detail=str(ale)) from ale


@app.post("/anomalies/findings/{finding_id}/resolve", response_model=AnomalyFinding)
def resolve_anomaly_finding_endpoint(finding_id: UUID, req: FindingActionRequest | None = None):
    """Mark a finding as resolved after verification or baseline remediation."""
    repo = WorldRepository()
    try:
        notes = req.notes if req else None
        return repo.resolve_anomaly_finding(finding_id, notes=notes)
    except AnomalyLifecycleError as ale:
        if "not found" in str(ale).lower():
            raise HTTPException(status_code=404, detail=str(ale)) from ale
        raise HTTPException(status_code=400, detail=str(ale)) from ale


# ==============================================================================
# Engine 18: Prediction Engine Endpoints
# ==============================================================================


@app.get("/predictions/methods", response_model=list[PredictionMethodDefinition])
def list_prediction_methods_endpoint():
    """List registered deterministic forecasting methods and configuration requirements."""
    repo = WorldRepository()
    return repo.list_prediction_methods()


@app.get("/predictions/metrics")
def list_prediction_evaluation_metrics_endpoint():
    """Inspect supported forecasting evaluation metrics and their mathematical definitions."""
    return {
        "metrics": [
            {
                "id": "mae",
                "name": "Mean Absolute Error",
                "formula": "mean(|y - y_hat|)",
                "description": "Measures average magnitude of forecast errors in the same units as the target metric.",
            },
            {
                "id": "rmse",
                "name": "Root Mean Squared Error",
                "formula": "sqrt(mean((y - y_hat)^2))",
                "description": "Penalizes larger forecast errors more severely than smaller errors.",
            },
            {
                "id": "mase",
                "name": "Mean Absolute Scaled Error",
                "formula": "MAE / in_sample_naive_MAE",
                "description": "Scale-independent metric comparing model accuracy to in-sample one-step naive baseline.",
            },
            {
                "id": "bias",
                "name": "Mean Signed Error",
                "formula": "mean(y_hat - y)",
                "description": "Identifies systematic tendency to overestimate (positive) or underestimate (negative).",
            },
            {
                "id": "interval_coverage",
                "name": "Prediction Interval Coverage",
                "formula": "count(lower <= y <= upper) / total_evaluations",
                "description": "Empirical proportion of verified observations falling within nominal prediction intervals.",
            },
        ]
    }


@app.post("/predictions", response_model=PredictionRun)
def create_prediction_endpoint(req: PredictionRequest):
    """Create, execute, and persist a bounded deterministic forecasting run."""
    repo = WorldRepository()
    return repo.create_and_run_prediction(req)


@app.get("/predictions/runs", response_model=list[PredictionRun])
def list_prediction_runs_endpoint(
    entity_id: UUID | None = None,
    metric: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List historical prediction runs with optional entity, metric, and status filters."""
    repo = WorldRepository()
    return repo.list_prediction_runs(
        entity_id=entity_id,
        metric=metric,
        status=status,
        limit=limit,
        offset=offset,
    )


@app.get("/predictions/runs/{run_id}", response_model=PredictionRun)
def get_prediction_run_endpoint(run_id: UUID):
    """Retrieve metadata and historical summary for a specific prediction run."""
    repo = WorldRepository()
    run = repo.get_prediction_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Prediction run '{run_id}' not found")
    return run


@app.get("/predictions/runs/{run_id}/trajectory", response_model=list[PredictionPoint])
def get_prediction_trajectory_endpoint(
    run_id: UUID,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """Retrieve ordered forecast trajectory points with uncertainty intervals for a run."""
    repo = WorldRepository()
    run = repo.get_prediction_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Prediction run '{run_id}' not found")
    return repo.get_prediction_trajectory(run_id, limit=limit, offset=offset)


@app.post("/predictions/runs/{run_id}/evaluate", response_model=PredictionEvaluation)
def evaluate_prediction_run_endpoint(run_id: UUID):
    """Evaluate a completed prediction run against subsequently observed empirical observations."""
    repo = WorldRepository()
    run = repo.get_prediction_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Prediction run '{run_id}' not found")
    return repo.evaluate_prediction_run(run_id)


@app.get("/predictions/runs/{run_id}/evaluation", response_model=PredictionEvaluation)
def get_prediction_evaluation_endpoint(run_id: UUID):
    """Retrieve recorded evaluation metrics for a prediction run."""
    repo = WorldRepository()
    eval_rec = repo.get_prediction_evaluation(run_id)
    if not eval_rec:
        raise HTTPException(status_code=404, detail=f"No evaluation recorded for prediction run '{run_id}'")
    return eval_rec


@app.post("/predictions/backtest", response_model=BacktestResult)
def run_prediction_backtest_endpoint(req: BacktestRequest):
    """Execute a rolling-origin walk-forward backtest to evaluate out-of-sample forecast accuracy."""
    repo = WorldRepository()
    return repo.run_prediction_backtest(req)


# =============================================================================
# Strategic Multi-Modal Route Planning & Threat Avoidance (Phase 1)
# =============================================================================
from .routing import (
    StrategicRouteEngine,
    RoutePlanRequest,
    RoutePlanResponse,
    HubLocation,
    ConflictZone,
)


@app.get("/routing/hubs", response_model=dict[str, list[HubLocation]])
def get_routing_hubs_endpoint():
    """Retrieve curated global aviation airports and maritime seaports for route planning."""
    engine = StrategicRouteEngine()
    return engine.list_hubs()


@app.get("/routing/conflict-zones", response_model=list[ConflictZone])
def get_routing_conflict_zones_endpoint():
    """Retrieve active geopolitical conflict zones and closed airspace/maritime exclusion areas."""
    engine = StrategicRouteEngine()
    return engine.list_conflict_zones()


@app.post("/routing/plan", response_model=RoutePlanResponse)
def plan_strategic_route_endpoint(req: RoutePlanRequest):
    """Compute an optimized multi-modal route with geodesic curvature, threat avoidance, and metrics."""
    engine = StrategicRouteEngine()
    try:
        return engine.plan_route(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

