from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4, uuid5

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

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
    ScenarioProposal,
    SensitivityVariation,
    SnapshotManifest,
    Source,
    SpatialRollupItem,
    SpatialSliceComparison,
    TemporalTrendItem,
    TimeInterval,
    TruthClass,
    WorldBundle,
    WorldContext,
)
from .analytics import DuckDbSpatialAnalytics
from .benchmarks import AnalyticalBenchmarkSuite
from .constraints import ConstraintEngine, ConstraintViolationError
from .export import export_observations
from .ingestion.natural_earth import fetch_country_boundary
from .ingestion.usgs import EarthquakeRecord, fetch_earthquake
from .ingestion.world_bank import fetch_country_point, fetch_population, retrieved_now
from .snapshots import SnapshotCatalog, SnapshotManager
from .storage import WorldRepository

app = FastAPI(title="WORLDOS", version="0.1.0", description="Evidence-first world model API")


@app.exception_handler(ConstraintViolationError)
def constraint_violation_handler(request, exc: ConstraintViolationError):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=422,
        content={
            "detail": str(exc),
            "validation": exc.result.model_dump(mode="json"),
        },
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
