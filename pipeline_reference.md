# Pipeline Reference — Raw Job Ads to Silver

An end-to-end explanation of the ingestion and crosswalk pipeline: what each
piece is, what goes in, what comes out, and why. Non-plain-English terms are
flagged the first time they appear and gathered in a glossary at the end. A
deeper-answers section follows for the parts worth understanding closely.

The overall shape follows the **medallion architecture** — a data-engineering
convention with three layers: **bronze** (raw data exactly as it arrived),
**silver** (cleaned, standardised, enriched — one row per real-world thing,
trustworthy), and **gold** (aggregated results ready for analysis or charts).
Bronze → silver is built in Python; silver → gold is built with dbt (SQL); both live in a Postgres warehouse, orchestrated by Airflow and served via Streamlit.

---

## Stage 0 — Reference data (built once, sits beside the pipeline)

These two files aren't job postings; they're the "dictionaries" the pipeline
joins against.

**`reference/ilo_ai_exposure_isco08.csv`** — the AI-exposure scores, built from
**ILO** (International Labour Organization) Working Paper 140's Annex Table A1.
427 rows, one per occupation, with columns: `isco08_4digit` (the occupation
code), `occupation_name`, `exposure_category` (the band), `exposure_order` (that
band as a sortable number, 4 down to −1), `mean_task_score` (0–1, how automatable
the occupation's tasks are on average), and `sd_task_score` (how spread out those
task scores are). This is the answer key — it says "this occupation is this
exposed to generative AI."

**ISCO-08** = International Standard Classification of Occupations, 2008 revision
— a UN/ILO system that gives every occupation a 4-digit code. It's the join key
that ties everything together: postings get an ISCO code, and the ISCO code looks
up exposure.

**`reference/esco/occupations_de.csv`** — the occupation taxonomy with German
names. **ESCO** = European Skills, Competences, Qualifications and Occupations —
an EU classification listing ~3,000 occupations, each with a `preferredLabel`,
many `altLabels` (synonyms), and an `iscoGroup` (its ISCO-08 code). It's in
German and maps to ISCO, so it's the bridge that lets a German job title find an
ISCO code. A **taxonomy** here just means a structured, official list of
categories.

## Stage 1 — Bronze (raw input)

**Files:** `data/bronze/kaggle/sample_jobs_5000.csv` (general German jobs, 5,000
rows) and `data/bronze/kaggle/job_postings_raw.csv` (tech jobs, 3,200 rows).

An input row (general) looks roughly like:

```
job_id=123, title="Verkäufer (m/w/d)", normalized_title="verkäufer",
date_published=1704067200000, company="…", city="Berlin",
description_text="Wir suchen …", has_salary_info=True
```

`date_published` is in **epoch milliseconds** — milliseconds since Jan 1 1970, a
common machine time format that must be converted to a real date. The tech file
instead has `title_clean`, `posted_date` (already a normal date),
`skills_extracted`, `description_clean`, `seniority`, `cluster_name`.

Nothing is changed at bronze — it's the untouched source.

## Stage 2 — Ingestion (the orchestration scripts)

**Files:** `src/ingestion/kaggle_jobs.py` and `src/ingestion/tech_jobs.py`. These
are the conductors; they call the transform modules and write silver. Both work
on a **DataFrame** (a pandas in-memory table — think a spreadsheet you manipulate
in code).

### 2a. `ingest()` — read and filter

**Input:** the bronze CSV.
**Does:** reads the file, converts `date_published` from epoch-ms to a real
datetime, derives a `year`, keeps only 2022+.
**Output:** a DataFrame of 4,936 rows (from 5,000) with a clean `year` column.

```python
df["date_published"] = pd.to_datetime(df["date_published"], unit="ms", errors="coerce")
df = df[df["date_published"].dt.year >= MIN_YEAR].copy()
df["year"] = df["date_published"].dt.year
```

Why: the study is about recent years, and the raw timestamp is unusable as-is.

### 2b. `transform(df, xw)` — the enrichment step

