#!/usr/bin/env python3
"""
Ingest the Kaggle German job postings (sample_jobs_5000.csv) into silver.

Flow:  bronze CSV -> filter 2022+ -> crosswalk title->ISCO -> AI-skill tag on
       full description -> join ILO exposure -> write dated silver.

Reads bronze and writes silver under LAKE_ROOT (local data/ or s3://bucket).
Run from project root:
    python3 -m src.ingestion.kaggle_jobs
"""
import os
from datetime import date, datetime, timezone

try:
    from dotenv import load_dotenv; load_dotenv()   # so LAKE_ROOT/PG* from .env are set
except ImportError:
    pass

import pandas as pd

from src.common.config import lake_path, lake_makedirs
from src.transform.esco_crosswalk import EscoCrosswalk
from src.transform.ai_skill_tagger import detect_ai_skill

BRONZE = lake_path("bronze/kaggle/sample_jobs_5000.csv")
ILO_FILE = "reference/ilo_ai_exposure_isco08.csv"   # reference data stays local
SILVER_DIR = lake_path("silver/kaggle")
MIN_YEAR = 2022


def ingest():
    print(f"[1] READ: {BRONZE}")
    df = pd.read_csv(BRONZE, low_memory=False)
    print(f"    {len(df)} rows total")

    df["date_published"] = pd.to_datetime(df["date_published"], unit="ms", errors="coerce")
    df = df[df["date_published"].dt.year >= MIN_YEAR].copy()
    df["year"] = df["date_published"].dt.year
    print(f"    {len(df)} rows from {MIN_YEAR}+  | by year: "
          f"{df['year'].value_counts().sort_index().to_dict()}")
    return df


def transform(df, xw):
    mapped = xw.map_titles(df["normalized_title"].fillna("").tolist())
    df = df.drop(columns=[c for c in mapped.columns if c in df.columns], errors="ignore")
    df = pd.concat([df.reset_index(drop=True), mapped.reset_index(drop=True)], axis=1)

    usage_flags, build_flags, terms = [], [], []
    for title, desc in zip(df["title"].fillna(""), df["description_text"].fillna("")):
        usage, building, ts = detect_ai_skill(title, desc)
        usage_flags.append(usage)
        build_flags.append(building)
        terms.append(";".join(ts))
    df["has_ai_usage"] = usage_flags
    df["has_ai_building"] = build_flags
    df["has_ai_skill"] = df["has_ai_usage"] | df["has_ai_building"]
    df["ai_skill_terms"] = terms

    print("[2] TRANSFORM: crosswalk (ESCO semantic) + AI-skill tag (usage/building)")
    print(f"    match_method: {df['match_method'].value_counts().to_dict()}")
    print(f"    AI-usage:    {int(df['has_ai_usage'].sum())}/{len(df)} "
          f"({100*df['has_ai_usage'].mean():.1f}%)")
    print(f"    AI-building: {int(df['has_ai_building'].sum())}/{len(df)} "
          f"({100*df['has_ai_building'].mean():.1f}%)")
    return df


def store_silver(df):
    keep = ["job_id", "title", "normalized_title", "company", "city",
        "country_code", "date_published", "year", "has_salary_info",
        "isco08_4digit", "match_method", "matched_label", "match_score",
        "needs_review", "has_ai_usage", "has_ai_building", "has_ai_skill",
        "ai_skill_terms",
        "occupation_name", "exposure_category", "exposure_order",
        "mean_task_score", "sd_task_score", "exposure_imputed"]
    df = df[[c for c in keep if c in df.columns]]
    day = date.today().isoformat()
    out_dir = f"{SILVER_DIR}/dt={day}"
    lake_makedirs(out_dir)                       # local: mkdir; s3: no-op
    path = f"{out_dir}/de_jobs.csv"
    df.to_csv(path, index=False)                 # pandas+s3fs handle s3:// natively
    print(f"[4] SILVER: wrote {len(df)} rows -> {path}")
    return path


def main():
    print("=" * 60); print("Kaggle German jobs -> silver"); print("=" * 60)
    xw = EscoCrosswalk("reference/esco/occupations_de.csv", ILO_FILE)
    df = ingest()
    df = transform(df, xw)
    store_silver(df)
    mapped = df[df["match_method"] != "unmapped"]

    print("\n[preview] AI-USAGE % by exposure band x year")
    piv = (mapped.groupby(["exposure_category", "year"])["has_ai_usage"]
           .mean().mul(100).round(1).reset_index())
    print(piv.to_string(index=False))


if __name__ == "__main__":
    main()