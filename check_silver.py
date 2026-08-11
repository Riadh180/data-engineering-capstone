#!/usr/bin/env python3
"""
check_silver.py — one quality report for any silver file.

WHAT IT CHECKS (and why each matters):
  [1] Coverage        how many titles mapped to an ISCO code, and via which tier
                      (alias/exact = reliable, fuzzy = guess-prone, unmapped = none).
  [2] AI-skill        the AI-skill demand rate + which terms fired (spot noise).
  [3] Fuzzy accuracy  sample of the risky fuzzy-matched rows to eyeball correctness.
  [4] Exposure bands  AI-skill % by High/Mid/Low exposure — the actual finding.
  [5] Top unmapped    the highest-frequency titles still missing a code (grow rules).
  [6] Broken joins    rows that got a code but NO exposure (code absent from ILO file).
  [7] Null audit      missing values in the columns the analysis depends on.

USAGE:
  python3 check_silver.py <silver.csv> [title_column]
  python3 check_silver.py data/silver/kaggle/dt=2026-08-10/de_jobs.csv normalized_title
  python3 check_silver.py data/silver/tech/dt=2026-08-10/de_tech_jobs.csv title_clean
"""
import sys
import pandas as pd

path = sys.argv[1]
d = pd.read_csv(path)
if len(sys.argv) > 2:
    title_col = sys.argv[2]
else:
    title_col = next((c for c in ["normalized_title", "title_clean", "title"]
                      if c in d.columns), d.columns[0])
mapped_mask = d["match_method"] != "unmapped"

print("=" * 62)
print(f"SILVER CHECK: {path}")
print(f"rows: {len(d)}  |  title column: {title_col}")
print("=" * 62)

# [1] coverage
print("\n[1] COVERAGE (crosswalk)")
print("    by tier:", d["match_method"].value_counts().to_dict())
print(f"    mapped: {round(100*mapped_mask.mean())}%  "
      f"| unmapped: {round(100*(~mapped_mask).mean())}%")

# [2] AI-skill
print("\n[2] AI-SKILL DEMAND")
print(f"    rate: {round(100*d['has_ai_skill'].mean(),1)}%  "
      f"({int(d['has_ai_skill'].sum())}/{len(d)})")
hits = d[d["has_ai_skill"] == True]
print("    top terms:", hits["ai_skill_terms"].value_counts().head(15).to_dict())

# [3] fuzzy accuracy — how many, and how many landed with NO exposure (a red flag)
print("\n[3] FUZZY MAPPING (guess-prone tier — verify correctness)")
fz_rows = d[d["match_method"] == "esco_fuzzy"]
fz = fz_rows[[title_col, "occupation_name"]].drop_duplicates()
print(f"    total fuzzy rows: {len(fz_rows)}  ({round(100*len(fz_rows)/len(d),1)}% of all)")
print(f"    distinct fuzzy titles: {len(fz)}")
print(f"    fuzzy rows with NO exposure (bad code): {fz_rows['occupation_name'].isna().sum()}")
print("    --- full list of distinct fuzzy mappings ---")
if len(fz):
    print(fz.sort_values(title_col).to_string(index=False))

# [4] exposure breakdown — full ILO categories + the 0-1 exposure score
print("\n[4] AI-SKILL % BY EXPOSURE CATEGORY (finest -> coarsest)")
m = d[mapped_mask].copy()
g = (m.groupby(["exposure_order", "exposure_category"])
       .agg(postings=("has_ai_skill", "size"),
            ai_pct=("has_ai_skill", lambda x: round(100 * x.mean(), 1)),
            avg_exposure_0to1=("mean_task_score", lambda x: round(x.mean(), 2)))
       .sort_index(ascending=False))
print(g.to_string())

# [5] top unmapped
print("\n[5] TOP UNMAPPED TITLES (grow the crosswalk from these)")
un = d[~mapped_mask]
if len(un):
    print(un[title_col].value_counts().head(30).to_string())
else:
    print("    (nothing unmapped)")

# [6] broken joins — mapped to a code that isn't in the ILO exposure file
print("\n[6] BROKEN JOINS (mapped but no exposure attached)")
broken = d[mapped_mask & d["occupation_name"].isna()]
print(f"    {len(broken)} rows mapped to an ISCO code missing from the ILO file")
if len(broken):
    print("    codes:", broken["isco08_4digit"].value_counts().head(8).to_dict())

# [7] null audit — only among MAPPED rows (unmapped correctly have no exposure)
print("\n[7] NULL AUDIT (among mapped rows — unmapped are expected to be empty)")
audit = d[mapped_mask]
for col in ["isco08_4digit", "has_ai_skill", "exposure_category", "mean_task_score", "year"]:
    if col in d.columns:
        n = audit[col].isna().sum()
        flag = "  <-- check" if n else ""
        print(f"    {col:<18} nulls: {n}{flag}")