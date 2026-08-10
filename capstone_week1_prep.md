# Capstone Project — Week 1 Preparation

**Project:** AI & the German Job Market
**Author:** Riadh · Ginger-Graphs cohort
**Date:** August 2026

---

## 1. Project Overview

**Domain:** Labour market / employment — focus on German job postings, all occupations, with software/IT as the analytical centre of gravity.

**In one sentence:** A data pipeline that measures how AI is reshaping the German job market, by combining real job-posting text (what employers demand) with official employment statistics (how jobs changed over time) and public GitHub activity (AI's footprint in code) — all tied to each occupation's AI-exposure score.

**Who would use it:** Labour-market and workforce researchers, and analysts studying AI's effect on employment.

**Problem it solves (business need):** The evidence on AI's impact on jobs is scattered — posting text sits in one place, employment history in another, code activity in a third — and nobody joins them on a common occupation standard. Analysts need these signals in one pipeline, refreshed and comparable, keyed to how AI-exposed each occupation is.

**The core question:** In AI-exposed occupations, is AI *substituting* workers (employment/demand falling) or *augmenting* them (demand for AI skills rising)?

---

## 2. Data

Verified sources (each pulled and inspected on real data), with the honest role of each:

| Source | Role | Type | Coverage | Verified |
|---|---|---|---|---|
| **Kaggle German postings** (`sample_jobs_5000`) | granular AI-skill demand (full descriptions, salary) | CSV, per-posting | Germany, 2022–2026 (dense 2025–26) | ✅ |
| **Eurostat** `lfsa_egai2d` | historical employment by occupation | REST / JSON-stat | EU incl. DE, 2011–2025, ISCO 2-digit | ✅ |
| **GH Archive** | AI-authorship signals in code | hourly JSON events | global, 2011→ | ✅ |
| **ILO WP140** exposure | AI-exposure score per occupation | static CSV | ISCO-08 4-digit, 300 occupations | ✅ built |
| **ESCO** (occupations_de) | German job title → ISCO occupation code | static CSV | 3,043 occupations, German labels | ✅ |
| `job_postings_raw` (Kaggle) | development / validation only | CSV | Germany, 2024–2025 | ✅ |

**Join key across everything:** the **ISCO-08 occupation code** — produced by matching each German title to an ESCO occupation, then joined to the ILO exposure score and (rolled to 2-digit) to Eurostat.

**Sources evaluated and rejected (due diligence):**
- **Adzuna API** — descriptions truncated to 500 chars; unusable for skill detection.
- **Bundesagentur für Arbeit API** — unofficial, auth changed, could not authenticate reliably.
- **Techmap / Lightcast / TheirStack** — rich granular history exists but is **paid** (~€4,800/yr class).
- **OECD.AI / Stanford AI Index** — aggregated percentages only; benchmark, not raw material.

**Honest conclusion on data:** free, granular, multi-year, full-text German posting data does **not** exist — it is a commercial product. The design therefore combines a rich *recent* granular source (Kaggle) with an aggregate *historical* source (Eurostat), each covering the other's blind spot.

---

## 3. Pipeline Design

Medallion architecture, one occupation code linking every layer.

```
Kaggle CSV  ─┐                    bronze  (raw, immutable, dated folders)
Eurostat    ─┼── ingest ───────►  silver  (ESCO crosswalk → ISCO, AI-skill tag, clean)
GH Archive  ─┘                    gold    (star schema: fact + dims + marts)
ESCO + ILO  ──────────────────►   joined on ISCO code in silver / gold
                                    │
                                    └──► serving: AI-skill demand by exposure band,
                                         employment trend by exposure band, code-AI trend
```

- **Bronze:** exact raw pulls, partitioned `data/bronze/<source>/dt=YYYY-MM-DD/`. Never mutated.
- **Silver:** one clean row per posting — **German title → ESCO occupation → ISCO code**, AI-skill flag from the full description, ILO exposure joined.
- **Gold:** `fact_job_postings` + `fact_employment` + `dim_occupation` (holds exposure) + `dim_date`, plus serving marts.

---

## 4. Technology Choices

| Tech | Why |
|---|---|
| Python + pandas | ingestion and transforms at this stage |
| **rapidfuzz** | fuzzy-match German titles to ESCO occupation labels |
| ESCO occupation taxonomy | authoritative title → ISCO mapping (no hand-guessing) |
| **PostgreSQL** | the warehouse — chosen because it is the DB I learned and can defend |
| dbt | transforms + tests + lineage *(planned, after approval)* |
| Airflow | orchestration *(planned)* |
| Docker Compose | containerisation *(planned)* |
| Metabase / Streamlit | serving / dashboard *(planned)* |

**Deliberately NOT used:** Kafka/streaming (postings are batch, not a stream); paid cloud warehouses (Postgres suffices). Recorded as ADRs.

---

## 5. Scope

**MVP (must work):** Kaggle German postings → ESCO crosswalk to ISCO → AI-skill tag on full descriptions → join ILO exposure → dated silver → gold mart showing **AI-skill demand by AI-exposure band**. *This runs end-to-end today on real data.*

**Stretch goals (ordered):**
1. Eurostat historical employment by exposure band (the before/during-AI trend).
2. GH Archive AI-authorship trend (the code side).
3. Productionise: dbt + Postgres + Airflow + Docker.
4. Dashboard; embeddings upgrade for the ESCO crosswalk.

---

## 6. Risks

| Risk | Mitigation |
|---|---|
| **Sample thin per (band × year) cell** → noisy year-by-year trend | Aggregate into larger buckets (High vs Low exposure; 2022–24 vs 2025–26); report comparisons, not fragile per-year %s |
| **No historical granular posting text** (proprietary) | Route history to Eurostat *employment*; Kaggle covers *recent* granular detail; state the split openly |
| **Crosswalk coverage ~61%** (title → ISCO) | ESCO exact+fuzzy matching (real occupations, not guesses); grow via an unmapped-review file each run; tune fuzzy threshold |
| **Correlation, not causation** | Compare exposure bands relative to each other (control group); never claim AI *caused* a change |

---

## 7. Plan for Next Week

1. Push crosswalk coverage above ~75% (tune the ESCO fuzzy threshold; review unmapped titles) and confirm mapped codes are occupation-accurate.
2. Build the Eurostat ingestion (`eurostat.py`): JSON-stat → tidy employment rows joined to exposure — the historical dimension.
3. Build the gold layer (fact + dims) and the first serving mart: AI-skill demand by exposure band, aggregated into stable buckets.

---

## 5-Minute Pitch

- **Problem:** everyone asks how AI is reshaping work, but the data is scattered and unjoined.
- **Solution:** one pipeline joining German posting text (demand), official employment history (Eurostat), and GitHub code activity — all on the ISCO occupation code plus an AI-exposure score.
- **Data:** verified — Kaggle German postings (now), Eurostat (history), GH Archive (code), ESCO + ILO (the mapping and the lens).
- **Honest framing:** findings are trends and correlations, not proof of causation; granular history is proprietary, so recent granular detail (Kaggle) pairs with aggregate history (Eurostat).
- **MVP:** the German-postings → ESCO → exposure → AI-skill mart — working today.
- **Next week:** raise crosswalk coverage, add the Eurostat historical layer, build the gold mart.

---

## Current Status (what already works)

- ✅ All core sources verified on **real data**, not assumptions.
- ✅ ISCO exposure reference (ILO WP140) extracted to CSV.
- ✅ ESCO crosswalk: German title → ISCO occupation (61% mapped: exact + fuzzy).
- ✅ AI-skill tagger (German + English) running on full descriptions.
- ✅ End-to-end run: Kaggle CSV → silver → preview mart (AI-skill % by exposure band × year).
- ✅ GH Archive AI-authorship parser, independently audited.

**Early observation:** AI-skill demand is ~1% across all German occupations but ~10% among IT roles — demand concentrates in tech, negligible elsewhere.

---

## How to Demo / Test

```bash
# occupation mapping works (German title → ISCO via ESCO)
python3 -m src.transform.esco_crosswalk

# full pipeline: Kaggle German postings → silver
python3 -m src.ingestion.kaggle_jobs
#   → prints coverage (esco_exact / esco_fuzzy / unmapped),
#     AI-skill %, and AI-skill by exposure band × year

# historical source verified live
python3 src/ingestion/eurostat_sample.py     # German ICT employment 2011–2025

# code-side signals verified
python3 src/transform/gharchive_signals.py data/bronze/gharchive/<file>.json
```