CREATE TABLE IF NOT EXISTS ingestion_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id uuid NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  pipeline_version text NOT NULL,
  status text NOT NULL CHECK (status IN ('started', 'completed', 'failed', 'partial')),
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  records_fetched int NOT NULL DEFAULT 0,
  records_persisted int NOT NULL DEFAULT 0,
  records_failed int NOT NULL DEFAULT 0,
  error_message text,
  freshness_observed_at timestamptz,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_ingestion_runs_source_status ON ingestion_runs (source_id, status);
CREATE INDEX IF NOT EXISTS idx_ingestion_runs_started ON ingestion_runs (started_at DESC);
