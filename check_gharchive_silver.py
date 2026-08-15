#!/usr/bin/env python3
"""
check_gharchive_silver.py — audit the GitHub-pillar silver layer.

The GitHub equivalent of check_silver.py: it changes nothing, it validates.
Fails loudly (exit 1) if any invariant is broken, so a future change can't
silently reintroduce duplicates, break the numerator/denominator relationship,
or ship nulls.

Canonical layout (see schema doc):
  ADOPTION  ->  {silver}/gharchive/matches.csv , totals.csv
  QUALITY   ->  pooled {silver}/gharchive_day_*/pr_outcomes.csv , pr_reviews.csv

Run:  python check_gharchive_silver.py            # defaults to data/silver
      python check_gharchive_silver.py --silver data/silver
"""
import argparse, glob, os, sys
import pandas as pd

REVIEW_STATES = {"approved", "changes_requested", "commented", "dismissed", ""}
CLASSES = {"ai_agent", "baseline"}
CHURN_CLASSES = {"ai_agent", "ai_coauthor", "human"}

fails = []          # collected failure messages -> non-zero exit
def check(ok, label, detail=""):
    print(f"    [{'PASS' if ok else 'FAIL'}] {label}" + (f"  — {detail}" if detail else ""))
    if not ok:
        fails.append(label)

def as_bool_series(s):
    return s.astype(str).str.strip().str.lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--silver", default="data/silver")
    a = ap.parse_args()
    G = os.path.join(a.silver, "gharchive")

    print("=" * 62)
    print("GH ARCHIVE SILVER CHECK")
    print("=" * 62)

    # ---------------- [1] adoption: matches.csv ----------------
    print("\n[1] ADOPTION — matches.csv")
    mpath = os.path.join(G, "matches.csv")
    m = pd.read_csv(mpath)
    need = {"sha", "month", "repo", "coauthor_ai", "ai_agent", "selfadmit_phrase"}
    check(need.issubset(m.columns), "required columns present",
          f"missing {need - set(m.columns)}" if not need.issubset(m.columns) else f"{len(m)} rows")
    check(m["month"].notna().all(), "no null month")
    # dedup invariant: SHA unique (blank shas allowed, they can't be deduped)
    dup = m[m.sha.astype(str) != ""].sha.duplicated().sum()
    check(dup == 0, "no duplicate sha (dedup holds)", f"{dup} duplicate SHAs" if dup else "")
    check(m["month"].astype(str).str.match(r"^\d{4}-\d{2}$").all(), "month is YYYY-MM")

    # ---------------- [2] adoption: totals.csv (denominator) ----------------
    print("\n[2] ADOPTION — totals.csv (denominator)")
    t = pd.read_csv(os.path.join(G, "totals.csv"))
    check({"month", "n_commits", "n_pr_events"}.issubset(t.columns), "required columns present")
    check((t["n_commits"] > 0).all(), "n_commits > 0 for every month")
    # numerator <= denominator, per month
    ai_by_month = m.groupby("month").size()
    merged = t.set_index("month").join(ai_by_month.rename("n_ai")).fillna({"n_ai": 0})
    bad = merged[merged.n_ai > merged.n_commits]
    check(len(bad) == 0, "AI matches <= n_commits every month (numerator <= denominator)",
          f"{len(bad)} months violate" if len(bad) else "")

    # ---------------- [3] adoption: ai_share by year (info) ----------------
    print("\n[3] ADOPTION — ai_share by year (info)")
    merged["year"] = merged.index.str[:4]
    yr = merged.groupby("year").agg(n_ai=("n_ai", "sum"), n_commits=("n_commits", "sum"))
    yr["ai_share_pct"] = (100 * yr.n_ai / yr.n_commits).round(3)
    print(yr.to_string())

    # ---------------- [4] quality: pooled pr_outcomes ----------------
    print("\n[4] QUALITY — pooled pr_outcomes (gharchive_day_*)")
    opaths = sorted(glob.glob(os.path.join(a.silver, "gharchive_day_*", "pr_outcomes.csv")))
    check(len(opaths) > 0, "found day folders", f"{len(opaths)} days")
    frames = []
    for p in opaths:
        df = pd.read_csv(p)
        # dedup invariant is WITHIN a day (parse-time guarantee)
        d = df.duplicated(["repo", "pr_number"]).sum()
        check(d == 0, f"no dup (repo,pr_number) in {os.path.basename(os.path.dirname(p))}",
              f"{d} dups" if d else "")
        frames.append(df)
    o = pd.concat(frames, ignore_index=True)
    check(o["merged"].notna().all() and o["author_class"].notna().all(),
          "no null merged / author_class")
    check(set(as_bool_series(o["merged"]).unique()) <= {"true", "false"},
          "merged is boolean")
    check(set(o["author_class"].unique()) <= CLASSES, "author_class in {ai_agent, baseline}")
    n_agent = (o.author_class == "ai_agent").sum()
    print(f"    pooled PRs: {len(o):,} | ai_agent: {n_agent} | days: {len(opaths)}")

    # ---------------- [5] quality: pooled pr_reviews ----------------
    print("\n[5] QUALITY — pooled pr_reviews")
    rpaths = sorted(glob.glob(os.path.join(a.silver, "gharchive_day_*", "pr_reviews.csv")))
    r = pd.concat([pd.read_csv(p) for p in rpaths], ignore_index=True) if rpaths else pd.DataFrame()
    if len(r):
        check(set(r["state"].fillna("").unique()) <= REVIEW_STATES, "review state values known",
              f"unexpected {set(r['state'].fillna('').unique()) - REVIEW_STATES}")
        check(set(r["pr_author_class"].unique()) <= CLASSES, "pr_author_class valid")
    else:
        print("    (no review rows)")

    # ---------------- [6] churn: churn_events.csv ----------------
    print("\n[6] CHURN — churn_events.csv")
    cpath = os.path.join(a.silver, "churn", "churn_events.csv")
    if os.path.exists(cpath):
        ch = pd.read_csv(cpath)
        need = {"repo", "sha", "author_class", "file", "churn", "followup_churn"}
        check(need.issubset(ch.columns), "required columns present",
              f"{len(ch)} rows" if need.issubset(ch.columns) else f"missing {need - set(ch.columns)}")
        check(ch[["sha", "author_class", "file"]].notna().all().all(),
              "no null sha / author_class / file")
        check(set(ch["author_class"].unique()) <= CHURN_CLASSES,
              "author_class in {ai_agent, ai_coauthor, human}",
              f"unexpected {set(ch['author_class'].unique()) - CHURN_CLASSES}")
        check((ch["churn"] >= 0).all() and (ch["followup_churn"] >= 0).all(),
              "churn and followup_churn >= 0")
        # info: per-repo AI share (a finding, not a failure)
        share = ch.assign(ai=ch.author_class != "human").groupby("repo").ai.mean().mul(100).round(1)
        print("    AI share by repo:", share.to_dict())
    else:
        print("    (no churn_events.csv — churn pipeline not run)")

    # ---------------- verdict ----------------
    print("\n" + "=" * 62)
    if fails:
        print(f"RESULT: FAIL — {len(fails)} check(s) failed: {fails}")
        sys.exit(1)
    print("RESULT: PASS — silver is clean")


if __name__ == "__main__":
    main()