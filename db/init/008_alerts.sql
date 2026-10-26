-- Migration 008: Alert Rules, Event Evaluations, and Alert Records
-- Deepens Engine 14 (Event / Alert Engine) with deterministic threshold rules,
-- spatial-temporal correlation, deduplication/cooldown, and evidence lineage.

CREATE TABLE IF NOT EXISTS alert_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    event_kind TEXT NOT NULL,
    operator TEXT NOT NULL CHECK (operator IN ('>', '>=', '<', '<=', '==', '!=')),
    metric_field TEXT NOT NULL,
    threshold NUMERIC NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL')),
    spatial_scope JSONB,
    temporal_window_seconds INT,
    cluster_threshold INT,
    cooldown_seconds INT NOT NULL DEFAULT 300,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alert_rules_kind ON alert_rules(event_kind, is_enabled);

CREATE TABLE IF NOT EXISTS alert_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('RECEIVED', 'VALIDATED', 'EVALUATED', 'ALERTED', 'SUPPRESSED', 'FAILED')),
    matched_rule_ids UUID[] NOT NULL DEFAULT '{}',
    alerts_generated INT NOT NULL DEFAULT 0,
    reason TEXT,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_alert_evaluations_event ON alert_evaluations(event_id);
CREATE INDEX IF NOT EXISTS idx_alert_evaluations_status ON alert_evaluations(status);

CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id UUID NOT NULL REFERENCES alert_rules(id) ON DELETE CASCADE,
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    severity TEXT NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL')),
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    dedup_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'acknowledged', 'resolved')) DEFAULT 'active',
    evidence_id UUID NOT NULL REFERENCES evidence(id) ON DELETE RESTRICT,
    context_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by TEXT,
    resolved_at TIMESTAMPTZ,
    resolution_notes TEXT,
    UNIQUE (dedup_key)
);

CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status, severity);
CREATE INDEX IF NOT EXISTS idx_alerts_event ON alerts(event_id);
CREATE INDEX IF NOT EXISTS idx_alerts_rule ON alerts(rule_id);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at DESC);
