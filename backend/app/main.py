from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid5

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from .domain import (Confidence, Entity, EntityIdentifier, Event, Evidence, Geometry, Observation, Provenance,
                     Relationship, Source, TimeInterval, WorldBundle)
from .ingestion.natural_earth import fetch_country_boundary
from .ingestion.usgs import EarthquakeRecord, fetch_earthquake
from .ingestion.world_bank import fetch_country_point, fetch_population, retrieved_now
from .storage import WorldRepository

app = FastAPI(title="WORLDOS", version="0.1.0", description="Evidence-first world model API")
NAMESPACE = UUID("b0dcd802-3c40-4b12-99d5-3707d5a07603")


def stable_id(*parts: str) -> UUID:
    return uuid5(NAMESPACE, ":".join(parts))


class IngestionResult(BaseModel):
    country_code: str
    observations_written: int
    observation_ids: list[UUID]


class GeometryIngestionResult(BaseModel):
    country_code: str
    geometry_id: UUID


class EarthquakeIngestionResult(BaseModel):
    event_id: str
    entity_id: UUID
    observation_id: UUID
    event_id_persisted: UUID
    containing_country_id: UUID | None = None
    relationships_written: int


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
    records = fetch_population(country_code, year=year)
    if not records:
        raise HTTPException(status_code=404, detail="World Bank returned no population observations")
    point, now, repo = fetch_country_point(country_code), retrieved_now(), WorldRepository()
    ids = [repo.ingest(world_bank_bundle(record, point, now)) for record in records]
    return IngestionResult(country_code=country_code, observations_written=len(ids), observation_ids=ids)


@app.post("/ingest/natural-earth/country/{country_code}", response_model=GeometryIngestionResult)
def ingest_natural_earth_country(country_code: str) -> GeometryIngestionResult:
    country_code = country_code.upper()
    try:
        boundary = fetch_country_boundary(country_code)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    geometry_id = WorldRepository().ingest(natural_earth_bundle(boundary, retrieved_now()))
    return GeometryIngestionResult(country_code=country_code, geometry_id=geometry_id)


@app.post("/ingest/usgs/earthquake/{event_id}", response_model=EarthquakeIngestionResult)
def ingest_usgs_earthquake(event_id: str) -> EarthquakeIngestionResult:
    try:
        record = fetch_earthquake(event_id)
    except Exception as error:
        raise HTTPException(status_code=404, detail=f"USGS earthquake {event_id} not found: {error}") from error
    repo = WorldRepository()
    containing_country = repo.find_containing_entity(record.longitude, record.latitude)
    containing_id = containing_country["id"] if containing_country else None
    bundle = usgs_earthquake_bundle(record, retrieved_now(), containing_entity_id=containing_id)
    repo.ingest(bundle)
    return EarthquakeIngestionResult(
        event_id=record.event_id,
        entity_id=bundle.entity.id,
        observation_id=bundle.observation.id,
        event_id_persisted=bundle.event.id,
        containing_country_id=containing_id,
        relationships_written=len(bundle.relationships),
    )


@app.get("/observations")
def observations(measure: str = "population.total", start: datetime | None = None, end: datetime | None = None):
    return WorldRepository().observations(measure, start, end)


@app.get("/events")
def events(kind: str | None = None):
    return WorldRepository().events(kind=kind)


@app.get("/entities/{entity_id}/context")
def context(entity_id: UUID):
    result = WorldRepository().context(entity_id)
    if not result:
        raise HTTPException(status_code=404, detail="entity not found")
    return result


@app.get("/spatial/entities")
def nearby_entities(longitude: float = Query(ge=-180, le=180), latitude: float = Query(ge=-90, le=90),
                    radius_km: float = Query(default=50, gt=0, le=20_000)):
    return WorldRepository().near(longitude, latitude, radius_km)


@app.get("/geometries")
def geometries():
    return WorldRepository().geometries()


@app.get("/analytics/population/{entity_id}/change")
def population_change(entity_id: UUID):
    return WorldRepository().population_change(entity_id)

