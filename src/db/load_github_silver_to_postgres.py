#!/usr/bin/env python3
"""
Load GitHub silver into Postgres schema `silver` (dbt sources for the GitHub gold).

  silver.gh_matches       <- <LAKE>/silver/github/adoption/matches.csv
  silver.gh_totals        <- <LAKE>/silver/github/adoption/totals.csv
  silver.gh_pr_outcomes   <- <LAKE>/silver/github/pr_quality/dt=*/pr_outcomes.csv  (pooled)
  silver.gh_pr_reviews    <- <LAKE>/silver/github/pr_quality/dt=*/pr_reviews.csv   (pooled)
  silver.gh_churn_events  <- <LAKE>/silver/github/churn/churn_events.csv

Silver is read from LAKE_ROOT (local data/ or s3://bucket). Idempotent (replace).
Bulk-loads via Postgres COPY so large tables land in seconds against Neon.

Run:  python -m src.db.load_github_silver_to_postgres
"""
import io, os
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass
import pandas as pd
from sqlalchemy import create_engine, text

from src.common.config import lake_path, lake_glob, lake_exists   # AFTER load_dotenv


def engine_from_env():
    u=os.environ.get("PGUSER","aiwork"); p=os.environ.get("PGPASSWORD","aiwork")
    h=os.environ.get("PGHOST","localhost"); pt=os.environ.get("PGPORT","5432")
    db=os.environ.get("PGDATABASE","aiwork")
    sslmode=os.environ.get("PGSSLMODE","prefer")   # Neon: set PGSSLMODE=require in .env
    return create_engine(
        f"postgresql+psycopg2://{u}:{p}@{h}:{pt}/{db}",
        pool_pre_ping=True,
        connect_args={
            "sslmode": sslmode,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
    )


def _copy_into(eng, table, df):
    """Create silver.<table> with df's schema, then bulk-load rows via COPY."""
    df.head(0).to_sql(table, eng, schema="silver", if_exists="replace", index=False)
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False)
    buf.seek(0)
    raw = eng.raw_connection()
    try:
        cur = raw.cursor()
        cur.copy_expert(f'COPY silver."{table}" FROM STDIN WITH (FORMAT csv)', buf)
        raw.commit()
    finally:
        raw.close()


def load_one(eng, table, path):
    if not lake_exists(path):
        print(f"    skip {table} (no {path})"); return
    df = pd.read_csv(path)
    _copy_into(eng, table, df)
    print(f"    loaded silver.{table}: {len(df):,} rows  <- {path}")


def load_pooled(eng, table, glob_pat):
    paths = lake_glob(glob_pat)
    if not paths:
        print(f"    skip {table} (no files at {glob_pat})"); return
    df = pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
    _copy_into(eng, table, df)
    print(f"    loaded silver.{table}: {len(df):,} rows  <- {len(paths)} day-folders")


def main():
    eng = engine_from_env()
    with eng.begin() as c:
        c.execute(text("CREATE SCHEMA IF NOT EXISTS silver"))
    load_one(eng, "gh_matches", lake_path("silver/github/adoption/matches.csv"))
    load_one(eng, "gh_totals",  lake_path("silver/github/adoption/totals.csv"))
    load_pooled(eng, "gh_pr_outcomes", lake_path("silver/github/pr_quality/dt=*/pr_outcomes.csv"))
    load_pooled(eng, "gh_pr_reviews",  lake_path("silver/github/pr_quality/dt=*/pr_reviews.csv"))
    load_one(eng, "gh_churn_events", lake_path("silver/github/churn/churn_events.csv"))
    print("\nGitHub silver -> Postgres done")


if __name__ == "__main__":
    main()