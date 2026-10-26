"""PostgreSQL/PostGIS is the write authority; no map cache is a source of truth."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from typing import Any, Iterator
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from .domain import (
    Alert,
    AlertEvaluation,
    AlertLifecycleStatus,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    BoundingBox,
    Claim,
    ConstraintCategory,
    ConstraintFinding,
    ConstraintSeverity,
    ConstraintStatus,
    ConstraintValidationResult,
    ContextQueryScope,
    EvidenceCitation,
    Relationship,
    ScenarioProposal,
    SpatialScope,
    TemporalScope,
    WorldBundle,
    WorldContext,
)
from .alerts import AlertEngine
from .constraints import ConstraintEngine, ConstraintViolationError


def _extract_int(val: Any, default: int = 100) -> int:
    if hasattr(val, "default"):
        val = getattr(val, "default")
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _clean_record(d: dict[str, Any]) -> dict[str, Any]:
    res = {}
    for k, v in d.items():
        if isinstance(v, Decimal):
            res[k] = float(v)
        elif hasattr(v, "lower") and hasattr(v, "upper") and not isinstance(v, (str, bytes)):
            res[k] = str(v)
        else:
            res[k] = v
    return res


class WorldRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.environ["WORLDOS_DATABASE_URL"]
        self.constraint_engine = ConstraintEngine(repository=self)
        self.alert_engine = AlertEngine(repository=self)

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            yield connection

    def validate_bundle(self, bundle: WorldBundle) -> ConstraintValidationResult:
        """Validate a bundle against physical, spatial, temporal, and referential constraints."""
        with self._connection() as conn:
            return self.constraint_engine.validate_bundle(bundle, conn=conn)

    def validate_scenario(self, proposal: ScenarioProposal) -> ConstraintValidationResult:
        """Validate proposed scenario modifications without mutating authoritative world state."""
        with self._connection() as conn:
            return self.constraint_engine.validate_scenario_proposal(proposal, conn=conn)

    def ingest(self, bundle: WorldBundle, enforce_constraints: bool = True) -> UUID:
        """Idempotently persist one fact and every piece of its provenance after constraint validation."""
        b = bundle
        with self._connection() as conn, conn.cursor() as cur:
            if enforce_constraints:
                validation = self.constraint_engine.validate_bundle(b, conn=conn)
                if validation.status == ConstraintStatus.INVALID:
                    raise ConstraintViolationError(validation)
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
                cur.execute("SELECT id FROM entities WHERE id = %s", (b.entity.id,))
                existing_entity = cur.fetchone()
                if existing_entity:
                    entity_id = existing_entity["id"]
                else:
                    cur.execute(
                        """INSERT INTO entities (id,kind,canonical_name,source_id,source_key,attributes,confidence)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (source_id,source_key) DO UPDATE SET canonical_name=EXCLUDED.canonical_name,
                               attributes=EXCLUDED.attributes, confidence=EXCLUDED.confidence RETURNING id""",
                        (b.entity.id, b.entity.kind, b.entity.canonical_name, source_id, b.entity.source_key,
                         json.dumps(b.entity.attributes), b.entity.confidence.value),
                    )
                    entity_id = cur.fetchone()["id"]
                    cur.execute(
                        "SELECT id, canonical_name FROM entities WHERE LOWER(canonical_name) = LOWER(%s) AND id <> %s LIMIT 1",
                        (b.entity.canonical_name, entity_id),
                    )
                    name_match = cur.fetchone()
                    if name_match:
                        cur.execute(
                            """INSERT INTO entity_resolution_reviews
                               (candidate_entity_id, target_entity_id, match_reason, confidence, status, metadata)
                               VALUES (%s, %s, %s, %s, 'pending', %s)
                               ON CONFLICT (candidate_entity_id, target_entity_id, match_reason) DO NOTHING""",
                            (
                                entity_id,
                                name_match["id"],
                                "normalized_name_exact_match_unconfirmed",
                                0.70,
                                json.dumps({"candidate_source": b.source.slug, "target_name": name_match["canonical_name"]}),
                            ),
                        )
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
                geom_evidence_id = b.geometry.evidence_id or evidence_id
                geom_starts = None
                geom_ends = None
                if b.geometry.valid_during:
                    geom_starts = b.geometry.valid_during.starts_at
                    geom_ends = b.geometry.valid_during.ends_at
                elif b.time_interval:
                    geom_starts = b.time_interval.starts_at
                    geom_ends = b.time_interval.ends_at

                geom_range = None
                if geom_starts and geom_ends:
                    geom_range = f"[{geom_starts.isoformat()}, {geom_ends.isoformat()}]"
                elif geom_starts:
                    geom_range = f"[{geom_starts.isoformat()},)"

                cur.execute(
                    """INSERT INTO geometries (id,entity_id,geometry,geometry_kind,valid_during,source_id,evidence_id,confidence)
                       VALUES (%s,%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),%s,%s::tstzrange,%s,%s,%s)
                       ON CONFLICT (id) DO UPDATE SET
                         geometry=EXCLUDED.geometry,
                         geometry_kind=EXCLUDED.geometry_kind,
                         valid_during=EXCLUDED.valid_during,
                         evidence_id=EXCLUDED.evidence_id,
                         confidence=EXCLUDED.confidence""",
                    (b.geometry.id, entity_id, json.dumps(b.geometry.geojson), b.geometry.geometry_kind,
                     geom_range, source_id, geom_evidence_id, b.geometry.confidence.value),
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

    def observations(
        self,
        measure: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        valid_at: datetime | None = None,
        precision: str | None = None,
        entity_id: UUID | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        limit = _extract_int(limit, 100)
        clauses, values = [], []
        if measure:
            clauses.append("o.measure = %s")
            values.append(measure)
        if entity_id:
            clauses.append("o.subject_entity_id = %s")
            values.append(entity_id)
        if valid_at:
            clauses.append("t.starts_at <= %s AND (t.ends_at IS NULL OR t.ends_at >= %s)")
            values.extend([valid_at, valid_at])
        else:
            if start and end:
                clauses.append("(t.ends_at IS NULL OR t.ends_at >= %s) AND t.starts_at <= %s")
                values.extend([start, end])
            elif start:
                clauses.append("(t.ends_at IS NULL OR t.ends_at >= %s)")
                values.append(start)
            elif end:
                clauses.append("t.starts_at <= %s")
                values.append(end)
        if precision:
            clauses.append("t.precision = %s")
            values.append(precision)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""SELECT o.id, e.id AS entity_id, e.canonical_name, o.measure, o.value, o.unit,
                         o.truth_class, t.starts_at, t.ends_at, t.precision,
                         ev.locator AS evidence_locator, s.slug AS source_slug, o.confidence, o.attributes
                  FROM observations o JOIN entities e ON e.id=o.subject_entity_id
                  JOIN time_intervals t ON t.id=o.time_interval_id JOIN evidence ev ON ev.id=o.evidence_id
                  JOIN sources s ON s.id=ev.source_id
                  {where_clause} ORDER BY t.starts_at DESC LIMIT %s"""
        values.append(limit)
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, values)
            return list(cur.fetchall())

    def events(
        self,
        kind: str | None = None,
        entity_id: UUID | None = None,
        valid_at: datetime | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        limit = _extract_int(limit, 100)
        clauses, values = [], []
        if kind:
            clauses.append("ev.kind = %s")
            values.append(kind)
        if entity_id:
            clauses.append("ev.subject_entity_id = %s")
            values.append(entity_id)
        if valid_at:
            clauses.append("t.starts_at <= %s AND (t.ends_at IS NULL OR t.ends_at >= %s)")
            values.extend([valid_at, valid_at])
        else:
            if start and end:
                clauses.append("(t.ends_at IS NULL OR t.ends_at >= %s) AND t.starts_at <= %s")
                values.extend([start, end])
            elif start:
                clauses.append("(t.ends_at IS NULL OR t.ends_at >= %s)")
                values.append(start)
            elif end:
                clauses.append("t.starts_at <= %s")
                values.append(end)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""SELECT ev.id, ev.kind, ev.subject_entity_id, e.canonical_name AS subject_name,
                         t.starts_at, t.ends_at, t.precision,
                         evi.locator AS evidence_locator, s.slug AS source_slug,
                         ev.confidence, ev.attributes
                  FROM events ev LEFT JOIN entities e ON e.id=ev.subject_entity_id
                  JOIN time_intervals t ON t.id=ev.time_interval_id
                  JOIN evidence evi ON evi.id=ev.evidence_id
                  JOIN sources s ON s.id=evi.source_id
                  {where_clause} ORDER BY t.starts_at DESC LIMIT %s"""
        values.append(limit)
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, values)
            return list(cur.fetchall())

    def context(self, entity_id: UUID) -> dict[str, Any] | None:
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT id,kind,canonical_name,attributes,confidence FROM entities WHERE id=%s", (entity_id,))
            entity = cur.fetchone()
            if not entity:
                return None
            cur.execute("""SELECT r.predicate, r.object_entity_id, r.confidence, ev.locator AS evidence_locator
                           FROM relationships r JOIN evidence ev ON ev.id = r.evidence_id
                           WHERE r.subject_entity_id=%s
                           UNION ALL
                           SELECT r.predicate, r.subject_entity_id, r.confidence, ev.locator AS evidence_locator
                           FROM relationships r JOIN evidence ev ON ev.id = r.evidence_id
                           WHERE r.object_entity_id=%s""",
                        (entity_id, entity_id))
            entity["relationships"] = list(cur.fetchall())
            cur.execute("""SELECT measure,value,unit,truth_class,t.starts_at,t.precision,e.locator FROM observations o
                         JOIN time_intervals t ON t.id=o.time_interval_id JOIN evidence e ON e.id=o.evidence_id
                         WHERE subject_entity_id=%s ORDER BY t.starts_at DESC LIMIT 100""", (entity_id,))
            entity["observations"] = list(cur.fetchall())
            cur.execute("""SELECT id, claim_type, truth_class, value, unit, method,
                                  computation_version, inputs, evidence_ids, assumptions,
                                  confidence, created_at
                           FROM claims
                           WHERE subject_entity_id = %s
                           ORDER BY created_at DESC LIMIT 100""", (entity_id,))
            entity["claims"] = list(cur.fetchall())
            return entity

    def scoped_context(
        self,
        bbox: BoundingBox | None = None,
        valid_at: datetime | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        precision: str | None = None,
        entity_ids: list[UUID] | None = None,
        entity_kind: str | None = None,
        limit: int = 100,
    ) -> WorldContext:
        limit = _extract_int(limit, 100)
        assumptions: list[str] = [
            "Deterministic world context assembled directly from authoritative PostGIS operational tables",
            "Observed, derived, and inferred assertions retain explicit truth classes and evidence citations",
        ]
        if bbox:
            assumptions.append(
                f"Spatially scoped to bounding box [{bbox.min_longitude}, {bbox.min_latitude}, {bbox.max_longitude}, {bbox.max_latitude}]"
            )
        if valid_at:
            assumptions.append(f"Temporally scoped to point-in-time valid_at={valid_at.isoformat()}")
        elif start or end:
            s_str = start.isoformat() if start else "earliest"
            e_str = end.isoformat() if end else "latest"
            assumptions.append(f"Temporally scoped to interval [{s_str}, {e_str}]")
        if precision:
            assumptions.append(f"Constrained to temporal precision={precision}")
        assumptions.append(f"Slice bounded to maximum {limit} entities and factual records")

        with self._connection() as conn, conn.cursor() as cur:
            matched_geoms: dict[UUID, dict[str, Any]] = {}
            target_entity_ids: set[UUID] = set()

            if bbox:
                g_clauses = ["ST_Intersects(g.geometry, ST_MakeEnvelope(%s, %s, %s, %s, 4326))"]
                g_values: list[Any] = [bbox.min_longitude, bbox.min_latitude, bbox.max_longitude, bbox.max_latitude]
                if valid_at:
                    g_clauses.append("(g.valid_during IS NULL OR g.valid_during @> %s::timestamptz)")
                    g_values.append(valid_at)
                elif start and end:
                    g_clauses.append("(g.valid_during IS NULL OR g.valid_during && tstzrange(%s, %s, '[]'))")
                    g_values.extend([start, end])
                elif start:
                    g_clauses.append("(g.valid_during IS NULL OR upper(g.valid_during) IS NULL OR upper(g.valid_during) >= %s)")
                    g_values.append(start)
                elif end:
                    g_clauses.append("(g.valid_during IS NULL OR lower(g.valid_during) <= %s)")
                    g_values.append(end)

                if entity_kind:
                    g_clauses.append("e.kind = %s")
                    g_values.append(entity_kind)
                if entity_ids:
                    g_clauses.append("g.entity_id = ANY(%s)")
                    g_values.append(list(entity_ids))

                g_sql = f"""
                    SELECT g.id, g.entity_id, e.canonical_name, g.geometry_kind, g.confidence, g.valid_during,
                           g.evidence_id, ev.locator AS evidence_locator, ev.retrieved_at AS evidence_retrieved_at,
                           s.id AS source_id, s.slug AS source_slug, s.name AS source_name,
                           ST_AsGeoJSON(g.geometry)::json AS geometry
                    FROM geometries g
                    JOIN entities e ON e.id = g.entity_id
                    JOIN sources s ON s.id = g.source_id
                    LEFT JOIN evidence ev ON ev.id = g.evidence_id
                    WHERE {' AND '.join(g_clauses)}
                    ORDER BY e.canonical_name, g.geometry_kind, g.id
                    LIMIT %s
                """
                g_values.append(limit)
                cur.execute(g_sql, g_values)
                for row in cur.fetchall():
                    row_clean = _clean_record(row)
                    matched_geoms[row_clean["id"]] = row_clean
                    target_entity_ids.add(row_clean["entity_id"])

                if entity_ids:
                    target_entity_ids.update(entity_ids)
            else:
                if entity_ids:
                    target_entity_ids.update(entity_ids)
                else:
                    e_clauses = []
                    e_values = []
                    if entity_kind:
                        e_clauses.append("e.kind = %s")
                        e_values.append(entity_kind)
                    if valid_at:
                        e_clauses.append("""
                            e.id IN (
                                SELECT o.subject_entity_id FROM observations o
                                JOIN time_intervals t ON t.id = o.time_interval_id
                                WHERE t.starts_at <= %s AND (t.ends_at IS NULL OR t.ends_at >= %s)
                                UNION
                                SELECT ev.subject_entity_id FROM events ev
                                JOIN time_intervals t ON t.id = ev.time_interval_id
                                WHERE ev.subject_entity_id IS NOT NULL AND t.starts_at <= %s AND (t.ends_at IS NULL OR t.ends_at >= %s)
                            )
                        """)
                        e_values.extend([valid_at, valid_at, valid_at, valid_at])
                    elif start and end:
                        e_clauses.append("""
                            e.id IN (
                                SELECT o.subject_entity_id FROM observations o
                                JOIN time_intervals t ON t.id = o.time_interval_id
                                WHERE (t.ends_at IS NULL OR t.ends_at >= %s) AND t.starts_at <= %s
                                UNION
                                SELECT ev.subject_entity_id FROM events ev
                                JOIN time_intervals t ON t.id = ev.time_interval_id
                                WHERE ev.subject_entity_id IS NOT NULL AND (t.ends_at IS NULL OR t.ends_at >= %s) AND t.starts_at <= %s
                            )
                        """)
                        e_values.extend([start, end, start, end])
                    elif start:
                        e_clauses.append("""
                            e.id IN (
                                SELECT o.subject_entity_id FROM observations o
                                JOIN time_intervals t ON t.id = o.time_interval_id
                                WHERE (t.ends_at IS NULL OR t.ends_at >= %s)
                                UNION
                                SELECT ev.subject_entity_id FROM events ev
                                JOIN time_intervals t ON t.id = ev.time_interval_id
                                WHERE ev.subject_entity_id IS NOT NULL AND (t.ends_at IS NULL OR t.ends_at >= %s)
                            )
                        """)
                        e_values.extend([start, start])
                    elif end:
                        e_clauses.append("""
                            e.id IN (
                                SELECT o.subject_entity_id FROM observations o
                                JOIN time_intervals t ON t.id = o.time_interval_id
                                WHERE t.starts_at <= %s
                                UNION
                                SELECT ev.subject_entity_id FROM events ev
                                JOIN time_intervals t ON t.id = ev.time_interval_id
                                WHERE ev.subject_entity_id IS NOT NULL AND t.starts_at <= %s
                            )
                        """)
                        e_values.extend([end, end])

                    where_e = f"WHERE {' AND '.join(e_clauses)}" if e_clauses else ""
                    cur.execute(f"SELECT e.id FROM entities e {where_e} ORDER BY e.canonical_name, e.id LIMIT %s", e_values + [limit])
                    for r in cur.fetchall():
                        target_entity_ids.add(r["id"])

            query_scope = ContextQueryScope(
                spatial=SpatialScope(bounding_box=bbox, filter_type="intersects") if bbox else None,
                temporal=TemporalScope(valid_at=valid_at, starts_at=start, ends_at=end, precision=precision) if (valid_at or start or end or precision) else None,
                entity_ids=list(entity_ids) if entity_ids else None,
                entity_kind=entity_kind,
                limit=limit,
            )

            if not target_entity_ids:
                return WorldContext(
                    query_scope=query_scope,
                    entities=[],
                    observations=[],
                    events=[],
                    geometries=[],
                    relationships=[],
                    claims=[],
                    evidence=[],
                    assumptions_or_limitations=assumptions + ["No entities matched the requested query scope"],
                )

            target_list = list(target_entity_ids)

            # Step 2: Fetch Entities
            cur.execute(
                """SELECT id, kind, canonical_name, attributes, confidence
                   FROM entities
                   WHERE id = ANY(%s)
                   ORDER BY canonical_name, id""",
                (target_list,),
            )
            entities_list = [_clean_record(r) for r in cur.fetchall()]
            resolved_entity_ids = [e["id"] for e in entities_list]

            if not resolved_entity_ids:
                return WorldContext(
                    query_scope=query_scope,
                    entities=[],
                    observations=[],
                    events=[],
                    geometries=[],
                    relationships=[],
                    claims=[],
                    evidence=[],
                    assumptions_or_limitations=assumptions + ["Specified entity IDs not found in authoritative world state"],
                )

            # Step 3: Fetch Geometries (if not already fetched with bbox)
            if not bbox:
                cur.execute(
                    """SELECT g.id, g.entity_id, e.canonical_name, g.geometry_kind, g.confidence, g.valid_during,
                              g.evidence_id, ev.locator AS evidence_locator, ev.retrieved_at AS evidence_retrieved_at,
                              s.id AS source_id, s.slug AS source_slug, s.name AS source_name,
                              ST_AsGeoJSON(g.geometry)::json AS geometry
                       FROM geometries g
                       JOIN entities e ON e.id = g.entity_id
                       JOIN sources s ON s.id = g.source_id
                       LEFT JOIN evidence ev ON ev.id = g.evidence_id
                       WHERE g.entity_id = ANY(%s)
                       ORDER BY e.canonical_name, g.geometry_kind, g.id
                       LIMIT %s""",
                    (resolved_entity_ids, limit),
                )
                for row in cur.fetchall():
                    row_clean = _clean_record(row)
                    matched_geoms[row_clean["id"]] = row_clean

            geometries_list = list(matched_geoms.values())
            geometries_list.sort(key=lambda x: (x.get("canonical_name", ""), x.get("geometry_kind", ""), str(x.get("id"))))

            # Step 4: Observations Query
            obs_clauses = ["o.subject_entity_id = ANY(%s)"]
            obs_values: list[Any] = [resolved_entity_ids]
            if valid_at:
                obs_clauses.append("t.starts_at <= %s AND (t.ends_at IS NULL OR t.ends_at >= %s)")
                obs_values.extend([valid_at, valid_at])
            elif start and end:
                obs_clauses.append("(t.ends_at IS NULL OR t.ends_at >= %s) AND t.starts_at <= %s")
                obs_values.extend([start, end])
            elif start:
                obs_clauses.append("(t.ends_at IS NULL OR t.ends_at >= %s)")
                obs_values.append(start)
            elif end:
                obs_clauses.append("t.starts_at <= %s")
                obs_values.append(end)
            if precision:
                obs_clauses.append("t.precision = %s")
                obs_values.append(precision)

            obs_sql = f"""
                SELECT o.id, o.subject_entity_id, e.canonical_name AS subject_name,
                       o.measure, o.value, o.unit, o.truth_class,
                       t.starts_at, t.ends_at, t.precision,
                       o.evidence_id, ev.locator AS evidence_locator, ev.retrieved_at AS evidence_retrieved_at,
                       s.id AS source_id, s.slug AS source_slug, s.name AS source_name,
                       o.confidence, o.attributes
                FROM observations o
                JOIN entities e ON e.id = o.subject_entity_id
                JOIN time_intervals t ON t.id = o.time_interval_id
                JOIN evidence ev ON ev.id = o.evidence_id
                JOIN sources s ON s.id = ev.source_id
                WHERE {' AND '.join(obs_clauses)}
                ORDER BY t.starts_at DESC, o.id
                LIMIT %s
            """
            obs_values.append(limit)
            cur.execute(obs_sql, obs_values)
            observations_list = [_clean_record(r) for r in cur.fetchall()]

            # Step 5: Events Query
            ev_clauses = ["ev.subject_entity_id = ANY(%s)"]
            ev_values: list[Any] = [resolved_entity_ids]
            if valid_at:
                ev_clauses.append("t.starts_at <= %s AND (t.ends_at IS NULL OR t.ends_at >= %s)")
                ev_values.extend([valid_at, valid_at])
            elif start and end:
                ev_clauses.append("(t.ends_at IS NULL OR t.ends_at >= %s) AND t.starts_at <= %s")
                ev_values.extend([start, end])
            elif start:
                ev_clauses.append("(t.ends_at IS NULL OR t.ends_at >= %s)")
                ev_values.append(start)
            elif end:
                ev_clauses.append("t.starts_at <= %s")
                ev_values.append(end)
            if precision:
                ev_clauses.append("t.precision = %s")
                ev_values.append(precision)

            ev_sql = f"""
                SELECT ev.id, ev.kind, ev.subject_entity_id, e.canonical_name AS subject_name,
                       t.starts_at, t.ends_at, t.precision,
                       ev.evidence_id, evi.locator AS evidence_locator, evi.retrieved_at AS evidence_retrieved_at,
                       s.id AS source_id, s.slug AS source_slug, s.name AS source_name,
                       ev.confidence, ev.attributes
                FROM events ev
                LEFT JOIN entities e ON e.id = ev.subject_entity_id
                JOIN time_intervals t ON t.id = ev.time_interval_id
                JOIN evidence evi ON evi.id = ev.evidence_id
                JOIN sources s ON s.id = evi.source_id
                WHERE {' AND '.join(ev_clauses)}
                ORDER BY t.starts_at DESC, ev.id
                LIMIT %s
            """
            ev_values.append(limit)
            cur.execute(ev_sql, ev_values)
            events_list = [_clean_record(r) for r in cur.fetchall()]

            # Step 6: Relationships Query
            cur.execute(
                """SELECT r.id, r.subject_entity_id, sub.canonical_name AS subject_name, sub.kind AS subject_kind,
                          r.predicate, r.object_entity_id, obj.canonical_name AS object_name, obj.kind AS object_kind,
                          r.confidence, r.evidence_id, ev.locator AS evidence_locator, ev.retrieved_at AS evidence_retrieved_at,
                          s.id AS source_id, s.slug AS source_slug, s.name AS source_name,
                          t.starts_at, t.ends_at, t.precision, r.attributes
                   FROM relationships r
                   JOIN entities sub ON sub.id = r.subject_entity_id
                   JOIN entities obj ON obj.id = r.object_entity_id
                   JOIN evidence ev ON ev.id = r.evidence_id
                   JOIN sources s ON s.id = ev.source_id
                   LEFT JOIN time_intervals t ON t.id = r.time_interval_id
                   WHERE (r.subject_entity_id = ANY(%s) OR r.object_entity_id = ANY(%s))
                   ORDER BY r.id
                   LIMIT %s""",
                (resolved_entity_ids, resolved_entity_ids, limit),
            )
            relationships_list = [_clean_record(r) for r in cur.fetchall()]

            # Step 7: Claims Query
            cur.execute(
                """SELECT c.id, c.subject_entity_id, e.canonical_name AS subject_name,
                          c.claim_type, c.truth_class, c.value, c.unit,
                          c.time_interval_id, c.spatial_scope, c.method, c.computation_version,
                          c.inputs, c.evidence_ids, c.assumptions, c.confidence, c.created_at
                   FROM claims c
                   LEFT JOIN entities e ON e.id = c.subject_entity_id
                   WHERE c.subject_entity_id = ANY(%s)
                   ORDER BY c.created_at DESC, c.id
                   LIMIT %s""",
                (resolved_entity_ids, limit),
            )
            claims_list = [_clean_record(r) for r in cur.fetchall()]

            # Step 8: Deduplicated Evidence Citations
            collected_evidence_ids: set[UUID] = set()
            for o in observations_list:
                if o.get("evidence_id"):
                    collected_evidence_ids.add(UUID(str(o["evidence_id"])))
            for ev in events_list:
                if ev.get("evidence_id"):
                    collected_evidence_ids.add(UUID(str(ev["evidence_id"])))
            for g in geometries_list:
                if g.get("evidence_id"):
                    collected_evidence_ids.add(UUID(str(g["evidence_id"])))
            for r in relationships_list:
                if r.get("evidence_id"):
                    collected_evidence_ids.add(UUID(str(r["evidence_id"])))
            for c in claims_list:
                for eid in c.get("evidence_ids") or []:
                    collected_evidence_ids.add(UUID(str(eid)))

            evidence_citations: list[EvidenceCitation] = []
            if collected_evidence_ids:
                cur.execute(
                    """SELECT ev.id AS evidence_id, ev.source_id, s.slug AS source_slug, s.name AS source_name,
                              ev.locator, ev.retrieved_at, ev.content_hash, ev.excerpt
                       FROM evidence ev
                       JOIN sources s ON s.id = ev.source_id
                       WHERE ev.id = ANY(%s)
                       ORDER BY s.slug, ev.locator, ev.id""",
                    (list(collected_evidence_ids),),
                )
                for r in cur.fetchall():
                    evidence_citations.append(EvidenceCitation(**_clean_record(r)))

            return WorldContext(
                query_scope=query_scope,
                entities=entities_list,
                observations=observations_list,
                events=events_list,
                geometries=geometries_list,
                relationships=relationships_list,
                claims=claims_list,
                evidence=evidence_citations,
                assumptions_or_limitations=assumptions,
            )


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

    def containing_geometries(
        self,
        longitude: float,
        latitude: float,
        geometry_kind: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        limit = _extract_int(limit, 50)
        clauses = ["ST_Contains(g.geometry, ST_SetSRID(ST_MakePoint(%s, %s), 4326))"]
        values: list[Any] = [longitude, latitude]
        if geometry_kind:
            clauses.append("g.geometry_kind = %s")
            values.append(geometry_kind)
        where_clause = f"WHERE {' AND '.join(clauses)}"
        sql = f"""
            SELECT e.id AS entity_id, e.canonical_name, e.kind AS entity_kind,
                   g.id AS geometry_id, g.geometry_kind, g.confidence,
                   s.slug AS source_slug, s.name AS source_name,
                   COALESCE(ev.locator, fallback_ev.locator) AS evidence_locator,
                   COALESCE(ev.retrieved_at, fallback_ev.retrieved_at) AS evidence_retrieved_at,
                   ST_AsGeoJSON(g.geometry)::json AS geometry
            FROM geometries g
            JOIN entities e ON e.id = g.entity_id
            JOIN sources s ON s.id = g.source_id
            LEFT JOIN evidence ev ON ev.id = g.evidence_id
            LEFT JOIN LATERAL (
                SELECT locator, retrieved_at FROM evidence e WHERE e.source_id = g.source_id ORDER BY e.retrieved_at DESC LIMIT 1
            ) fallback_ev ON g.evidence_id IS NULL
            {where_clause}
            ORDER BY g.confidence DESC, e.canonical_name
            LIMIT %s
        """
        values.append(limit)
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, values)
            return list(cur.fetchall())

    def spatial_intersections(
        self,
        entity_id: UUID,
        target_geometry_kind: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        limit = _extract_int(limit, 50)
        clauses = [
            "source_g.entity_id = %s",
            "target_g.id <> source_g.id",
            "ST_Intersects(source_g.geometry, target_g.geometry)",
        ]
        values: list[Any] = [entity_id]
        if target_geometry_kind:
            clauses.append("target_g.geometry_kind = %s")
            values.append(target_geometry_kind)
        where_clause = f"WHERE {' AND '.join(clauses)}"
        sql = f"""
            SELECT
                target_e.id AS target_entity_id,
                target_e.canonical_name AS target_name,
                target_e.kind AS target_kind,
                target_g.id AS target_geometry_id,
                target_g.geometry_kind AS target_geometry_kind,
                ST_GeometryType(target_g.geometry) AS target_geometry_type,
                ST_Contains(target_g.geometry, source_g.geometry) AS target_contains_source,
                ST_Intersects(source_g.geometry, target_g.geometry) AS intersects,
                target_g.confidence,
                COALESCE(ev.locator, fallback_ev.locator) AS evidence_locator,
                s.slug AS source_slug
            FROM geometries source_g
            JOIN geometries target_g ON ST_Intersects(source_g.geometry, target_g.geometry) AND target_g.id <> source_g.id
            JOIN entities target_e ON target_e.id = target_g.entity_id
            JOIN sources s ON s.id = target_g.source_id
            LEFT JOIN evidence ev ON ev.id = target_g.evidence_id
            LEFT JOIN LATERAL (
                SELECT locator FROM evidence e WHERE e.source_id = target_g.source_id ORDER BY e.retrieved_at DESC LIMIT 1
            ) fallback_ev ON target_g.evidence_id IS NULL
            {where_clause}
            ORDER BY target_g.confidence DESC, target_e.canonical_name
            LIMIT %s
        """
        values.append(limit)
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, values)
            return list(cur.fetchall())

    def geometries(
        self,
        entity_id: UUID | None = None,
        geometry_kind: str | None = None,
        valid_at: datetime | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        limit = _extract_int(limit, 1000)
        clauses, values = [], []
        if entity_id:
            clauses.append("g.entity_id = %s")
            values.append(entity_id)
        if geometry_kind:
            clauses.append("g.geometry_kind = %s")
            values.append(geometry_kind)
        if valid_at:
            clauses.append("(g.valid_during IS NULL OR g.valid_during @> %s::timestamptz)")
            values.append(valid_at)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""SELECT g.id, e.id AS entity_id, e.canonical_name, g.geometry_kind,
                         g.valid_during, g.confidence,
                         COALESCE(ev.locator, fallback_ev.locator) AS evidence_locator,
                         s.slug AS source_slug, s.name AS source_name,
                         ST_AsGeoJSON(g.geometry)::json AS geometry
                  FROM geometries g
                  JOIN entities e ON e.id=g.entity_id
                  JOIN sources s ON s.id=g.source_id
                  LEFT JOIN evidence ev ON ev.id=g.evidence_id
                  LEFT JOIN LATERAL (
                      SELECT locator FROM evidence e WHERE e.source_id = g.source_id ORDER BY e.retrieved_at DESC LIMIT 1
                  ) fallback_ev ON g.evidence_id IS NULL
                  {where_clause}
                  ORDER BY e.canonical_name, g.geometry_kind
                  LIMIT %s"""
        values.append(limit)
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, values)
            return list(cur.fetchall())

    def relationships(
        self,
        subject_entity_id: UUID | None = None,
        predicate: str | None = None,
        object_entity_id: UUID | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        limit = _extract_int(limit, 100)
        clauses, values = [], []
        if subject_entity_id:
            clauses.append("r.subject_entity_id = %s")
            values.append(subject_entity_id)
        if predicate:
            clauses.append("r.predicate = %s")
            values.append(predicate)
        if object_entity_id:
            clauses.append("r.object_entity_id = %s")
            values.append(object_entity_id)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT
                r.id,
                r.subject_entity_id,
                sub.canonical_name AS subject_name,
                sub.kind AS subject_kind,
                r.predicate,
                r.object_entity_id,
                obj.canonical_name AS object_name,
                obj.kind AS object_kind,
                r.confidence,
                ev.locator AS evidence_locator,
                s.slug AS source_slug,
                s.name AS source_name,
                t.starts_at,
                t.ends_at,
                t.precision,
                r.attributes
            FROM relationships r
            JOIN entities sub ON sub.id = r.subject_entity_id
            JOIN entities obj ON obj.id = r.object_entity_id
            JOIN evidence ev ON ev.id = r.evidence_id
            JOIN sources s ON s.id = ev.source_id
            LEFT JOIN time_intervals t ON t.id = r.time_interval_id
            {where_clause}
            ORDER BY r.id
            LIMIT %s
        """
        values.append(limit)
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, values)
            return list(cur.fetchall())

    def record_relationship(self, relationship: Relationship) -> UUID:
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO relationships (id, subject_entity_id, predicate, object_entity_id,
                                              time_interval_id, evidence_id, confidence, attributes)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET
                     confidence = EXCLUDED.confidence,
                     attributes = EXCLUDED.attributes
                   RETURNING id""",
                (
                    relationship.id,
                    relationship.subject_entity_id,
                    relationship.predicate,
                    relationship.object_entity_id,
                    relationship.time_interval_id,
                    relationship.evidence_id,
                    relationship.confidence.value,
                    json.dumps(relationship.attributes),
                ),
            )
            return cur.fetchone()["id"]

    def entity_graph(self, entity_id: UUID, depth: int = 1, limit: int = 100) -> dict[str, Any]:
        depth = _extract_int(depth, 1)
        limit = _extract_int(limit, 100)
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, canonical_name, kind, confidence FROM entities WHERE id = %s", (entity_id,))
            root = cur.fetchone()
            if not root:
                return {"root_entity_id": str(entity_id), "nodes": [], "edges": []}

            cur.execute(
                """SELECT r.id, r.subject_entity_id, sub.canonical_name AS subject_name, sub.kind AS subject_kind,
                          r.predicate, r.object_entity_id, obj.canonical_name AS object_name, obj.kind AS object_kind,
                          r.confidence, ev.locator AS evidence_locator, s.slug AS source_slug
                   FROM relationships r
                   JOIN entities sub ON sub.id = r.subject_entity_id
                   JOIN entities obj ON obj.id = r.object_entity_id
                   JOIN evidence ev ON ev.id = r.evidence_id
                   JOIN sources s ON s.id = ev.source_id
                   WHERE r.subject_entity_id = %s OR r.object_entity_id = %s
                   LIMIT %s""",
                (entity_id, entity_id, limit),
            )
            edges_1 = list(cur.fetchall())
            node_ids = {entity_id}
            for e in edges_1:
                node_ids.add(e["subject_entity_id"])
                node_ids.add(e["object_entity_id"])

            edges = list(edges_1)
            if depth >= 2 and node_ids:
                adjacent_ids = list(node_ids - {entity_id})
                if adjacent_ids:
                    cur.execute(
                        """SELECT r.id, r.subject_entity_id, sub.canonical_name AS subject_name, sub.kind AS subject_kind,
                                  r.predicate, r.object_entity_id, obj.canonical_name AS object_name, obj.kind AS object_kind,
                                  r.confidence, ev.locator AS evidence_locator, s.slug AS source_slug
                           FROM relationships r
                           JOIN entities sub ON sub.id = r.subject_entity_id
                           JOIN entities obj ON obj.id = r.object_entity_id
                           JOIN evidence ev ON ev.id = r.evidence_id
                           JOIN sources s ON s.id = ev.source_id
                           WHERE (r.subject_entity_id = ANY(%s) OR r.object_entity_id = ANY(%s))
                             AND r.id NOT IN (SELECT unnest(%s::uuid[]))
                           LIMIT %s""",
                        (adjacent_ids, adjacent_ids, [e["id"] for e in edges] or [uuid4()], limit),
                    )
                    edges_2 = list(cur.fetchall())
                    edges.extend(edges_2)
                    for e in edges_2:
                        node_ids.add(e["subject_entity_id"])
                        node_ids.add(e["object_entity_id"])

            cur.execute(
                "SELECT id, canonical_name, kind, confidence FROM entities WHERE id = ANY(%s)",
                (list(node_ids),),
            )
            nodes = list(cur.fetchall())

            return {
                "root_entity_id": str(entity_id),
                "depth": depth,
                "node_count": len(nodes),
                "edge_count": len(edges),
                "nodes": nodes,
                "edges": edges,
            }

    def population_change(self, entity_id: UUID) -> list[dict[str, Any]]:
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT t.starts_at, o.value, o.value - LAG(o.value) OVER (ORDER BY t.starts_at) AS change
                   FROM observations o JOIN time_intervals t ON t.id=o.time_interval_id
                   WHERE o.subject_entity_id=%s AND o.measure='population.total' ORDER BY t.starts_at""",
                (entity_id,),
            )
            return list(cur.fetchall())

    def record_ingestion_run(
        self,
        source_id: UUID,
        pipeline_version: str,
        status: str = "started",
        metadata: dict[str, Any] | None = None,
        started_at: datetime | None = None,
    ) -> UUID:
        from datetime import UTC
        start_time = started_at or datetime.now(UTC)
        meta = metadata or {}
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO ingestion_runs (source_id, pipeline_version, status, started_at, metadata)
                   VALUES (%s, %s, %s, %s, %s)
                   RETURNING id""",
                (source_id, pipeline_version, status, start_time, json.dumps(meta)),
            )
            return cur.fetchone()["id"]

    def finish_ingestion_run(
        self,
        run_id: UUID,
        *,
        status: str,
        records_fetched: int = 0,
        records_persisted: int = 0,
        records_failed: int = 0,
        error_message: str | None = None,
        freshness_observed_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        from datetime import UTC
        end_time = completed_at or datetime.now(UTC)
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(
                """UPDATE ingestion_runs
                   SET status = %s,
                       completed_at = %s,
                       records_fetched = %s,
                       records_persisted = %s,
                       records_failed = %s,
                       error_message = %s,
                       freshness_observed_at = %s
                   WHERE id = %s""",
                (
                    status,
                    end_time,
                    records_fetched,
                    records_persisted,
                    records_failed,
                    error_message,
                    freshness_observed_at,
                    run_id,
                ),
            )

    def source_health(self, source_slug: str | None = None) -> list[dict[str, Any]]:
        clauses, values = [], []
        if source_slug:
            clauses.append("s.slug = %s")
            values.append(source_slug)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT
                s.slug AS source_slug,
                s.name AS source_name,
                s.publisher,
                recent.status AS last_run_status,
                recent.completed_at AS last_successful_ingest,
                recent.freshness_observed_at,
                COALESCE(stats.total_runs, 0) AS total_runs,
                COALESCE(stats.total_records_persisted, 0) AS total_records_persisted,
                CASE WHEN recent.status = 'completed' OR recent.status IS NULL THEN true ELSE false END AS is_healthy
            FROM sources s
            LEFT JOIN LATERAL (
                SELECT status, completed_at, freshness_observed_at
                FROM ingestion_runs r
                WHERE r.source_id = s.id
                ORDER BY r.started_at DESC
                LIMIT 1
            ) recent ON true
            LEFT JOIN LATERAL (
                SELECT
                    count(*)::int AS total_runs,
                    sum(records_persisted)::int AS total_records_persisted
                FROM ingestion_runs r
                WHERE r.source_id = s.id
            ) stats ON true
            {where_clause}
            ORDER BY s.slug
        """
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, values)
            return list(cur.fetchall())

    def ingestion_runs(self, source_slug: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        clauses, values = [], []
        if source_slug:
            clauses.append("s.slug = %s")
            values.append(source_slug)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT
                r.id,
                s.slug AS source_slug,
                s.name AS source_name,
                r.pipeline_version,
                r.status,
                r.started_at,
                r.completed_at,
                r.records_fetched,
                r.records_persisted,
                r.records_failed,
                r.error_message,
                r.freshness_observed_at,
                r.metadata
            FROM ingestion_runs r
            JOIN sources s ON s.id = r.source_id
            {where_clause}
            ORDER BY r.started_at DESC
            LIMIT %s
        """
        values.append(limit)
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, values)
            return list(cur.fetchall())

    def resolution_reviews(self, status: str | None = None) -> list[dict[str, Any]]:
        clauses, values = [], []
        if status:
            clauses.append("r.status = %s")
            values.append(status)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT
                r.id,
                r.candidate_entity_id,
                c.canonical_name AS candidate_name,
                c.source_key AS candidate_source_key,
                r.target_entity_id,
                t.canonical_name AS target_name,
                t.source_key AS target_source_key,
                r.match_reason,
                r.confidence,
                r.status,
                r.created_at,
                r.reviewed_at,
                r.reviewed_by,
                r.resolution_notes,
                r.metadata
            FROM entity_resolution_reviews r
            JOIN entities c ON c.id = r.candidate_entity_id
            JOIN entities t ON t.id = r.target_entity_id
            {where_clause}
            ORDER BY r.created_at DESC
        """
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, values)
            return list(cur.fetchall())

    def approve_resolution_review(self, review_id: UUID, reviewed_by: str, notes: str | None = None) -> bool:
        from datetime import UTC
        now = datetime.now(UTC)
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM entity_resolution_reviews WHERE id = %s", (review_id,))
            review = cur.fetchone()
            if not review or review["status"] != "pending":
                return False
            cand_id = review["candidate_entity_id"]
            tgt_id = review["target_entity_id"]
            cur.execute("UPDATE observations SET subject_entity_id = %s WHERE subject_entity_id = %s", (tgt_id, cand_id))
            cur.execute("UPDATE geometries SET entity_id = %s WHERE entity_id = %s", (tgt_id, cand_id))
            cur.execute("UPDATE events SET subject_entity_id = %s WHERE subject_entity_id = %s", (tgt_id, cand_id))
            cur.execute("UPDATE relationships SET subject_entity_id = %s WHERE subject_entity_id = %s", (tgt_id, cand_id))
            cur.execute("UPDATE relationships SET object_entity_id = %s WHERE object_entity_id = %s", (tgt_id, cand_id))
            cur.execute(
                """INSERT INTO entity_identifiers (entity_id, source_id, source_key, scheme, value, confidence)
                   SELECT %s, source_id, source_key, scheme, value, confidence
                   FROM entity_identifiers WHERE entity_id = %s
                   ON CONFLICT DO NOTHING""",
                (tgt_id, cand_id),
            )
            cur.execute(
                """UPDATE entity_resolution_reviews
                   SET status = 'approved', reviewed_at = %s, reviewed_by = %s, resolution_notes = %s
                   WHERE id = %s""",
                (now, reviewed_by, notes, review_id),
            )
            return True

    def reject_resolution_review(self, review_id: UUID, reviewed_by: str, notes: str | None = None) -> bool:
        from datetime import UTC
        now = datetime.now(UTC)
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(
                """UPDATE entity_resolution_reviews
                   SET status = 'rejected', reviewed_at = %s, reviewed_by = %s, resolution_notes = %s
                   WHERE id = %s AND status = 'pending'""",
                (now, reviewed_by, notes, review_id),
            )
            return cur.rowcount > 0

    def record_claim(self, claim: Claim) -> UUID:
        with self._connection() as conn, conn.cursor() as cur:
            evidence_ids_str = [str(eid) for eid in claim.evidence_ids]
            cur.execute(
                """INSERT INTO claims (
                    id, subject_entity_id, claim_type, truth_class, value, unit,
                    time_interval_id, spatial_scope, method, computation_version,
                    inputs, evidence_ids, assumptions, confidence, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                ) ON CONFLICT (id) DO NOTHING
                RETURNING id""",
                (
                    claim.id,
                    claim.subject_entity_id,
                    claim.claim_type,
                    claim.truth_class.value if hasattr(claim.truth_class, "value") else str(claim.truth_class),
                    json.dumps(claim.value),
                    claim.unit,
                    claim.time_interval_id,
                    json.dumps(claim.spatial_scope) if claim.spatial_scope else None,
                    claim.method,
                    claim.computation_version,
                    json.dumps(claim.inputs),
                    evidence_ids_str,
                    json.dumps(claim.assumptions),
                    claim.confidence.value,
                    claim.created_at,
                ),
            )
            row = cur.fetchone()
            return row["id"] if row else claim.id

    def claims(
        self,
        subject_entity_id: UUID | None = None,
        truth_class: str | None = None,
        claim_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        limit = _extract_int(limit, 100)
        clauses, values = [], []
        if subject_entity_id:
            clauses.append("c.subject_entity_id = %s")
            values.append(subject_entity_id)
        if truth_class:
            clauses.append("c.truth_class = %s")
            values.append(truth_class)
        if claim_type:
            clauses.append("c.claim_type = %s")
            values.append(claim_type)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT
                c.id,
                c.subject_entity_id,
                e.canonical_name AS subject_name,
                c.claim_type,
                c.truth_class,
                c.value,
                c.unit,
                c.time_interval_id,
                c.spatial_scope,
                c.method,
                c.computation_version,
                c.inputs,
                c.evidence_ids,
                c.assumptions,
                c.confidence,
                c.created_at
            FROM claims c
            LEFT JOIN entities e ON e.id = c.subject_entity_id
            {where_clause}
            ORDER BY c.created_at DESC
            LIMIT %s
        """
        values.append(limit)
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, values)
            return list(cur.fetchall())

    def record_snapshot_run(
        self,
        snapshot_id: UUID,
        schema_version: str,
        status: str,
        storage_path: str,
        datasets: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO snapshot_runs (id, schema_version, status, storage_path, datasets, metadata)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    storage_path = EXCLUDED.storage_path,
                    metadata = EXCLUDED.metadata
                """,
                (
                    snapshot_id,
                    schema_version,
                    status,
                    storage_path,
                    datasets,
                    json.dumps(metadata or {}),
                ),
            )
            conn.commit()

    def update_snapshot_run(
        self,
        snapshot_id: UUID,
        status: str,
        completed_at: datetime | None = None,
        total_records: int = 0,
        row_counts: dict[str, int] | None = None,
        partition_counts: dict[str, int] | None = None,
        min_year: int | None = None,
        max_year: int | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE snapshot_runs
                SET
                    status = %s,
                    completed_at = %s,
                    total_records = %s,
                    row_counts = %s,
                    partition_counts = %s,
                    min_year = %s,
                    max_year = %s,
                    error_message = %s,
                    metadata = COALESCE(%s, metadata)
                WHERE id = %s
                """,
                (
                    status,
                    completed_at,
                    total_records,
                    json.dumps(row_counts or {}),
                    json.dumps(partition_counts or {}),
                    min_year,
                    max_year,
                    error_message,
                    json.dumps(metadata) if metadata is not None else None,
                    snapshot_id,
                ),
            )
            conn.commit()

    def get_snapshot_runs(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        clauses = []
        values: list[Any] = []
        if status:
            clauses.append("status = %s")
            values.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT id, schema_version, status, started_at, completed_at, datasets,
                   total_records, row_counts, partition_counts, min_year, max_year,
                   storage_path, error_message, metadata
            FROM snapshot_runs
            {where}
            ORDER BY started_at DESC
            LIMIT %s
        """
        values.append(limit)
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, values)
            return [_clean_record(r) for r in cur.fetchall()]

    def get_snapshot_run(self, snapshot_id: UUID) -> dict[str, Any] | None:
        sql = """
            SELECT id, schema_version, status, started_at, completed_at, datasets,
                   total_records, row_counts, partition_counts, min_year, max_year,
                   storage_path, error_message, metadata
            FROM snapshot_runs
            WHERE id = %s
        """
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, (snapshot_id,))
            row = cur.fetchone()
            return _clean_record(row) if row else None

    # -------------------------------------------------------------------------
    # Alert Rules, Evaluations, and Triggered Alerts (Engine 14)
    # -------------------------------------------------------------------------

    def create_alert_rule(self, rule: AlertRule) -> UUID:
        errors = self.alert_engine.validate_rule(rule)
        if errors:
            raise ValueError(f"Alert rule validation failed: {'; '.join(errors)}")

        sql = """
            INSERT INTO alert_rules (
                id, name, description, event_kind, operator, metric_field, threshold,
                severity, spatial_scope, temporal_window_seconds, cluster_threshold,
                cooldown_seconds, is_enabled, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            RETURNING id
        """
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    rule.id,
                    rule.name,
                    rule.description,
                    rule.event_kind,
                    rule.operator,
                    rule.metric_field,
                    rule.threshold,
                    rule.severity.value,
                    json.dumps(rule.spatial_scope) if rule.spatial_scope else None,
                    rule.temporal_window_seconds,
                    rule.cluster_threshold,
                    rule.cooldown_seconds,
                    rule.is_enabled,
                ),
            )
            return cur.fetchone()["id"]

    def get_alert_rule(self, rule_id: UUID) -> AlertRule | None:
        sql = """
            SELECT id, name, description, event_kind, operator, metric_field, threshold,
                   severity, spatial_scope, temporal_window_seconds, cluster_threshold,
                   cooldown_seconds, is_enabled, created_at, updated_at
            FROM alert_rules
            WHERE id = %s
        """
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, (rule_id,))
            row = cur.fetchone()
            if not row:
                return None
            return AlertRule(
                id=row["id"],
                name=row["name"],
                description=row.get("description"),
                event_kind=row["event_kind"],
                operator=row["operator"],
                metric_field=row["metric_field"],
                threshold=float(row["threshold"]),
                severity=AlertSeverity(row["severity"]),
                spatial_scope=row.get("spatial_scope"),
                temporal_window_seconds=row.get("temporal_window_seconds"),
                cluster_threshold=row.get("cluster_threshold"),
                cooldown_seconds=row.get("cooldown_seconds", 300),
                is_enabled=row.get("is_enabled", True),
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
            )

    def list_alert_rules(
        self,
        event_kind: str | None = None,
        is_enabled: bool | None = None,
        limit: int = 100,
    ) -> list[AlertRule]:
        limit = _extract_int(limit, 100)
        clauses, values = [], []
        if event_kind:
            clauses.append("event_kind = %s")
            values.append(event_kind)
        if is_enabled is not None:
            clauses.append("is_enabled = %s")
            values.append(is_enabled)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT id, name, description, event_kind, operator, metric_field, threshold,
                   severity, spatial_scope, temporal_window_seconds, cluster_threshold,
                   cooldown_seconds, is_enabled, created_at, updated_at
            FROM alert_rules
            {where}
            ORDER BY created_at DESC
            LIMIT %s
        """
        values.append(limit)
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, values)
            rules = []
            for row in cur.fetchall():
                rules.append(
                    AlertRule(
                        id=row["id"],
                        name=row["name"],
                        description=row.get("description"),
                        event_kind=row["event_kind"],
                        operator=row["operator"],
                        metric_field=row["metric_field"],
                        threshold=float(row["threshold"]),
                        severity=AlertSeverity(row["severity"]),
                        spatial_scope=row.get("spatial_scope"),
                        temporal_window_seconds=row.get("temporal_window_seconds"),
                        cluster_threshold=row.get("cluster_threshold"),
                        cooldown_seconds=row.get("cooldown_seconds", 300),
                        is_enabled=row.get("is_enabled", True),
                        created_at=row.get("created_at"),
                        updated_at=row.get("updated_at"),
                    )
                )
            return rules

    def update_alert_rule(
        self,
        rule_id: UUID,
        is_enabled: bool | None = None,
        threshold: float | None = None,
    ) -> bool:
        sets, values = [], []
        if is_enabled is not None:
            sets.append("is_enabled = %s")
            values.append(is_enabled)
        if threshold is not None:
            sets.append("threshold = %s")
            values.append(threshold)
        if not sets:
            return False
        sets.append("updated_at = NOW()")
        values.append(rule_id)
        sql = f"UPDATE alert_rules SET {', '.join(sets)} WHERE id = %s"
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, values)
            return cur.rowcount > 0

    def delete_alert_rule(self, rule_id: UUID) -> bool:
        sql = "DELETE FROM alert_rules WHERE id = %s"
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, (rule_id,))
            return cur.rowcount > 0

    def evaluate_event_alerts(self, event_id: UUID, rule_ids: list[UUID] | None = None) -> AlertEvaluation:
        """Run deterministic event evaluation against active rules."""
        return self.alert_engine.evaluate_event(event_id, rule_ids=rule_ids)

    def list_alerts(
        self,
        status: str | None = None,
        severity: str | None = None,
        event_id: UUID | None = None,
        rule_id: UUID | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        limit = _extract_int(limit, 100)
        clauses, values = [], []
        if status:
            clauses.append("a.status = %s")
            values.append(status)
        if severity:
            clauses.append("a.severity = %s")
            values.append(severity)
        if event_id:
            clauses.append("a.event_id = %s")
            values.append(event_id)
        if rule_id:
            clauses.append("a.rule_id = %s")
            values.append(rule_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT a.id, a.rule_id, r.name AS rule_name, a.event_id, a.severity,
                   a.title, a.message, a.dedup_key, a.status, a.evidence_id,
                   a.context_summary, a.created_at, a.acknowledged_at,
                   a.acknowledged_by, a.resolved_at, a.resolution_notes,
                   evi.locator AS evidence_locator, s.slug AS source_slug
            FROM alerts a
            JOIN alert_rules r ON r.id = a.rule_id
            JOIN evidence evi ON evi.id = a.evidence_id
            JOIN sources s ON s.id = evi.source_id
            {where}
            ORDER BY a.created_at DESC
            LIMIT %s
        """
        values.append(limit)
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, values)
            return [_clean_record(row) for row in cur.fetchall()]

    def get_alert(self, alert_id: UUID) -> dict[str, Any] | None:
        sql = """
            SELECT a.id, a.rule_id, r.name AS rule_name, a.event_id, a.severity,
                   a.title, a.message, a.dedup_key, a.status, a.evidence_id,
                   a.context_summary, a.created_at, a.acknowledged_at,
                   a.acknowledged_by, a.resolved_at, a.resolution_notes,
                   evi.locator AS evidence_locator, s.slug AS source_slug
            FROM alerts a
            JOIN alert_rules r ON r.id = a.rule_id
            JOIN evidence evi ON evi.id = a.evidence_id
            JOIN sources s ON s.id = evi.source_id
            WHERE a.id = %s
        """
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, (alert_id,))
            row = cur.fetchone()
            return _clean_record(row) if row else None

    def acknowledge_alert(self, alert_id: UUID, acknowledged_by: str = "operator") -> bool:
        sql = """
            UPDATE alerts
            SET status = 'acknowledged',
                acknowledged_at = NOW(),
                acknowledged_by = %s
            WHERE id = %s AND status = 'active'
        """
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, (acknowledged_by, alert_id))
            return cur.rowcount > 0

    def resolve_alert(self, alert_id: UUID, resolution_notes: str = "Resolved by operator") -> bool:
        sql = """
            UPDATE alerts
            SET status = 'resolved',
                resolved_at = NOW(),
                resolution_notes = %s
            WHERE id = %s AND status IN ('active', 'acknowledged')
        """
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, (resolution_notes, alert_id))
            return cur.rowcount > 0

    def list_alert_evaluations(self, event_id: UUID | None = None, limit: int = 100) -> list[dict[str, Any]]:
        limit = _extract_int(limit, 100)
        clauses, values = [], []
        if event_id:
            clauses.append("event_id = %s")
            values.append(event_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT id, event_id, status, matched_rule_ids, alerts_generated,
                   reason, evaluated_at, metadata
            FROM alert_evaluations
            {where}
            ORDER BY evaluated_at DESC
            LIMIT %s
        """
        values.append(limit)
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, values)
            return [_clean_record(row) for row in cur.fetchall()]
