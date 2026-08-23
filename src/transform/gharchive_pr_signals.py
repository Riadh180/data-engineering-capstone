#!/usr/bin/env python3
"""
GH Archive - PR quality signals (ideas #1 merge-rate, #2 changes-requested).

Emits two slim silver tables, split by author_class (ai_agent vs baseline):
  pr_outcomes.csv  - one row per CLOSED pull request -> merge rate, size, time-open
  pr_reviews.csv   - one row per pull-request review  -> changes-requested rate

Agent identity comes from gharchive_signals.is_ai_agent (single source of truth).
Only AUTONOMOUS AI-AGENT PRs are labelled ai_agent; human-with-Copilot PRs are not.

Input/output work on both local paths and s3:// (via fsspec/s3fs). Output goes to
<LAKE>/silver/github/pr_quality[/dt=<dt>]; pass --dt to write a dated partition.
"""
import argparse, csv, io, json, os
from datetime import datetime

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass

import fsspec
from src.common.config import lake_path, lake_makedirs, lake_glob
from src.transform.gharchive_signals import is_ai_agent   # single source of truth


def author_class(login: str) -> str:
    return "ai_agent" if is_ai_agent(login) else "baseline"

def open_any(path):
    return fsspec.open(path, "rt", compression="infer",
                       encoding="utf-8", errors="replace").open()

def expand_inputs(paths):
    out = []
    for p in paths:
        out.extend(lake_glob(p) if any(ch in p for ch in "*?[") else [p])
    return out

def month_of(ts: str) -> str:
    return (ts or "")[:7]

def hours_open(created, closed):
    try:
        c = datetime.fromisoformat(created.replace("Z", "+00:00"))
        d = datetime.fromisoformat(closed.replace("Z", "+00:00"))
        return round((d - c).total_seconds() / 3600, 1)
    except Exception:
        return ""

def parse_file(path, outcomes, reviews):
    for line in open_any(path):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        etype = e.get("type")
        repo = e.get("repo", {}).get("name", "")
        p = e.get("payload", {})

        if etype == "PullRequestEvent" and p.get("action") == "closed":
            pr = p.get("pull_request", {}) or {}
            login = (pr.get("user") or {}).get("login", "")
            outcomes[(repo, pr.get("number", ""))] = {
                "month": month_of(e.get("created_at", "")),
                "repo": repo, "pr_number": pr.get("number", ""),
                "author_login": login, "author_class": author_class(login),
                "merged": bool(pr.get("merged")),
                "size_lines": (pr.get("additions") or 0) + (pr.get("deletions") or 0),
                "changed_files": pr.get("changed_files", ""),
                "hours_open": hours_open(pr.get("created_at", ""), pr.get("closed_at", "")),
            }
        elif etype == "PullRequestReviewEvent":
            review = p.get("review", {}) or {}
            pr = p.get("pull_request", {}) or {}
            login = (pr.get("user") or {}).get("login", "")
            reviews.append({
                "month": month_of(e.get("created_at", "")),
                "repo": repo, "pr_number": pr.get("number", ""),
                "pr_author_class": author_class(login),
                "state": review.get("state", ""),
            })

def write_csv(rows, path, fields):
    lake_makedirs(os.path.dirname(path) or ".")
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader(); w.writerows(rows)
    with fsspec.open(path, "w", encoding="utf-8") as f:
        f.write(buf.getvalue())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="GH Archive file(s), local or s3://")
    ap.add_argument("--outdir", default=lake_path("silver/github/pr_quality"))
    ap.add_argument("--dt", default=None, help="partition date -> writes under dt=<dt>/")
    a = ap.parse_args()

    outdir = f"{a.outdir}/dt={a.dt}" if a.dt else a.outdir
    files = expand_inputs(a.files)

    outcomes, reviews = {}, []
    for path in files:
        parse_file(path, outcomes, reviews)
    write_csv(list(outcomes.values()), f"{outdir}/pr_outcomes.csv",
              ["month", "repo", "pr_number", "author_login", "author_class",
               "merged", "size_lines", "changed_files", "hours_open"])
    write_csv(reviews, f"{outdir}/pr_reviews.csv",
              ["month", "repo", "pr_number", "pr_author_class", "state"])
    rows = list(outcomes.values())
    na = sum(1 for r in rows if r["author_class"] == "ai_agent")
    print(f"closed PRs: {len(rows)} ({na} ai_agent) | reviews: {len(reviews)}")
    print(f"wrote -> {outdir}/pr_outcomes.csv , pr_reviews.csv")

if __name__ == "__main__":
    main()