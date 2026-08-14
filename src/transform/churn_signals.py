#!/usr/bin/env python3
"""
churn_signals.py — code-quality (durability) signal from real git history.

Answers the question merge-rate can't: does AI-touched code get REWRITTEN more
soon after? Merge rate measures acceptance; this measures whether the code
survived.

Design (the honest one):
  - Walk each repo commit-by-commit with PyDriller.
  - Classify each commit: `ai` if the author/committer is a known AI agent OR
    the message credits AI (Co-authored-by trailer); else `human`.
    (Same is_ai_agent / commit_signals rules as the GH Archive pillar — one
    source of truth. Caveat: catches agent + AI-credited commits, NOT silent
    Copilot use.)
  - SILVER: one row per (commit, file) touched -> churn_events.csv.
  - SIGNAL: follow-up churn. For each file touch, sum the churn (added+deleted)
    that lands on the SAME file within the next N days, by ANYONE. If AI-touched
    files draw more follow-up churn than human-touched files, that's the
    "AI code needs fixing" signal — and it correctly attributes a human's repair
    of AI code to the AI touch, not the human.

Run:
  python -m src.transform.churn_signals \
      https://github.com/owner/repo1 https://github.com/owner/repo2 \
      --outdir data/silver/churn --window-days 14 --since-days 365
"""
import argparse, csv, os
from datetime import datetime, timedelta, timezone

import re
from pydriller import Repository
COAUTHOR_LINE = re.compile(r'^\s*co-authored-by:.*', re.IGNORECASE | re.MULTILINE)
try:
    from src.transform.gharchive_signals import is_ai_agent, AI_TOOLS
except Exception:                                   # standalone fallback
    import re
    _STEMS = {"copilot-swe-agent","github-copilot","devin-ai-integration",
              "cursoragent","cursor[bot]","sweep-ai","codegen-sh",
              "openhands-agent","gemini-code-assist","claude[bot]","codex[bot]"}
    AI_TOOLS = ["copilot","chatgpt","claude","cursor","devin","aider","codeium","gemini","codex"]
    def is_ai_agent(v):
        v = (v or "").lower().replace("%5b","[").replace("%5d","]")
        return any(s in v for s in _STEMS)


def classify(commit) -> str:
    """ai_agent = an AI agent AUTHORED it; ai_coauthor = a human authored with
    AI assistance (real Co-authored-by trailer naming an agent); else human."""
    a = commit.author
    # authored by a known AI agent (author identity only — never committer)
    if a and (is_ai_agent(a.email) or is_ai_agent(a.name)):
        return "ai_agent"
    # AI-assisted: a real "Co-authored-by:" trailer LINE naming an AI agent/tool
    for line in COAUTHOR_LINE.findall(commit.msg or ""):
        low = line.lower()
        if is_ai_agent(low) or any(t in low for t in AI_TOOLS):
            return "ai_coauthor"
    return "human"


def walk_repo(url, events, since_days=None):
    kwargs = {}
    if since_days:
        kwargs["since"] = datetime.now(timezone.utc) - timedelta(days=since_days)
    name = url.rstrip("/").split("/")[-1].replace(".git", "")
    n = 0
    for c in Repository(url, **kwargs).traverse_commits():
        cls = classify(c)
        n += 1
        for f in c.modified_files:
            path = f.new_path or f.old_path
            if not path:
                continue
            events.append({
                "repo": name, "sha": c.hash[:12],
                "date": c.author_date.astimezone(timezone.utc).isoformat(),
                "author_class": cls, "file": path,
                "added": f.added_lines, "deleted": f.deleted_lines,
                "churn": f.added_lines + f.deleted_lines,
            })
    print(f"    {name}: {n} commits")


def followup_churn(events, window_days=14):
    """For each file touch, sum churn on the same file within the next window."""
    win = timedelta(days=window_days)
    by_file = {}
    for e in events:
        by_file.setdefault((e["repo"], e["file"]), []).append(e)
    for evs in by_file.values():
        evs.sort(key=lambda e: e["date"])
        times = [datetime.fromisoformat(e["date"]) for e in evs]
        churns = [e["churn"] for e in evs]
        for i, e in enumerate(evs):
            t0 = times[i]
            follow = sum(churns[j] for j in range(i + 1, len(evs))
                         if t0 < times[j] <= t0 + win)
            e["followup_churn"] = follow


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repos", nargs="+", help="repo URLs or local paths")
    ap.add_argument("--outdir", default="data/silver/churn")
    ap.add_argument("--window-days", type=int, default=14)
    ap.add_argument("--since-days", type=int, default=None,
                    help="only walk commits newer than N days (speed)")
    a = ap.parse_args()

    print("=" * 60)
    print(f"CHURN SIGNALS  —  {len(a.repos)} repo(s), {a.window_days}-day window")
    print("=" * 60)

    events = []
    for url in a.repos:
        try:
            walk_repo(url, events, a.since_days)
        except Exception as ex:
            print(f"    SKIP {url}: {ex}")

    followup_churn(events, a.window_days)

    # ---- write silver ----
    os.makedirs(a.outdir, exist_ok=True)
    path = os.path.join(a.outdir, "churn_events.csv")
    cols = ["repo", "sha", "date", "author_class", "file",
            "added", "deleted", "churn", "followup_churn"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(events)
    print(f"\nwrote {len(events)} file-touches -> {path}")

    # ---- signal report: three classes, median-based (robust to outliers) ----
    import statistics as st
    print("\n--- follow-up churn by author_class (the signal) ---")
    classes = ("ai_agent", "ai_coauthor", "human")
    by_cls = {c: [e for e in events if e["author_class"] == c] for c in classes}
    for c in classes:
        evs = by_cls[c]
        if not evs:
            continue
        med_size = st.median(e["churn"] for e in evs)
        med_follow = st.median(e["followup_churn"] for e in evs)
        mean_follow = sum(e["followup_churn"] for e in evs) / len(evs)
        print(f"  {c:12s}: touches={len(evs):6d}  median_commit_churn={med_size:6.0f}  "
              f"median_followup={med_follow:6.0f}  mean_followup={mean_follow:7.1f}")

    # ---- Fix 2: per-repo AI share (high share = a finding, not an error) ----
    print("\n--- AI share by repo (agent + coauthor) ---")
    repos = sorted({e["repo"] for e in events})
    for r in repos:
        re_ = [e for e in events if e["repo"] == r]
        ai = sum(1 for e in re_ if e["author_class"] != "human")
        print(f"  {r:24s}: {ai:6d}/{len(re_):6d} touches AI ({100*ai/len(re_):4.1f}%)")

    # ---- Fix 3: follow-up churn WITHIN size buckets (control for size) ----
    print(f"\n--- mean follow-up churn ({a.window_days}d) by size bucket x class ---")
    def bucket(n):
        return ("0-20" if n <= 20 else "20-100" if n <= 100 else
                "100-500" if n <= 500 else "500+")
    buckets = ["0-20", "20-100", "100-500", "500+"]
    print(f"  {'bucket':8s} " + "".join(f"{c:>14s}" for c in classes))
    for b in buckets:
        row = f"  {b:8s} "
        for c in classes:
            evs = [e for e in by_cls[c] if bucket(e["churn"]) == b]
            row += (f"{sum(e['followup_churn'] for e in evs)/len(evs):9.1f}(n={len(evs)})"
                    if evs else f"{'—':>14s}")
        print(row)
    print("\n  compare AI vs human WITHIN a bucket: that isolates rework from size")


if __name__ == "__main__":
    main()