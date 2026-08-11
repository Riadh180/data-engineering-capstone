# AI & the Software Job Market — Data Engineering Capstone

A data pipeline that measures how AI is reshaping software work, by joining two live
sources on a shared timeline: **what employers demand** (job postings) and **what is
happening in real code** (public GitHub activity). The exposure lens comes from
research data keyed to the international occupation standard.

> **Scope note:** the deliverable is the *pipeline*. Dashboards, extra sources, and
> modelling are extensions. The findings are framed as **trends and correlations,
> honestly caveated — not proof of causation.**

---

## The question

Is AI **substituting** software workers (demand for exposed roles falls) or
**augmenting** them (demand rises)? The pipeline surfaces directional evidence by
tracking, over time:

- **Labour side (strong data):** the share of postings demanding AI skills, the
  salary premium those postings carry, and demand by AI-exposure band.
- **Code side (supporting signal, honestly limited):** the *visible* footprint of
  AI authorship in commits and pull requests — a floor, since invisible IDE
  autocomplete leaves no trace.

---

## Data sources

| # | Source | Role | Type | Join key | Stage | Status |
|---|--------|------|------|----------|-------|--------|
| 1 | **Adzuna API** | job postings, AI-skill demand, salary | REST/JSON (free) | title → ISCO | Core | ✅ verified |
| 2 | **GH Archive** | AI-authorship signals in code | hourly JSON event log | — | Core | ✅ verified |
| 3 | **ILO WP140 exposure** | AI-exposure score per occupation | static CSV | ISCO-08 | Core | ✅ built |
| 4 | Adzuna `/history` | recent salary trend by category | REST/JSON | category → ISCO | Backdrop | ✅ verified (~24 mo only) |
| 5 | **Eurostat** | pre-AI employment history (2011+) | API | ISCO-08 / NACE | Backdrop | ✅ verified |
| 6 | Destatis / BA | German labour backdrop | API | ISCO / KldB | Backdrop | ✅ verified |
| 7 | ESCO | multilingual title → ISCO (semantic crosswalk) | CSV download | ISCO-08 | Stretch | ✅ verified |
| 8 | Anthropic Economic Index | time-varying AI-usage lens | CSV | O*NET/ISCO | Optional | noted |

**MVP uses sources 1–3 only.** 4–6 are the historical/backdrop tier; Eurostat (not
Adzuna) is the real pre-AI demand anchor. 7–8 are stretch.

---

## Pipeline

Two branches, medallion layers, meeting at the serving layer on a shared timeline.

```
Adzuna API ─┐                         ┌─ bronze (raw, immutable)
            ├─ ingest ─────────────►  ├─ silver (crosswalk → ISCO, AI-skill tag)
GH Archive ─┘                         └─ gold   (star schema: fact + dims)
ILO exposure CSV ───────────────────►  joined on ISCO in silver/gold
                                        │
                                        └─► serving: demand & salary by exposure band,
                                            AI-authorship trend, and the two overlaid
```

- **bronze** — exact raw pulls, partitioned by date. Never mutated.
- **silver** — cleaned, deduplicated, crosswalked, tagged.
- **gold** — `fact_job_postings` + `dim_occupation` (with exposure) + `dim_date` / `dim_country`.

---

## Tech stack

All local and free for the MVP; each tool has a real job (no tool for its own sake).

- **Python + requests** — ingestion
- **crosswalk (rules + category fallback; ESCO semantic = stretch)** — title → ISCO-08
- **DuckDB** — warehouse (embedded, zero-cost)
- **dbt-core** — transforms, tests, lineage
- **PySpark** — the GH Archive (big-data) branch only
- **Airflow** — orchestration
- **Docker Compose** — containerisation
- **Metabase / Streamlit** — serving / dashboard

**Deliberately not used:** Kafka/streaming (postings are batch), paid cloud warehouses
(DuckDB suffices). See ADRs for the reasoning.

---

## Project structure

```
.
├── README.md
├── requirements.txt
├── .env / .env.example        # Adzuna key (real .env git-ignored)
├── docs/                      # architecture.md, runbook.md, adr/
├── src/
│   ├── ingestion/             # Adzuna pull, GH Archive reader → bronze
│   └── transform/
│       ├── crosswalk.py       # title → ISCO-08 (library)
│       └── gharchive_signals.py
├── reference/                 # static lookups (ILO exposure CSV) — committed
├── data/                      # bronze / silver / gold — git-ignored
└── tests/                     # unit tests (e.g. crosswalk assertions)
```

---

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add ADZUNA_APP_ID / ADZUNA_APP_KEY
```

## Run

```bash
export $(grep -v '^#' .env | xargs)

# Adzuna: ingest + crosswalk one or more categories
python3 -m src.ingestion.poc_ai_jobs_pipeline it-jobs accounting-finance-jobs

