"""Apply bundled SQL migrations once before starting the API."""
from __future__ import annotations

import os
from pathlib import Path

import psycopg


def run_migrations() -> None:
    migration_dir = Path(__file__).resolve().parents[1] / "db" / "init"
    database_url = os.environ["WORLDOS_DATABASE_URL"]
    with psycopg.connect(database_url, connect_timeout=20) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS worldos_schema_migrations (
                migration_name text PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now()
            )"""
        )
        for migration in sorted(migration_dir.glob("*.sql")):
            with connection.transaction():
                applied = connection.execute(
                    "SELECT 1 FROM worldos_schema_migrations WHERE migration_name = %s",
                    (migration.name,),
                ).fetchone()
                if applied:
                    continue
                connection.execute(migration.read_text(encoding="utf-8"), prepare=False)
                connection.execute(
                    "INSERT INTO worldos_schema_migrations (migration_name) VALUES (%s)",
                    (migration.name,),
                )
                print(f"Applied database migration {migration.name}", flush=True)


if __name__ == "__main__":
    run_migrations()
