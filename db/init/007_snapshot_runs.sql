-- Migration 007: Snapshot Runs and Analytical Export Tracking
-- Tracks the lifecycle of deterministic DuckDB/Parquet snapshot exports

CREATE TABLE IF NOT EXISTS snapshot_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    schema_version VARCHAR(64) NOT NULL DEFAULT 'worldos-snapshot-v1',
    status VARCHAR(32) NOT NULL CHECK (status IN ('in_progress', 'completed', 'failed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    datasets TEXT[] NOT NULL DEFAULT '{}',
    total_records INT NOT NULL DEFAULT 0,
    row_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    partition_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    min_year INT,
    max_year INT,
    storage_path TEXT NOT NULL,
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_snapshot_runs_status ON snapshot_runs(status);
CREATE INDEX IF NOT EXISTS idx_snapshot_runs_started ON snapshot_runs(started_at DESC);
