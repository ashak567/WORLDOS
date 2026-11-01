-- Migration 015: Optimize aircraft/observations queries, evidence lookups, and geometries
-- Eliminates full table sequential scans and disk-spill sorts on live world-state queries

CREATE INDEX IF NOT EXISTS idx_observations_measure_subject ON observations (measure, subject_entity_id);
CREATE INDEX IF NOT EXISTS idx_geometries_entity_evidence_kind ON geometries (entity_id, evidence_id, geometry_kind);
CREATE INDEX IF NOT EXISTS idx_geometries_kind_entity ON geometries (geometry_kind, entity_id);
CREATE INDEX IF NOT EXISTS idx_evidence_source_id ON evidence (source_id);
CREATE INDEX IF NOT EXISTS idx_observations_time_interval ON observations (time_interval_id);

