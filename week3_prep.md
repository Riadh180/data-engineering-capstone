# Week 3 Prep — Warehouse, Transformation, Orchestration

Where the project stands going into week 3, and what to be ready to explain.

## What's built and working (verified end-to-end)

The full local stack runs: a triggered Airflow DAG loads both pillars' silver
into Postgres, dbt builds all 8 gold tables as SQL (and tests them), and the
Streamlit dashboard reads gold from Postgres. One `docker compose up -d --build`
brings up Postgres + Airflow; one DAG run rebuilds everything.

| Layer | Tool | State |
|---|---|---|
| Storage | Postgres (`silver` + `gold` schemas) | ✅ |
| Transformation | dbt — 8 SQL models, both pillars | ✅ |
| Governance | dbt tests (not_null, accepted_values) | ✅ |
| Orchestration | Airflow DAG (green run) | ✅ |
| Serving | Streamlit + Plotly (reads Postgres) | ✅ |
| Containerization | Docker Compose (+ custom Airflow image) | ✅ |

## The key architecture decision to defend

**Silver = Python (on host). Gold = dbt/SQL.**

- Silver creation is *procedural*: the ESCO crosswalk runs a multilingual
  embedding model (sentence-transformers) to match job titles by meaning; the
  AI-skill tagger is regex/keyword logic; GitHub silver parses GH Archive JSON
  and walks git history (PyDriller). None of that is expressible in SQL.
- Gold is *set-based* aggregation (group / join / filter) — exactly what dbt is
  for. Both pillars' gold are now uniform dbt SQL models with tests.
- Heavy silver steps (≈1 GB embedding model, repo clones) run **on the host**,
  not inside the Airflow worker. Airflow orchestrates the light warehouse flow
  (load silver → dbt run → dbt test). In production the heavy steps would run in
  a dedicated worker container (DockerOperator / KubernetesPodOperator) still
  triggered by Airflow — the host split is the local-first simplification.

## dbt specifics

- `dbt/models/gold/` — 8 models: 2 jobs (`jobs_by_exposure_band_year`,
  `jobs_by_occupation`) + 6 github (adoption year/month, merge_rate,
  changes_requested, churn_by_bucket, ai_share_by_repo).
- Sources = the `silver.*` tables the loaders populate.
- Verified: dbt SQL output matches the original Python gold exactly (e.g. the
  code-adoption 20× jump: 0.0068 → 0.0076 → 0.1562).
- Tests run with `dbt test`; lineage/docs available via `dbt docs generate`.

## Scheduling — an honest note

The data is a fixed historical snapshot (a Kaggle CSV, specific GH Archive days),
so nothing new arrives. The DAG uses `schedule=None` (on-demand), and Airflow's
value here is **orchestration + reproducibility**, not live scheduling. Real
scheduling would require a live source (e.g. GH Archive's hourly feed or a live
jobs API) — noted as future work rather than overclaimed.

## To be ready to explain

- Why silver is Python and gold is SQL (nature of the work, above).
- Why ingestion runs on the host, not in Airflow (heavy ML deps).
- The `GOLD_BACKEND` switch: the dashboard reads CSVs or Postgres via one env
  var, so the serving layer demos with or without the DB and the cloud lift is
  trivial.
- The medallion split and where each rubric box is satisfied.

## Next (cloud lift — parked)

1. **MinIO** (local S3) — bronze/silver/gold in object storage; prove the
   `s3://` code path locally.
2. **AWS S3** — swap MinIO → real S3 (same code, different endpoint).
3. **AWS RDS** — lift Postgres → managed cloud (change the connection string).
