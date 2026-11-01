CREATE TABLE IF NOT EXISTS satellite_catalog_cache (
    cache_key text PRIMARY KEY CHECK (cache_key = 'active'),
    catalog jsonb NOT NULL,
    retrieved_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
