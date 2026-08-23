# AI × Work — Data Engineering Capstone

How is AI reshaping **code** and the **German job market**? This project builds a
full **bronze → silver → gold** data pipeline over two pillars, **lifted to the
cloud** and served through an interactive public dashboard.

**🔗 Live dashboard:** `https://<your-app>.streamlit.app`
*neuefische / SPICED Data-Engineering bootcamp.*

---

## The two questions

**Jobs pillar** — how AI is affecting existing jobs:
- Do AI-*exposed* occupations rise or decline in demand over time?
- Do jobs increasingly want humans who can **use** AI (vs. **build** it)?
- Are AI-*building* roles a distinct, growing population?

**Code pillar** — how AI is entering software:
- How fast is attributable AI authorship growing in real repos?
- Are AI-authored PRs accepted less — and is that quality or process?
- Is AI-touched code reworked more (less durable) than human code?

## Headline findings (all with honest caveats — see the dashboard)

- **Code adoption**: attributable-AI commit share **0.68 % → 0.76 % → 15.62 %**
  (2023→24→25) — ~20× jump as agents went mainstream in 2025. Git-attributable
  only; undercounts silent Copilot, so it's a **floor**.
- **Jobs — using AI**: AI-usage demand emerges in 2026, concentrated in
  AI-exposed roles. Small but real.
- **Jobs — building AI**: a tech phenomenon (~40–57 % of tech roles); ~0 % in the
  general market. A clear divide.
- **PR acceptance**: agent PRs merge less at equal size — but draw no more
  change-requests → process/trust, not worse code.
- **Code durability**: AI-touched code reworked *no more* than human at equal
  size. Contradicts the "AI is sloppier" prior.

---

## Architecture — medallion on the cloud

```
        BRONZE (raw)            SILVER (clean, Python)          GOLD (aggregated, dbt/SQL)
 jobs:  job postings + Adzuna →  ESCO crosswalk + AI-tagger  →  jobs_by_exposure_band_year …
 code:  GH Archive + git repos →  signal parse + PyDriller    →  github_adoption / merge / churn …

        ── all files live in the R2 lake ──        ── gold built by dbt in Neon ──
        Cloudflare R2 (bronze + silver)   ─loaders→   Neon Postgres (silver.* → gold.*)
                     ▲                                          │
        Airflow: @daily Adzuna pull                     Streamlit Community Cloud
        + on-demand load → dbt → test                   (public dashboard, reads gold)
```

| Layer | Tool | Why |
|---|---|---|
| Data lake | **Cloudflare R2** (S3-compatible) | bronze + silver files; free tier, zero egress |
| Warehouse | **Neon** (managed Postgres) | `silver` + `gold` schemas; serverless, autosuspend |
| Silver transform | **Python** | ESCO embedding crosswalk, AI-skill tagger, ISCO→ILO join, GH-Archive parsing, PyDriller |
| Gold transform | **dbt** (SQL models) | aggregate silver → 8 gold tables, + tests |
| Orchestration / schedule | **Airflow** (Docker) | daily Adzuna ingestion + on-demand rebuild |
| Serving | **Streamlit Community Cloud** + Plotly | public interactive dashboard |
| Portability | `LAKE_ROOT` + S3 endpoint | point the lake at R2 / S3 / MinIO — no code change |

**Design split (important):** *silver creation is Python, gold is SQL/dbt.*
Silver is procedural (ML embeddings, regex tagging, GH-Archive parsing, git
history) — SQL can't express it. Gold is set-based aggregation — dbt's home turf.
Heavy silver steps run **on the host**; Airflow orchestrates the light warehouse
flow and the daily live ingestion.

**Cost:** R2 (10 GB free, zero egress) + Neon (free) + Streamlit Community Cloud =
**~$0/month at this scale.**

---

## Live scheduled ingestion

Two Airflow DAGs:

- **`aiwork_adzuna_daily`** (`@daily`) — pulls fresh German job postings across
  several categories from the **Adzuna API** and lands them in the R2 lake
  (`bronze/adzuna/dt=<date>/` + enriched `silver/adzuna/dt=<date>/`). The
  pipeline's live data-collection engine; the lake accumulates a new dated
  partition every day.
- **`aiwork_pipeline`** (on-demand) — loads both pillars' silver from R2 into
  Neon, then `dbt run` + `dbt test` rebuilds and validates gold.

> Airflow runs locally in Docker, so scheduled runs fire while the machine is up;
> in production it would deploy to managed Airflow (MWAA / Composer) — the DAGs
> are unchanged.

---

## Dashboard highlights

Tabs: **Adoption · Jobs · Acceptance · Durability · Synthesis · Architecture.**
- **Jobs** opens with an **ILO-style AI-exposure snapshot** — every occupation
  posted in a chosen year, plotted by mean exposure score × task variability,
  coloured by exposure gradient, sized by number of postings (year slider).
- **Architecture** renders the cloud pipeline diagram, the stack, per-pillar data
  lineage, and a **live Adzuna panel** reading the latest R2 partition.
- Every chart carries a *What / Why / Honest-limitation* note.