Where each posting gains its occupation and its AI flag. Two things happen.

**First, the crosswalk** — one batched call to the `EscoCrosswalk` instance
(`xw`, short for "crosswalk"):

```python
mapped = xw.map_titles(df["normalized_title"].fillna("").tolist())
df = pd.concat([df, mapped], axis=1)
```

**Input:** the list of titles (`normalized_title` for general, `title_clean` for
tech).
**Output:** new columns joined on — `isco08_4digit`, `occupation_name`,
`match_method`, `matched_label`, `match_score`, `needs_review`,
`exposure_category`, `exposure_order`, `mean_task_score`, `sd_task_score`,
`exposure_imputed`. (Internals in Stage 3.)

**Second, the AI-skill tag:**

```python
for title, desc in zip(df["title"], df["description_text"]):
    f, ts = detect_ai_skill(title, desc)
```

**Input:** title + full description. **Output:** `has_ai_skill` (True/False) and
`ai_skill_terms` (which AI terms matched). (Internals in Stage 4.)

Why here: ingestion is the single place a raw posting becomes an analysable
record — occupation attached, exposure attached, AI-demand flagged.

### 2c. `store_silver()` — select and write

**Input:** the enriched DataFrame.
**Does:** keeps a fixed column list (drops intermediate junk) and writes to a
date-partitioned path:

```
data/silver/kaggle/dt=2026-08-12/de_jobs.csv
```

The `dt=YYYY-MM-DD` folder is **Hive-style partitioning** — a convention where
the folder name encodes a column value (here, the run date), so every day's run
sits side by side and can be queried by date. **Output:** the silver CSV.

## Stage 3 — The crosswalk (`src/transform/esco_crosswalk.py`)

The core of the pipeline. A **crosswalk** is a mapping table between two
classification systems — here, free-text German job titles → ISCO-08 codes. The
class is `EscoCrosswalk`.

### Construction (`__init__`, runs once)

- `load_esco()` reads the ESCO file and explodes it into one row per *label*
  (preferred + every alt-label), each pointing at its ISCO code — 18,180 labels
  across 426 codes. `_col()` auto-detects column names so it's robust to ESCO's
  exact headers.
- `load_exposure()` reads the ILO file into a code→exposure lookup, plus 3-digit
  and 2-digit parent averages for imputation.
- `get_model()` loads the **embedding model**, and `esco_embeddings()` turns all
  18,180 labels into vectors, cached to disk (`.emb.npy`) so it only happens once.

An **embedding** is a list of numbers (a vector) representing the *meaning* of a
piece of text, produced by a neural network. Texts with similar meaning get
similar vectors. The model is **multilingual-e5** (a **sentence-transformer** — a
model specialised in turning whole phrases into meaning-vectors), chosen because
it handles German and is built for retrieval (finding the closest match).

### `normalize(title)` — cleaning before matching

**Input:** a raw title like `"Senior Data Scientist (m/w/d)"`. **Output:**
`"data scientist"`. It lowercases, strips gender markers `(m/w/d)`, strips gender
suffixes (`:in`, `/-in`), removes punctuation, and strips leading **wrapper
words** — employment-form/seniority decorations (`senior`, `ausbildung`,
`werkstudent`, `contract`, `freelance`…) that aren't the occupation. Why: so the
*occupation* is what gets matched, not the packaging. A title that's *only* a
wrapper (`allrounder`) survives normalisation but then finds no good match —
correctly ending up unmapped.

### `map_titles()` — the tiered matcher

A **tier** is an ordered strategy: try the most reliable method first, fall
through only if it misses.

- **Tier 0 — alias.** A hand-curated dict (`ALIAS`) of normalized title → ISCO
  code, for high-frequency modern roles ISCO-08 has no clean slot for
  (`data scientist`→2511, `ml engineer`→2512, `oberarzt`→2212). Checked first
  because it's authoritative. `match_method="alias"`.
- **Tier 1 — exact.** If the normalized title exactly equals an ESCO label, take
  that label's code. `match_method="esco_exact"`, score 1.0.
