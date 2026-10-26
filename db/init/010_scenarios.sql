-- Migration 010: Engine 16 Scenario Engine Isolation and Versioning
-- Implements sandboxed scenario branches, deterministic modifications overlay,
-- and immutable evaluation records without mutating authoritative world state.

CREATE TABLE IF NOT EXISTS scenarios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'VALIDATED', 'EVALUATED', 'ARCHIVED')),
    version INT NOT NULL DEFAULT 1,
    parent_scenario_id UUID REFERENCES scenarios(id) ON DELETE SET NULL,
    parent_scenario_version INT,
    baseline_context JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scenarios_status ON scenarios(status);
CREATE INDEX IF NOT EXISTS idx_scenarios_parent ON scenarios(parent_scenario_id);
CREATE INDEX IF NOT EXISTS idx_scenarios_created ON scenarios(created_at DESC);

CREATE TABLE IF NOT EXISTS scenario_modifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scenario_id UUID NOT NULL REFERENCES scenarios(id) ON DELETE CASCADE,
    target_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    target_field TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('SET', 'DELTA', 'SCALE', 'REMOVE')),
    value JSONB NOT NULL,
    unit TEXT,
    effective_interval JSONB,
    rationale TEXT,
    evidence_references UUID[] DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'superseded', 'invalid')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scenario_modifications_scenario ON scenario_modifications(scenario_id, status);
CREATE INDEX IF NOT EXISTS idx_scenario_modifications_target ON scenario_modifications(target_entity_id);

CREATE TABLE IF NOT EXISTS scenario_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scenario_id UUID NOT NULL REFERENCES scenarios(id) ON DELETE CASCADE,
    scenario_version INT NOT NULL,
    baseline_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    simulated_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    delta_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    constraint_findings JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_feasible BOOLEAN NOT NULL DEFAULT TRUE,
    derived_metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    assumptions JSONB NOT NULL DEFAULT '[]'::jsonb,
    limitations JSONB NOT NULL DEFAULT '[]'::jsonb,
    evaluation_version TEXT NOT NULL DEFAULT 'v1.0.0',
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scenario_evaluations_scenario_version ON scenario_evaluations(scenario_id, scenario_version DESC);
