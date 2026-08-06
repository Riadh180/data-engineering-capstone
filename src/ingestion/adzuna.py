#!/usr/bin/env python3
"""
PROOF OF CONCEPT — "AI impact on the job market" data pipeline
================================================================

Flow (this is the whole MVP in one file):

  1. INGEST     pull job postings from the Adzuna API  (live if you set a key,
                otherwise a bundled sample so the POC runs anywhere)
  2. STORE RAW  write the untouched API response to a raw zone (immutable)
  3. TRANSFORM  extract fields -> normalize title -> crosswalk to ISCO-08 code
  4. ENRICH     join to the ILO AI-exposure file on the ISCO code
  5. ANALYZE    demand & salary by exposure band  (the actual insight)

Run live:
  export ADZUNA_APP_ID=xxxx
  export ADZUNA_APP_KEY=xxxx
  python poc_ai_jobs_pipeline.py

Run on the bundled sample (no key needed):
  python poc_ai_jobs_pipeline.py
"""
import json
import os
import sys
from datetime import datetime, timezone, date

import pandas as pd

from src.transform.crosswalk import map_title_to_isco   # reuse the crosswalk
from src.transform.ai_skill_tagger import detect_ai_skill

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
COUNTRY = "de"                        # Germany
DEFAULT_CATEGORY = "it-jobs"          # used when no category is passed on the CLI
DEFAULT_WHAT = None                   # optional keyword filter; None = whole category
RESULTS_PER_PAGE = 20

ILO_FILE = "reference/ilo_ai_exposure_isco08.csv"
BRONZE_DIR = "data/bronze/adzuna"
SILVER_DIR = "data/silver/adzuna"

APP_ID = os.getenv("ADZUNA_APP_ID")
APP_KEY = os.getenv("ADZUNA_APP_KEY")


# ---------------------------------------------------------------------------
# 1) INGEST
# ---------------------------------------------------------------------------
def fetch_adzuna_live(category=DEFAULT_CATEGORY, what=DEFAULT_WHAT):
    import requests
    url = f"https://api.adzuna.com/v1/api/jobs/{COUNTRY}/search/1"
    params = {
        "app_id": APP_ID, "app_key": APP_KEY,
        "results_per_page": RESULTS_PER_PAGE,
        "category": category,
        "content-type": "application/json",
    }
    if what:                       # only filter by keyword when one is given
        params["what"] = what
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


