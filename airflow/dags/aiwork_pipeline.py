"""
Airflow DAG: AI x Work pipeline (orchestration layer).

Flow:
  load_jobs_silver ─┐
                    ├─► dbt_run ─► dbt_test
  load_gh_silver   ─┘

Loads both pillars' silver into Postgres, then dbt builds ALL gold tables
(jobs + github) as SQL models and tests them. Gold lives in Postgres, produced
by dbt — there is no separate gold-CSV load step.

SILVER CREATION RUNS ON THE HOST (heavy, on purpose):
  - jobs:   ESCO crosswalk uses a ~1GB embedding model (sentence-transformers)
  - github: GH Archive parsing + PyDriller repo clones
Refresh silver on the host, then this DAG loads it and rebuilds gold:
    python -m src.ingestion.kaggle_jobs
    python -m src.ingestion.tech_jobs
    # (+ the github silver scripts: gharchive_signals / pr_signals / churn_signals)
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT = "/opt/airflow/project"
ENV = "PGHOST=postgres PGPORT=5432 PGDATABASE=aiwork PGUSER=aiwork PGPASSWORD=aiwork "

default_args = {"owner": "aiwork", "retries": 1, "retry_delay": timedelta(minutes=2)}

with DAG(
    dag_id="aiwork_pipeline",
    description="load jobs+github silver -> dbt run/test (gold built by dbt)",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule=None,          # static snapshot data: manual/on-demand, not scheduled
    catchup=False,
    tags=["capstone", "medallion"],
) as dag:

    load_jobs_silver = BashOperator(
        task_id="load_jobs_silver",
        bash_command=f"cd {PROJECT} && {ENV} python -m src.db.load_silver_to_postgres",
    )
    load_gh_silver = BashOperator(
        task_id="load_gh_silver",
        bash_command=f"cd {PROJECT} && {ENV} python -m src.db.load_github_silver_to_postgres",
    )
    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=f"cd {PROJECT}/dbt && {ENV} dbt run --profiles-dir .",
    )
    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"cd {PROJECT}/dbt && {ENV} dbt test --profiles-dir .",
    )

    [load_jobs_silver, load_gh_silver] >> dbt_run >> dbt_test