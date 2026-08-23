"""
Airflow DAG: daily Adzuna ingestion (live scheduled data collection).

    adzuna_ingest  (@daily)

Pulls fresh German job postings from the Adzuna API and lands them in the R2
lake (bronze raw JSON + enriched silver), one dated partition per run. This is
the pipeline's live, scheduled data-collection engine: each day adds a new
dt=<date> partition, so the lake accumulates real job-market data over time.

Lightweight on purpose: the Adzuna transform uses the keyword crosswalk
(map_title_to_isco) + regex AI-skill tagger — no embedding model — so it runs
inside the Airflow container.

Secrets (ADZUNA_APP_ID/KEY, AWS_*/S3_ENDPOINT_URL, LAKE_ROOT) are sourced from
the mounted .env at runtime, not hardcoded. Without API keys it falls back to a
bundled sample so the DAG still succeeds.
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT = "/opt/airflow/project"
ENVSRC = f"set -a && . {PROJECT}/.env && set +a && "

default_args = {"owner": "aiwork", "retries": 1, "retry_delay": timedelta(minutes=5)}

with DAG(
    dag_id="aiwork_adzuna_daily",
    description="daily Adzuna API pull -> R2 lake (bronze + silver)",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule="@daily",       # live scheduled ingestion
    catchup=False,           # don't backfill missed days
    max_active_runs=1,
    tags=["capstone", "ingestion", "scheduled"],
) as dag:

    adzuna_ingest = BashOperator(
        task_id="adzuna_ingest",
        bash_command=f"cd {PROJECT} && {ENVSRC} python -m src.ingestion.adzuna "
                     "it-jobs engineering-jobs scientific-jobs "
                     "accounting-finance-jobs admin-jobs healthcare-nursing-jobs",
    )