- **Tier 2 — semantic.** For everything left, embed the title and compute
  **cosine similarity** against all 18,180 ESCO label vectors (1.0 = same
  meaning, 0 = unrelated). Take the nearest label. If its score ≥ `ACCEPT`
  (0.88) accept; between `REVIEW_LOW` (0.85) and 0.88 accept but flag
  `needs_review`; below 0.85 → unmapped. `match_method="esco_semantic"`.
- **Guard + unmapped.** A final pass: any matched row whose ISCO code has no
  exposure anywhere in ILO (armed forces, etc.) is downgraded to unmapped rather
  than carried as a null. Anything with no acceptable match is unmapped with a
  null code.

Why the tiers: exact and alias are near-perfect but only cover titles you've
seen; semantic generalises to paraphrases; the thresholds keep the guesses honest
(a wrong-but-plausible match scores lower and gets rejected). This replaced an
earlier **fuzzy** approach (rapidfuzz — matching on shared characters/tokens,
which latched onto generic words like "mitarbeiter" and produced systematic wrong
codes).

### `attach_exposure()` — the join to ILO

**Input:** an ISCO code. **Output:** its exposure band, order, mean, sd, and
`exposure_imputed`. If the code is in ILO's 427, it uses the real values
(`exposure_imputed=False`). If not, it **imputes** — fills from the 3-digit
parent group's average, then the 2-digit parent — and marks
`exposure_imputed=True`. **Imputation** = estimating a missing value from related
data. It's rare because ILO covers 426 of ~436 codes, so almost every match hits
a real score.

## Stage 4 — AI-skill tagger (`src/transform/ai_skill_tagger.py`)

**Function:** `detect_ai_skill(text_a, text_b)`. **Input:** title + description
(general) or skills + description (tech). **Does:** scans for AI-related terms
(`machine learning`, `ki-modelle`, `chatgpt`, `deep learning`,
`prompt engineering`…). **Output:** a boolean `has_ai_skill` and the list of
matched terms. Why: this is the *demand* signal — whether a posting asks for AI
skills — which you cross against exposure. It's keyword-based, so it's a floor,
not a perfect measure (hence the general set's sparse 0.4% vs tech's dense 50.5%).

## Stage 5 — Silver output (the deliverable of this half)

**Files:** `data/silver/kaggle/dt=…/de_jobs.csv`,
`data/silver/tech/dt=…/de_tech_jobs.csv`.

One silver row now looks like:

```
job_id=123, normalized_title="verkäufer", year=2025,
isco08_4digit="5223", occupation_name="Shop Sales Assistants",
match_method="esco_semantic", match_score=0.91, needs_review=False,
exposure_category="Gradient 1", exposure_order=1,
mean_task_score=0.38, sd_task_score=0.16, exposure_imputed=False,
has_ai_skill=False, ai_skill_terms=""
```

Every posting is now one clean, occupation-coded, exposure-scored, AI-flagged
record. That's the definition of "silver."

## Stage 6 — The check (`check_silver.py`) — validation, not transformation

Doesn't change data; it audits it. Reports coverage by tier, AI-skill rate, the
exposure×AI aggregate `[4]`, top unmapped titles `[5]` (the worklist), broken
joins `[6]`, and the null audit `[7]`. Why it exists: to catch exactly the
failures we hunted down — contaminated bands, wrong-code nulls, stale files —
before they reach the result.

---

## Glossary

- **ILO / ISCO-08 / ESCO** — the labour org, its 4-digit occupation-code system,
  and the EU taxonomy that maps German titles to those codes.
- **medallion / bronze-silver-gold** — the raw → cleaned → aggregated layering.
- **DataFrame** — an in-memory table (pandas).
- **crosswalk** — a mapping between two classification systems.
- **embedding** — a numeric vector representing text meaning.
- **sentence-transformer / multilingual-e5** — the neural model that produces
  those vectors; multilingual and retrieval-tuned.
