#!/usr/bin/env python3
"""
Load the gold CSVs into Postgres (the serving warehouse).

Each gold CSV -> one table in schema `gold`. Idempotent: replaces tables.
Reads connection from env (same vars the app and Airflow will use).

Env:
  PGHOST (default localhost) PGPORT (5432) PGDATABASE (aiwork)
  PGUSER (aiwork) PGPASSWORD (aiwork)

Run:  python -m src.db.load_gold_to_postgres
"""
import glob, os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import pandas as pd
from sqlalchemy import create_engine, text

GOLD = os.environ.get("GOLD_DIR", "data/gold")

TABLES = {
    "github_adoption_by_year": "github_adoption_by_year.csv",
    "github_adoption_by_month": "github_adoption_by_month.csv",
    "jobs_by_exposure_band_year": "jobs_by_exposure_band_year.csv",
    "jobs_by_occupation": "jobs_by_occupation.csv",
    "github_merge_rate": "github_merge_rate.csv",
    "github_changes_requested": "github_changes_requested.csv",
    "github_churn_by_bucket": "github_churn_by_bucket.csv",
    "github_ai_share_by_repo": "github_ai_share_by_repo.csv",
}


def engine_from_env():
    user = os.environ.get("PGUSER", "aiwork")
    pw   = os.environ.get("PGPASSWORD", "aiwork")
    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("PGPORT", "5432")
    db   = os.environ.get("PGDATABASE", "aiwork")
    return create_engine(f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}")


def main():
    eng = engine_from_env()
    with eng.begin() as c:
        c.execute(text("CREATE SCHEMA IF NOT EXISTS gold"))
    loaded = 0
    for table, fname in TABLES.items():
        path = os.path.join(GOLD, fname)
        if not os.path.exists(path):
            print(f"    skip {table} (no {fname})")
            continue
        df = pd.read_csv(path, dtype={"isco08_4digit": str})
        df.to_sql(table, eng, schema="gold", if_exists="replace", index=False)
        print(f"    loaded gold.{table}: {len(df):,} rows")
        loaded += 1
    print(f"\n{loaded} gold tables -> Postgres ({os.environ.get('PGDATABASE','aiwork')})")


if __name__ == "__main__":
    main()