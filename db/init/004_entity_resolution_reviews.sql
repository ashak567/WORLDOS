CREATE TABLE IF NOT EXISTS entity_resolution_reviews (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  target_entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  match_reason text NOT NULL,
  confidence numeric(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  status text NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
  created_at timestamptz NOT NULL DEFAULT now(),
  reviewed_at timestamptz,
  reviewed_by text,
  resolution_notes text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (candidate_entity_id, target_entity_id, match_reason)
);
CREATE INDEX IF NOT EXISTS idx_resolution_reviews_status ON entity_resolution_reviews (status);
