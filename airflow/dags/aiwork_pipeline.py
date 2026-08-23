"""
Airflow DAG: AI x Work pipeline (orchestration layer).

Flow:
  load_jobs_silver ─┐
                    ├─► dbt_run ─► dbt_test
  load_gh_silver   ─┘

Loads both pillars' silver into Postgres (Neon), then dbt builds ALL gold tables
(jobs + github) as SQL models and tests them. Gold lives in Postgres, produced
by dbt — there is no separate gold-CSV load step.

Secrets are NOT hardcoded here (this file is committed). Each task sources the
project's .env at runtime (mounted, gitignored) so it picks up the cloud
credentials: Neon (PG*), Cloudflare R2 (AWS_*/S3_ENDPOINT_URL), LAKE_ROOT.

SILVER CREATION RUNS ON THE HOST (heavy, on purpose):
  - jobs:   ESCO crosswalk uses a ~1GB embedding model (sentence-transformers)
  - github: GH Archive parsing + PyDriller repo clones
Refresh silver on the host, then this DAG loads it (from the R2 lake) and
rebuilds gold. This DAG is on-demand (schedule=None); the live daily Adzuna
pull is a separate scheduled DAG (aiwork_adzuna_daily).
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT = "/opt/airflow/project"
# source .env into the shell so PG*, AWS_*, S3_ENDPOINT_URL, LAKE_ROOT are set
ENVSRC = f"set -a && . {PROJECT}/.env && set +a && "

default_args = {"owner": "aiwork", "retries": 1, "retry_delay": timedelta(minutes=2)}

with DAG(
    dag_id="aiwork_pipeline",
    description="load jobs+github silver (from R2) -> dbt run/test (gold built by dbt)",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule=None,          # on-demand full rebuild; daily Adzuna is a separate DAG
    catchup=False,
    tags=["capstone", "medallion"],
) as dag:

    load_jobs_silver = BashOperator(
        task_id="load_jobs_silver",
        bash_command=f"cd {PROJECT} && {ENVSRC} python -m src.db.load_silver_to_postgres",
    )
    load_gh_silver = BashOperator(
        task_id="load_gh_silver",
        bash_command=f"cd {PROJECT} && {ENVSRC} python -m src.db.load_github_silver_to_postgres",
    )
    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=f"cd {PROJECT}/dbt && {ENVSRC} dbt run --profiles-dir .",
    )
    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"cd {PROJECT}/dbt && {ENVSRC} dbt test --profiles-dir .",
    )

    [load_jobs_silver, load_gh_silver] >> dbt_run >> dbt_test