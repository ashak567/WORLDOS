CREATE TABLE entity_identifiers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  source_id uuid NOT NULL REFERENCES sources(id),
  source_key text NOT NULL,
  scheme text NOT NULL,
  value text NOT NULL,
  confidence numeric(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_id, source_key),
  UNIQUE (scheme, value)
);
CREATE INDEX entity_identifiers_entity_idx ON entity_identifiers (entity_id);
