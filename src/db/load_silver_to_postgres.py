#!/usr/bin/env python3
"""
Load the latest silver partitions into Postgres schema `silver` (dbt sources).

  silver.jobs_kaggle   <- data/silver/kaggle/dt=*/de_jobs.csv       (general)
  silver.jobs_tech     <- data/silver/tech/dt=*/de_tech_jobs.csv    (tech)

Idempotent (replace). Env-driven connection (reads .env).

Run:  python -m src.db.load_silver_to_postgres
"""
import glob, os
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass
import pandas as pd
from sqlalchemy import create_engine, text

SILVER = {
    "jobs_kaggle": "data/silver/kaggle",
    "jobs_tech": "data/silver/tech",
}


def engine_from_env():
    u=os.environ.get("PGUSER","aiwork"); p=os.environ.get("PGPASSWORD","aiwork")
    h=os.environ.get("PGHOST","localhost"); pt=os.environ.get("PGPORT","5432")
    db=os.environ.get("PGDATABASE","aiwork")
    return create_engine(f"postgresql+psycopg2://{u}:{p}@{h}:{pt}/{db}")


def latest(base):
    parts = sorted(glob.glob(os.path.join(base, "dt=*")))
    if not parts: return None
    hits = glob.glob(os.path.join(parts[-1], "*.csv"))
    return hits[0] if hits else None


def main():
    eng = engine_from_env()
    with eng.begin() as c:
        c.execute(text("CREATE SCHEMA IF NOT EXISTS silver"))
    for table, base in SILVER.items():
        p = latest(base)
        if not p:
            print(f"    skip {table} (no silver in {base})"); continue
        df = pd.read_csv(p, dtype={"isco08_4digit": str})
        df.to_sql(table, eng, schema="silver", if_exists="replace", index=False)
        print(f"    loaded silver.{table}: {len(df):,} rows  <- {p}")
    print("\nsilver -> Postgres done")


if __name__ == "__main__":
    main()