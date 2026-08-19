#!/usr/bin/env python3
"""
Load GitHub silver into Postgres schema `silver` (dbt sources for the GitHub gold).

  silver.gh_matches       <- data/silver/gharchive/matches.csv
  silver.gh_totals        <- data/silver/gharchive/totals.csv
  silver.gh_pr_outcomes   <- data/silver/gharchive_day_*/pr_outcomes.csv  (pooled)
  silver.gh_pr_reviews    <- data/silver/gharchive_day_*/pr_reviews.csv   (pooled)
  silver.gh_churn_events  <- data/silver/churn/churn_events.csv

Idempotent (replace). Env-driven connection (.env).
Run:  python -m src.db.load_github_silver_to_postgres
"""
import glob, os
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass
import pandas as pd
from sqlalchemy import create_engine, text


def engine_from_env():
    u=os.environ.get("PGUSER","aiwork"); p=os.environ.get("PGPASSWORD","aiwork")
    h=os.environ.get("PGHOST","localhost"); pt=os.environ.get("PGPORT","5432")
    db=os.environ.get("PGDATABASE","aiwork")
    return create_engine(f"postgresql+psycopg2://{u}:{p}@{h}:{pt}/{db}")


def load_one(eng, table, path):
    if not os.path.exists(path):
        print(f"    skip {table} (no {path})"); return
    df = pd.read_csv(path)
    df.to_sql(table, eng, schema="silver", if_exists="replace", index=False)
    print(f"    loaded silver.{table}: {len(df):,} rows  <- {path}")


def load_pooled(eng, table, glob_pat):
    paths = sorted(glob.glob(glob_pat))
    if not paths:
        print(f"    skip {table} (no files at {glob_pat})"); return
    df = pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
    df.to_sql(table, eng, schema="silver", if_exists="replace", index=False)
    print(f"    loaded silver.{table}: {len(df):,} rows  <- {len(paths)} day-folders")


def main():
    eng = engine_from_env()
    with eng.begin() as c:
        c.execute(text("CREATE SCHEMA IF NOT EXISTS silver"))
    load_one(eng, "gh_matches", "data/silver/gharchive/matches.csv")
    load_one(eng, "gh_totals",  "data/silver/gharchive/totals.csv")
    load_pooled(eng, "gh_pr_outcomes", "data/silver/gharchive_day_*/pr_outcomes.csv")
    load_pooled(eng, "gh_pr_reviews",  "data/silver/gharchive_day_*/pr_reviews.csv")
    load_one(eng, "gh_churn_events", "data/silver/churn/churn_events.csv")
    print("\nGitHub silver -> Postgres done")


if __name__ == "__main__":
    main()