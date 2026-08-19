#!/usr/bin/env python3
"""
Ingest the German TECH job postings (job_postings_raw.csv) into silver.

Same shape as kaggle_jobs.py but for the tech dataset:
  - crosswalk title_clean -> ISCO-08 by MEANING (ESCO semantic)
  - AI-skill tag from skills_extracted + description_clean (denser signal),
    split into USAGE (uses AI as a tool) vs BUILDING (engineers AI/ML)
  - exposure is attached by the crosswalk (no separate merge) -> dated silver

Run:  python3 -m src.ingestion.tech_jobs
"""
import os
from datetime import date
import pandas as pd

from src.transform.esco_crosswalk import EscoCrosswalk
from src.transform.ai_skill_tagger import detect_ai_skill

BRONZE = "data/bronze/kaggle/job_postings_raw.csv"
ESCO_FILE = "reference/esco/occupations_de.csv"
ILO_FILE = "reference/ilo_ai_exposure_isco08.csv"
SILVER_DIR = "data/silver/tech"


def main():
    print("=" * 60)
    print("German TECH jobs -> silver")
    print("=" * 60)

    # Build the crosswalk ONCE (loads the embedding model + encodes ESCO labels).
    # If you also run kaggle_jobs in the same process, reuse this instance.
    crosswalk = EscoCrosswalk(ESCO_FILE, ILO_FILE)
    print(f"[0] CROSSWALK: {len(crosswalk.esco):,} ESCO labels indexed")

    df = pd.read_csv(BRONZE)
    print(f"[1] READ: {len(df)} rows")
    df["posted_date"] = pd.to_datetime(df["posted_date"], errors="coerce")
    df["year"] = df["posted_date"].dt.year

    # crosswalk on title_clean (batched semantic match -> ISCO + exposure + score)
    mapped = crosswalk.map_titles(df["title_clean"].fillna("").tolist())
    df = df.drop(columns=[c for c in mapped.columns if c in df.columns], errors="ignore")
    df = pd.concat([df.reset_index(drop=True), mapped.reset_index(drop=True)], axis=1)

    # AI-skill tag from skills_extracted + description_clean — split usage/building
    usage_flags, build_flags, terms = [], [], []
    for sk, desc in zip(df["skills_extracted"].fillna(""), df["description_clean"].fillna("")):
        usage, building, ts = detect_ai_skill(sk, desc)
        usage_flags.append(usage)
        build_flags.append(building)
        terms.append(";".join(ts))
    df["has_ai_usage"] = usage_flags
    df["has_ai_building"] = build_flags
    df["has_ai_skill"] = df["has_ai_usage"] | df["has_ai_building"]   # back-compat (usage OR building)
    df["ai_skill_terms"] = terms

    print("[2] TRANSFORM: crosswalk (ESCO semantic) + AI-skill tag (usage/building)")
    print(f"    match_method: {df['match_method'].value_counts().to_dict()}")
    print(f"    AI-usage:    {int(df['has_ai_usage'].sum())}/{len(df)} "
          f"({100*df['has_ai_usage'].mean():.1f}%)")
    print(f"    AI-building: {int(df['has_ai_building'].sum())}/{len(df)} "
          f"({100*df['has_ai_building'].mean():.1f}%)")

    # (exposure already attached by the crosswalk — no separate ILO merge)

    # write dated silver
    keep = ["posting_id", "title_clean", "city", "posted_date", "year",
            "seniority", "cluster_name", "isco08_4digit", "match_method",
            "matched_label", "match_score", "needs_review",
            "has_ai_usage", "has_ai_building", "has_ai_skill", "ai_skill_terms",
            "occupation_name", "exposure_category", "exposure_order",
            "mean_task_score", "sd_task_score", "exposure_imputed"]
    df = df[[c for c in keep if c in df.columns]]
    day = date.today().isoformat()
    out_dir = os.path.join(SILVER_DIR, f"dt={day}")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "de_tech_jobs.csv")
    df.to_csv(path, index=False)
    print(f"[3] SILVER: wrote {len(df)} rows -> {path}")

    # preview: usage vs building by exposure band
    mapped_rows = df[df["match_method"] != "unmapped"]
    print("\n[preview] AI-usage / AI-building % by exposure band")
    g = (mapped_rows.groupby("exposure_category")
         .agg(postings=("has_ai_usage", "size"),
              usage_pct=("has_ai_usage", lambda x: round(100 * x.mean(), 1)),
              building_pct=("has_ai_building", lambda x: round(100 * x.mean(), 1))))
    print(g.to_string())


if __name__ == "__main__":
    main()