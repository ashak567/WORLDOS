"""Engine 14: Event / Alert Engine Deepening.

Provides deterministic threshold evaluation, spatial-temporal correlation,
deduplication and cooldown policies, and evidence-linked alert records.
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from .domain import (
    Alert,
    AlertComparisonOperator,
    AlertEvaluation,
    AlertLifecycleStatus,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    Event,
)


class AlertEngine:
    """Deterministic Event & Alert Engine for WORLDOS.

    Evaluates real-world events against registered alert rules using
    PostGIS spatial predicates, temporal sliding windows, cluster thresholds,
    and deduplication/cooldown policies.
    """

    def __init__(self, repository: Any = None) -> None:
        self.repository = repository

    # -------------------------------------------------------------------------
    # 1. Rule Validation
    # -------------------------------------------------------------------------

    def validate_rule(self, rule: AlertRule) -> list[str]:
        """Validate alert rule definitions before persistence or activation."""
        errors: list[str] = []

        if not rule.name or not rule.name.strip():
            errors.append("Rule name cannot be empty")
        if not rule.event_kind or not rule.event_kind.strip():
            errors.append("event_kind cannot be empty")
        if not rule.metric_field or not rule.metric_field.strip():
            errors.append("metric_field cannot be empty")

        if rule.operator not in (">", ">=", "<", "<=", "==", "!="):
            errors.append(f"Unsupported operator '{rule.operator}'. Supported: >, >=, <, <=, ==, !=")

        if not isinstance(rule.threshold, (int, float)) or not math.isfinite(rule.threshold):
            errors.append(f"Threshold must be a finite number; received {rule.threshold}")

        if rule.cooldown_seconds < 0:
            errors.append(f"cooldown_seconds must be >= 0; received {rule.cooldown_seconds}")

        # Validate spatial scope if present
        if rule.spatial_scope:
            scope_type = rule.spatial_scope.get("type")
            if scope_type not in ("bbox", "entity", "geometry"):
                errors.append(f"Unsupported spatial_scope type '{scope_type}'. Must be 'bbox', 'entity', or 'geometry'")
            elif scope_type == "bbox":
                min_lon = rule.spatial_scope.get("min_lon")
                max_lon = rule.spatial_scope.get("max_lon")
                min_lat = rule.spatial_scope.get("min_lat")
                max_lat = rule.spatial_scope.get("max_lat")
                if None in (min_lon, max_lon, min_lat, max_lat):
                    errors.append("spatial_scope bbox requires min_lon, max_lon, min_lat, and max_lat")
                else:
                    for val, name, lo, hi in [
                        (min_lon, "min_lon", -180.0, 180.0),
                        (max_lon, "max_lon", -180.0, 180.0),
                        (min_lat, "min_lat", -90.0, 90.0),
                        (max_lat, "max_lat", -90.0, 90.0),
                    ]:
                        if not isinstance(val, (int, float)) or not math.isfinite(val) or val < lo or val > hi:
                            errors.append(f"spatial_scope {name} must be finite number in [{lo}, {hi}]; received {val}")
                    if isinstance(min_lon, (int, float)) and isinstance(max_lon, (int, float)) and min_lon > max_lon:
                        errors.append(f"spatial_scope min_lon ({min_lon}) cannot exceed max_lon ({max_lon})")
                    if isinstance(min_lat, (int, float)) and isinstance(max_lat, (int, float)) and min_lat > max_lat:
                        errors.append(f"spatial_scope min_lat ({min_lat}) cannot exceed max_lat ({max_lat})")
            elif scope_type == "entity":
                if not rule.spatial_scope.get("entity_id") and not rule.spatial_scope.get("country_code"):
                    errors.append("spatial_scope entity requires either 'entity_id' or 'country_code'")
            elif scope_type == "geometry":
                geom = rule.spatial_scope.get("geometry") or rule.spatial_scope
                if not isinstance(geom, dict) or "type" not in geom or "coordinates" not in geom:
                    errors.append("spatial_scope geometry must contain GeoJSON 'type' and 'coordinates'")

        # Validate temporal window and clustering
        if rule.cluster_threshold is not None:
            if rule.cluster_threshold < 1:
                errors.append(f"cluster_threshold must be >= 1; received {rule.cluster_threshold}")
            if not rule.temporal_window_seconds or rule.temporal_window_seconds <= 0:
                errors.append("cluster_threshold requires a positive temporal_window_seconds")

        if rule.temporal_window_seconds is not None and rule.temporal_window_seconds <= 0:
            errors.append(f"temporal_window_seconds must be > 0; received {rule.temporal_window_seconds}")

        return errors

    # -------------------------------------------------------------------------
    # 2. Deterministic Operator Evaluation
    # -------------------------------------------------------------------------

    @staticmethod
    def evaluate_operator(value: float, operator: str, threshold: float) -> bool:
        """Deterministically evaluate numeric comparisons with floating-point tolerance."""
        if operator == ">":
            return value > threshold and not math.isclose(value, threshold, rel_tol=1e-9, abs_tol=1e-9)
        elif operator == ">=":
            return value >= threshold or math.isclose(value, threshold, rel_tol=1e-9, abs_tol=1e-9)
        elif operator == "<":
            return value < threshold and not math.isclose(value, threshold, rel_tol=1e-9, abs_tol=1e-9)
        elif operator == "<=":
            return value <= threshold or math.isclose(value, threshold, rel_tol=1e-9, abs_tol=1e-9)
        elif operator == "==":
            return math.isclose(value, threshold, rel_tol=1e-9, abs_tol=1e-9)
        elif operator == "!=":
            return not math.isclose(value, threshold, rel_tol=1e-9, abs_tol=1e-9)
        else:
            raise ValueError(f"Unknown comparison operator '{operator}'")

    # -------------------------------------------------------------------------
    # 3. Spatial Scope Matching
    # -------------------------------------------------------------------------

    def matches_spatial_scope(
        self,
        longitude: float | None,
        latitude: float | None,
        spatial_scope: dict[str, Any] | None,
        cur: psycopg.Cursor | None = None,
    ) -> bool:
        """Check whether event coordinates satisfy the configured spatial scope."""
        if not spatial_scope:
            return True  # Unconstrained global rule

        if longitude is None or latitude is None:
            return False

        scope_type = spatial_scope.get("type")
        if scope_type == "bbox":
            min_lon = float(spatial_scope["min_lon"])
            max_lon = float(spatial_scope["max_lon"])
            min_lat = float(spatial_scope["min_lat"])
            max_lat = float(spatial_scope["max_lat"])
            return min_lon <= longitude <= max_lon and min_lat <= latitude <= max_lat

        elif scope_type == "entity":
            if not cur:
                return False
            country_code = spatial_scope.get("country_code")
            entity_id = spatial_scope.get("entity_id")
            if country_code:
                cur.execute(
                    """SELECT 1 FROM geometries g
                       JOIN entity_identifiers ei ON ei.entity_id = g.entity_id
                       WHERE UPPER(ei.value) = UPPER(%s)
                         AND ST_Contains(g.geometry, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                       LIMIT 1""",
                    (country_code, longitude, latitude),
                )
                return cur.fetchone() is not None
            elif entity_id:
                cur.execute(
                    """SELECT 1 FROM geometries g
                       WHERE g.entity_id = %s
                         AND ST_Contains(g.geometry, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                       LIMIT 1""",
                    (entity_id, longitude, latitude),
                )
                return cur.fetchone() is not None
            return False

        elif scope_type == "geometry":
            if not cur:
                return False
            geojson_str = json.dumps(spatial_scope.get("geometry") or spatial_scope)
            cur.execute(
                """SELECT ST_Contains(
                       ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
                       ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                   ) AS contains""",
                (geojson_str, longitude, latitude),
            )
            row = cur.fetchone()
            return bool(row and row.get("contains"))

        return True

    # -------------------------------------------------------------------------
    # 4. Temporal Window & Cluster Threshold Evaluation
    # -------------------------------------------------------------------------

    def evaluate_clustering(
        self,
        event_id: UUID,
        event_kind: str,
        event_time: datetime,
        rule: AlertRule,
        cur: psycopg.Cursor | None = None,
    ) -> tuple[bool, int]:
        """Check if enough qualifying events occurred in the temporal window."""
        if rule.cluster_threshold is None:
            return True, 1

        if not cur or not rule.temporal_window_seconds:
            return True, 1

        window_start = event_time - timedelta(seconds=rule.temporal_window_seconds)

        if rule.spatial_scope and rule.spatial_scope.get("type") == "bbox":
            bbox = rule.spatial_scope
            cur.execute(
                """SELECT count(*) AS count
                   FROM events ev
                   JOIN time_intervals t ON t.id = ev.time_interval_id
                   JOIN geometries g ON g.entity_id = ev.subject_entity_id
                   WHERE ev.kind = %s
                     AND t.starts_at BETWEEN %s AND %s
                     AND ST_Intersects(g.geometry, ST_MakeEnvelope(%s, %s, %s, %s, 4326))""",
                (
                    event_kind,
                    window_start,
                    event_time,
                    float(bbox["min_lon"]),
                    float(bbox["min_lat"]),
                    float(bbox["max_lon"]),
                    float(bbox["max_lat"]),
                ),
            )
        else:
            cur.execute(
                """SELECT count(*) AS count
                   FROM events ev
                   JOIN time_intervals t ON t.id = ev.time_interval_id
                   WHERE ev.kind = %s
                     AND t.starts_at BETWEEN %s AND %s""",
                (event_kind, window_start, event_time),
            )

        row = cur.fetchone()
        count = int(row["count"]) if row and "count" in row else 1
        return count >= rule.cluster_threshold, count

    # -------------------------------------------------------------------------
    # 5. Full Event Evaluation Pipeline
    # -------------------------------------------------------------------------

    def evaluate_event(
        self,
        event_id: UUID,
        rule_ids: list[UUID] | None = None,
        conn: psycopg.Connection | None = None,
    ) -> AlertEvaluation:
        """Run the authoritative event evaluation pipeline against all enabled alert rules."""
        if conn is not None:
            return self._evaluate_with_conn(event_id, conn, rule_ids=rule_ids)

        repo = self.repository
        if not repo:
            from .storage import WorldRepository
            repo = WorldRepository()

        with repo._connection() as active_conn:
            return self._evaluate_with_conn(event_id, active_conn, rule_ids=rule_ids)

    def _evaluate_with_conn(
        self,
        event_id: UUID,
        conn: psycopg.Connection,
        rule_ids: list[UUID] | None = None,
    ) -> AlertEvaluation:
        with conn.cursor() as cur:
            # 1. State: RECEIVED - Fetch event, interval, geometry, and evidence
            cur.execute(
                """SELECT ev.id, ev.kind, ev.subject_entity_id, ev.confidence, ev.attributes,
                          ev.evidence_id, t.starts_at, t.ends_at, t.precision,
                          ST_X(g.geometry) AS longitude, ST_Y(g.geometry) AS latitude,
                          evi.locator AS evidence_locator, s.slug AS source_slug
                   FROM events ev
                   JOIN time_intervals t ON t.id = ev.time_interval_id
                   JOIN evidence evi ON evi.id = ev.evidence_id
                   JOIN sources s ON s.id = evi.source_id
                   LEFT JOIN geometries g ON g.entity_id = ev.subject_entity_id
                   WHERE ev.id = %s""",
                (event_id,),
            )
            event_row = cur.fetchone()

            if not event_row:
                eval_record = AlertEvaluation(
                    event_id=event_id,
                    status=AlertLifecycleStatus.FAILED,
                    matched_rule_ids=[],
                    alerts_generated=0,
                    reason=f"Event '{event_id}' not found in PostgreSQL operational store.",
                )
                return eval_record

            # 2. State: VALIDATED - Check structural constraints
            starts_at = event_row["starts_at"]
            ends_at = event_row.get("ends_at")
            lon = event_row.get("longitude")
            lat = event_row.get("latitude")

            if ends_at and ends_at < starts_at:
                eval_record = AlertEvaluation(
                    event_id=event_id,
                    status=AlertLifecycleStatus.FAILED,
                    matched_rule_ids=[],
                    alerts_generated=0,
                    reason=f"Event temporal interval constraint violation: ends_at ({ends_at}) precedes starts_at ({starts_at}).",
                )
                self._persist_evaluation(cur, eval_record)
                conn.commit()
                return eval_record

            if lon is not None and lat is not None:
                if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
                    eval_record = AlertEvaluation(
                        event_id=event_id,
                        status=AlertLifecycleStatus.FAILED,
                        matched_rule_ids=[],
                        alerts_generated=0,
                        reason=f"Event coordinate constraint violation: longitude ({lon}) or latitude ({lat}) out of WGS 84 bounds.",
                    )
                    self._persist_evaluation(cur, eval_record)
                    conn.commit()
                    return eval_record

            # 3. State: EVALUATED - Retrieve enabled rules matching event_kind (or rule_ids)
            if rule_ids:
                cur.execute(
                    """SELECT id, name, description, event_kind, operator, metric_field, threshold,
                              severity, spatial_scope, temporal_window_seconds, cluster_threshold,
                              cooldown_seconds, is_enabled
                       FROM alert_rules
                       WHERE id = ANY(%s) AND is_enabled = TRUE""",
                    ([str(rid) for rid in rule_ids],),
                )
            else:
                cur.execute(
                    """SELECT id, name, description, event_kind, operator, metric_field, threshold,
                              severity, spatial_scope, temporal_window_seconds, cluster_threshold,
                              cooldown_seconds, is_enabled
                       FROM alert_rules
                       WHERE event_kind = %s AND is_enabled = TRUE""",
                    (event_row["kind"],),
                )
            rule_rows = cur.fetchall()

            if not rule_rows:
                eval_record = AlertEvaluation(
                    event_id=event_id,
                    status=AlertLifecycleStatus.EVALUATED,
                    matched_rule_ids=[],
                    alerts_generated=0,
                    reason=f"Evaluated event against 0 enabled rules for kind '{event_row['kind']}'.",
                )
                self._persist_evaluation(cur, eval_record)
                conn.commit()
                return eval_record

            event_attrs = event_row.get("attributes") or {}
            matched_rule_ids: list[UUID] = []
            alerts_to_create: list[dict[str, Any]] = []
            suppressed_count = 0

            for r in rule_rows:
                rule_id = r["id"]
                rule_obj = AlertRule(
                    id=rule_id,
                    name=r["name"],
                    description=r.get("description"),
                    event_kind=r["event_kind"],
                    operator=r["operator"],
                    metric_field=r["metric_field"],
                    threshold=float(r["threshold"]),
                    severity=AlertSeverity(r["severity"]),
                    spatial_scope=r.get("spatial_scope"),
                    temporal_window_seconds=r.get("temporal_window_seconds"),
                    cluster_threshold=r.get("cluster_threshold"),
                    cooldown_seconds=r.get("cooldown_seconds", 300),
                    is_enabled=r.get("is_enabled", True),
                )

                # Extract metric from event attributes
                metric_val = event_attrs.get(rule_obj.metric_field)
                if metric_val is None:
                    # Also check observations if linked
                    cur.execute(
                        """SELECT value FROM observations
                           WHERE subject_entity_id = %s
                             AND (measure = %s OR measure = %s)
                           LIMIT 1""",
                        (event_row["subject_entity_id"], rule_obj.metric_field, f"{rule_obj.event_kind}.{rule_obj.metric_field}"),
                    )
                    obs_row = cur.fetchone()
                    if obs_row and obs_row.get("value") is not None:
                        metric_val = float(obs_row["value"])

                if metric_val is None or not isinstance(metric_val, (int, float)):
                    continue

                metric_float = float(metric_val)

                # Evaluate threshold operator
                if not self.evaluate_operator(metric_float, rule_obj.operator, rule_obj.threshold):
                    continue

                # Evaluate spatial scope
                if not self.matches_spatial_scope(lon, lat, rule_obj.spatial_scope, cur):
                    continue

                # Evaluate clustering if required
                cluster_ok, cluster_count = self.evaluate_clustering(
                    event_id=event_id,
                    event_kind=rule_obj.event_kind,
                    event_time=starts_at,
                    rule=rule_obj,
                    cur=cur,
                )
                if not cluster_ok:
                    continue

                matched_rule_ids.append(rule_id)

                # Check cooldown / suppression
                # If an active alert for this rule was created within cooldown_seconds, suppress it
                cooldown_sec = rule_obj.cooldown_seconds
                cur.execute(
                    """SELECT id FROM alerts
                       WHERE rule_id = %s
                         AND (event_id = %s OR context_summary->>'subject_entity_id' = %s)
                         AND created_at >= %s - (%s || ' seconds')::interval
                       LIMIT 1""",
                    (rule_id, event_id, str(event_row["subject_entity_id"]), starts_at, cooldown_sec),
                )
                existing_alert = cur.fetchone()

                if existing_alert:
                    suppressed_count += 1
                else:
                    dedup_key = f"{rule_id}:{event_id}"
                    alerts_to_create.append({
                        "rule": rule_obj,
                        "dedup_key": dedup_key,
                        "metric_val": metric_float,
                        "cluster_count": cluster_count,
                    })

            # 4. State: ALERTED or SUPPRESSED or EVALUATED
            alerts_generated = 0
            for item in alerts_to_create:
                rule_obj = item["rule"]
                metric_float = item["metric_val"]
                cluster_count = item["cluster_count"]
                dedup_key = item["dedup_key"]

                title = f"[{rule_obj.severity.value}] {rule_obj.name}"
                cluster_info = f" (Cluster: {cluster_count} events in {rule_obj.temporal_window_seconds}s)" if rule_obj.cluster_threshold else ""
                message = (
                    f"Event '{event_attrs.get('title', event_id)}' triggered rule '{rule_obj.name}': "
                    f"{rule_obj.metric_field}={metric_float} {rule_obj.operator} {rule_obj.threshold}{cluster_info}. "
                    f"Threshold met deterministically based on publisher-reported data from {event_row['source_slug']}. "
                    f"Does not assert secondary impacts without dedicated modeling."
                )

                context_summary = {
                    "event_kind": event_row["kind"],
                    "event_id": str(event_id),
                    "subject_entity_id": str(event_row["subject_entity_id"]) if event_row["subject_entity_id"] else None,
                    "starts_at": starts_at.isoformat() if hasattr(starts_at, "isoformat") else str(starts_at),
                    "coordinates": [lon, lat] if lon is not None and lat is not None else None,
                    "metric_field": rule_obj.metric_field,
                    "metric_value": metric_float,
                    "operator": rule_obj.operator,
                    "threshold": rule_obj.threshold,
                    "cluster_count": cluster_count,
                    "evidence_locator": event_row["evidence_locator"],
                    "source_slug": event_row["source_slug"],
                }

                alert_id = uuid4()
                cur.execute(
                    """INSERT INTO alerts (
                           id, rule_id, event_id, severity, title, message,
                           dedup_key, status, evidence_id, context_summary, created_at
                       ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                       ON CONFLICT (dedup_key) DO NOTHING
                       RETURNING id""",
                    (
                        alert_id,
                        rule_obj.id,
                        event_id,
                        rule_obj.severity.value,
                        title,
                        message,
                        dedup_key,
                        "active",
                        event_row["evidence_id"],
                        json.dumps(context_summary),
                    ),
                )
                inserted = cur.fetchone()
                if inserted:
                    alerts_generated += 1

            if alerts_generated > 0:
                lifecycle_status = AlertLifecycleStatus.ALERTED
                reason = f"Triggered {alerts_generated} alert(s) across {len(matched_rule_ids)} matching rule(s)."
            elif suppressed_count > 0 and len(matched_rule_ids) > 0:
                lifecycle_status = AlertLifecycleStatus.SUPPRESSED
                reason = f"Suppressed {suppressed_count} matching alert(s) due to active cooldown policy ({cooldown_sec}s)."
            elif len(matched_rule_ids) > 0:
                lifecycle_status = AlertLifecycleStatus.EVALUATED
                reason = f"Matched {len(matched_rule_ids)} rule(s) with 0 new alerts generated (idempotent / deduplicated)."
            else:
                lifecycle_status = AlertLifecycleStatus.EVALUATED
                reason = f"Evaluated {len(rule_rows)} rule(s); 0 met condition criteria."

            eval_record = AlertEvaluation(
                event_id=event_id,
                status=lifecycle_status,
                matched_rule_ids=matched_rule_ids,
                alerts_generated=alerts_generated,
                reason=reason,
                metadata={"suppressed_count": suppressed_count, "matched_rules_total": len(matched_rule_ids)},
            )
            self._persist_evaluation(cur, eval_record)
            conn.commit()
            return eval_record

    def _persist_evaluation(self, cur: psycopg.Cursor, evaluation: AlertEvaluation) -> None:
        """Record the evaluation lifecycle state into PostgreSQL."""
        cur.execute(
            """INSERT INTO alert_evaluations (
                   id, event_id, status, matched_rule_ids, alerts_generated,
                   reason, evaluated_at, metadata
               ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                evaluation.id,
                evaluation.event_id,
                evaluation.status.value,
                [str(rid) for rid in evaluation.matched_rule_ids],
                evaluation.alerts_generated,
                evaluation.reason,
                evaluation.evaluated_at,
                json.dumps(evaluation.metadata),
            ),
        )
