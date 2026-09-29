CREATE TABLE IF NOT EXISTS claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_entity_id UUID REFERENCES entities(id) ON DELETE CASCADE,
    claim_type VARCHAR(128) NOT NULL,
    truth_class VARCHAR(32) NOT NULL CHECK (truth_class IN ('OBSERVED', 'DERIVED', 'INFERRED', 'PREDICTED', 'SIMULATED')),
    value JSONB NOT NULL,
    unit VARCHAR(64),
    time_interval_id UUID REFERENCES time_intervals(id) ON DELETE SET NULL,
    spatial_scope JSONB,
    method VARCHAR(255) NOT NULL,
    computation_version VARCHAR(64) NOT NULL,
    inputs JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_ids UUID[] NOT NULL DEFAULT '{}',
    assumptions JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence NUMERIC(4, 3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_claims_subject_entity ON claims(subject_entity_id);
CREATE INDEX IF NOT EXISTS idx_claims_truth_class ON claims(truth_class);
CREATE INDEX IF NOT EXISTS idx_claims_claim_type ON claims(claim_type);

-- Enforce at the PostgreSQL level that observations are strictly OBSERVED
ALTER TABLE observations ADD COLUMN IF NOT EXISTS truth_class VARCHAR(32) NOT NULL DEFAULT 'OBSERVED';
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'check_observation_truth_class_observed'
    ) THEN
        ALTER TABLE observations ADD CONSTRAINT check_observation_truth_class_observed CHECK (truth_class = 'OBSERVED');
    END IF;
END $$;