- **cosine similarity** — angle-based closeness of two vectors; 1 = same meaning.
- **normalization** — reducing text to a canonical cleaned form.
- **tier** — an ordered fallback strategy (alias → exact → semantic → unmapped).
- **alias table** — curated manual title→code mappings.
- **fuzzy matching** — the older character/token-overlap method we replaced.
- **imputation** — estimating a missing value from related data (the ISCO parent).
- **epoch milliseconds** — machine time as ms since 1970.
- **Hive-style / `dt=` partition** — encoding a column value (the date) in the
  folder name.
- **exposure gradient / band** — ILO's grouping of occupations by AI exposure
  (Gradient 4 highest → Not Exposed).

**One-line big picture:** two raw German job-posting files flow through an
ingestion script that (a) maps each title to an ISCO occupation code via a tiered
ESCO crosswalk, (b) joins that code to ILO AI-exposure scores, and (c) flags
AI-skill demand — landing one clean, coded, scored record per posting in the
silver layer, ready to aggregate into gold.

---

## Deeper answers

**What ALIAS is for.** A hand-written dictionary of normalized title → ISCO code
for titles the automatic matcher can't get right — mainly modern roles ISCO-08
(from 2008) has no clean slot for (data scientist, ML engineer) and cases where
the semantic match went wrong (oberarzt → colonel). Checked first because it's
manually verified, so it overrides the model.

**The 1.0 score in Tier 1 (exact).** It's the `match_score`, on the same 0–1
scale as cosine. An exact string match is perfect confidence by definition, so
it's hard-coded to 1.0 rather than computed — a flag meaning "no guessing
involved." (Alias rows also get 1.0 for the same reason.)

**Cosine similarity.** A number from 0 to 1 measuring how close two vectors point
in direction. Formula: dot product of the two vectors divided by their lengths —
`cos θ = (A·B)/(‖A‖‖B‖)`. 1 = same direction (same meaning), 0 = unrelated.
Because the model outputs length-1 (normalised) vectors, the division drops out
and it's just the dot product `A·B`.

**How e5 produces and compares vectors.** The model reads the text and outputs a
fixed-length list of numbers (768 of them) encoding its meaning — the embedding.
You embed the job title and all 18,180 ESCO labels the same way, then compare by
cosine: the label with the highest cosine to the title is the nearest match. In
code it's one matrix multiply, `title_vector @ all_label_vectors.T`, giving a
similarity to every label at once; `argmax` picks the winner.

**Guard + unmapped — is it "below REVIEW_LOW"?** Two separate things. (1) Below
`REVIEW_LOW` (0.85) → unmapped because the match is too weak to trust. (2) The
guard is different: a match can score *high* yet land on an ISCO code with no
exposure anywhere in ILO (armed forces, etc.) — that row is also sent to
unmapped, because a code with no score is useless even if the match was
confident. So: unmapped = low score **or** matched-to-a-scoreless-code.

**Exposure band / mean / sd / imputed, and where the parent averages come from.**
- **band** (`exposure_category`) — ILO's grouping of the occupation by AI
  exposure (Gradient 4 highest → Not Exposed).
- **mean** (`mean_task_score`) — the occupation's average task-automation score,
  0–1.
- **sd** (`sd_task_score`) — how spread out those task scores are within the
  occupation.
- **exposure_imputed** — True if the score was estimated rather than taken
  directly from ILO.
- **the 3-/2-digit parent averages** — computed from the ILO file at load time:
  group the 427 rows by the first 3 digits (and first 2 digits) of their ISCO
  code and average their `mean_task_score`. So a "295x" parent average is just the
  mean of every occupation whose code starts with those digits. When a matched
  code isn't in ILO, borrow its 3-digit family average; if that's empty too, the
  broader 2-digit average.

**What "EU taxonomy" means.** "Taxonomy" = an official, structured list of
categories. "EU taxonomy" here just means ESCO is the European Union's
standardised catalogue of occupations and skills — the authoritative list, in
multiple languages, that everything maps to.

---