# GH Archive: score one hour of events for AI-authorship signals
python3 src/transform/gharchive_signals.py data/bronze/gharchive/2025-06-02-15.json
```

---

## AI-authorship signals (code side)

Detected from GH Archive events, from strongest to noisiest:

- **coauthor_ai** — `Co-authored-by:` trailer naming an AI tool (structured; strongest)
- **ai_agent** — commit/PR by a known AI agent (Devin, Copilot-swe, Cursor…), checked on
  actor *and* commit author, deduped per commit
- **selfadmit** — prose admitting AI use (trend, not exact count)
- *context only, not AI:* `coauthor_bot`, `bot_actor`, bare tool-name mentions

**Interpretation:** these are a **floor**. A low absolute rate is expected; the value is
the *trend over time* and the *composition* (e.g. agents do mostly fixes/refactors).

---

## Honest limitations

- AI-authorship signals **undercount** true AI use (invisible autocomplete).
- Live Adzuna demand accrues **forward from launch**; deep pre-AI history comes from
  Eurostat, at coarser (aggregate) granularity.
- Findings are **correlation, not causation** — controlled via exposure-band comparison
  groups, never claimed as proof over a short window.

---

## Status

- ✅ Both core sources verified on real data
- ✅ ILO exposure reference built (ISCO-08)
- ✅ Crosswalk + GH Archive signal parser working and independently audited
- ▶ Next: crosswalk on non-software categories, then requirements sign-off, then build


## Check Silver:
```bash
python3 -m src.ingestion.kaggle_jobs
python3 -m src.ingestion.tech_jobs

head -1 data/silver/kaggle/dt=*/de_jobs.csv | tr ',' '\n'
# check coverage:
python3 -c "import pandas as pd; d=pd.read_csv('data/silver/kaggle/dt=2026-08-10/de_jobs.csv'); print(round(100*(d['match_method']!='unmapped').mean()),'% mapped'); print(d['match_method'].value_counts().to_dict())"
```

---

## Tagger sanity check:

check_it.py — pulls IT/data occupations (ISCO 251/252) and shows how many have has_ai_skill=False. Purpose: confirm the tagger isn't missing AI on tech roles.

check_ai.py — lists the postings flagged has_ai_skill=True + which terms fired. Purpose: confirm the hits are real AI roles, not false positives.

agg.py — the AI-skill % by exposure band × period. Purpose: the actual finding (the High>Mid>Low gradient), in stable buckets.

check_map.py - It spot-checks whether the crosswalk assigned the right occupation. It pulls 20 random rows that matched via esco_fuzzy (the riskiest tier — fuzzy guesses, not exact) and shows each German title next to the English ISCO occupation it got mapped to.

```bash
python3 check_it.py

python3 check_ai.py

python3 agg.py

python3 check_map.py
```

It does all five checks — coverage, AI-skill rate, fuzzy spot-check, exposure-band breakdown, and top unmapped titles — for any silver file:
```bash
python3 check_silver.py data/silver/kaggle/dt=2026-08-10/de_jobs.csv normalized_title
python3 check_silver.py data/silver/tech/dt=2026-08-10/de_tech_jobs.csv title_clean
```


## Script to show all skills from the job_postings_raw.csv:

```bash
cat > find_ai_terms.py << 'EOF'
import pandas as pd, re
from collections import Counter
d = pd.read_csv('data/bronze/kaggle/job_postings_raw.csv')
text = " ".join(d['skills_extracted'].fillna('').astype(str)).lower()
# count all distinct skills (they're ; separated)
skills = Counter(s.strip() for s in text.replace('\n',';').split(';') if s.strip())
print("TOP 60 skills in the data:")
for s, n in skills.most_common(60):
    print(f"{n:>5}  {s}")
EOF
python3 find_ai_terms.py
```


## Verifying the silver layer

`check_silver.py` runs a 7-point quality report on any silver file. Run it after
every ingestion to confirm the data is trustworthy before building gold.

### Usage
```bash
python3 check_silver.py <silver.csv> [title_column]

# general dataset
python3 check_silver.py data/silver/kaggle/dt=YYYY-MM-DD/de_jobs.csv normalized_title

# tech dataset
python3 check_silver.py data/silver/tech/dt=YYYY-MM-DD/de_tech_jobs.csv title_clean
```

### What it checks
| # | Check | What it tells you |
|---|-------|-------------------|
| 1 | Coverage | % of titles mapped to ISCO, and via which tier (alias/exact = reliable, fuzzy = risky, unmapped = none) |
| 2 | AI-skill demand | the AI-skill rate and which terms fired (spot false positives) |
| 3 | Fuzzy spot-check | sample of fuzzy-matched rows to eyeball for wrong occupations |
| 4 | Exposure bands | AI-skill % by High/Mid/Low exposure — the core finding |
| 5 | Top unmapped | highest-frequency titles missing a code (what rules to add next) |
| 6 | Broken joins | rows mapped to an ISCO code absent from the ILO exposure file |
| 7 | Null audit | missing values in analysis-critical columns |

### What "good" looks like
- **Coverage** ≥ ~80%, mostly `alias`/`esco_exact` (not fuzzy).
- **AI-skill terms** are genuine AI/ML (no incidental mentions).
- **Fuzzy spot-check** rows map to sensible occupations (or the tier is empty).
- **Broken joins** and **critical nulls** are 0.
- **Unmapped** remainder is mostly non-occupations (Werkstudent, Minijob, FSJ).