---

## Quickstart (local dev against the cloud)

```bash
# 0. deps + env
pip install -r requirements.txt
cp env.example .env      # then fill in: Neon (PG*), R2 (AWS_*/endpoint), Adzuna keys, LAKE_ROOT

# 1. export .env into the shell (dbt & Airflow read the shell, not .env)
set -a; source .env; set +a

# 2. (host, occasional) create silver — heavy ML/parsing → writes to the R2 lake
python -m src.ingestion.kaggle_jobs
python -m src.ingestion.tech_jobs
#   + github silver: gharchive_signals / gharchive_pr_signals / churn_signals

# 3. load silver (from R2) + build gold (in Neon)
python -m src.db.load_silver_to_postgres
python -m src.db.load_github_silver_to_postgres
cd dbt && dbt run --profiles-dir . && dbt test --profiles-dir . && cd ..

# 4. dashboard
streamlit run app.py     # http://localhost:8501
```

Airflow stack (for the scheduled Adzuna DAG): `docker compose up -d --build`,
then trigger `aiwork_adzuna_daily` at http://localhost:8080.

### `.env` keys
```
PGHOST / PGPORT / PGDATABASE / PGUSER / PGPASSWORD / PGSSLMODE=require   # Neon
LAKE_ROOT=s3://<bucket>                                                  # R2 lake root
AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_DEFAULT_REGION=auto       # R2 creds
S3_ENDPOINT_URL=https://<acct>.r2.cloudflarestorage.com                  # R2 endpoint (config.py)
AWS_ENDPOINT_URL_S3=https://<acct>.r2.cloudflarestorage.com              # R2 endpoint (pandas/s3fs)
ADZUNA_APP_ID / ADZUNA_APP_KEY                                           # Adzuna API
GOLD_BACKEND=postgres
```
`.env` is gitignored — never commit it. R2 values go in the `AWS_*` variable
names (S3-compatible convention); `S3_ENDPOINT_URL` routes them to Cloudflare.

### Deploy (Streamlit Community Cloud)
Push to a public repo → share.streamlit.io → pick `app.py` → add the same keys
under **Secrets** (top-level, TOML). Add `.streamlit/config.toml` (dark theme) to
the repo so the deployed app renders dark.

---

## Repo layout
```
src/common/config.py     LAKE_ROOT + S3 endpoint (local ⇄ R2/S3/MinIO)
src/ingestion/           bronze → silver (kaggle_jobs, tech_jobs, adzuna)
src/transform/           ESCO crosswalk, AI-skill tagger, GH signal parsers, churn
src/db/                  silver → Neon loaders (COPY, read from R2)
dbt/                     gold as SQL models + tests (both pillars)
airflow/dags/            aiwork_pipeline (rebuild) + aiwork_adzuna_daily (scheduled)
airflow/Dockerfile       dbt + s3fs/requests baked into the image
app.py                   Streamlit dashboard
.streamlit/config.toml   dark theme
docker-compose.yml       Airflow stack
docs/                    pipeline_reference_cloud.md, week notes
```

## Honest limitations
Git-attributable AI only (undercounts silent Copilot — adoption is a floor); PR
quality is autonomous-agents-only and small-N; churn measures activity within a
14-day window, not proven quality; jobs AI-usage is sparse (report direction, not
precise rates); tech "usage" is ~0 by artifact (tagged from a structured skills
field). Adzuna returns short descriptions (thin AI-skill signal) and no salary in
some categories. Airflow runs locally, so daily scheduling fires while the machine
is up. Trends across sources are **parallel**, not fitted correlations.

---

## Command reference (cloud)

```bash
# always export env first (dbt & Airflow read the shell)
set -a; source .env; set +a

# --- lake (R2) sanity ---
python -c "import os,s3fs; r=os.environ['LAKE_ROOT'][5:]; \
  fs=s3fs.S3FileSystem(client_kwargs={'endpoint_url':os.environ['S3_ENDPOINT_URL']}); \
  print(fs.ls(r))"

# --- verify gold + silver in Neon ---
python -c "import os; from dotenv import load_dotenv; load_dotenv(); \
  from sqlalchemy import create_engine, text; import pandas as pd; \
  e=create_engine(f\"postgresql+psycopg2://{os.environ['PGUSER']}:{os.environ['PGPASSWORD']}@{os.environ['PGHOST']}:5432/{os.environ['PGDATABASE']}?sslmode=require\"); \
  print(pd.read_sql('select schemaname,relname,n_live_tup from pg_stat_user_tables where schemaname in (\'silver\',\'gold\') order by 1,2', e))"

# --- Adzuna daily DAG ---
docker compose exec airflow-scheduler airflow dags unpause aiwork_adzuna_daily
docker compose exec airflow-scheduler airflow dags trigger aiwork_adzuna_daily
docker compose exec airflow-scheduler airflow dags list-runs -d aiwork_adzuna_daily

# --- rebuild DAG (load silver → dbt) ---
docker compose exec airflow-scheduler airflow dags trigger aiwork_pipeline

# --- dashboard ---
streamlit run app.py
```
