# Silver Layer — Schema & Canonical Layout

The silver layer holds cleaned, deduplicated, analysis-ready tables. Each table
below lists its **grain** (what one row means), columns, the **canonical
location**, and known limitations. Gold is built by aggregating these — no
cleanup step required, because silver is clean by construction (parse-time
dedup) and enforced by the check scripts.

Audits: `check_silver.py` (jobs) and `check_gharchive_silver.py` (GitHub). A
silver table is not "done" until its check passes.

---

## Jobs pillar

### `data/silver/kaggle/dt=YYYY-MM-DD/de_jobs.csv` (general) and `…/tech/…/de_tech_jobs.csv` (tech)
**Grain:** one job posting.
Occupation-coded and exposure-scored postings; the base for demand / skills /
pay analysis by exposure band.

| column | type | meaning |
|---|---|---|
| `normalized_title` / `title_clean` | str | cleaned job title |
| `isco08_4digit` | str | ISCO-08 occupation code (join key); may be null if unmapped |
| `occupation_name` | str | occupation name for that code |
| `match_method` | str | how mapped: `alias` / `esco_exact` / `esco_semantic` / `unmapped` |
| `match_score` | float | match confidence 0–1 (1.0 for alias/exact) |
| `needs_review` | bool | semantic match in the 0.85–0.88 review band |
| `exposure_category` | str | ILO band (Gradient 4 … Not Exposed / Imputed) |
| `exposure_order` | int | sortable band (4 … -1); null for imputed |
| `mean_task_score` | float | AI-exposure score 0–1 |
| `sd_task_score` | float | task-score spread within the occupation |
| `exposure_imputed` | bool | True if exposure came from ISCO parent, not ILO directly |
| `has_ai_skill` | bool | posting mentions AI skills |
| `year` | int | posting year (for trends) |

**Limitations:** general-dataset AI-skill mentions are sparse (report as
direction, not rate); tech dataset is alias-dominated (~⅔), so its band split
reflects the alias assignment.

---

## GitHub pillar

Two independent signals from two different samples — **do not pool across them.**

### ADOPTION — canonical: `data/silver/gharchive/`

#### `matches.csv` — the adoption *numerator*
**Grain:** one commit carrying an AI-authorship signal. Deduplicated on `sha`.

| column | type | meaning |
|---|---|---|
| `created_at` | str | event timestamp |
| `month` | str | `YYYY-MM` (bucket) |
| `repo` | str | repository |
| `actor` / `author_name` | str | pushing actor / commit author |
| `sha` | str | commit hash — **unique** (dedup key) |
| `coauthor_ai` | bool | Co-authored-by trailer names an AI tool (trust) |
| `ai_agent` | bool | actor or author is a known AI agent (trust) |
| `selfadmit_phrase` | bool | prose claims AI use (noisy — suggestive only) |
| `message` | str | commit message (truncated) |

#### `totals.csv` — the adoption *denominator*
**Grain:** one month. `ai_share = (matches per month) / n_commits`.

| column | type | meaning |
|---|---|---|
| `month` | str | `YYYY-MM` |
| `n_commits` | int | distinct commits scanned that month |
| `n_pr_events` | int | PR events scanned that month |

**Sample:** monthly, one hour per month, 2023-01 → 2025-07.
**Invariant:** AI matches ≤ `n_commits` per month (enforced by check).
**Limitations:** one hour/month → monthly rates are noisy (use yearly);
`selfadmit` is noisy; trust `coauthor_ai` + `ai_agent`.

### QUALITY — canonical: pooled `data/silver/gharchive_day_*/`

#### `pr_outcomes.csv` — merge-rate signal
**Grain:** one closed PR. Deduplicated on `(repo, pr_number)` within a day.

| column | type | meaning |
|---|---|---|
| `month` | str | `YYYY-MM` |
| `repo`, `pr_number` | str/int | PR identity (dedup key, within day) |
| `author_login` | str | PR author |
| `author_class` | str | `ai_agent` or `baseline` |
| `merged` | bool | was the PR merged (the outcome) |
| `size_lines` | int | additions + deletions |
| `changed_files`, `hours_open` | int/float | PR size / time open |

#### `pr_reviews.csv` — changes-requested signal
**Grain:** one PR review.

| column | type | meaning |
|---|---|---|
| `month`, `repo`, `pr_number` | | PR identity |
| `pr_author_class` | str | `ai_agent` or `baseline` (PR author, not reviewer) |
| `state` | str | `approved` / `changes_requested` / `commented` / … |

**Sample:** four full days (2024-11-15, 2025-02-15, 2025-04-15, 2025-06-15),
pooled = 4 independent months.
**Limitations:** captures **autonomous-agent** PRs only (~0.08% of all PRs);
human-with-Copilot PRs look like `baseline`. Merge rate measures *acceptance*,
not code quality (confounded by maintainers distrusting bots).

---

## Canonical-layout rules (why the folders are what they are)

- **Adoption** always reads `gharchive/matches.csv` + `totals.csv`. Never the
  monthly-hours PR files (deleted — they were a thin, different sample).
- **Quality** always reads pooled `gharchive_day_*/`. Never `gharchive/pr_*`.
- Raw bronze for the four quality days was deleted after parsing
  (stream-and-discard); silver is the record.
- No two silver folders may contain the same day (the `gharchive_fullday`
  duplicate of `gharchive_day_2025-06-15` was removed).

## Banked extensions (not yet built)
- Full-timeline quality trend (quarterly, 2023→now) via BigQuery.
- Follow-up churn on AI-touched files (GitHub API) — the real code-quality test.
- "Is the merge-rate gap closing or widening over time" — reads off the trend.
