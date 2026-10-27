-- Migration 013: Engine 18 Prediction Engine
-- Implements deterministic forecasting, trajectory point storage, prediction intervals,
-- and walk-forward historical evaluations without mutating authoritative operational world-state data.

CREATE TABLE IF NOT EXISTS prediction_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    metric VARCHAR(128) NOT NULL,
    unit VARCHAR(64) NOT NULL DEFAULT '',
    status VARCHAR(32) NOT NULL DEFAULT 'CREATED' CHECK (status IN ('CREATED', 'RUNNING', 'COMPLETED', 'FAILED', 'INSUFFICIENT_DATA')),
    method VARCHAR(64) NOT NULL,
    method_version VARCHAR(32) NOT NULL DEFAULT 'v1.0.0',
    request_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    observations_count INT NOT NULL DEFAULT 0,
    trajectory_points_count INT NOT NULL DEFAULT 0,
    historical_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    model_parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    quality_warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    assumptions JSONB NOT NULL DEFAULT '[]'::jsonb,
    limitations JSONB NOT NULL DEFAULT '[]'::jsonb,
    reproducibility_fingerprint TEXT NOT NULL,
    execution_duration_ms DOUBLE PRECISION,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_prediction_runs_entity ON prediction_runs(entity_id);
CREATE INDEX IF NOT EXISTS idx_prediction_runs_metric ON prediction_runs(metric);
CREATE INDEX IF NOT EXISTS idx_prediction_runs_status ON prediction_runs(status);
CREATE INDEX IF NOT EXISTS idx_prediction_runs_created ON prediction_runs(created_at DESC);

CREATE TABLE IF NOT EXISTS prediction_points (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES prediction_runs(id) ON DELETE CASCADE,
    step_index INT NOT NULL,
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    metric VARCHAR(128) NOT NULL,
    unit VARCHAR(64) NOT NULL,
    forecast_timestamp TIMESTAMPTZ NOT NULL,
    predicted_value DOUBLE PRECISION NOT NULL,
    lower_bound DOUBLE PRECISION,
    upper_bound DOUBLE PRECISION,
    confidence_level DOUBLE PRECISION,
    method VARCHAR(64) NOT NULL,
    method_version VARCHAR(32) NOT NULL DEFAULT 'v1.0.0',
    truth_class VARCHAR(32) NOT NULL DEFAULT 'PREDICTED',
    evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    assumptions JSONB NOT NULL DEFAULT '[]'::jsonb,
    limitations JSONB NOT NULL DEFAULT '[]'::jsonb,
    data_quality_warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    fingerprint TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_prediction_point UNIQUE (run_id, step_index)
);

CREATE INDEX IF NOT EXISTS idx_prediction_points_run_step ON prediction_points(run_id, step_index ASC);
CREATE INDEX IF NOT EXISTS idx_prediction_points_entity ON prediction_points(entity_id);
CREATE INDEX IF NOT EXISTS idx_prediction_points_timestamp ON prediction_points(forecast_timestamp);

CREATE TABLE IF NOT EXISTS prediction_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES prediction_runs(id) ON DELETE CASCADE,
    metric VARCHAR(128) NOT NULL,
    evaluation_window JSONB NOT NULL DEFAULT '{}'::jsonb,
    matched_points_count INT NOT NULL DEFAULT 0,
    mae DOUBLE PRECISION NOT NULL,
    rmse DOUBLE PRECISION NOT NULL,
    mase DOUBLE PRECISION,
    bias DOUBLE PRECISION NOT NULL,
    interval_coverage DOUBLE PRECISION,
    baseline_comparison JSONB NOT NULL DEFAULT '{}'::jsonb,
    evaluation_method VARCHAR(64) NOT NULL DEFAULT 'walk_forward',
    method_version VARCHAR(32) NOT NULL DEFAULT 'v1.0.0',
    limitations JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prediction_evaluations_run ON prediction_evaluations(run_id);
CREATE INDEX IF NOT EXISTS idx_prediction_evaluations_metric ON prediction_evaluations(metric);
