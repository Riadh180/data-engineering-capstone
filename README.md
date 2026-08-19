# AI × Work — Data Engineering Capstone

How is AI reshaping **code** and the **German job market**? This project builds a
full **bronze → silver → gold** data pipeline over two pillars and serves the
findings through an interactive dashboard.

*neuefische / SPICED Data-Engineering bootcamp — Ginger-Graphs cohort.*

---

## The two questions

**Jobs pillar** — how AI is affecting existing jobs:
- Do AI-*exposed* occupations rise or decline in demand over time?
- Do jobs increasingly want humans who can **use** AI? (vs. **build** it)
- Are AI-*building* roles a distinct, growing population?

**Code pillar** — how AI is entering software:
- How fast is attributable AI authorship growing in real repos?
- Are AI-authored PRs accepted less — and is that quality or process?
- Is AI-touched code reworked more (less durable) than human code?

## Headline findings (all with honest caveats — see the dashboard)

- **Code adoption**: attributable-AI commit share ~20× 2024→2025 (agents went
  mainstream in 2025). Git-attributable only — undercounts silent Copilot.
- **Jobs — using AI**: ~0.6% of general German ads ask for AI-usage skills,
  emerging in 2026, concentrated in AI-exposed roles. Small but real.
- **Jobs — building AI**: ~43% of *tech* roles; ~0% general. A clear divide.
- **PR acceptance**: agent PRs merge ~10 pts less at equal size — but draw no
  more change-requests → process/trust, not worse code.
- **Code durability**: AI-touched code reworked *no more* than human at equal
  size. Contradicts the "AI is sloppier" prior.

---

## Architecture (medallion + modern stack)

```
          BRONZE (raw)         SILVER (clean, Python)      GOLD (aggregated, dbt/SQL)
 jobs:  Kaggle CSVs      →  ESCO crosswalk + AI tagger  →  jobs_by_exposure_band_year
 code:  GH Archive, repos →  signal parse + PyDriller    →  github_adoption / merge / churn ...
                                     │                              │
                                     ▼                              ▼
                              Postgres  silver.*   ──dbt run──►  Postgres  gold.*
                                     │                              │
                              Airflow orchestrates          Streamlit dashboard
                              (silver load → dbt → test)     (reads gold from Postgres)
```

| Layer | Tool | Why |
|---|---|---|
| Storage / warehouse | **Postgres** (Docker) | `silver` + `gold` schemas |
| Transformation | **dbt** (SQL models) | both pillars' gold as tested SQL |
| Governance | **dbt tests** | not_null / accepted_values, etc. |
| Orchestration | **Airflow** (Docker) | load silver → dbt run → dbt test |
| Serving | **Streamlit + Plotly** | interactive charts, reads Postgres |
| Containerization | **Docker Compose** | Postgres + Airflow in one stack |

**Design split (important):** *silver creation is Python, gold is SQL/dbt.*
Silver is procedural (ML embeddings for the ESCO crosswalk, regex AI-tagging,
GH Archive parsing, git history) — SQL can't express it. Gold is set-based
aggregation — dbt's home turf. Heavy silver steps run **on the host**; Airflow
orchestrates the light warehouse flow.

---

## Quickstart

```bash
# 0. deps + env
pip install -r requirements.txt
cp env.example .env            # dev defaults; sets GOLD_BACKEND=postgres

# 1. warehouse + orchestrator (needs Docker Desktop running)
docker compose up -d --build   # Postgres + Airflow (first build ~2 min)

# 2. (host, occasional) create silver — heavy ML/parsing
python -m src.ingestion.kaggle_jobs
python -m src.ingestion.tech_jobs
#   + the github silver scripts (gharchive_signals / pr_signals / churn_signals)

# 3. load silver + build gold (either via Airflow or by hand)
python -m src.db.load_silver_to_postgres
python -m src.db.load_github_silver_to_postgres
cd dbt && dbt run --profiles-dir . && dbt test --profiles-dir . && cd ..

# 4. dashboard
streamlit run app.py           # http://localhost:8501
```

Airflow UI: http://localhost:8080 (admin/admin) — trigger `aiwork_pipeline`.

## Repo layout
```
src/ingestion/     bronze → silver (Python: crosswalk, tagging)
src/transform/     ESCO crosswalk, AI-skill tagger, GH signal parsers
src/db/            silver → Postgres loaders
dbt/               gold as SQL models + tests (both pillars)
airflow/           DAG + Dockerfile (dbt baked in)
app.py             Streamlit dashboard
docker-compose.yml Postgres + Airflow
docs/              pipeline_reference.md, silver_schema.md, week notes
```

## Honest limitations
Git-attributable AI only (undercounts silent Copilot); PR quality is
autonomous-agents-only and small-N; churn measures activity not proven quality;
jobs AI-usage is sparse (report direction, not precise rates); tech "usage" is
0 by artifact (tagged from a structured skills field). Data is a fixed snapshot,
so the pipeline is on-demand (`schedule=None`), not live-scheduled.

