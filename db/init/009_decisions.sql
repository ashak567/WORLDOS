-- Migration 009: Deterministic Decision Support Runs and Auditing
-- Implements persistence for Engine 13 (Decision Support Engine).
-- Preserves full calculation trace, input criteria, weights, constraint findings,
-- normalized scores, trade-off explanations, and evidence citations.

CREATE TABLE IF NOT EXISTS decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    objective TEXT NOT NULL,
    scope JSONB NOT NULL DEFAULT '{}'::jsonb,
    request JSONB NOT NULL,
    result JSONB NOT NULL,
    alternatives_count INT NOT NULL DEFAULT 0,
    feasible_count INT NOT NULL DEFAULT 0,
    top_alternative_id TEXT,
    top_alternative_name TEXT,
    top_score NUMERIC(6, 4),
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_decisions_evaluated_at ON decisions(evaluated_at DESC);
CREATE INDEX IF NOT EXISTS idx_decisions_objective ON decisions(objective);
