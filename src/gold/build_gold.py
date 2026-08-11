#!/usr/bin/env python3
"""
Build the GOLD layer (CSV) from silver.  Source-agnostic: reads whatever
silver files match the glob, so it works for Kaggle now and other sources later.

Reads : data/silver/kaggle/dt=*/de_jobs.csv   (override with arg 1)
Writes: data/gold/{dim_occupation,dim_date,fact_job_postings,mart_ai_by_exposure}.csv

Run from project root:
    python3 -m src.gold.build_gold
"""
import glob, os, sys
import pandas as pd

SILVER_GLOB = sys.argv[1] if len(sys.argv) > 1 else "data/silver/kaggle/dt=*/de_jobs.csv"
GOLD_DIR = "data/gold"


def main():
    files = glob.glob(SILVER_GLOB)
    if not files:
        sys.exit(f"no silver files match {SILVER_GLOB}")
    print(f"[read] {len(files)} silver file(s)")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)

    # normalise + derive keys
    df["isco08_4digit"] = df["isco08_4digit"].astype(str)
    df = df[df["isco08_4digit"] != "unmapped"].copy()
    df["has_ai_skill"] = df["has_ai_skill"].fillna(False).astype(bool)
    df["date_key"] = pd.to_datetime(df["date_published"], errors="coerce").dt.date
    if "year" not in df.columns:
        df["year"] = pd.to_datetime(df["date_published"], errors="coerce").dt.year
    df["isco_2digit"] = df["isco08_4digit"].str[:2]

    os.makedirs(GOLD_DIR, exist_ok=True)

    # dim_occupation — exposure stored ONCE per occupation
    dim_occ = (df[["isco08_4digit", "isco_2digit", "occupation_name",
                   "exposure_category", "exposure_order", "mean_task_score"]]
               .drop_duplicates("isco08_4digit"))

    # dim_date — one row per day
    dim_date = pd.DataFrame({"date_key": sorted(df["date_key"].dropna().unique())})
    dim_date["year"] = pd.to_datetime(dim_date["date_key"]).dt.year
    dim_date["month"] = pd.to_datetime(dim_date["date_key"]).dt.month

    # fact_job_postings — measures + foreign keys (use job_id as the posting key)
    fact = df[["job_id", "isco08_4digit", "date_key", "year",
               "city", "has_ai_skill", "match_method"]].copy()

    # mart — AI-skill demand by exposure band (the serving answer)
    m = fact.merge(dim_occ, on="isco08_4digit")
    mart = (m.groupby(["exposure_order", "exposure_category"])
              .agg(postings=("job_id", "count"),
                   ai_skill_postings=("has_ai_skill", "sum"),
                   avg_exposure=("mean_task_score", "mean"))
              .reset_index())
    mart["ai_penetration_pct"] = (100 * mart["ai_skill_postings"] / mart["postings"]).round(1)
    mart = mart.sort_values("exposure_order", ascending=False)

    for name, t in [("dim_occupation", dim_occ), ("dim_date", dim_date),
                    ("fact_job_postings", fact), ("mart_ai_by_exposure", mart)]:
        t.to_csv(f"{GOLD_DIR}/{name}.csv", index=False)
        print(f"[gold] {name:<20} {len(t):>4} rows")

    print("\nmart_ai_by_exposure:")
    print(mart[["exposure_category", "postings", "ai_skill_postings",
                "ai_penetration_pct", "avg_exposure"]].to_string(index=False))


if __name__ == "__main__":
    main()