#!/usr/bin/env python3
"""
Load the latest silver partitions into Postgres schema `silver` (dbt sources).

  silver.jobs_kaggle   <- <LAKE>/silver/kaggle/dt=*/de_jobs.csv       (general)
  silver.jobs_tech     <- <LAKE>/silver/tech/dt=*/de_tech_jobs.csv    (tech)

Silver is read from LAKE_ROOT (local data/ or s3://bucket). Idempotent (replace).
Bulk-loads via Postgres COPY (fast against remote/Neon).

Run:  python -m src.db.load_silver_to_postgres
"""
import io, os
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass
import pandas as pd
from sqlalchemy import create_engine, text

from src.common.config import lake_path, lake_glob   # imported AFTER load_dotenv

SILVER = {
    "jobs_kaggle": lake_path("silver/kaggle"),
    "jobs_tech": lake_path("silver/tech"),
}


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


def latest(base):
    """Newest dt= partition's first CSV, from local or S3. Globs real files so
    it doesn't depend on S3 pseudo-directory listing."""
    hits = lake_glob(f"{base}/dt=*/*.csv")
    if not hits:
        return None
    latest_dt = max(h.split("/dt=")[1].split("/")[0] for h in hits)
    inpart = sorted(h for h in hits if f"/dt={latest_dt}/" in h)
    return inpart[0] if inpart else None


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


def main():
    eng = engine_from_env()
    with eng.begin() as c:
        c.execute(text("CREATE SCHEMA IF NOT EXISTS silver"))
    for table, base in SILVER.items():
        p = latest(base)
        if not p:
            print(f"    skip {table} (no silver in {base})"); continue
        df = pd.read_csv(p, dtype={"isco08_4digit": str})   # s3:// ok via s3fs
        _copy_into(eng, table, df)
        print(f"    loaded silver.{table}: {len(df):,} rows  <- {p}")
    print("\nsilver -> Postgres done")


if __name__ == "__main__":
    main()