---

## Command reference

All commands run from the project root unless noted.

### Setup
```bash
pip install -r requirements.txt        # install deps
cp env.example .env                    # create env (GOLD_BACKEND=postgres, PG* creds)
cat .env                               # verify contents
```

### Docker stack (Postgres + Airflow)
```bash
open -a Docker                         # macOS: start Docker Desktop, wait until ready
docker compose up -d --build           # build + start all services (first build ~2 min)
docker compose ps                      # all services "Up" (postgres, airflow-web, -scheduler)
docker compose logs -f airflow-init    # watch first-time init (ends "User admin created")
docker compose down                    # stop everything (keeps data volume)
docker compose down -v                 # stop + wipe the pg volume (fresh start)
docker compose restart airflow-scheduler   # reload after changing a DAG
```

### Create silver (host — heavy ML/parsing, run when data changes)
```bash
python -m src.ingestion.kaggle_jobs    # general jobs → silver
python -m src.ingestion.tech_jobs      # tech jobs → silver
# (+ github silver: gharchive_signals / gharchive_pr_signals / churn_signals)
```

### Load silver into Postgres
```bash
python -m src.db.load_silver_to_postgres          # jobs silver → silver.*
python -m src.db.load_github_silver_to_postgres   # github silver → silver.*
```

### Build + test gold with dbt
```bash
cd dbt
dbt debug   --profiles-dir .           # check project + DB connection
dbt run     --profiles-dir .           # build all 8 gold tables (both pillars)
dbt test    --profiles-dir .           # run data tests
dbt docs generate --profiles-dir .     # build lineage/docs
dbt docs serve    --profiles-dir .     # view the DAG in a browser
cd ..
```

### Run the pipeline via Airflow
```bash
# UI: http://localhost:8080  (admin / admin) → enable + trigger "aiwork_pipeline"

# CLI:
docker exec aiwork_airflow_scheduler airflow dags list | grep aiwork
docker exec aiwork_airflow_scheduler airflow dags trigger aiwork_pipeline
docker exec aiwork_airflow_scheduler airflow dags list-runs -d aiwork_pipeline      # state: success
docker exec aiwork_airflow_scheduler airflow tasks states-for-dag-run aiwork_pipeline <run_id>
docker exec aiwork_airflow_scheduler airflow tasks test aiwork_pipeline dbt_run 2026-08-19   # test one task
docker exec aiwork_airflow_scheduler which dbt                                      # confirm dbt in image
```

### Inspect the warehouse
```bash
# schemas + tables
docker exec -it aiwork_postgres psql -U aiwork -d aiwork -c "\dn"          # schemas
docker exec -it aiwork_postgres psql -U aiwork -d aiwork -c "\dt silver.*" # silver tables
docker exec -it aiwork_postgres psql -U aiwork -d aiwork -c "\dt gold.*"   # gold tables (8)

# spot-check key results
docker exec -it aiwork_postgres psql -U aiwork -d aiwork -c "select * from gold.github_adoption_by_year;"
docker exec -it aiwork_postgres psql -U aiwork -d aiwork -c "select * from gold.jobs_by_exposure_band_year limit 10;"
docker exec -it aiwork_postgres psql -U aiwork -d aiwork -c "select * from gold.github_merge_rate;"

# interactive shell
docker exec -it aiwork_postgres psql -U aiwork -d aiwork   # then \dt gold.*  /  select ...  /  \q
```

### Run the dashboard
```bash
streamlit run app.py                   # http://localhost:8501 (reads Postgres via .env)

# confirm it's reading Postgres, not CSVs:
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.environ.get('GOLD_BACKEND'))"
# → postgres
```

### Verify the whole thing (end-to-end checklist)
```bash
docker compose ps                                              # 1. services up
docker exec aiwork_airflow_scheduler airflow dags trigger aiwork_pipeline   # 2. run DAG
docker exec aiwork_airflow_scheduler airflow dags list-runs -d aiwork_pipeline   #    → success
docker exec -it aiwork_postgres psql -U aiwork -d aiwork -c "\dt gold.*"    # 3. 8 gold tables
docker exec -it aiwork_postgres psql -U aiwork -d aiwork -c "select * from gold.github_adoption_by_year;"  # 4. 20× jump
streamlit run app.py                                          # 5. all charts render
```

### Data-quality audits (silver)
```bash
python check_silver.py                 # jobs silver invariants
python check_gharchive_silver.py       # github silver invariants (dedup, num≤denom, enums)
```

### Git hygiene
```bash
git status                             # what's staged
git rm -r --cached data/bronze data/silver   # untrack large/regenerable data (keep on disk)
```
