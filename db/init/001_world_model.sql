CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE sources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug text UNIQUE NOT NULL,
  name text NOT NULL,
  publisher text NOT NULL,
  license text,
  homepage text,
  refresh_policy text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE entities (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind text NOT NULL,
  canonical_name text NOT NULL,
  source_id uuid REFERENCES sources(id),
  source_key text,
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence numeric(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_id, source_key)
);

CREATE TABLE geometries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  geometry geometry(Geometry, 4326) NOT NULL,
  geometry_kind text NOT NULL,
  valid_during tstzrange,
  source_id uuid NOT NULL REFERENCES sources(id),
  confidence numeric(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX geometries_shape_idx ON geometries USING gist (geometry);

CREATE TABLE time_intervals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  starts_at timestamptz NOT NULL,
  ends_at timestamptz,
  precision text NOT NULL,
  CHECK (ends_at IS NULL OR ends_at >= starts_at)
);

CREATE TABLE evidence (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id uuid NOT NULL REFERENCES sources(id),
  locator text NOT NULL,
  retrieved_at timestamptz NOT NULL,
  content_hash text,
  excerpt text,
  UNIQUE (source_id, locator)
);

CREATE TABLE provenance (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  evidence_id uuid NOT NULL REFERENCES evidence(id),
  pipeline_version text NOT NULL,
  transformation jsonb NOT NULL DEFAULT '{}'::jsonb,
  recorded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE observations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_entity_id uuid NOT NULL REFERENCES entities(id),
  measure text NOT NULL,
  value numeric NOT NULL,
  unit text NOT NULL,
  time_interval_id uuid NOT NULL REFERENCES time_intervals(id),
  evidence_id uuid NOT NULL REFERENCES evidence(id),
  provenance_id uuid NOT NULL REFERENCES provenance(id),
  confidence numeric(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (subject_entity_id, measure, time_interval_id, evidence_id)
);
CREATE INDEX observations_subject_measure_idx ON observations (subject_entity_id, measure);

CREATE TABLE events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind text NOT NULL,
  subject_entity_id uuid REFERENCES entities(id),
  time_interval_id uuid NOT NULL REFERENCES time_intervals(id),
  evidence_id uuid NOT NULL REFERENCES evidence(id),
  confidence numeric(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE relationships (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_entity_id uuid NOT NULL REFERENCES entities(id),
  predicate text NOT NULL,
  object_entity_id uuid NOT NULL REFERENCES entities(id),
  time_interval_id uuid REFERENCES time_intervals(id),
  evidence_id uuid NOT NULL REFERENCES evidence(id),
  confidence numeric(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  CHECK (subject_entity_id <> object_entity_id)
);
CREATE INDEX relationships_subject_idx ON relationships (subject_entity_id, predicate);
CREATE INDEX relationships_object_idx ON relationships (object_entity_id, predicate);
