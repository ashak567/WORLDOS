-- Engine 15: Anomaly Detection Engine Tables
-- Implements audit-trailed storage for anomaly detection runs and findings.
-- Strict adherence to non-mutation of authoritative observation facts.

CREATE TABLE IF NOT EXISTS anomaly_runs (
    id UUID PRIMARY KEY,
    status VARCHAR(32) NOT NULL DEFAULT 'RUNNING',
    request_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    observations_evaluated INT NOT NULL DEFAULT 0,
    findings_count INT NOT NULL DEFAULT 0,
    summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    exclusions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    execution_duration_ms DOUBLE PRECISION,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS anomaly_findings (
    id UUID PRIMARY KEY,
    run_id UUID REFERENCES anomaly_runs(id) ON DELETE SET NULL,
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    observation_id UUID REFERENCES observations(id) ON DELETE SET NULL,
    metric VARCHAR(128) NOT NULL,
    unit VARCHAR(64) NOT NULL,
    observed_value DOUBLE PRECISION NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    expected_value DOUBLE PRECISION,
    deviation DOUBLE PRECISION NOT NULL,
    deviation_magnitude DOUBLE PRECISION NOT NULL,
    anomaly_score DOUBLE PRECISION NOT NULL,
    detection_method VARCHAR(64) NOT NULL,
    method_version VARCHAR(32) NOT NULL DEFAULT 'v1.0.0',
    threshold_applied DOUBLE PRECISION NOT NULL,
    severity VARCHAR(32) NOT NULL DEFAULT 'WARNING',
    status VARCHAR(32) NOT NULL DEFAULT 'NEW',
    data_reliability DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    baseline_observation_count INT NOT NULL DEFAULT 0,
    baseline_window JSONB NOT NULL DEFAULT '{}'::jsonb,
    baseline_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    truth_class VARCHAR(32) NOT NULL DEFAULT 'DERIVED',
    explanation TEXT NOT NULL,
    limitations JSONB NOT NULL DEFAULT '[]'::jsonb,
    data_quality_warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    fingerprint VARCHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_anomaly_findings_entity_id ON anomaly_findings(entity_id);
CREATE INDEX IF NOT EXISTS idx_anomaly_findings_metric ON anomaly_findings(metric);
CREATE INDEX IF NOT EXISTS idx_anomaly_findings_observed_at ON anomaly_findings(observed_at);
CREATE INDEX IF NOT EXISTS idx_anomaly_findings_severity ON anomaly_findings(severity);
CREATE INDEX IF NOT EXISTS idx_anomaly_findings_status ON anomaly_findings(status);
CREATE INDEX IF NOT EXISTS idx_anomaly_findings_detection_method ON anomaly_findings(detection_method);
CREATE INDEX IF NOT EXISTS idx_anomaly_findings_run_id ON anomaly_findings(run_id);
CREATE INDEX IF NOT EXISTS idx_anomaly_runs_created_at ON anomaly_runs(created_at);
