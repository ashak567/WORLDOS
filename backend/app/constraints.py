"""Engine 12: Deterministic Constraint Engine.

Validates physical invariants, coordinate bounds, PostGIS geometry topology,
temporal ordering, relationship predicates, conservative entity resolution,
evidence lineage, truth classes, and proposed scenario modifications.
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg

from .domain import (
    VALID_PREDICATES,
    BoundingBox,
    Claim,
    ConstraintCategory,
    ConstraintFinding,
    ConstraintSeverity,
    ConstraintStatus,
    ConstraintValidationResult,
    Entity,
    Geometry,
    Observation,
    Relationship,
    ScenarioProposal,
    TimeInterval,
    TruthClass,
    WorldBundle,
)


class ConstraintViolationError(Exception):
    """Raised when an operation encounters blocking constraint violations."""

    def __init__(self, result: ConstraintValidationResult) -> None:
        self.result = result
        blocking_messages = [f.message for f in result.findings if f.severity == ConstraintSeverity.BLOCKING]
        super().__init__(f"Constraint violation: {'; '.join(blocking_messages)}")


class ConstraintEngine:
    """Deterministic validation layer for WORLDOS.

    Enforces invariants across:
    1. Physical and coordinate bounds (lat [-90, 90], lon [-180, 180], finite values, PostGIS topology).
    2. Spatial consistency (containment, intersection, disjoint contradictions, bbox ordering).
    3. Temporal consistency (starts_at <= ends_at, timezone awareness, precision preservation).
    4. Entity & relationship consistency (referential integrity, self-relationships, conservative resolution).
    5. Claims & evidence consistency (truth classes, evidence citations, confidence bounds, domain sanity).
    6. Scenario proposals (pre-flight dry-run validation without state mutation).
    """

    def __init__(self, repository: Any = None) -> None:
        self.repository = repository

    # -------------------------------------------------------------------------
    # 1. Physical & Coordinate Invariants
    # -------------------------------------------------------------------------

    def validate_coordinate_pair(
        self,
        lon: Any,
        lat: Any,
        field: str = "coordinates",
        evidence_ids: list[UUID] | None = None,
    ) -> list[ConstraintFinding]:
        """Validate a single longitude/latitude coordinate pair."""
        findings: list[ConstraintFinding] = []
        ev_ids = evidence_ids or []

        # 1. Finite numeric checks
        if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
            findings.append(
                ConstraintFinding(
                    code="COORD_NON_NUMERIC",
                    category=ConstraintCategory.PHYSICAL_COORDINATES,
                    severity=ConstraintSeverity.BLOCKING,
                    message=f"Coordinates must be numeric values; received ({type(lon).__name__}, {type(lat).__name__})",
                    field=field,
                    actual_value={"lon": str(lon), "lat": str(lat)},
                    expected_value="numeric float or int",
                    evidence_ids=ev_ids,
                )
            )
            return findings

        if not math.isfinite(lon) or not math.isfinite(lat):
            findings.append(
                ConstraintFinding(
                    code="COORD_NON_FINITE",
                    category=ConstraintCategory.PHYSICAL_COORDINATES,
                    severity=ConstraintSeverity.BLOCKING,
                    message=f"Coordinates must be finite numbers; received ({lon}, {lat})",
                    field=field,
                    actual_value={"lon": lon, "lat": lat},
                    expected_value="finite float values without NaN or Inf",
                    evidence_ids=ev_ids,
                )
            )
            return findings

        # 2. Coordinate range bounds: Longitude [-180, 180]
        if lon < -180.0 or lon > 180.0:
            findings.append(
                ConstraintFinding(
                    code="COORD_LON_OUT_OF_BOUNDS",
                    category=ConstraintCategory.PHYSICAL_COORDINATES,
                    severity=ConstraintSeverity.BLOCKING,
                    message=f"Longitude {lon} is out of bounds; must be between -180.0 and +180.0 degrees",
                    field=f"{field}.longitude",
                    actual_value=lon,
                    expected_value="[-180.0, 180.0]",
                    evidence_ids=ev_ids,
                )
            )

        # 3. Coordinate range bounds: Latitude [-90, 90]
        if lat < -90.0 or lat > 90.0:
            findings.append(
                ConstraintFinding(
                    code="COORD_LAT_OUT_OF_BOUNDS",
                    category=ConstraintCategory.PHYSICAL_COORDINATES,
                    severity=ConstraintSeverity.BLOCKING,
                    message=f"Latitude {lat} is out of bounds; must be between -90.0 and +90.0 degrees",
                    field=f"{field}.latitude",
                    actual_value=lat,
                    expected_value="[-90.0, 90.0]",
                    evidence_ids=ev_ids,
                )
            )

        return findings

    def check_antimeridian_crossing(self, coordinates: list[Any]) -> bool:
        """Detect whether a coordinate sequence spans across the 180th anti-meridian."""
        longitudes: list[float] = []

        def _collect_lons(coords: Any) -> None:
            if isinstance(coords, (list, tuple)):
                if len(coords) >= 2 and isinstance(coords[0], (int, float)) and isinstance(coords[1], (int, float)):
                    if math.isfinite(coords[0]):
                        longitudes.append(coords[0])
                else:
                    for child in coords:
                        _collect_lons(child)

        _collect_lons(coordinates)
        if not longitudes:
            return False

        has_far_east = any(lon > 100.0 for lon in longitudes)
        has_far_west = any(lon < -100.0 for lon in longitudes)
        return has_far_east and has_far_west

    def validate_bounding_box(
        self,
        bbox: BoundingBox,
        allow_antimeridian: bool = True,
        evidence_ids: list[UUID] | None = None,
    ) -> list[ConstraintFinding]:
        """Validate bounding box coordinate ranges and ordering."""
        findings: list[ConstraintFinding] = []
        ev_ids = evidence_ids or []

        # Validate coordinate bounds
        findings.extend(self.validate_coordinate_pair(bbox.min_longitude, bbox.min_latitude, "bounding_box.min", ev_ids))
        findings.extend(self.validate_coordinate_pair(bbox.max_longitude, bbox.max_latitude, "bounding_box.max", ev_ids))

        # Check latitude ordering (north must be >= south)
        if bbox.min_latitude > bbox.max_latitude:
            findings.append(
                ConstraintFinding(
                    code="BBOX_LATITUDE_INVERTED",
                    category=ConstraintCategory.PHYSICAL_COORDINATES,
                    severity=ConstraintSeverity.BLOCKING,
                    message=f"Bounding box min_latitude ({bbox.min_latitude}) exceeds max_latitude ({bbox.max_latitude})",
                    field="bounding_box.latitude",
                    actual_value={"min": bbox.min_latitude, "max": bbox.max_latitude},
                    expected_value="min_latitude <= max_latitude",
                    evidence_ids=ev_ids,
                )
            )

        # Check longitude ordering
        if bbox.min_longitude > bbox.max_longitude:
            if allow_antimeridian and (bbox.min_longitude > 0 and bbox.max_longitude < 0):
                # Legitimate anti-meridian wrapping bounding box (e.g. [170, -170])
                findings.append(
                    ConstraintFinding(
                        code="BBOX_ANTIMERIDIAN_SPAN",
                        category=ConstraintCategory.PHYSICAL_COORDINATES,
                        severity=ConstraintSeverity.WARNING,
                        message=f"Bounding box spans the anti-meridian (min_lon={bbox.min_longitude} > max_lon={bbox.max_longitude})",
                        field="bounding_box.longitude",
                        actual_value={"min": bbox.min_longitude, "max": bbox.max_longitude},
                        expected_value="min_longitude <= max_longitude or valid anti-meridian span",
                        evidence_ids=ev_ids,
                    )
                )
            else:
                findings.append(
                    ConstraintFinding(
                        code="BBOX_LONGITUDE_INVERTED",
                        category=ConstraintCategory.PHYSICAL_COORDINATES,
                        severity=ConstraintSeverity.BLOCKING,
                        message=f"Bounding box min_longitude ({bbox.min_longitude}) exceeds max_longitude ({bbox.max_longitude})",
                        field="bounding_box.longitude",
                        actual_value={"min": bbox.min_longitude, "max": bbox.max_longitude},
                        expected_value="min_longitude <= max_longitude",
                        evidence_ids=ev_ids,
                    )
                )

        return findings

    def validate_geometry_structure(
        self,
        geojson: dict[str, Any],
        evidence_ids: list[UUID] | None = None,
    ) -> list[ConstraintFinding]:
        """Validate GeoJSON geometry structure, coordinate finiteness, bounds, and polygon closure."""
        findings: list[ConstraintFinding] = []
        ev_ids = evidence_ids or []

        if not isinstance(geojson, dict):
            findings.append(
                ConstraintFinding(
                    code="GEOM_NOT_A_DICT",
                    category=ConstraintCategory.PHYSICAL_COORDINATES,
                    severity=ConstraintSeverity.BLOCKING,
                    message="GeoJSON must be a JSON object dictionary",
                    field="geojson",
                    evidence_ids=ev_ids,
                )
            )
            return findings

        gtype = geojson.get("type")
        supported_types = {
            "Point",
            "MultiPoint",
            "LineString",
            "MultiLineString",
            "Polygon",
            "MultiPolygon",
            "GeometryCollection",
        }
        if gtype not in supported_types:
            findings.append(
                ConstraintFinding(
                    code="GEOM_UNSUPPORTED_TYPE",
                    category=ConstraintCategory.PHYSICAL_COORDINATES,
                    severity=ConstraintSeverity.BLOCKING,
                    message=f"Unsupported geometry type '{gtype}'. Supported types: {sorted(supported_types)}",
                    field="geojson.type",
                    actual_value=gtype,
                    expected_value=list(supported_types),
                    evidence_ids=ev_ids,
                )
            )
            return findings

        if gtype == "GeometryCollection":
            geometries = geojson.get("geometries")
            if not isinstance(geometries, list) or len(geometries) == 0:
                findings.append(
                    ConstraintFinding(
                        code="GEOM_EMPTY_COLLECTION",
                        category=ConstraintCategory.PHYSICAL_COORDINATES,
                        severity=ConstraintSeverity.BLOCKING,
                        message="GeometryCollection must contain a non-empty list of geometries",
                        field="geojson.geometries",
                        evidence_ids=ev_ids,
                    )
                )
            else:
                for idx, sub_geom in enumerate(geometries):
                    findings.extend(self.validate_geometry_structure(sub_geom, ev_ids))
            return findings

        coords = geojson.get("coordinates")
        if coords is None:
            findings.append(
                ConstraintFinding(
                    code="GEOM_MISSING_COORDINATES",
                    category=ConstraintCategory.PHYSICAL_COORDINATES,
                    severity=ConstraintSeverity.BLOCKING,
                    message=f"Geometry of type '{gtype}' is missing 'coordinates' field",
                    field="geojson.coordinates",
                    evidence_ids=ev_ids,
                )
            )
            return findings

        # Validate specific geometry types
        if gtype == "Point":
            if not isinstance(coords, (list, tuple)) or len(coords) < 2:
                findings.append(
                    ConstraintFinding(
                        code="GEOM_MALFORMED_POINT",
                        category=ConstraintCategory.PHYSICAL_COORDINATES,
                        severity=ConstraintSeverity.BLOCKING,
                        message=f"Point coordinates must be a sequence of at least [lon, lat], received {coords}",
                        field="geojson.coordinates",
                        evidence_ids=ev_ids,
                    )
                )
            else:
                findings.extend(self.validate_coordinate_pair(coords[0], coords[1], "geojson.coordinates", ev_ids))

        elif gtype == "Polygon":
            if not isinstance(coords, list) or len(coords) == 0:
                findings.append(
                    ConstraintFinding(
                        code="GEOM_EMPTY_POLYGON",
                        category=ConstraintCategory.PHYSICAL_COORDINATES,
                        severity=ConstraintSeverity.BLOCKING,
                        message="Polygon must contain at least one linear ring",
                        field="geojson.coordinates",
                        evidence_ids=ev_ids,
                    )
                )
            else:
                for ring_idx, ring in enumerate(coords):
                    if not isinstance(ring, list) or len(ring) < 4:
                        findings.append(
                            ConstraintFinding(
                                code="GEOM_POLYGON_RING_TOO_FEW_POINTS",
                                category=ConstraintCategory.PHYSICAL_COORDINATES,
                                severity=ConstraintSeverity.BLOCKING,
                                message=f"Polygon ring {ring_idx} must contain at least 4 positions (received {len(ring) if isinstance(ring, list) else 0})",
                                field=f"geojson.coordinates[{ring_idx}]",
                                evidence_ids=ev_ids,
                            )
                        )
                    else:
                        # Check ring closure: first position must match last position
                        first_pt, last_pt = ring[0], ring[-1]
                        if not isinstance(first_pt, (list, tuple)) or not isinstance(last_pt, (list, tuple)):
                            findings.append(
                                ConstraintFinding(
                                    code="GEOM_POLYGON_INVALID_RING_FORMAT",
                                    category=ConstraintCategory.PHYSICAL_COORDINATES,
                                    severity=ConstraintSeverity.BLOCKING,
                                    message=f"Polygon ring {ring_idx} positions must be coordinate arrays",
                                    field=f"geojson.coordinates[{ring_idx}]",
                                    evidence_ids=ev_ids,
                                )
                            )
                        elif len(first_pt) >= 2 and len(last_pt) >= 2:
                            if first_pt[0] != last_pt[0] or first_pt[1] != last_pt[1]:
                                findings.append(
                                    ConstraintFinding(
                                        code="GEOM_POLYGON_RING_NOT_CLOSED",
                                        category=ConstraintCategory.PHYSICAL_COORDINATES,
                                        severity=ConstraintSeverity.BLOCKING,
                                        message=f"Polygon ring {ring_idx} is not closed: first position {first_pt} does not match last position {last_pt}",
                                        field=f"geojson.coordinates[{ring_idx}]",
                                        actual_value={"first": first_pt, "last": last_pt},
                                        expected_value="first position == last position",
                                        evidence_ids=ev_ids,
                                    )
                                )
                        # Check all points in ring
                        for pt_idx, pt in enumerate(ring):
                            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                                findings.extend(
                                    self.validate_coordinate_pair(
                                        pt[0], pt[1], f"geojson.coordinates[{ring_idx}][{pt_idx}]", ev_ids
                                    )
                                )

        # Recursive coordinate scanner for other multi-types
        elif gtype in ("MultiPoint", "LineString", "MultiLineString", "MultiPolygon"):
            def _scan_coords(node: Any, path: str) -> None:
                if isinstance(node, (list, tuple)):
                    if len(node) >= 2 and isinstance(node[0], (int, float)) and isinstance(node[1], (int, float)):
                        findings.extend(self.validate_coordinate_pair(node[0], node[1], path, ev_ids))
                    else:
                        for idx, item in enumerate(node):
                            _scan_coords(item, f"{path}[{idx}]")

            _scan_coords(coords, "geojson.coordinates")

        # Note anti-meridian crossing without rejecting
        if self.check_antimeridian_crossing(coords):
            findings.append(
                ConstraintFinding(
                    code="GEOM_CROSSES_ANTIMERIDIAN",
                    category=ConstraintCategory.PHYSICAL_COORDINATES,
                    severity=ConstraintSeverity.WARNING,
                    message="Geometry spans the 180th anti-meridian; valid global geometry detected",
                    field="geojson.coordinates",
                    evidence_ids=ev_ids,
                )
            )

        return findings

    def validate_geometry_with_postgis(
        self,
        geojson: dict[str, Any],
        conn: psycopg.Connection,
        evidence_ids: list[UUID] | None = None,
    ) -> list[ConstraintFinding]:
        """Authoritative PostGIS geometry topology verification using ST_IsValid and ST_IsValidReason."""
        findings: list[ConstraintFinding] = []
        ev_ids = evidence_ids or []

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT
                         ST_IsValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)) AS is_valid,
                         ST_IsValidReason(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)) AS reason,
                         ST_GeometryType(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)) AS geom_type""",
                    (json.dumps(geojson), json.dumps(geojson), json.dumps(geojson)),
                )
                row = cur.fetchone()
                if row:
                    is_valid = row.get("is_valid")
                    reason = row.get("reason")
                    if not is_valid:
                        findings.append(
                            ConstraintFinding(
                                code="GEOM_INVALID_TOPOLOGY",
                                category=ConstraintCategory.PHYSICAL_COORDINATES,
                                severity=ConstraintSeverity.BLOCKING,
                                message=f"PostGIS topology validation failed: {reason}",
                                field="geojson",
                                actual_value=reason,
                                expected_value="Valid geometry according to OGC/PostGIS topology rules",
                                evidence_ids=ev_ids,
                            )
                        )
        except Exception as exc:
            findings.append(
                ConstraintFinding(
                    code="GEOM_POSTGIS_PARSE_ERROR",
                    category=ConstraintCategory.PHYSICAL_COORDINATES,
                    severity=ConstraintSeverity.BLOCKING,
                    message=f"PostGIS could not parse GeoJSON: {str(exc)}",
                    field="geojson",
                    actual_value=str(exc),
                    evidence_ids=ev_ids,
                )
            )

        return findings

    def validate_geometry(
        self,
        geom: Geometry,
        conn: psycopg.Connection | None = None,
    ) -> list[ConstraintFinding]:
        """Validate a domain Geometry model."""
        ev_ids = [geom.evidence_id] if geom.evidence_id else []
        findings = self.validate_geometry_structure(geom.geojson, evidence_ids=ev_ids)

        # Confidence bounds
        if geom.confidence.value < 0.0 or geom.confidence.value > 1.0:
            findings.append(
                ConstraintFinding(
                    code="CONFIDENCE_OUT_OF_BOUNDS",
                    category=ConstraintCategory.CLAIM_EVIDENCE,
                    severity=ConstraintSeverity.BLOCKING,
                    message=f"Geometry confidence {geom.confidence.value} is out of bounds [0.0, 1.0]",
                    field="geometry.confidence.value",
                    actual_value=geom.confidence.value,
                    expected_value="[0.0, 1.0]",
                    evidence_ids=ev_ids,
                )
            )

        # Validate temporal validity interval if present
        if geom.valid_during:
            findings.extend(self.validate_temporal(geom.valid_during, evidence_ids=ev_ids))

        # Run authoritative PostGIS topology check if database connection provided
        if conn and not any(f.code == "GEOM_NOT_A_DICT" for f in findings):
            findings.extend(self.validate_geometry_with_postgis(geom.geojson, conn, evidence_ids=ev_ids))

        return findings

    # -------------------------------------------------------------------------
    # 2. Spatial Consistency
    # -------------------------------------------------------------------------

    def validate_spatial_relationship(
        self,
        rel: Relationship,
        conn: psycopg.Connection | None = None,
    ) -> list[ConstraintFinding]:
        """Verify spatial predicates (located_in, adjacent_to, intersects, covers, part_of) against PostGIS geometries."""
        findings: list[ConstraintFinding] = []
        ev_ids = [rel.evidence_id]

        spatial_predicates = {"located_in", "part_of", "adjacent_to", "intersects", "covers", "near"}
        if rel.predicate not in spatial_predicates:
            return findings

        if not conn:
            return findings

        try:
            with conn.cursor() as cur:
                # Query authoritative geometries for both entities
                cur.execute(
                    """SELECT
                         (SELECT geometry FROM geometries WHERE entity_id = %s ORDER BY created_at DESC LIMIT 1) AS subj_geom,
                         (SELECT geometry FROM geometries WHERE entity_id = %s ORDER BY created_at DESC LIMIT 1) AS obj_geom""",
                    (rel.subject_entity_id, rel.object_entity_id),
                )
                row = cur.fetchone()
                if not row or not row.get("subj_geom") or not row.get("obj_geom"):
                    findings.append(
                        ConstraintFinding(
                            code="SPATIAL_EVIDENCE_MISSING",
                            category=ConstraintCategory.SPATIAL_CONSISTENCY,
                            severity=ConstraintSeverity.WARNING,
                            message=(
                                f"Cannot authoritatively verify spatial predicate '{rel.predicate}': "
                                "one or both entities lack registered geometries in PostGIS"
                            ),
                            field="predicate",
                            actual_value=rel.predicate,
                            evidence_ids=ev_ids,
                        )
                    )
                    return findings

                # Both geometries exist in PostGIS - test topological relationship
                cur.execute(
                    """SELECT
                         ST_Contains(obj.geometry, subj.geometry) AS obj_contains_subj,
                         ST_Covers(obj.geometry, subj.geometry) AS obj_covers_subj,
                         ST_Intersects(subj.geometry, obj.geometry) AS intersects,
                         ST_Disjoint(subj.geometry, obj.geometry) AS disjoint,
                         ST_Touches(subj.geometry, obj.geometry) AS touches
                       FROM (SELECT geometry FROM geometries WHERE entity_id = %s ORDER BY created_at DESC LIMIT 1) AS subj
                       CROSS JOIN (SELECT geometry FROM geometries WHERE entity_id = %s ORDER BY created_at DESC LIMIT 1) AS obj""",
                    (rel.subject_entity_id, rel.object_entity_id),
                )
                eval_row = cur.fetchone()
                if not eval_row:
                    return findings

                is_contained = eval_row.get("obj_contains_subj") or eval_row.get("obj_covers_subj")
                is_disjoint = eval_row.get("disjoint")
                is_intersecting = eval_row.get("intersects")

                if rel.predicate in ("located_in", "part_of"):
                    if is_disjoint:
                        findings.append(
                            ConstraintFinding(
                                code="SPATIAL_RELATION_CONTRADICTION",
                                category=ConstraintCategory.SPATIAL_CONSISTENCY,
                                severity=ConstraintSeverity.BLOCKING,
                                message=(
                                    f"Spatial contradiction: entity {rel.subject_entity_id} is asserted to be '{rel.predicate}' "
                                    f"entity {rel.object_entity_id}, but their authoritative geometries are completely disjoint."
                                ),
                                field="predicate",
                                actual_value={"predicate": rel.predicate, "disjoint": True},
                                expected_value="spatial containment or overlap",
                                evidence_ids=ev_ids,
                            )
                        )
                    elif not is_contained:
                        findings.append(
                            ConstraintFinding(
                                code="SPATIAL_RELATION_PARTIAL_OVERLAP",
                                category=ConstraintCategory.SPATIAL_CONSISTENCY,
                                severity=ConstraintSeverity.WARNING,
                                message=(
                                    f"Spatial advisory: entity {rel.subject_entity_id} intersects entity {rel.object_entity_id} "
                                    f"but is not strictly contained within it for predicate '{rel.predicate}'."
                                ),
                                field="predicate",
                                actual_value={"intersects": True, "contains": False},
                                evidence_ids=ev_ids,
                            )
                        )

                elif rel.predicate == "intersects":
                    if is_disjoint:
                        findings.append(
                            ConstraintFinding(
                                code="SPATIAL_RELATION_CONTRADICTION",
                                category=ConstraintCategory.SPATIAL_CONSISTENCY,
                                severity=ConstraintSeverity.BLOCKING,
                                message=(
                                    f"Spatial contradiction: entity {rel.subject_entity_id} is asserted to intersect "
                                    f"entity {rel.object_entity_id}, but their geometries are disjoint."
                                ),
                                field="predicate",
                                actual_value={"disjoint": True},
                                expected_value="ST_Intersects == True",
                                evidence_ids=ev_ids,
                            )
                        )

        except Exception as exc:
            findings.append(
                ConstraintFinding(
                    code="SPATIAL_CHECK_ERROR",
                    category=ConstraintCategory.SPATIAL_CONSISTENCY,
                    severity=ConstraintSeverity.WARNING,
                    message=f"Spatial evaluation encountered error: {str(exc)}",
                    field="predicate",
                    evidence_ids=ev_ids,
                )
            )

        return findings

    # -------------------------------------------------------------------------
    # 3. Temporal Consistency
    # -------------------------------------------------------------------------

    def validate_temporal(
        self,
        interval: TimeInterval,
        evidence_ids: list[UUID] | None = None,
    ) -> list[ConstraintFinding]:
        """Validate temporal interval ordering, timezone awareness, and precision tiers."""
        findings: list[ConstraintFinding] = []
        ev_ids = evidence_ids or []

        # 1. Timezone awareness check
        if interval.starts_at.tzinfo is None:
            findings.append(
                ConstraintFinding(
                    code="TEMPORAL_TIMEZONE_MISSING",
                    category=ConstraintCategory.TEMPORAL_CONSISTENCY,
                    severity=ConstraintSeverity.BLOCKING,
                    message=f"starts_at timestamp {interval.starts_at} must be timezone-aware (e.g. UTC)",
                    field="time_interval.starts_at",
                    actual_value=str(interval.starts_at),
                    expected_value="timezone-aware datetime (UTC)",
                    evidence_ids=ev_ids,
                )
            )

        if interval.ends_at and interval.ends_at.tzinfo is None:
            findings.append(
                ConstraintFinding(
                    code="TEMPORAL_TIMEZONE_MISSING",
                    category=ConstraintCategory.TEMPORAL_CONSISTENCY,
                    severity=ConstraintSeverity.BLOCKING,
                    message=f"ends_at timestamp {interval.ends_at} must be timezone-aware (e.g. UTC)",
                    field="time_interval.ends_at",
                    actual_value=str(interval.ends_at),
                    expected_value="timezone-aware datetime (UTC)",
                    evidence_ids=ev_ids,
                )
            )

        # 2. Start/End ordering check
        if interval.ends_at and interval.ends_at < interval.starts_at:
            findings.append(
                ConstraintFinding(
                    code="TEMPORAL_INVERTED",
                    category=ConstraintCategory.TEMPORAL_CONSISTENCY,
                    severity=ConstraintSeverity.BLOCKING,
                    message=f"Interval ends_at ({interval.ends_at}) precedes starts_at ({interval.starts_at})",
                    field="time_interval.ends_at",
                    actual_value={"starts_at": str(interval.starts_at), "ends_at": str(interval.ends_at)},
                    expected_value="starts_at <= ends_at",
                    evidence_ids=ev_ids,
                )
            )

        # 3. Supported precision tier
        allowed_precisions = {"instant", "day", "month", "year", "unknown"}
        if interval.precision not in allowed_precisions:
            findings.append(
                ConstraintFinding(
                    code="TEMPORAL_PRECISION_INVALID",
                    category=ConstraintCategory.TEMPORAL_CONSISTENCY,
                    severity=ConstraintSeverity.BLOCKING,
                    message=f"Unsupported temporal precision '{interval.precision}'. Allowed: {sorted(allowed_precisions)}",
                    field="time_interval.precision",
                    actual_value=interval.precision,
                    expected_value=list(allowed_precisions),
                    evidence_ids=ev_ids,
                )
            )

        return findings

    # -------------------------------------------------------------------------
    # 4. Entity & Relationship Consistency
    # -------------------------------------------------------------------------

    def validate_entity(
        self,
        entity: Entity,
        conn: psycopg.Connection | None = None,
    ) -> list[ConstraintFinding]:
        """Validate entity attributes, confidence, and check conservative entity resolution against existing DB records."""
        findings: list[ConstraintFinding] = []

        if not entity.canonical_name or not entity.canonical_name.strip():
            findings.append(
                ConstraintFinding(
                    code="ENTITY_NAME_EMPTY",
                    category=ConstraintCategory.ENTITY_RELATIONSHIP,
                    severity=ConstraintSeverity.BLOCKING,
                    message="Entity canonical_name cannot be empty or whitespace",
                    field="entity.canonical_name",
                    actual_value=entity.canonical_name,
                    expected_value="non-empty string",
                )
            )

        if entity.confidence.value < 0.0 or entity.confidence.value > 1.0:
            findings.append(
                ConstraintFinding(
                    code="CONFIDENCE_OUT_OF_BOUNDS",
                    category=ConstraintCategory.CLAIM_EVIDENCE,
                    severity=ConstraintSeverity.BLOCKING,
                    message=f"Entity confidence {entity.confidence.value} is outside [0.0, 1.0]",
                    field="entity.confidence.value",
                    actual_value=entity.confidence.value,
                    expected_value="[0.0, 1.0]",
                )
            )

        # Conservative resolution check: detect potential false merge candidates
        if conn and entity.canonical_name:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, canonical_name FROM entities WHERE LOWER(canonical_name) = LOWER(%s) AND id <> %s LIMIT 1",
                        (entity.canonical_name.strip(), entity.id),
                    )
                    match = cur.fetchone()
                    if match:
                        findings.append(
                            ConstraintFinding(
                                code="ENTITY_RESOLUTION_UNVERIFIED_MATCH",
                                category=ConstraintCategory.ENTITY_RELATIONSHIP,
                                severity=ConstraintSeverity.REVIEW_REQUIRED,
                                message=(
                                    f"Entity name '{entity.canonical_name}' matches existing entity {match['id']} "
                                    "without confirmed publisher identifier. Conservative resolution requires human review."
                                ),
                                field="entity.canonical_name",
                                actual_value={"name": entity.canonical_name, "existing_id": str(match["id"])},
                                expected_value="matching publisher identifier (scheme/value) before merge",
                            )
                        )
            except Exception:
                pass

        return findings

    def validate_relationship(
        self,
        rel: Relationship,
        conn: psycopg.Connection | None = None,
    ) -> list[ConstraintFinding]:
        """Validate relationship referential integrity, anti-reflexivity, predicate support, and spatial rules."""
        findings: list[ConstraintFinding] = []
        ev_ids = [rel.evidence_id]

        # 1. Prohibit self-relationship
        if rel.subject_entity_id == rel.object_entity_id:
            findings.append(
                ConstraintFinding(
                    code="REL_SELF_RELATIONSHIP",
                    category=ConstraintCategory.ENTITY_RELATIONSHIP,
                    severity=ConstraintSeverity.BLOCKING,
                    message=f"Self-relationships are prohibited; subject_entity_id and object_entity_id are both {rel.subject_entity_id}",
                    field="relationship.object_entity_id",
                    actual_value=str(rel.subject_entity_id),
                    expected_value="distinct entity identifiers",
                    evidence_ids=ev_ids,
                )
            )

        # 2. Supported predicate
        if rel.predicate not in VALID_PREDICATES:
            findings.append(
                ConstraintFinding(
                    code="REL_INVALID_PREDICATE",
                    category=ConstraintCategory.ENTITY_RELATIONSHIP,
                    severity=ConstraintSeverity.BLOCKING,
                    message=f"Predicate '{rel.predicate}' is not in VALID_PREDICATES: {sorted(VALID_PREDICATES)}",
                    field="relationship.predicate",
                    actual_value=rel.predicate,
                    expected_value=list(VALID_PREDICATES),
                    evidence_ids=ev_ids,
                )
            )

        # 3. Confidence bounds
        if rel.confidence.value < 0.0 or rel.confidence.value > 1.0:
            findings.append(
                ConstraintFinding(
                    code="CONFIDENCE_OUT_OF_BOUNDS",
                    category=ConstraintCategory.CLAIM_EVIDENCE,
                    severity=ConstraintSeverity.BLOCKING,
                    message=f"Relationship confidence {rel.confidence.value} is outside [0.0, 1.0]",
                    field="relationship.confidence.value",
                    actual_value=rel.confidence.value,
                    expected_value="[0.0, 1.0]",
                    evidence_ids=ev_ids,
                )
            )

        # 4. Spatial consistency checks for spatial predicates
        findings.extend(self.validate_spatial_relationship(rel, conn=conn))

        return findings

    # -------------------------------------------------------------------------
    # 5. Claims & Evidence Consistency
    # -------------------------------------------------------------------------

    def validate_observation(
        self,
        obs: Observation,
        conn: psycopg.Connection | None = None,
    ) -> list[ConstraintFinding]:
        """Validate observation truth class, evidence citation, measure sanity, and value bounds."""
        findings: list[ConstraintFinding] = []
        ev_ids = [obs.evidence_id]

        # 1. Truth class must strictly be OBSERVED
        if obs.truth_class != "OBSERVED":
            findings.append(
                ConstraintFinding(
                    code="TRUTH_CLASS_INVALID",
                    category=ConstraintCategory.CLAIM_EVIDENCE,
                    severity=ConstraintSeverity.BLOCKING,
                    message=f"Observations must have truth_class 'OBSERVED', got '{obs.truth_class}'",
                    field="observation.truth_class",
                    actual_value=obs.truth_class,
                    expected_value="OBSERVED",
                    evidence_ids=ev_ids,
                )
            )

        # 2. Confidence bounds
        if obs.confidence.value < 0.0 or obs.confidence.value > 1.0:
            findings.append(
                ConstraintFinding(
                    code="CONFIDENCE_OUT_OF_BOUNDS",
                    category=ConstraintCategory.CLAIM_EVIDENCE,
                    severity=ConstraintSeverity.BLOCKING,
                    message=f"Observation confidence {obs.confidence.value} is outside [0.0, 1.0]",
                    field="observation.confidence.value",
                    actual_value=obs.confidence.value,
                    expected_value="[0.0, 1.0]",
                    evidence_ids=ev_ids,
                )
            )

        # 3. Measure value domain sanity checks
        if obs.measure == "population.total":
            if obs.value < 0:
                findings.append(
                    ConstraintFinding(
                        code="MEASURE_VALUE_NEGATIVE",
                        category=ConstraintCategory.CLAIM_EVIDENCE,
                        severity=ConstraintSeverity.BLOCKING,
                        message=f"Population measure '{obs.measure}' cannot be negative ({obs.value})",
                        field="observation.value",
                        actual_value=obs.value,
                        expected_value="value >= 0",
                        evidence_ids=ev_ids,
                    )
                )

        elif obs.measure == "magnitude":
            if obs.value < -2.0 or obs.value > 12.0:
                findings.append(
                    ConstraintFinding(
                        code="MEASURE_VALUE_OUT_OF_BOUNDS",
                        category=ConstraintCategory.CLAIM_EVIDENCE,
                        severity=ConstraintSeverity.BLOCKING,
                        message=f"Earthquake magnitude {obs.value} is outside plausible physical range [-2.0, 12.0]",
                        field="observation.value",
                        actual_value=obs.value,
                        expected_value="[-2.0, 12.0]",
                        evidence_ids=ev_ids,
                    )
                )

        # 4. Check DB evidence referential integrity if connection provided
        if conn and obs.evidence_id:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM evidence WHERE id = %s", (obs.evidence_id,))
                    if not cur.fetchone():
                        findings.append(
                            ConstraintFinding(
                                code="EVIDENCE_REFERENCE_DANGLING",
                                category=ConstraintCategory.CLAIM_EVIDENCE,
                                severity=ConstraintSeverity.WARNING,
                                message=f"Referenced evidence_id {obs.evidence_id} is not yet registered in evidence table",
                                field="observation.evidence_id",
                                actual_value=str(obs.evidence_id),
                                evidence_ids=ev_ids,
                            )
                        )
            except Exception:
                pass

        return findings

    def validate_claim(
        self,
        claim: Claim,
        conn: psycopg.Connection | None = None,
    ) -> list[ConstraintFinding]:
        """Validate claim epistemic truth class rules, input tracking, and method attribution."""
        findings: list[ConstraintFinding] = []
        ev_ids = claim.evidence_ids

        # 1. Truth class contract requirements
        if claim.truth_class == TruthClass.DERIVED:
            if not claim.inputs:
                findings.append(
                    ConstraintFinding(
                        code="DERIVED_CLAIM_INPUTS_MISSING",
                        category=ConstraintCategory.CLAIM_EVIDENCE,
                        severity=ConstraintSeverity.BLOCKING,
                        message="Derived claims must preserve explicit inputs (e.g. input_entity_ids or observation_ids)",
                        field="claim.inputs",
                        evidence_ids=ev_ids,
                    )
                )
            if not claim.method or not claim.computation_version:
                findings.append(
                    ConstraintFinding(
                        code="DERIVED_CLAIM_METHOD_MISSING",
                        category=ConstraintCategory.CLAIM_EVIDENCE,
                        severity=ConstraintSeverity.BLOCKING,
                        message="Derived claims must record method and computation_version",
                        field="claim.method",
                        evidence_ids=ev_ids,
                    )
                )

        elif claim.truth_class in (TruthClass.PREDICTED, TruthClass.SIMULATED):
            if not claim.assumptions:
                findings.append(
                    ConstraintFinding(
                        code="HYPOTHESIS_ASSUMPTIONS_MISSING",
                        category=ConstraintCategory.CLAIM_EVIDENCE,
                        severity=ConstraintSeverity.BLOCKING,
                        message=f"{claim.truth_class.value} claims must document explicit assumptions",
                        field="claim.assumptions",
                        evidence_ids=ev_ids,
                    )
                )
            if not claim.method:
                findings.append(
                    ConstraintFinding(
                        code="HYPOTHESIS_METHOD_MISSING",
                        category=ConstraintCategory.CLAIM_EVIDENCE,
                        severity=ConstraintSeverity.BLOCKING,
                        message=f"{claim.truth_class.value} claims must specify predictive or simulation method",
                        field="claim.method",
                        evidence_ids=ev_ids,
                    )
                )

        # 2. Confidence bounds
        if claim.confidence.value < 0.0 or claim.confidence.value > 1.0:
            findings.append(
                ConstraintFinding(
                    code="CONFIDENCE_OUT_OF_BOUNDS",
                    category=ConstraintCategory.CLAIM_EVIDENCE,
                    severity=ConstraintSeverity.BLOCKING,
                    message=f"Claim confidence {claim.confidence.value} is outside [0.0, 1.0]",
                    field="claim.confidence.value",
                    actual_value=claim.confidence.value,
                    expected_value="[0.0, 1.0]",
                    evidence_ids=ev_ids,
                )
            )

        return findings

    # -------------------------------------------------------------------------
    # Composite Bundle Validation
    # -------------------------------------------------------------------------

    def validate_bundle(
        self,
        bundle: WorldBundle,
        conn: psycopg.Connection | None = None,
    ) -> ConstraintValidationResult:
        """Validate an entire incoming WorldBundle before persistence."""
        findings: list[ConstraintFinding] = []
        ev_id = bundle.evidence.id

        # 1. Source checks
        if not bundle.source.slug or not bundle.source.name:
            findings.append(
                ConstraintFinding(
                    code="SOURCE_METADATA_INCOMPLETE",
                    category=ConstraintCategory.CLAIM_EVIDENCE,
                    severity=ConstraintSeverity.BLOCKING,
                    message="Source must provide valid slug and name",
                    field="bundle.source",
                    evidence_ids=[ev_id],
                )
            )

        # 2. Entity checks
        findings.extend(self.validate_entity(bundle.entity, conn=conn))

        # 3. Temporal checks
        if bundle.time_interval:
            findings.extend(self.validate_temporal(bundle.time_interval, evidence_ids=[ev_id]))

        # 4. Geometry checks
        if bundle.geometry:
            findings.extend(self.validate_geometry(bundle.geometry, conn=conn))

        # 5. Observation checks
        if bundle.observation:
            findings.extend(self.validate_observation(bundle.observation, conn=conn))

        # 6. Relationships checks
        for rel in bundle.relationships:
            findings.extend(self.validate_relationship(rel, conn=conn))

        return ConstraintValidationResult.from_findings(findings)

    # -------------------------------------------------------------------------
    # 6. Scenario & Proposed-Change Validation (Dry-run non-mutating)
    # -------------------------------------------------------------------------

    def validate_scenario_proposal(
        self,
        proposal: ScenarioProposal,
        conn: psycopg.Connection | None = None,
    ) -> ConstraintValidationResult:
        """Evaluate a proposed scenario modification dry-run without mutating authoritative state."""
        findings: list[ConstraintFinding] = []

        if not proposal.name or not proposal.name.strip():
            findings.append(
                ConstraintFinding(
                    code="SCENARIO_NAME_EMPTY",
                    category=ConstraintCategory.SCENARIO_PROPOSAL,
                    severity=ConstraintSeverity.BLOCKING,
                    message="Scenario proposal requires a valid name",
                    field="proposal.name",
                )
            )

        # Validate proposed observations
        for obs in proposal.proposed_observations:
            findings.extend(self.validate_observation(obs, conn=conn))

        # Validate proposed geometries
        for geom in proposal.proposed_geometries:
            findings.extend(self.validate_geometry(geom, conn=conn))

        # Validate proposed relationships
        for rel in proposal.proposed_relationships:
            findings.extend(self.validate_relationship(rel, conn=conn))

        # Check parameter boundary constraints
        for param_name, param_val in proposal.parameters.items():
            if isinstance(param_val, (int, float)):
                if not math.isfinite(param_val):
                    findings.append(
                        ConstraintFinding(
                            code="SCENARIO_PARAMETER_NON_FINITE",
                            category=ConstraintCategory.SCENARIO_PROPOSAL,
                            severity=ConstraintSeverity.BLOCKING,
                            message=f"Scenario parameter '{param_name}' must be finite",
                            field=f"proposal.parameters.{param_name}",
                            actual_value=param_val,
                        )
                    )
                if "population" in param_name.lower() and param_val < 0:
                    findings.append(
                        ConstraintFinding(
                            code="SCENARIO_PARAMETER_NEGATIVE_POPULATION",
                            category=ConstraintCategory.SCENARIO_PROPOSAL,
                            severity=ConstraintSeverity.BLOCKING,
                            message=f"Scenario parameter '{param_name}' cannot be negative",
                            field=f"proposal.parameters.{param_name}",
                            actual_value=param_val,
                        )
                    )

        return ConstraintValidationResult.from_findings(findings)

    # ScenarioEngine Protocol compatibility
    def validate_constraints(self, scenario: dict[str, Any]) -> list[str]:
        """Satisfies ScenarioEngine protocol interface in interfaces.py."""
        # Convert dictionary to proposal or parse findings
        try:
            proposal = ScenarioProposal(**scenario)
            result = self.validate_scenario_proposal(proposal)
            return [f.message for f in result.findings if f.severity == ConstraintSeverity.BLOCKING]
        except Exception as exc:
            return [f"Malformed scenario payload: {str(exc)}"]
