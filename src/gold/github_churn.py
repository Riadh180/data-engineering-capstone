#!/usr/bin/env python3
"""
gold/github_churn.py — code-durability gold from the churn silver.

Does AI-touched code get rewritten more soon after? Measures follow-up churn
(lines changed on the same file within 14 days) by author_class, controlled for
the size of the original change — because bigger changes attract more follow-up
regardless of author.

  ai_agent    = commit authored by a known AI agent
  ai_coauthor = human authored WITH AI credited (assisted)
  human       = no AI signal

Source = data/silver/churn/churn_events.csv

Outputs:
  gold/github_churn_by_bucket.csv   (author_class x size_bucket -> mean/median followup)
  gold/github_ai_share_by_repo.csv  (how AI-heavy each repo is)

Run:  python -m src.gold.github_churn
"""
import argparse, os
import pandas as pd

BUCKETS = [0, 20, 100, 500, 10**9]
LABELS = ["0-20", "20-100", "100-500", "500+"]
CLASSES = ["ai_agent", "ai_coauthor", "human"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--silver", default="data/silver/churn/churn_events.csv")
    ap.add_argument("--outdir", default="data/gold")
    a = ap.parse_args()

    c = pd.read_csv(a.silver)
    print(f"    {len(c):,} file-touches across {c.repo.nunique()} repos")

    c["size_bucket"] = pd.cut(c["churn"], BUCKETS, labels=LABELS, include_lowest=True)

    # ---- follow-up churn by class x size bucket (the durability signal) ----
    g = (c.groupby(["size_bucket", "author_class"], observed=True)
           .agg(n=("followup_churn", "size"),
                mean_followup=("followup_churn", "mean"),
                median_followup=("followup_churn", "median"))
           .reset_index())
    g["mean_followup"] = g["mean_followup"].round(1)

    # ---- AI share by repo (adoption varies wildly by project) ----
    share = (c.assign(ai=c.author_class != "human")
               .groupby("repo")
               .agg(touches=("ai", "size"), ai_touches=("ai", "sum"))
               .reset_index())
    share["ai_pct"] = (100 * share.ai_touches / share.touches).round(1)

    os.makedirs(a.outdir, exist_ok=True)
    g.to_csv(os.path.join(a.outdir, "github_churn_by_bucket.csv"), index=False)
    share.to_csv(os.path.join(a.outdir, "github_ai_share_by_repo.csv"), index=False)

    print("\n=== mean follow-up churn (14d) WITHIN size buckets ===")
    pivot = g.pivot(index="size_bucket", columns="author_class", values="mean_followup")
    pivot = pivot.reindex(columns=[c_ for c_ in CLASSES if c_ in pivot.columns])
    print(pivot.to_string())
    print("\n  (n per cell)")
    counts = g.pivot(index="size_bucket", columns="author_class", values="n")
    counts = counts.reindex(columns=[c_ for c_ in CLASSES if c_ in counts.columns])
    print(counts.to_string())
    print("\n=== AI share by repo ===")
    print(share.to_string(index=False))
    print(f"\nwrote -> {a.outdir}/github_churn_by_bucket.csv , github_ai_share_by_repo.csv")


if __name__ == "__main__":
    main()
