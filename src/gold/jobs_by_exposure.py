#!/usr/bin/env python3
"""
gold/jobs_by_exposure.py — jobs-pillar gold from the silver postings.

Emits the split AI signal per exposure band and year:
  ai_usage_rate    -> mean(has_ai_usage)     (uses AI as a tool at work)
  ai_building_rate -> mean(has_ai_building)   (engineers AI/ML — new AI jobs)
  avg_exposure     -> mean(mean_task_score)   (the clean, monotonic gradient)
  n_postings       -> demand volume

Also an occupation-level table (isco08_4digit) for correlations.

Reads the latest dated silver partition for each dataset (kaggle=general, tech).

Outputs:
  gold/jobs_by_exposure_band_year.csv
  gold/jobs_by_occupation.csv

Run:  python -m src.gold.jobs_by_exposure
"""
import argparse, glob, os
import pandas as pd


def latest_silver(base):
    parts = sorted(glob.glob(os.path.join(base, "dt=*")))
    if not parts:
        return None
    hits = glob.glob(os.path.join(parts[-1], "*.csv"))
    return hits[0] if hits else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--general", default="data/silver/kaggle")
    ap.add_argument("--tech", default="data/silver/tech")
    ap.add_argument("--outdir", default="data/gold")
    a = ap.parse_args()

    frames = []
    for label, base in [("general", a.general), ("tech", a.tech)]:
        p = latest_silver(base)
        if p:
            df = pd.read_csv(p, dtype={"isco08_4digit": str})
            df["dataset"] = label
            # back-compat: if an old silver lacks the split, derive from has_ai_skill
            if "has_ai_usage" not in df:
                df["has_ai_usage"] = df.get("has_ai_skill", False)
            if "has_ai_building" not in df:
                df["has_ai_building"] = False
            frames.append(df)
            print(f"    {label}: {len(df):,} rows  <- {p}")
    d = pd.concat(frames, ignore_index=True)
    d = d[d["match_method"] != "unmapped"].copy()

    # ---- band x year (trend table) ----
    band = (d.groupby(["dataset", "exposure_order", "exposure_category", "year"])
              .agg(n_postings=("has_ai_usage", "size"),
                   ai_usage_rate=("has_ai_usage", "mean"),
                   ai_building_rate=("has_ai_building", "mean"),
                   avg_exposure=("mean_task_score", "mean"))
              .reset_index()
              .sort_values(["dataset", "exposure_order", "year"],
                           ascending=[True, False, True]))
    for c in ["ai_usage_rate", "ai_building_rate", "avg_exposure"]:
        band[c] = band[c].round(4)

    # ---- occupation level (for correlations) ----
    occ = (d.groupby(["dataset", "isco08_4digit", "occupation_name",
                      "exposure_category", "exposure_order"])
             .agg(n_postings=("has_ai_usage", "size"),
                  ai_usage_rate=("has_ai_usage", "mean"),
                  ai_building_rate=("has_ai_building", "mean"),
                  mean_task_score=("mean_task_score", "mean"))
             .reset_index().sort_values("n_postings", ascending=False))
    for c in ["ai_usage_rate", "ai_building_rate"]:
        occ[c] = occ[c].round(4)

    os.makedirs(a.outdir, exist_ok=True)
    band.to_csv(os.path.join(a.outdir, "jobs_by_exposure_band_year.csv"), index=False)
    occ.to_csv(os.path.join(a.outdir, "jobs_by_occupation.csv"), index=False)

    # ---- report: pooled per dataset (honest, avoids per-year sparsity) ----
    for ds in d.dataset.unique():
        sub = d[d.dataset == ds]
        print(f"\n=== {ds}: AI-usage / AI-building by exposure band (pooled) ===")
        pooled = (sub.groupby(["exposure_order", "exposure_category"])
                    .agg(postings=("has_ai_usage", "size"),
                         usage_pct=("has_ai_usage", lambda s: round(100*s.mean(), 2)),
                         building_pct=("has_ai_building", lambda s: round(100*s.mean(), 2)),
                         avg_exposure=("mean_task_score", "mean"))
                    .reset_index().sort_values("exposure_order", ascending=False))
        pooled["avg_exposure"] = pooled["avg_exposure"].round(3)
        print(pooled.to_string(index=False))
    print(f"\nwrote -> {a.outdir}/jobs_by_exposure_band_year.csv , jobs_by_occupation.csv")


if __name__ == "__main__":
    main()