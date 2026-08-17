#!/usr/bin/env python3
"""
gold/github_pr_quality.py — PR-quality (acceptance) gold from the GitHub silver.

Two acceptance signals, both split by author_class and controlled for PR size:
  merge rate            <- pr_outcomes.csv  (mean of merged)
  changes-requested     <- pr_reviews.csv   (mean of state == changes_requested)

Size control matters: agent PRs are larger, and larger PRs merge less regardless
of author — so the headline is the WITHIN-size-bucket comparison, not the raw gap.

Source of truth = pooled data/silver/gharchive_day_* (the four full days).

Outputs:
  gold/github_merge_rate.csv            (author_class x size_bucket)
  gold/github_changes_requested.csv     (author_class)

Run:  python -m src.gold.github_pr_quality
"""
import argparse, glob, os
import pandas as pd

BUCKETS = [0, 20, 100, 500, 10**9]
LABELS = ["0-20", "20-100", "100-500", "500+"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--silver", default="data/silver")
    ap.add_argument("--outdir", default="data/gold")
    a = ap.parse_args()

    opaths = sorted(glob.glob(os.path.join(a.silver, "gharchive_day_*", "pr_outcomes.csv")))
    rpaths = sorted(glob.glob(os.path.join(a.silver, "gharchive_day_*", "pr_reviews.csv")))
    o = pd.concat([pd.read_csv(p) for p in opaths], ignore_index=True)
    r = pd.concat([pd.read_csv(p) for p in rpaths], ignore_index=True) if rpaths else pd.DataFrame()
    print(f"    pooled {len(o):,} PRs from {len(opaths)} days "
          f"({(o.author_class=='ai_agent').sum()} ai_agent)")

    # ---- merge rate: overall + within size buckets ----
    o["size_bucket"] = pd.cut(o["size_lines"], BUCKETS, labels=LABELS, include_lowest=True)

    overall = (o.groupby("author_class")
                 .agg(n_prs=("merged", "size"), merged_rate=("merged", "mean"),
                      median_size=("size_lines", "median"))
                 .reset_index())
    overall["merged_rate"] = overall["merged_rate"].round(4)

    bucketed = (o.groupby(["size_bucket", "author_class"], observed=True)
                  .agg(n_prs=("merged", "size"), merged_rate=("merged", "mean"))
                  .reset_index())
    bucketed["merged_rate"] = bucketed["merged_rate"].round(4)

    # ---- changes-requested rate ----
    if len(r):
        r["is_cr"] = (r["state"] == "changes_requested")
        cr = (r.groupby("pr_author_class")
                .agg(n_reviews=("is_cr", "size"),
                     changes_requested_rate=("is_cr", "mean"))
                .reset_index())
        cr["changes_requested_rate"] = cr["changes_requested_rate"].round(4)
    else:
        cr = pd.DataFrame()

    os.makedirs(a.outdir, exist_ok=True)
    bucketed.to_csv(os.path.join(a.outdir, "github_merge_rate.csv"), index=False)
    if len(cr):
        cr.to_csv(os.path.join(a.outdir, "github_changes_requested.csv"), index=False)

    print("\n=== merge rate OVERALL (note the size confound) ===")
    print(overall.to_string(index=False))
    print("\n=== merge rate WITHIN size buckets (the headline) ===")
    pivot = bucketed.pivot(index="size_bucket", columns="author_class",
                           values="merged_rate")
    counts = bucketed.pivot(index="size_bucket", columns="author_class", values="n_prs")
    print(pivot.to_string())
    print("\n  (n per cell)")
    print(counts.to_string())
    if len(cr):
        print("\n=== changes-requested rate by PR author class ===")
        print(cr.to_string(index=False))
    print(f"\nwrote -> {a.outdir}/github_merge_rate.csv , github_changes_requested.csv")


if __name__ == "__main__":
    main()
