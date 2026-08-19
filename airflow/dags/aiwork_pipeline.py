"""
Airflow DAG: AI x Work pipeline (orchestration layer).

Flow (the warehouse/transform pipeline, which is light and reliable in-container):
  load_silver ─► dbt_run ─► dbt_test ─► load_gold

INGESTION IS A HOST STEP, ON PURPOSE.
The ingesters load a multilingual embedding model (sentence-transformers/torch,
~1GB) for the ESCO crosswalk — heavy, GPU-friendly, and slow to pull inside an
Airflow worker. Standard practice is to keep such ML-heavy extraction out of the
orchestrator. Run ingestion on the host (or a dedicated worker) to refresh silver:

    python -m src.ingestion.kaggle_jobs
    python -m src.ingestion.tech_jobs

Then this DAG loads silver -> Postgres, rebuilds gold via dbt (with tests), and
publishes gold. Each task shells out to the existing, tested code.
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT = "/opt/airflow/project"
ENV = "PGHOST=postgres PGPORT=5432 PGDATABASE=aiwork PGUSER=aiwork PGPASSWORD=aiwork "

default_args = {"owner": "aiwork", "retries": 1, "retry_delay": timedelta(minutes=2)}

with DAG(
    dag_id="aiwork_pipeline",
    description="load silver -> dbt run/test -> load gold (ingestion runs on host)",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule="@weekly",
    catchup=False,
    tags=["capstone", "medallion"],
) as dag:

    load_silver = BashOperator(
        task_id="load_silver",
        bash_command=f"cd {PROJECT} && {ENV} python -m src.db.load_silver_to_postgres",
    )
    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=f"cd {PROJECT}/dbt && {ENV} dbt run --profiles-dir .",
    )
    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"cd {PROJECT}/dbt && {ENV} dbt test --profiles-dir .",
    )
    load_gold = BashOperator(
        task_id="load_gold",
        bash_command=f"cd {PROJECT} && {ENV} python -m src.db.load_gold_to_postgres",
    )

    load_silver >> dbt_run >> dbt_test >> load_gold