## Stage 3 — Gold (aggregation, built with dbt/SQL)

Gold turns trustworthy silver rows into the aggregated tables the charts read.
**All gold is built by dbt as SQL models** (both pillars), reading from the
`silver.*` tables in Postgres and writing `gold.*` tables in Postgres.

**Why dbt/SQL here (and Python for silver):** gold is set-based aggregation —
group, join, average, bucket. That's what SQL is for, and dbt adds tests,
lineage, and docs on top. Silver, by contrast, is procedural enrichment (an
embedding model, regex tagging, git-history parsing) that SQL can't express — so
silver stays Python. The boundary follows the nature of the work, not habit.

**Jobs gold** (`dbt/models/gold/`):
- `jobs_by_exposure_band_year` — per dataset × exposure band × year:
  `n_postings`, `ai_usage_rate`, `ai_building_rate`, `avg_exposure`.
- `jobs_by_occupation` — occupation-level grain (for correlations).

**Code gold**:
- `github_adoption_by_year` / `_by_month` — AI-signal commit share
  (numerator `gh_matches` deduped by sha, denominator `gh_totals`).
- `github_merge_rate` — merge rate by author_class × size bucket (PRs deduped).
- `github_changes_requested` — review pushback rate by author class.
- `github_churn_by_bucket` — 14-day follow-up churn by class × size bucket.
- `github_ai_share_by_repo` — AI touch share per repo.

Each aggregation was verified to match the original Python implementation exactly
(e.g. adoption 0.0068 → 0.0076 → 0.1562).

## Stage 4 — Warehouse (Postgres, two schemas)

- **`silver.*`** — the cleaned tables the loaders push in
  (`jobs_kaggle`, `jobs_tech`, `gh_matches`, `gh_totals`, `gh_pr_outcomes`,
  `gh_pr_reviews`, `gh_churn_events`). dbt reads *from* here.
- **`gold.*`** — the 8 aggregated tables dbt *writes*. The dashboard reads here.

Loaders: `src/db/load_silver_to_postgres.py` (jobs) and
`src/db/load_github_silver_to_postgres.py` (code) — CSV silver → `silver.*`.
Gold is **not** loaded from CSV; dbt builds it directly in Postgres.

## Stage 5 — Orchestration (Airflow)

DAG `aiwork_pipeline` (Docker, LocalExecutor):

```
load_jobs_silver ─┐
                  ├─► dbt_run ─► dbt_test
load_gh_silver   ─┘
```

Both silvers load in parallel, dbt builds all gold, dbt tests run. dbt is baked
into a custom Airflow image (`airflow/Dockerfile`) so the scheduler always has
it. `schedule=None` — the data is a fixed snapshot, so runs are on-demand;
Airflow's value here is reproducible orchestration, not live scheduling.

**Ingestion is not in the DAG** — the silver-creation scripts need a ~1 GB
embedding model / repo clones and run on the host. Standard practice: keep
heavy ML extraction out of the orchestrator container.

## Stage 6 — Serving (Streamlit)

`app.py` — an interactive Plotly dashboard, five tabs (Adoption, Jobs,
Acceptance, Durability, Synthesis), each chart with a What / Why / Honest-
limitation note. Data source is a single boundary: `GOLD_BACKEND=postgres`
reads `gold.*` from the warehouse; otherwise it reads gold CSVs. One env var
switches backends, so the dashboard demos with or without the DB and the future
cloud lift changes only the connection.

## The stack at a glance

| Layer | Tool |
|---|---|
| Storage / warehouse | Postgres (`silver` + `gold`) |
| Transformation | dbt (SQL models, both pillars) |
| Governance | dbt tests |
| Orchestration | Airflow (Docker) |
| Serving | Streamlit + Plotly |
| Containerization | Docker Compose |

## Next (cloud, parked)
MinIO (local S3) for bronze/silver/gold → real AWS S3 → Postgres to AWS RDS.
Each is a config/endpoint change, not a rewrite — the local-first design makes
the lift incremental.
