"""Minimal SQL migration runner. discover() is unit-tested; apply() needs psycopg + a database (UNTESTED here)."""
import os, re


def discover(directory):
    files = sorted(f for f in os.listdir(directory) if re.match(r"^\d{3}_.+\.sql$", f))
    out = []
    for f in files:
        with open(os.path.join(directory, f)) as fh: out.append((f.split("_")[0], f, fh.read()))
    return out


def apply(dsn, directory):
    import psycopg
    with psycopg.connect(dsn, autocommit=True) as conn:      # each migration is its own transaction; earlier ones stay applied
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, applied_at timestamptz DEFAULT now())")
        done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        for version, name, sql in discover(directory):
            if version in done: continue
            with conn.transaction():
                conn.execute(sql)
                conn.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (version,))
            print("applied", name)


if __name__ == "__main__":
    from .config import database_dsn          # same DB_* / DATABASE_URL contract as the API and workers
    apply(database_dsn(), os.environ.get("MIGRATIONS_DIR", "infra/db/migrations"))
