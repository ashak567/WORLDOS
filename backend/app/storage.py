"""PostgreSQL/PostGIS is the write authority; no map cache is a source of truth."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from .domain import WorldBundle


class WorldRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.environ["WORLDOS_DATABASE_URL"]

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            yield connection

    def ingest(self, bundle: WorldBundle) -> UUID:
        """Idempotently persist one fact and every piece of its provenance."""
        b = bundle
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO sources (id,slug,name,publisher,license,homepage,refresh_policy)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name
                   RETURNING id""",
                (b.source.id, b.source.slug, b.source.name, b.source.publisher, b.source.license,
                 str(b.source.homepage) if b.source.homepage else None, b.source.refresh_policy),
            )
            source_id = cur.fetchone()["id"]
            entity_id = None
            for identifier in b.identifiers:
                cur.execute("SELECT entity_id FROM entity_identifiers WHERE scheme=%s AND value=%s",
                            (identifier.scheme, identifier.value))
                match = cur.fetchone()
                if match:
                    entity_id = match["entity_id"]
                    break
            if entity_id is None:
                cur.execute(
                    """INSERT INTO entities (id,kind,canonical_name,source_id,source_key,attributes,confidence)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (source_id,source_key) DO UPDATE SET canonical_name=EXCLUDED.canonical_name,
                           attributes=EXCLUDED.attributes, confidence=EXCLUDED.confidence RETURNING id""",
                    (b.entity.id, b.entity.kind, b.entity.canonical_name, source_id, b.entity.source_key,
                     json.dumps(b.entity.attributes), b.entity.confidence.value),
                )
                entity_id = cur.fetchone()["id"]
            for identifier in b.identifiers:
                cur.execute(
                    """INSERT INTO entity_identifiers (entity_id,source_id,source_key,scheme,value,confidence)
                       VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (entity_id, source_id, identifier.source_key, identifier.scheme, identifier.value,
                     identifier.confidence.value),
                )
            if b.time_interval:
                cur.execute(
                    """INSERT INTO time_intervals (id,starts_at,ends_at,precision) VALUES (%s,%s,%s,%s)
                       ON CONFLICT (id) DO NOTHING""",
                    (b.time_interval.id, b.time_interval.starts_at, b.time_interval.ends_at, b.time_interval.precision),
                )
            cur.execute(
                """INSERT INTO evidence (id,source_id,locator,retrieved_at,content_hash,excerpt)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (source_id,locator) DO UPDATE SET retrieved_at=EXCLUDED.retrieved_at,
                       content_hash=EXCLUDED.content_hash RETURNING id""",
                (b.evidence.id, source_id, b.evidence.locator, b.evidence.retrieved_at,
                 b.evidence.content_hash, b.evidence.excerpt),
            )
            evidence_id = cur.fetchone()["id"]
            cur.execute(
                """INSERT INTO provenance (id,evidence_id,pipeline_version,transformation)
                   VALUES (%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
                (b.provenance.id, evidence_id, b.provenance.pipeline_version,
                 json.dumps(b.provenance.transformation)),
            )
            if b.geometry:
                cur.execute(
                    """INSERT INTO geometries (id,entity_id,geometry,geometry_kind,valid_during,source_id,confidence)
                       VALUES (%s,%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),%s,NULL,%s,%s)
                       ON CONFLICT (id) DO NOTHING""",
                    (b.geometry.id, entity_id, json.dumps(b.geometry.geojson), b.geometry.geometry_kind,
                     source_id, b.geometry.confidence.value),
                )
            if b.event:
                cur.execute(
                    """INSERT INTO events (id,kind,subject_entity_id,time_interval_id,evidence_id,confidence,attributes)
                       VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
                    (b.event.id, b.event.kind, entity_id, b.time_interval.id, evidence_id,
                     b.event.confidence.value, json.dumps(b.event.attributes)),
                )
            for rel in b.relationships:
                rel_interval_id = rel.time_interval_id or (b.time_interval.id if b.time_interval else None)
                cur.execute(
                    """INSERT INTO relationships (id,subject_entity_id,predicate,object_entity_id,time_interval_id,evidence_id,confidence,attributes)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
                    (rel.id, rel.subject_entity_id, rel.predicate, rel.object_entity_id,
                     rel_interval_id, evidence_id, rel.confidence.value, json.dumps(rel.attributes)),
                )
            if b.observation:
                cur.execute(
                    """INSERT INTO observations (id,subject_entity_id,measure,value,unit,time_interval_id,evidence_id,
                        provenance_id,confidence,attributes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (id) DO UPDATE SET value=EXCLUDED.value, evidence_id=EXCLUDED.evidence_id,
                           provenance_id=EXCLUDED.provenance_id, confidence=EXCLUDED.confidence,
                           attributes=EXCLUDED.attributes
                       RETURNING id""",
                    (b.observation.id, entity_id, b.observation.measure, b.observation.value, b.observation.unit,
                     b.time_interval.id, evidence_id, b.provenance.id, b.observation.confidence.value,
                     json.dumps(b.observation.attributes)),
                )
                return cur.fetchone()["id"]
            if b.event:
                return b.event.id
            if b.geometry:
                return b.geometry.id
            return entity_id

    def observations(self, measure: str, start: datetime | None, end: datetime | None) -> list[dict[str, Any]]:
        clauses, values = ["o.measure = %s"], [measure]
        if start:
            clauses.append("t.starts_at >= %s")
            values.append(start)
        if end:
            clauses.append("t.starts_at <= %s")
            values.append(end)
        sql = f"""SELECT o.id, e.id AS entity_id, e.canonical_name, o.measure, o.value, o.unit,
                         t.starts_at, t.ends_at, ev.locator AS evidence_locator, o.confidence
                  FROM observations o JOIN entities e ON e.id=o.subject_entity_id
                  JOIN time_intervals t ON t.id=o.time_interval_id JOIN evidence ev ON ev.id=o.evidence_id
                  WHERE {' AND '.join(clauses)} ORDER BY t.starts_at DESC"""
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, values)
            return list(cur.fetchall())

    def events(self, kind: str | None = None) -> list[dict[str, Any]]:
        clauses, values = [], []
        if kind:
            clauses.append("ev.kind = %s")
            values.append(kind)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""SELECT ev.id, ev.kind, ev.subject_entity_id, e.canonical_name AS subject_name,
                         t.starts_at, evi.locator AS evidence_locator, ev.confidence, ev.attributes
                  FROM events ev LEFT JOIN entities e ON e.id=ev.subject_entity_id
                  JOIN time_intervals t ON t.id=ev.time_interval_id
                  JOIN evidence evi ON evi.id=ev.evidence_id
                  {where_clause} ORDER BY t.starts_at DESC"""
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, values)
            return list(cur.fetchall())

    def context(self, entity_id: UUID) -> dict[str, Any] | None:
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT id,kind,canonical_name,attributes,confidence FROM entities WHERE id=%s", (entity_id,))
            entity = cur.fetchone()
            if not entity:
                return None
            cur.execute("""SELECT predicate, object_entity_id, confidence FROM relationships WHERE subject_entity_id=%s
                         UNION ALL SELECT predicate, subject_entity_id, confidence FROM relationships WHERE object_entity_id=%s""",
                        (entity_id, entity_id))
            entity["relationships"] = list(cur.fetchall())
            cur.execute("""SELECT measure,value,unit,t.starts_at,e.locator FROM observations o
                         JOIN time_intervals t ON t.id=o.time_interval_id JOIN evidence e ON e.id=o.evidence_id
                         WHERE subject_entity_id=%s ORDER BY t.starts_at DESC LIMIT 100""", (entity_id,))
            entity["observations"] = list(cur.fetchall())
            return entity

    def near(self, longitude: float, latitude: float, radius_km: float) -> list[dict[str, Any]]:
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT e.id, e.canonical_name, e.kind,
                         MIN(ST_Distance(g.geometry::geography, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography)/1000) AS distance_km
                   FROM geometries g JOIN entities e ON e.id=g.entity_id
                   WHERE ST_DWithin(g.geometry::geography, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s)
                   GROUP BY e.id, e.canonical_name, e.kind
                   ORDER BY distance_km""",
                (longitude, latitude, longitude, latitude, radius_km * 1000),
            )
            return list(cur.fetchall())

    def find_containing_entity(self, longitude: float, latitude: float, geometry_kind: str = "country_boundary") -> dict[str, Any] | None:
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT e.id, e.canonical_name, e.kind
                   FROM geometries g JOIN entities e ON e.id=g.entity_id
                   WHERE g.geometry_kind=%s
                     AND ST_Contains(g.geometry, ST_SetSRID(ST_MakePoint(%s,%s), 4326))
                   LIMIT 1""",
                (geometry_kind, longitude, latitude),
            )
            return cur.fetchone()

    def geometries(self) -> list[dict[str, Any]]:
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT g.id, e.id AS entity_id, e.canonical_name, g.geometry_kind,
                         ST_AsGeoJSON(g.geometry)::json AS geometry
                   FROM geometries g JOIN entities e ON e.id=g.entity_id ORDER BY e.canonical_name"""
            )
            return list(cur.fetchall())

    def population_change(self, entity_id: UUID) -> list[dict[str, Any]]:
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT t.starts_at, o.value, o.value - LAG(o.value) OVER (ORDER BY t.starts_at) AS change
                   FROM observations o JOIN time_intervals t ON t.id=o.time_interval_id
                   WHERE o.subject_entity_id=%s AND o.measure='population.total' ORDER BY t.starts_at""",
                (entity_id,),
            )
            return list(cur.fetchall())

