#!/usr/bin/env python3
"""
Adzuna live ingestion — daily job-market pull (scheduled via Airflow).

Flow:
  1. INGEST     pull job postings from the Adzuna API (live if keys set, else sample)
  2. STORE RAW  write the untouched API response to bronze (immutable)
  3. TRANSFORM  flatten -> normalize title -> crosswalk to ISCO-08 -> AI-skill tag
  4. ENRICH     join to ILO AI-exposure on the ISCO code
  5. STORE      write enriched postings to silver

Bronze + silver are written under LAKE_ROOT (local data/ or s3://R2 bucket).
Writes go through config._s3fs(), which passes the R2 endpoint explicitly, so
they hit Cloudflare R2 (not AWS) regardless of env-var auto-discovery quirks.

Run:  python -m src.ingestion.adzuna [category ...]
"""
import io
import json
import os
import sys
from datetime import datetime, timezone, date

try:
    from dotenv import load_dotenv; load_dotenv()   # LAKE_ROOT / keys / endpoint from .env
except ImportError:
    pass

import pandas as pd

from src.common.config import lake_path, lake_makedirs, _s3fs
from src.transform.crosswalk import map_title_to_isco   # lightweight keyword crosswalk
from src.transform.ai_skill_tagger import detect_ai_skill

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
COUNTRY = "de"
DEFAULT_CATEGORY = "it-jobs"
DEFAULT_WHAT = None
RESULTS_PER_PAGE = 20

ILO_FILE = "reference/ilo_ai_exposure_isco08.csv"   # reference stays local
BRONZE_DIR = lake_path("bronze/adzuna")
SILVER_DIR = lake_path("silver/adzuna")

APP_ID = os.getenv("ADZUNA_APP_ID")
APP_KEY = os.getenv("ADZUNA_APP_KEY")


# ---------------------------------------------------------------------------
# writers — route s3:// through config._s3fs() (explicit R2 endpoint);
# fs.open() uploads the object directly (no bucket-create / makedirs).
# ---------------------------------------------------------------------------
def _write_text(path, text):
    if str(path).startswith("s3://"):
        with _s3fs().open(path, "w") as f:
            f.write(text)
    else:
        lake_makedirs(os.path.dirname(path) or ".")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)


def _write_df(df, path):
    if str(path).startswith("s3://"):
        buf = io.StringIO(); df.to_csv(buf, index=False)
        with _s3fs().open(path, "w") as f:
            f.write(buf.getvalue())
    else:
        lake_makedirs(os.path.dirname(path) or ".")
        df.to_csv(path, index=False)


def fetch_adzuna_live(category=DEFAULT_CATEGORY, what=DEFAULT_WHAT):
    import requests
    url = f"https://api.adzuna.com/v1/api/jobs/{COUNTRY}/search/1"
    params = {
        "app_id": APP_ID, "app_key": APP_KEY,
        "results_per_page": RESULTS_PER_PAGE,
        "category": category,
        "content-type": "application/json",
    }
    if what:
        params["what"] = what
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


SAMPLE_RESPONSE = {
    "count": 12873,
    "results": [
        {"title": "Software Engineer SAP & oscare (all genders)", "id": "5773181085",
         "company": {"display_name": "adesso business consulting AG"},
         "category": {"tag": "it-jobs", "label": "IT-Stellen"},
         "location": {"display_name": "Bonn, Nordrhein-Westfalen", "area": ["Deutschland", "Nordrhein-Westfalen", "Bonn"]},
         "salary_min": 60000, "salary_max": 82000, "salary_is_predicted": "1",
         "created": "2026-06-23T06:22:15Z"},
        {"title": "Data Engineer (all genders)", "id": "5773181092",
         "company": {"display_name": "Insight Analytics"},
         "category": {"tag": "it-jobs", "label": "IT-Stellen"},
         "location": {"display_name": "Berlin", "area": ["Deutschland", "Berlin"]},
         "salary_min": 70000, "salary_max": 92000, "salary_is_predicted": "0",
         "created": "2026-07-20T09:00:00Z"},
    ],
}


def ingest(category=DEFAULT_CATEGORY, what=DEFAULT_WHAT):
    if APP_ID and APP_KEY:
        try:
            print(f"[1] INGEST: calling Adzuna live ... (category={category})")
            data = fetch_adzuna_live(category, what)
            print(f"    got {len(data.get('results', []))} postings (of {data.get('count')} total)")
            return data, "live"
        except Exception as e:
            print(f"    live call failed ({e}); falling back to sample")
    else:
        print("[1] INGEST: no ADZUNA_APP_ID/KEY set -> using bundled sample")
    return SAMPLE_RESPONSE, "sample"


def _dated_path(base_dir, category, ext):
    day = date.today().isoformat()
    out_dir = f"{base_dir}/dt={day}"
    return f"{out_dir}/{COUNTRY}_{category}.{ext}"


def store_raw(data, category):
    path = _dated_path(BRONZE_DIR, category, "json")
    _write_text(path, json.dumps(data, ensure_ascii=False, indent=2))
    print(f"[2] STORE RAW: wrote {path}")
    return path


def store_silver(df, category):
    path = _dated_path(SILVER_DIR, category, "csv")
    _write_df(df, path)
    print(f"[5] SILVER: wrote {len(df)} rows -> {path}")
    return path


def transform(data, category_mean=None):
    rows = []
    for job in data.get("results", []):
        title = job.get("title", "")
        desc = job.get("description", "")
        cat = (job.get("category") or {}).get("tag", "")
        code, matched_kw = map_title_to_isco(title, cat)
        area = (job.get("location") or {}).get("area", [])
        usage, building, ai_terms = detect_ai_skill(title, desc)
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
            "category_mean_salary": category_mean,
            "created": job.get("created"),
            "isco08_4digit": code,
            "matched_keyword": matched_kw,
            "has_ai_usage": usage,
            "has_ai_building": building,
            "has_ai_skill": usage or building,
            "ai_skill_terms": ";".join(ai_terms),
        })
    df = pd.DataFrame(rows)
    df["created"] = pd.to_datetime(df["created"], errors="coerce")
    df["salary_avg"] = df[["salary_min", "salary_max"]].mean(axis=1)
    df["has_salary"] = df["salary_avg"].notna()
    n_ai = int(df["has_ai_skill"].sum())
    print(f"[3] TRANSFORM: {len(df)} postings | AI-skill: {n_ai}/{len(df)}")
    mapped = (df["isco08_4digit"] != "unmapped").sum()
    print(f"    mapped to ISCO: {mapped}/{len(df)}  |  unmapped: {len(df) - mapped}")
    return df


def enrich(df):
    if not os.path.exists(ILO_FILE):
        sys.exit(f"[4] ENRICH: {ILO_FILE} not found.")
    ilo = pd.read_csv(ILO_FILE, dtype={"isco08_4digit": str})
    out = df.merge(
        ilo[["isco08_4digit", "occupation_name", "exposure_category",
             "exposure_order", "mean_task_score"]],
        on="isco08_4digit", how="left",
    )
    print(f"[4] ENRICH: joined to ILO exposure ({len(ilo)} occupations)")
    return out


def main():
    categories = sys.argv[1:] or [DEFAULT_CATEGORY]
    for category in categories:
        print("=" * 60)
        print(f"Adzuna ingestion — {category}")
        print("=" * 60)
        data, _source = ingest(category)
        category_mean = data.get("mean")
        store_raw(data, category)
        df = transform(data, category_mean)
        enriched = enrich(df)
        store_silver(enriched, category)
    print("\nDone.")


if __name__ == "__main__":
    main()