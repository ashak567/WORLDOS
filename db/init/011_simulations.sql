-- Migration 011: Engine 17 Simulation Engine
-- Implements bounded, deterministic multi-step forward state evolution,
-- isolated simulation trajectories, and reproducibility metadata without mutating
-- authoritative operational world-state data.

CREATE TABLE IF NOT EXISTS simulation_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scenario_id UUID NOT NULL REFERENCES scenarios(id) ON DELETE CASCADE,
    scenario_version INT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('CREATED', 'VALIDATED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')),
    configuration JSONB NOT NULL DEFAULT '{}'::jsonb,
    initial_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    final_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    trajectory_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_feasible BOOLEAN NOT NULL DEFAULT TRUE,
    constraint_findings JSONB NOT NULL DEFAULT '[]'::jsonb,
    assumptions JSONB NOT NULL DEFAULT '[]'::jsonb,
    limitations JSONB NOT NULL DEFAULT '[]'::jsonb,
    step_count INT NOT NULL DEFAULT 0,
    execution_duration_ms DOUBLE PRECISION,
    reproducibility_fingerprint TEXT NOT NULL,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_simulation_runs_scenario ON simulation_runs(scenario_id, scenario_version);
CREATE INDEX IF NOT EXISTS idx_simulation_runs_status ON simulation_runs(status);
CREATE INDEX IF NOT EXISTS idx_simulation_runs_created ON simulation_runs(created_at DESC);

CREATE TABLE IF NOT EXISTS simulation_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id UUID NOT NULL REFERENCES simulation_runs(id) ON DELETE CASCADE,
    step_index INT NOT NULL,
    simulated_at TIMESTAMPTZ NOT NULL,
    state JSONB NOT NULL DEFAULT '{}'::jsonb,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    applied_rules JSONB NOT NULL DEFAULT '[]'::jsonb,
    constraint_findings JSONB NOT NULL DEFAULT '[]'::jsonb,
    findings JSONB NOT NULL DEFAULT '[]'::jsonb,
    step_fingerprint TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_simulation_step UNIQUE (simulation_id, step_index)
);

CREATE INDEX IF NOT EXISTS idx_simulation_steps_sim_step ON simulation_steps(simulation_id, step_index ASC);
