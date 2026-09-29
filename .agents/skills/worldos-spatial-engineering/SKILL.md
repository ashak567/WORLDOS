---
name: worldos-spatial-engineering
description: Rules and best practices for PostGIS spatial SQL, coordinate systems, geometry types, spatial indexing, topological operations, and deterministic geospatial computing in WORLDOS.
---

# WORLDOS Spatial Engineering & PostGIS Playbook

Geospatial data in WORLDOS models the physical earth. Spatial computations must be deterministic, mathematically rigorous, and grounded in PostGIS and standard GEOS/Shapely libraries.

---

## 1. Coordinate Reference Systems (CRS) Standards

- **Internal Storage Standard**: Always store spatial data in **WGS 84 (SRID 4326)** for geographic coordinates (latitude, longitude).
- **Coordinate Order Convention**:
  - In GeoJSON and PostGIS WKT/EWKB: **(Longitude, Latitude)** = $(X, Y)$.
  - Always verify whether an external source uses `(lat, lon)` or `(lon, lat)` before parsing.
  - Invert explicitly at the source adapter boundary if necessary.
- **Metric Distance Calculations**:
  - Never compute Euclidean distances (`sqrt(dx^2 + dy^2)`) on degree coordinates.
  - In PostGIS: Cast to `geography` for geodesic meters:
    ```sql
    ST_DWithin(geom1::geography, geom2::geography, 50000); -- 50 km
    ST_Distance(geom1::geography, geom2::geography);
    ```
  - In Python: Use `pyproj` or `geopy` for geodesic ellipsoidal distance (WGS-84 ellipsoid).

---

## 2. PostGIS Schema & Indexing Rules

### A. Column Definitions
Always specify explicit geometry type and SRID:
```sql
CREATE TABLE spatial_features (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID REFERENCES entities(id) ON DELETE CASCADE,
    geom geometry(Geometry, 4326) NOT NULL,
    centroid geometry(Point, 4326),
    bbox box2d
);
```

### B. Spatial Indexing
Every table containing geometry must have a **GiST** (Generalized Search Tree) index:
```sql
CREATE INDEX idx_spatial_features_geom ON spatial_features USING GIST (geom);
```
Without a GiST index, spatial joins (`ST_Contains`, `ST_Intersects`) perform quadratic $O(N \times M)$ full table scans.

---

## 3. Topological Predicates & Containment

When evaluating spatial relationships (e.g. "Did this earthquake occur in Japan?"):
- Use **`ST_Contains(polygon, point)`** or **`ST_Covers(polygon, point)`**.
- Use **`ST_Intersects(geom1, geom2)`** for boundary-touching or overlapping geometries.
- For proximity:
  ```sql
  -- Efficient indexed proximity search within 25km:
  SELECT e.id, e.name
  FROM entities e
  JOIN spatial_features s ON s.entity_id = e.id
  WHERE ST_DWithin(s.geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, 25000);
  ```

---

## 4. Antimeridian Crossing & Polygon Validity

- **Antimeridian ($\pm 180^\circ$)**: Polygons crossing the 180th meridian (e.g., Fiji, Russia, Alaska) can produce corrupted bounding boxes if treated as naive Cartesian polygons. Always split geometries at $-180 / +180$ degrees or use `ST_ShiftLongitude` / geography types.
- **Geometry Validity**:
  Before persisting geometries from external sources:
  ```sql
  SELECT ST_IsValid(geom), ST_IsValidReason(geom);
  -- Fix self-intersecting or malformed rings:
  UPDATE spatial_features SET geom = ST_MakeValid(geom) WHERE NOT ST_IsValid(geom);
  ```

---

## 5. Python Geospatial Stack Integration

In the backend Python engines:
- Use **Shapely** (`shapely.geometry`, `shapely.ops`) for in-memory geometric validation and operations.
- Convert between GeoJSON and Shapely:
  ```python
  from shapely.geometry import shape, mapping, Point, Polygon
  import json

  geojson_geom = {"type": "Point", "coordinates": [139.6917, 35.6895]}
  pt: Point = shape(geojson_geom)
  assert pt.x == 139.6917  # lon
  assert pt.y == 35.6895   # lat
  ```
- Use **GeoJSON Pydantic** models to validate incoming REST payloads before touching the database.

---

## 6. Anti-Patterns to Avoid

- **Anti-Pattern 1: Inverted Coordinates**: Storing `Point(35.6895, 139.6917)` as Tokyo, resulting in coordinates placed in Antarctica or the Indian Ocean.
- **Anti-Pattern 2: Unindexed Spatial Joins**: Writing `WHERE ST_Distance(a.geom, b.geom) < 10` without a GiST index and without `ST_DWithin`.
- **Anti-Pattern 3: Bounding-Box-Only Containment**: Assuming an event occurred inside a country because it lies within the rectangular bounding box ($BBOX$). Bounding boxes often overlap neighboring countries. Always test the polygon geometry.
