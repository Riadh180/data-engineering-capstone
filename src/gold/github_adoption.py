#!/usr/bin/env python3
"""
gold/github_adoption.py — AI-adoption trend from the GitHub silver.

Reads the adoption silver (numerator + denominator) and produces the headline
metric: ai_share = AI-signal commits / all commits, by year and by month.

  numerator   = matches.csv  (one row per AI-signal commit)
  denominator = totals.csv   (distinct commits scanned per month)

Signal definition (the clean one): a commit counts as AI if coauthor_ai OR
ai_agent. selfadmit_phrase is excluded here — it's noisy; a --with-selfadmit
flag adds it if you want the looser definition.

Outputs:
  gold/github_adoption_by_year.csv
  gold/github_adoption_by_month.csv

Run:  python -m src.gold.github_adoption
"""
import argparse, os
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--silver", default="data/silver/gharchive")
    ap.add_argument("--outdir", default="data/gold")
    ap.add_argument("--with-selfadmit", action="store_true",
                    help="also count noisy selfadmit_phrase signals")
    a = ap.parse_args()

    m = pd.read_csv(os.path.join(a.silver, "matches.csv"))
    t = pd.read_csv(os.path.join(a.silver, "totals.csv"))

    # numerator: distinct AI-signal commits per month (clean = coauthor_ai OR ai_agent)
    sig = m["coauthor_ai"].fillna(False) | m["ai_agent"].fillna(False)
    if a.with_selfadmit:
        sig = sig | m["selfadmit_phrase"].fillna(False)
    ai = m[sig].drop_duplicates("sha")
    ai_by_month = ai.groupby("month").size().rename("n_ai_commits")

    # join to denominator
    g = t.set_index("month").join(ai_by_month).fillna({"n_ai_commits": 0})
    g["n_ai_commits"] = g["n_ai_commits"].astype(int)
    g["ai_share_pct"] = (100 * g["n_ai_commits"] / g["n_commits"]).round(4)
    g = g.reset_index().sort_values("month")

    # by month
    by_month = g[["month", "n_ai_commits", "n_commits", "ai_share_pct"]]

    # by year (sum first, then divide — the correct way to aggregate a rate)
    g["year"] = g["month"].str[:4]
    by_year = (g.groupby("year")
                 .agg(n_ai_commits=("n_ai_commits", "sum"),
                      n_commits=("n_commits", "sum"))
                 .reset_index())
    by_year["ai_share_pct"] = (100 * by_year.n_ai_commits / by_year.n_commits).round(4)

    os.makedirs(a.outdir, exist_ok=True)
    by_year.to_csv(os.path.join(a.outdir, "github_adoption_by_year.csv"), index=False)
    by_month.to_csv(os.path.join(a.outdir, "github_adoption_by_month.csv"), index=False)

    print("=== AI adoption by YEAR (headline) ===")
    print(by_year.to_string(index=False))
    print(f"\nwrote -> {a.outdir}/github_adoption_by_year.csv , github_adoption_by_month.csv")


if __name__ == "__main__":
    main()