# Bundled sample — the shape Adzuna returns. Includes your real adesso posting.
SAMPLE_RESPONSE = {
    "count": 12873,
    "results": [
        {"title": "Software Engineer SAP & oscare (all genders)", "id": "5773181085",
         "company": {"display_name": "adesso business consulting AG"},
         "category": {"tag": "it-jobs", "label": "IT-Stellen"},
         "location": {"display_name": "Bonn, Nordrhein-Westfalen", "area": ["Deutschland", "Nordrhein-Westfalen", "Bonn"]},
         "salary_min": 60000, "salary_max": 82000, "salary_is_predicted": "1",
         "created": "2026-06-23T06:22:15Z"},
        {"title": "Softwareentwickler (m/w/d) Java", "id": "5773181086",
         "company": {"display_name": "Mustertech GmbH"},
         "category": {"tag": "it-jobs", "label": "IT-Stellen"},
         "location": {"display_name": "Munchen, Bayern", "area": ["Deutschland", "Bayern", "Munchen"]},
         "salary_min": 65000, "salary_max": 85000, "salary_is_predicted": "0",
         "created": "2026-07-02T09:00:00Z"},
        {"title": "Anwendungsentwickler C# (w/m/d)", "id": "5773181087",
         "company": {"display_name": "Beispiel AG"},
         "category": {"tag": "it-jobs", "label": "IT-Stellen"},
         "location": {"display_name": "Berlin", "area": ["Deutschland", "Berlin"]},
         "salary_min": 58000, "salary_max": 78000, "salary_is_predicted": "0",
         "created": "2026-07-05T09:00:00Z"},
        {"title": "Senior DevOps Engineer", "id": "5773181088",
         "company": {"display_name": "Cloudwerk GmbH"},
         "category": {"tag": "it-jobs", "label": "IT-Stellen"},
         "location": {"display_name": "Hamburg", "area": ["Deutschland", "Hamburg"]},
         "salary_min": 75000, "salary_max": 95000, "salary_is_predicted": "0",
         "created": "2026-07-10T09:00:00Z"},
        {"title": "Webentwickler Frontend (m/w/d)", "id": "5773181089",
         "company": {"display_name": "Pixelhaus"},
         "category": {"tag": "it-jobs", "label": "IT-Stellen"},
         "location": {"display_name": "Koln, Nordrhein-Westfalen", "area": ["Deutschland", "Nordrhein-Westfalen", "Koln"]},
         "salary_min": 52000, "salary_max": 70000, "salary_is_predicted": "1",
         "created": "2026-07-12T09:00:00Z"},
        {"title": "Datenbankadministrator PostgreSQL (m/w/d)", "id": "5773181090",
         "company": {"display_name": "Datenbank Systeme AG"},
         "category": {"tag": "it-jobs", "label": "IT-Stellen"},
         "location": {"display_name": "Frankfurt am Main, Hessen", "area": ["Deutschland", "Hessen", "Frankfurt am Main"]},
         "salary_min": 62000, "salary_max": 80000, "salary_is_predicted": "0",
         "created": "2026-07-15T09:00:00Z"},
        {"title": "IT-Support Mitarbeiter (m/w/d) 1st Level", "id": "5773181091",
         "company": {"display_name": "Servicedesk24"},
         "category": {"tag": "it-jobs", "label": "IT-Stellen"},
         "location": {"display_name": "Stuttgart, Baden-Wurttemberg", "area": ["Deutschland", "Baden-Wurttemberg", "Stuttgart"]},
         "salary_min": 38000, "salary_max": 48000, "salary_is_predicted": "1",
         "created": "2026-07-18T09:00:00Z"},
        {"title": "Data Engineer (all genders)", "id": "5773181092",
         "company": {"display_name": "Insight Analytics"},
         "category": {"tag": "it-jobs", "label": "IT-Stellen"},
         "location": {"display_name": "Berlin", "area": ["Deutschland", "Berlin"]},
         "salary_min": 70000, "salary_max": 92000, "salary_is_predicted": "0",
         "created": "2026-07-20T09:00:00Z"},
        {"title": "Fachinformatiker Systemintegration (m/w/d)", "id": "5773181093",
         "company": {"display_name": "Netzwerk Profis GmbH"},
         "category": {"tag": "it-jobs", "label": "IT-Stellen"},
         "location": {"display_name": "Dortmund, Nordrhein-Westfalen", "area": ["Deutschland", "Nordrhein-Westfalen", "Dortmund"]},
         "salary_min": 42000, "salary_max": 55000, "salary_is_predicted": "1",
         "created": "2026-07-22T09:00:00Z"},
        {"title": "Scrum Master (m/w/d)", "id": "5773181094",   # deliberately unmapped
         "company": {"display_name": "Agile Works"},
         "category": {"tag": "it-jobs", "label": "IT-Stellen"},
         "location": {"display_name": "Leipzig, Sachsen", "area": ["Deutschland", "Sachsen", "Leipzig"]},
         "salary_min": 68000, "salary_max": 88000, "salary_is_predicted": "1",
         "created": "2026-07-25T09:00:00Z"},
    ],
}


def ingest(category=DEFAULT_CATEGORY, what=DEFAULT_WHAT):
    if APP_ID and APP_KEY:
        try:
            print(f"[1] INGEST: calling Adzuna live ... (category={category})")
            data = fetch_adzuna_live(category, what)
            print(f"    got {len(data.get('results', []))} postings (of {data.get('count')} total)")
            print(f"    category mean salary: {data.get('mean')}")
            return data, "live"
        except Exception as e:
            print(f"    live call failed ({e}); falling back to sample")
    else:
        print("[1] INGEST: no ADZUNA_APP_ID/KEY set -> using bundled sample")
    return SAMPLE_RESPONSE, "sample"


# ---------------------------------------------------------------------------
# 2) STORE RAW / STORE SILVER  (immutable raw zone — one file per pull)
# ---------------------------------------------------------------------------

def _dated_path(base_dir, category, ext):
    """Single source of truth for file naming across all layers."""
    day = date.today().isoformat()
    out_dir = os.path.join(base_dir, f"dt={day}")
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, f"{COUNTRY}_{category}.{ext}")

def store_raw(data, category):
    path = _dated_path(BRONZE_DIR, category, "json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[2] STORE RAW: wrote {path}")
    return path

def store_silver(df, category):
    path = _dated_path(SILVER_DIR, category, "csv")
    df.to_csv(path, index=False)
    print(f"    wrote enriched postings -> {path}")
    return path


