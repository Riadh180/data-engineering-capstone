#!/usr/bin/env python3
"""
Ingest the Kaggle German job postings (sample_jobs_5000.csv) into silver.

Flow:  bronze CSV -> filter 2022+ -> crosswalk title->ISCO -> AI-skill tag on
       full description -> join ILO exposure -> write dated silver.

Run from project root:
    python3 -m src.ingestion.kaggle_jobs
"""
import os
from datetime import date, datetime, timezone

import pandas as pd

from src.transform.esco_crosswalk import map_title_to_isco, match_method
from src.transform.ai_skill_tagger import detect_ai_skill

BRONZE = "data/bronze/kaggle/sample_jobs_5000.csv"
ILO_FILE = "reference/ilo_ai_exposure_isco08.csv"
SILVER_DIR = "data/silver/kaggle"
MIN_YEAR = 2022


def ingest():
    print(f"[1] READ: {BRONZE}")
    df = pd.read_csv(BRONZE, low_memory=False)
    print(f"    {len(df)} rows total")

    # date_published is epoch-milliseconds -> real datetime, then filter 2022+
    df["date_published"] = pd.to_datetime(df["date_published"], unit="ms", errors="coerce")
    df = df[df["date_published"].dt.year >= MIN_YEAR].copy()
    df["year"] = df["date_published"].dt.year
    print(f"    {len(df)} rows from {MIN_YEAR}+  | by year: "
          f"{df['year'].value_counts().sort_index().to_dict()}")
    return df


def transform(df):
    # crosswalk: normalized_title (clean) -> ISCO-08 code. it-jobs tag helps some rules.
    codes, notes = [], []
    for t in df["normalized_title"].fillna(""):
        c, n = map_title_to_isco(t, "")          # no Adzuna category here
        codes.append(c); notes.append(n)
    df["isco08_4digit"] = codes
    df["match_method"] = [match_method(n) for n in notes]

    # AI-skill tag on the FULL description (this is the whole point of this dataset)
    flags, terms = [], []
    for title, desc in zip(df["title"].fillna(""), df["description_text"].fillna("")):
        f, ts = detect_ai_skill(title, desc)
        flags.append(f); terms.append(";".join(ts))
    df["has_ai_skill"] = flags
    df["ai_skill_terms"] = terms

    print(f"[2] TRANSFORM: crosswalk + AI-skill tag")
    print(f"    match_method: {df['match_method'].value_counts().to_dict()}")
    print(f"    AI-skill: {int(df['has_ai_skill'].sum())}/{len(df)} "
          f"({100*df['has_ai_skill'].mean():.1f}%)")
    return df


def enrich(df):
    ilo = pd.read_csv(ILO_FILE, dtype={"isco08_4digit": str})
    df["isco08_4digit"] = df["isco08_4digit"].astype(str)
    out = df.merge(
        ilo[["isco08_4digit", "occupation_name", "exposure_category",
             "exposure_order", "mean_task_score"]],
        on="isco08_4digit", how="left")
    print(f"[3] ENRICH: joined ILO exposure ({len(ilo)} occupations)")
    return out


def store_silver(df):
    keep = ["job_id", "title", "normalized_title", "company", "city",
            "country_code", "date_published", "year", "has_salary_info",
            "isco08_4digit", "match_method", "has_ai_skill", "ai_skill_terms",
            "occupation_name", "exposure_category", "exposure_order", "mean_task_score"]
    df = df[[c for c in keep if c in df.columns]]
    day = date.today().isoformat()
    out_dir = os.path.join(SILVER_DIR, f"dt={day}")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "de_jobs.csv")
    df.to_csv(path, index=False)
    print(f"[4] SILVER: wrote {len(df)} rows -> {path}")
    return path


def main():
    print("=" * 60)
    print("Kaggle German jobs -> silver")
    print("=" * 60)
    df = ingest()
    df = transform(df)
    df = enrich(df)
    store_silver(df)

    # quick preview of the headline metric
    mapped = df[df["isco08_4digit"] != "unmapped"]
    print("\n[preview] AI-skill % by exposure band × year")
    piv = (mapped.groupby(["exposure_category", "year"])["has_ai_skill"]
           .mean().mul(100).round(1).reset_index())
    print(piv.to_string(index=False))


if __name__ == "__main__":
    main()