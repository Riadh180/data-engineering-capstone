#!/usr/bin/env python3
"""
Ingest the German TECH job postings (job_postings_raw.csv) into silver.

Same shape as kaggle_jobs.py but for the tech dataset. Reads bronze and writes
silver under LAKE_ROOT (local data/ or s3://bucket).

Run:  python3 -m src.ingestion.tech_jobs
"""
import os
from datetime import date

try:
    from dotenv import load_dotenv; load_dotenv()   # so LAKE_ROOT/PG* from .env are set
except ImportError:
    pass

import pandas as pd

from src.common.config import lake_path, lake_makedirs
from src.transform.esco_crosswalk import EscoCrosswalk
from src.transform.ai_skill_tagger import detect_ai_skill

BRONZE = lake_path("bronze/kaggle/job_postings_raw.csv")
ESCO_FILE = "reference/esco/occupations_de.csv"     # reference data stays local
ILO_FILE = "reference/ilo_ai_exposure_isco08.csv"   # reference data stays local
SILVER_DIR = lake_path("silver/tech")


def main():
    print("=" * 60)
    print("German TECH jobs -> silver")
    print("=" * 60)

    crosswalk = EscoCrosswalk(ESCO_FILE, ILO_FILE)
    print(f"[0] CROSSWALK: {len(crosswalk.esco):,} ESCO labels indexed")

    df = pd.read_csv(BRONZE)
    print(f"[1] READ: {len(df)} rows")
    df["posted_date"] = pd.to_datetime(df["posted_date"], errors="coerce")
    df["year"] = df["posted_date"].dt.year

    mapped = crosswalk.map_titles(df["title_clean"].fillna("").tolist())
    df = df.drop(columns=[c for c in mapped.columns if c in df.columns], errors="ignore")
    df = pd.concat([df.reset_index(drop=True), mapped.reset_index(drop=True)], axis=1)

    usage_flags, build_flags, terms = [], [], []
    for sk, desc in zip(df["skills_extracted"].fillna(""), df["description_clean"].fillna("")):
        usage, building, ts = detect_ai_skill(sk, desc)
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

    keep = ["posting_id", "title_clean", "city", "posted_date", "year",
            "seniority", "cluster_name", "isco08_4digit", "match_method",
            "matched_label", "match_score", "needs_review",
            "has_ai_usage", "has_ai_building", "has_ai_skill", "ai_skill_terms",
            "occupation_name", "exposure_category", "exposure_order",
            "mean_task_score", "sd_task_score", "exposure_imputed"]
    df = df[[c for c in keep if c in df.columns]]
    day = date.today().isoformat()
    out_dir = f"{SILVER_DIR}/dt={day}"
    lake_makedirs(out_dir)                       # local: mkdir; s3: no-op
    path = f"{out_dir}/de_tech_jobs.csv"
    df.to_csv(path, index=False)                 # pandas+s3fs handle s3:// natively
    print(f"[3] SILVER: wrote {len(df)} rows -> {path}")

    mapped_rows = df[df["match_method"] != "unmapped"]
    print("\n[preview] AI-usage / AI-building % by exposure band")
    g = (mapped_rows.groupby("exposure_category")
         .agg(postings=("has_ai_usage", "size"),
              usage_pct=("has_ai_usage", lambda x: round(100 * x.mean(), 1)),
              building_pct=("has_ai_building", lambda x: round(100 * x.mean(), 1))))
    print(g.to_string())


if __name__ == "__main__":
    main()