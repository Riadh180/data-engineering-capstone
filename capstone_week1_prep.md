# Capstone — Week 1 Prep

**AI & the Software Job Market** · Ginger-Graphs cohort

---

## 1. Project Overview

**Domain:** Labour market / employment (software & IT focus, extensible to all jobs).

**In one sentence:** A data pipeline that measures how AI is reshaping the job market — combining live job postings (what employers demand today) with public GitHub activity (AI's footprint in real code) and official employment statistics (how jobs changed before vs. during the AI era), all keyed to how AI-exposed each occupation is.

**Who uses it:** Workforce / labour-market researchers and analysts.

**Problem it solves:** The data on AI's effect on jobs is scattered — postings in one place, code activity in another, employment history in a third — and nobody joins them. Analysts need these signals in one place, refreshed automatically, tied to a common occupation standard, so they can see how AI-exposed occupations are behaving.

---

## 2. Data

| Source | Role | Type | Update | Verified | Key limitation |
|---|---|---|---|---|---|
| **Adzuna API** | live postings, AI-skill demand | REST/JSON (free) | daily (forward only) | ✅ | descriptions truncated to 500 chars; ~33 calls/day |
| **GH Archive** | AI-authorship signals in code | hourly JSON event log | historical, 2011→ | ✅ | AI signals are a floor (invisible autocomplete untracked) |
| **ILO WP140 exposure** | AI-exposure score per occupation | static CSV | yearly | ✅ built | US-neutral, ISCO-08 keyed; static |
| **Eurostat lfsa_egai2d** | historical employment by occupation | REST/JSON-stat | annual, 2011–2025 | ✅ | ISCO **2-digit**, annual (coarse) |
| Destatis / BA | German labour backdrop | REST/JSON | — | verified | KldB codes need crosswalk |
| OECD.AI / Stanford AI Index | historical AI-skill demand trend | web / CSV | annual | **to verify** | aggregate, not per-posting |

**Join key across all:** ISCO-08 occupation code (`isco08_4digit`; rolled to 2-digit for Eurostat).

**Access verified?** Yes for the four core sources — each pulled and inspected on real data.

---

## 3. Pipeline Design

Two source branches, medallion layers, meeting on a shared occupation code + timeline.

```
Adzuna API ─┐                        bronze (raw, immutable, dated)
GH Archive ─┼── ingest ────────────► silver (crosswalk → ISCO, AI-skill tag, clean)
Eurostat  ──┘                        gold   (star schema: fact + dims + marts)
ILO CSV ───────────────────────────► joined on ISCO in silver/gold
                                        │
                                        └─► serving: AI-skill demand by exposure band;
                                            employment trend before/during AI; code-AI trend
```

- **Bronze:** exact raw pulls, `data/{layer}/adzuna|eurostat/dt=YYYY-MM-DD/...`, never mutated.
- **Silver:** one clean row per posting/event — crosswalked to ISCO, AI-skill tagged, exposure joined.
- **Gold:** `fact_job_postings` + `fact_employment` + `dim_occupation` (exposure) + `dim_date`, and serving marts.

---

## 4. Technology Choices

| Tech | Why |
|---|---|
| Python + requests | ingestion; the language of the pipeline |
| pandas | transforms at POC stage (CSV in/out) |
| custom crosswalk | title → ISCO-08 (keyword rules + category fallback) |
| **PostgreSQL** | the warehouse — chosen because it's what I learned and can defend |
| dbt | transforms + tests + lineage *(planned, post-approval)* |
| PySpark | the GH Archive branch only (genuine big data) *(planned)* |
| Airflow | orchestration *(planned)* |
| Docker Compose | containerisation *(planned)* |
| Metabase / Streamlit | serving / dashboard *(planned)* |

**Deliberately NOT used:** Kafka/streaming (postings are batch), paid cloud warehouses (Postgres suffices). Documented as ADRs.

---

## 5. Scope

**MVP (must work):** Adzuna → ISCO crosswalk → AI-skill tag → join ILO exposure → silver (dated) → gold mart showing **AI-skill demand by exposure band**. This is proven end-to-end on real data today.

**Stretch goals (in order):**
1. Eurostat historical employment by exposure band (before/during-AI trend).
2. GH Archive AI-authorship trend (the code side).
3. dbt + Postgres + Airflow + Docker (productionise).
4. Dashboard; ESCO semantic crosswalk; OECD/Stanford AI-demand trend.

---

## 6. Risks

| Risk | Mitigation |
|---|---|
| **No historical job-posting text exists** → can't trend AI-skill demand from descriptions | Route the historical question to Eurostat *employment* trends; use OECD/Stanford for aggregate AI-demand history; treat Adzuna AI-skill as a *current floor*, not a trend |
| Adzuna: truncated descriptions + 33 calls/day | Accept AI-skill rate as a floor (documented); pull small daily, accumulate; develop offline against stored bronze |
| Crosswalk mis-maps titles → wrong exposure | `match_method` flag (keyword vs fallback); grow rules from real data; unit tests |
| Scope creep (too many sources) | MVP = 3 core sources only; everything else sequenced after approval |

---

## 7. Plan for Next Week

1. Stabilise the Adzuna→silver→gold path with dated partitions accumulating (done — verify running daily).
2. Build `eurostat_tidy.py` — flatten JSON-stat → tidy employment rows joined to exposure.
3. Grow the crosswalk from real `category_fallback`/`unmapped` rows; add unit tests.
