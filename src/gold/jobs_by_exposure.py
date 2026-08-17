#!/usr/bin/env python3
"""
gold/jobs_by_exposure.py — jobs-pillar gold from the silver postings.

Answers the three jobs questions, sliced by exposure band and year:
  demand  -> n_postings
  skills  -> ai_skill_rate  (mean of has_ai_skill)
  pay     -> salary_rate    (mean of has_salary_info; a disclosure rate, not
                             a pay level — the silver has a flag, not amounts)

Also emits an occupation-level table (isco08_4digit) — the grain you need for
CORRELATIONS (band-level has too few rows to correlate).

Reads the latest dated silver partition for each dataset.

Outputs:
  gold/jobs_by_exposure_band_year.csv
  gold/jobs_by_occupation.csv

Run:  python -m src.gold.jobs_by_exposure
"""
import argparse, glob, os
import pandas as pd


def latest_silver(base):
    """Newest dt=YYYY-MM-DD partition under a silver dataset dir."""
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
            frames.append(df)
            print(f"    {label}: {len(df):,} rows  <- {p}")
    d = pd.concat(frames, ignore_index=True)

    # mapped rows only (unmapped have no exposure to analyse)
    d = d[d["match_method"] != "unmapped"].copy()

    # ---- band x year (the trend/headline table) ----
    band = (d.groupby(["dataset", "exposure_order", "exposure_category", "year"])
              .agg(n_postings=("has_ai_skill", "size"),
                   ai_skill_rate=("has_ai_skill", "mean"),
                   salary_disclosed_rate=("has_salary_info", "mean"),
                   avg_exposure=("mean_task_score", "mean"))
              .reset_index()
              .sort_values(["dataset", "exposure_order", "year"], ascending=[True, False, True]))
    for c in ["ai_skill_rate", "salary_disclosed_rate", "avg_exposure"]:
        band[c] = band[c].round(4)

    # ---- occupation level (grain for correlations) ----
    occ = (d.groupby(["isco08_4digit", "occupation_name",
                      "exposure_category", "exposure_order"])
             .agg(n_postings=("has_ai_skill", "size"),
                  ai_skill_rate=("has_ai_skill", "mean"),
                  mean_task_score=("mean_task_score", "mean"))
             .reset_index()
             .sort_values("n_postings", ascending=False))
    occ["ai_skill_rate"] = occ["ai_skill_rate"].round(4)

    os.makedirs(a.outdir, exist_ok=True)
    band.to_csv(os.path.join(a.outdir, "jobs_by_exposure_band_year.csv"), index=False)
    occ.to_csv(os.path.join(a.outdir, "jobs_by_occupation.csv"), index=False)

    # ---- report: pooled band view (across years) so the gradient is visible ----
    print("\n=== AI-skill demand by exposure band (pooled across years) ===")
    pooled = (d.groupby(["exposure_order", "exposure_category"])
                .agg(postings=("has_ai_skill", "size"),
                     ai_skill_pct=("has_ai_skill", lambda s: round(100*s.mean(), 2)),
                     avg_exposure=("mean_task_score", "mean"))
                .reset_index().sort_values("exposure_order", ascending=False))
    pooled["avg_exposure"] = pooled["avg_exposure"].round(3)
    print(pooled.to_string(index=False))
    print(f"\nwrote -> {a.outdir}/jobs_by_exposure_band_year.csv , jobs_by_occupation.csv")


if __name__ == "__main__":
    main()
