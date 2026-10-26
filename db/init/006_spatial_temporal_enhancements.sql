-- Migration 006: Spatial and Temporal Query Enhancements
-- Adds explicit evidence references to geometries and indexes for temporal range queries

ALTER TABLE geometries ADD COLUMN IF NOT EXISTS evidence_id uuid REFERENCES evidence(id);
CREATE INDEX IF NOT EXISTS geometries_valid_during_idx ON geometries USING gist (valid_during);
CREATE INDEX IF NOT EXISTS time_intervals_range_idx ON time_intervals (starts_at, ends_at);
