# Week: Serving Layer — Postgres warehouse + interactive dashboard

## Goal
Move the gold layer from flat CSVs into a real **Postgres warehouse**, and serve
the four findings through an interactive **Streamlit + Plotly** dashboard. This is
the "Serving" box of the data-engineering pipeline (Source → Storage →
Transformation → Orchestration → **Serving** → Governance).

## What was built

### 1. Postgres serving warehouse (local, Docker)
- `docker-compose.yml` runs Postgres 16 with a named volume (data persists).
- `src/db/load_gold_to_postgres.py` loads each gold CSV into schema `gold`
  (one table per finding), idempotent (`if_exists="replace"`).
- Connection is env-driven (`PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD`), read
  from `.env` automatically.

### 2. Dashboard reads from the warehouse
- `app.py` has a single data boundary: `load_gold()`.
- `GOLD_BACKEND=postgres` -> reads `gold.*` via `read_sql`; otherwise reads CSVs.
- Swapping backends changes nothing else in the app — the design point of the
  medallion serving layer.

### 3. Auto-config
- `python-dotenv` loads `.env`, so `streamlit run app.py` picks up the backend
  and DB credentials without setting them on the command line.

## How to run (local-first)
```bash
# 0. deps
pip install -r requirements.txt

# 1. start the warehouse (needs Docker Desktop running)
open -a Docker            # macOS: launch Docker Desktop, wait for it to be ready
docker compose up -d postgres

# 2. load gold into Postgres
python -m src.db.load_gold_to_postgres

# 3. run the dashboard (reads Postgres because .env sets GOLD_BACKEND=postgres)
streamlit run app.py
```

Verify the tables:
```bash
docker exec -it aiwork_postgres psql -U aiwork -d aiwork -c "\dt gold.*"
```

## Design decisions
- **Local-first, then lift to cloud.** Debug free and offline; "move to AWS RDS"
  later becomes a connection-string change, not a rebuild.
- **Streamlit over a BI tool.** The project needs custom, cross-pillar charts
  (usage/building split, exposure trends, the synthesis view) and inline caveats
  that a point-and-click BI tool fights. Streamlit reads the warehouse directly
  and stays in the Python stack the pipeline already uses.
- **Env-driven backend.** One flag (`GOLD_BACKEND`) switches CSV ↔ Postgres, so
  the dashboard demos with or without the DB and the cloud lift is trivial.

## Honest limitations / notes
- Postgres runs locally in Docker; not yet cloud-hosted (next: AWS RDS).
- Gold is still *loaded* from CSVs; the aggregations are not yet dbt SQL models
  (next step: dbt turns the Python group-bys into tested SQL models).
- Credentials in `.env` are dev defaults (`aiwork/aiwork`) — replace for anything
  shared; `.env` is gitignored.

## Next steps (productionize ladder)
1. **dbt** — gold marts as SQL models + tests + docs (Transformation + Governance).
2. **Airflow** — DAG runs ingest → silver → gold → load on a schedule (Orchestration).
3. **S3/MinIO** — bronze/silver in object storage (Storage).
4. **AWS** — lift Postgres → RDS, object store → S3, app → ECS/Fargate.