# ---------------------------------------------------------------------------
# 3) TRANSFORM  (flatten -> normalize -> crosswalk to ISCO)
# ---------------------------------------------------------------------------
def transform(data, category_mean=None):
    rows = []
    for job in data.get("results", []):
        title = job.get("title", "")
        desc = job.get("description", "")
        cat = (job.get("category") or {}).get("tag", "")
        code, matched_kw = map_title_to_isco(title, cat)
        area = (job.get("location") or {}).get("area", [])
        has_ai, ai_terms = detect_ai_skill(title, desc)          # <-- AI-skill tag
        rows.append({
            "adzuna_id": job.get("id"),
            "title": title,
            "company": (job.get("company") or {}).get("display_name"),
            "category_tag": cat,
            "region": area[1] if len(area) > 1 else None,
            "city": (job.get("location") or {}).get("display_name"),
            "salary_min": job.get("salary_min"),
            "salary_max": job.get("salary_max"),
            "salary_is_predicted": job.get("salary_is_predicted"),
            "category_mean_salary": category_mean,               # <-- category salary
            "created": job.get("created"),
            "isco08_4digit": code,
            "matched_keyword": matched_kw,
            "has_ai_skill": has_ai,                               # <-- new
            "ai_skill_terms": ";".join(ai_terms),                # <-- new
        })
    df = pd.DataFrame(rows)
    df["created"] = pd.to_datetime(df["created"], errors="coerce")
    df["salary_avg"] = df[["salary_min", "salary_max"]].mean(axis=1)
    df["has_salary"] = df["salary_avg"].notna()

    n_ai = int(df["has_ai_skill"].sum())
    print(f"[3] TRANSFORM: {len(df)} postings | AI-skill: {n_ai}/{len(df)} | category mean: {category_mean}")
    mapped = (df["isco08_4digit"] != "unmapped").sum()
    print(f"    mapped to ISCO: {mapped}/{len(df)}  |  unmapped: {len(df) - mapped}")
    return df


# ---------------------------------------------------------------------------
# 4) ENRICH  (join to ILO exposure on the ISCO code)
# ---------------------------------------------------------------------------
def enrich(df):
    if not os.path.exists(ILO_FILE):
        sys.exit(f"[4] ENRICH: {ILO_FILE} not found — put it beside this script.")
    ilo = pd.read_csv(ILO_FILE, dtype={"isco08_4digit": str})
    out = df.merge(
        ilo[["isco08_4digit", "occupation_name", "exposure_category",
             "exposure_order", "mean_task_score"]],
        on="isco08_4digit", how="left",
    )
    print(f"[4] ENRICH: joined to ILO exposure ({len(ilo)} occupations in reference)")
    return out


# ---------------------------------------------------------------------------
# 5) ANALYZE  (the payoff: demand & salary by exposure band)
# ---------------------------------------------------------------------------
def analyze(df):
    print("\n[5] ANALYZE")
    mapped = df[df["isco08_4digit"] != "unmapped"].copy()

    print("\n  Postings & avg salary by AI-exposure band")
    g = (mapped.groupby(["exposure_order", "exposure_category"], dropna=False)
         .agg(postings=("adzuna_id", "count"),
              avg_salary=("salary_avg", "mean"),
              avg_exposure=("mean_task_score", "mean"))
         .reset_index()
         .sort_values("exposure_order", ascending=False))
    for _, r in g.iterrows():
        print(f"    {r['exposure_category']:<12} | postings {int(r['postings']):>2} "
              f"| avg salary EUR {r['avg_salary']:>7,.0f} "
              f"| avg exposure {r['avg_exposure']:.2f}")

    print("\n  Postings by occupation (mapped)")
    occ = (mapped.groupby(["occupation_name", "mean_task_score"])
           .size().reset_index(name="postings")
           .sort_values("mean_task_score", ascending=False))
    for _, r in occ.iterrows():
        print(f"    {r['mean_task_score']:.2f}  {r['occupation_name']:<45} x{int(r['postings'])}")

    batch_exposure = mapped["mean_task_score"].mean()
    print(f"\n  Batch-level average AI-exposure score: {batch_exposure:.3f}")

    unmapped = df[df["isco08_4digit"] == "unmapped"]["title"].tolist()
    if unmapped:
        print(f"\n  Unmapped titles to review & add to the crosswalk: {unmapped}")


def main():
    categories = sys.argv[1:] or [DEFAULT_CATEGORY]
    os.makedirs(SILVER_DIR, exist_ok=True)
    for category in categories:
        print("=" * 66)
        print(f"POC: AI impact on the job market — {category}")
        print("=" * 66)

        data, _source = ingest(category)
        category_mean = data.get("mean")
        store_raw(data, category)
        df = transform(data, category_mean)
        enriched = enrich(df)
        out_file = store_silver(enriched, category)
        print(f"    wrote enriched postings -> {out_file}")
        analyze(enriched)
    print("\nDone.")


if __name__ == "__main__":
    main()
