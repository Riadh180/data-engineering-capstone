#!/usr/bin/env python3
"""
esco_crosswalk.py — German job title  ->  ISCO-08 4-digit code, by MEANING.

Why this exists
---------------
The fuzzy (rapidfuzz) tier matches on shared tokens, so it anchors on generic
wrapper words: "mitarbeiter logistik" shares the token 'mitarbeiter' with
"Technical and Medical Sales..." and maps there, though it means a logistics job.
Embeddings compare the WHOLE phrase by meaning against the ESCO occupation
taxonomy, which dissolves that whole class of error. This module is the
replacement for the fuzzy tier — not a patch on top of it.

Pipeline of tiers (high precision first, cheap first):
  1. esco_exact     normalized title == a normalized ESCO label     (precision ~1.0)
  2. esco_semantic  cosine(title, nearest ESCO label) >= ACCEPT       (the real fix)
  3. unmapped       below threshold -> routed to review with its score

Every row carries its match_method, the ESCO label it matched, and the cosine
score, so you tune the threshold from evidence (a score histogram) instead of
guessing, and audit any single mapping.

Key design choices (the parts that make it correct, not just clever):
  * Match against ESCO PREFERRED **and ALTERNATIVE** labels. ESCO lists many
    real-world synonyms per occupation ("Verkäufer", "Einzelhandelskaufmann"…),
    all pointing at one ISCO code. Using alt labels is the single biggest driver
    of recall+precision here.
  * multilingual-e5 embeddings with the required "query:"/"passage:" prefixes.
    Title = query, ESCO label = passage. It's a retrieval task; use a retrieval
    model. (Swap to paraphrase-multilingual-mpnet via MODEL_STYLE="plain".)
  * Normalization strips DECORATION that isn't the occupation — gender markers
    (m/w/d), and employment-form / seniority prefixes (ausbildung, werkstudent,
    senior, stellvertretender…) — so the embedding focuses on the occupational
    core. This is *cleaning*, the opposite of the stoplist hack: nothing is
    forced to unmapped; the cleaned phrase is still matched semantically.
  * Exposure codes absent from ILO Table A1 (e.g. 1439, 3435) are imputed from
    the 3-digit ISCO parent mean and flagged exposure_imputed=True.

Run
---
  pip install -r requirements-crosswalk.txt
  python esco_crosswalk.py \
      --esco       data/reference/ESCO/occupations_de.csv \
      --exposure   data/reference/ilo_ai_exposure_isco08.csv \
      --silver     data/silver/kaggle/dt=2026-08-11/de_jobs.csv \
      --title-col  normalized_title \
      --out        data/silver/kaggle/dt=2026-08-11/de_jobs_mapped.csv

First run encodes the ESCO label set once and caches it to <esco>.emb.npy;
later runs reuse it. CPU is fine for a few thousand titles.
"""
from __future__ import annotations
import argparse, hashlib, os, re, sys
import numpy as np
import pandas as pd

# ----------------------------- configuration --------------------------------
MODEL_NAME  = "intfloat/multilingual-e5-base"   # -> "-large" for more accuracy
MODEL_STYLE = "e5"        # "e5" (uses query:/passage: prefixes) or "plain"
ACCEPT      = 0.88       # cosine >= ACCEPT  -> accept the semantic match
REVIEW_LOW  = 0.85     # ACCEPT > cosine >= REVIEW_LOW -> mapped but flagged review
                          # cosine < REVIEW_LOW -> unmapped
BATCH       = 256

# Decoration to strip so the OCCUPATION is what gets embedded.
# These are employment form / seniority, never the occupation itself.
PREFIX_STRIP = [
    "ausbildung", "ausbildung zum", "ausbildung zur", "duales studium",
    "duales studium zum", "duales studium zur", "studium", "werkstudent",
    "werkstudentin", "praktikant", "praktikantin", "praktikum", "trainee",
    "aushilfe", "minijob", "minijobber", "nebenjob", "ferienjob",
    "studentische aushilfe", "quereinsteiger", "senior", "junior",
    "stellvertretender", "stellvertretende", "stellvertretung", "leitende",
    "leitender",
]
GENDER = re.compile(r"\(?\s*m\s*[/|]\s*w\s*[/|]\s*(d|x)\s*\)?", re.I)   # (m/w/d)
SUFX   = re.compile(r"(:in|/-?in|\*in|/in|\-in)\b", re.I)              # gender suffixes
NONWORD= re.compile(r"[^\wäöüß\s-]", re.I)

def normalize(title: str) -> str:
    t = (title or "").lower().strip()
    t = GENDER.sub(" ", t)
    t = SUFX.sub("", t)
    t = NONWORD.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    # strip a leading employment-form / seniority prefix (longest first)
    for p in sorted(PREFIX_STRIP, key=len, reverse=True):
        if t == p:
            break                     # title is ONLY the wrapper -> keep, will be low-conf
        if t.startswith(p + " "):
            t = t[len(p) + 1:].strip()
            break
    return t

# ------------------------------- ESCO load ----------------------------------
def _col(df, *cands):
    low = {c.lower(): c for c in df.columns}
    for c in cands:
        if c.lower() in low:
            return low[c.lower()]
    raise KeyError(f"none of {cands} in {list(df.columns)}")

def load_esco(path: str) -> pd.DataFrame:
    """Return long table: one row per (label, isco4, occupation)."""
    raw = pd.read_csv(path, dtype=str).fillna("")
    pref = _col(raw, "preferredLabel", "preferred_label", "label")
    isco = _col(raw, "iscoGroup", "isco_group", "isco08", "code_isco")
    alt  = None
    try:    alt = _col(raw, "altLabels", "alt_labels", "hiddenLabels")
    except KeyError: pass

    rows = []
    for _, r in raw.iterrows():
        code = re.sub(r"\D", "", str(r[isco]))[:4]
        if len(code) != 4:
            continue
        occ = r[pref].strip()
        labels = {occ}
        if alt:
            labels |= {x.strip() for x in re.split(r"[\n|;]+", str(r[alt])) if x.strip()}
        for lab in labels:
            n = normalize(lab)
            if n:
                rows.append((n, lab, code, occ))
    out = pd.DataFrame(rows, columns=["norm", "label", "isco4", "occupation"])
    return out.drop_duplicates("norm").reset_index(drop=True)

# ---------------------------- exposure + imputation -------------------------
def load_exposure(path: str):
    ex = pd.read_csv(path, dtype={"isco08_4digit": str})
    by_code = ex.set_index("isco08_4digit")[
        ["exposure_category", "exposure_order", "mean_task_score", "sd_task_score"]
    ].to_dict("index")
    ex["p3"] = ex["isco08_4digit"].str[:3]
    parent = ex.groupby("p3")["mean_task_score"].mean().round(2).to_dict()
    return by_code, parent

def attach_exposure(isco4, by_code, parent):
    if isco4 in by_code:
        r = by_code[isco4]
        return dict(exposure_category=r["exposure_category"],
                    exposure_order=int(r["exposure_order"]),
                    mean_task_score=r["mean_task_score"],
                    sd_task_score=r["sd_task_score"], exposure_imputed=False)
    m = parent.get(isco4[:3])
    if m is not None:                       # impute from 3-digit ISCO parent
        return dict(exposure_category="Imputed (3-digit parent)", exposure_order=None,
                    mean_task_score=m, sd_task_score=None, exposure_imputed=True)
    return dict(exposure_category=None, exposure_order=None, mean_task_score=None,
                sd_task_score=None, exposure_imputed=False)

# ------------------------------- embeddings ---------------------------------
def _prefix(texts, kind):               # kind: "query" | "passage"
    return [f"{kind}: {t}" for t in texts] if MODEL_STYLE == "e5" else list(texts)

def get_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)

def encode(model, texts, kind):
    emb = model.encode(_prefix(texts, kind), batch_size=BATCH,
                       normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(emb, dtype=np.float32)

def esco_embeddings(model, esco: pd.DataFrame, esco_path: str):
    key = hashlib.md5(("||".join(esco["norm"]) + MODEL_NAME).encode()).hexdigest()[:12]
    cache = f"{esco_path}.{key}.emb.npy"
    if os.path.exists(cache):
        return np.load(cache)
    emb = encode(model, esco["norm"].tolist(), "passage")
    np.save(cache, emb)
    return emb

# ------------------------------- crosswalk ----------------------------------
class EscoCrosswalk:
    def __init__(self, esco_path, exposure_path):
        self.esco = load_esco(esco_path)
        self.exact = {n: i for i, n in enumerate(self.esco["norm"])}
        self.by_code, self.parent = load_exposure(exposure_path)
        self.model = get_model()
        self.emb = esco_embeddings(self.model, self.esco, esco_path)

    def _row(self, i, method, score, norm):
        e = self.esco.iloc[i]
        rec = dict(isco08_4digit=e["isco4"], occupation_name=e["occupation"],
                   match_method=method, matched_label=e["label"],
                   match_score=round(float(score), 4), norm_title=norm)
        rec.update(attach_exposure(e["isco4"], self.by_code, self.parent))
        return rec

    def _unmapped(self, norm, score):
        return dict(isco08_4digit=None, occupation_name=None,
                    match_method="unmapped", matched_label=None,
                    match_score=round(float(score), 4), norm_title=norm,
                    exposure_category=None, mean_task_score=None,
                    sd_task_score=None, exposure_imputed=False)

    def map_titles(self, titles) -> pd.DataFrame:
        norms = [normalize(t) for t in titles]
        recs = [None] * len(norms)

        # tier 1: exact normalized-label match
        todo = []
        for k, n in enumerate(norms):
            i = self.exact.get(n)
            if i is not None:
                recs[k] = self._row(i, "esco_exact", 1.0, n)
            elif n:
                todo.append(k)
            else:
                recs[k] = self._unmapped(n, 0.0)

        # tier 2: semantic nearest neighbour (batched), on the unique remainder
        if todo:
            uniq = sorted({norms[k] for k in todo})
            qemb = encode(self.model, uniq, "query")
            sims = qemb @ self.emb.T                     # cosine (all normalized)
            best_i = sims.argmax(axis=1)
            best_s = sims.max(axis=1)
            lut = {u: (int(best_i[j]), float(best_s[j])) for j, u in enumerate(uniq)}
            for k in todo:
                i, s = lut[norms[k]]
                if s >= REVIEW_LOW:
                    rec = self._row(i, "esco_semantic", s, norms[k])
                    rec["needs_review"] = s < ACCEPT
                    recs[k] = rec
                else:
                    recs[k] = self._unmapped(norms[k], s)
        out = pd.DataFrame(recs)
        if "needs_review" not in out:
            out["needs_review"] = False
        out["needs_review"] = out["needs_review"].fillna(False)
        return out

# --------------------------------- CLI --------------------------------------
ATTRACTORS = [   # the fuzzy-tier disasters — must now map sanely
    "mitarbeiter logistik", "mitarbeiter it-support", "mitarbeiter küche",
    "mitarbeiter buchhaltung", "account manager", "key account manager",
    "social media manager", "projektleiter heizung", "sachbearbeiter export",
    "reiniger", "onkologe", "prüfer", "berater", "programmierer",
    "verkäufer backshop", "tierarzt", "night auditor",
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--esco", required=True)
    ap.add_argument("--exposure", required=True)
    ap.add_argument("--silver")
    ap.add_argument("--title-col", default="normalized_title")
    ap.add_argument("--out")
    ap.add_argument("--selfcheck", action="store_true",
                    help="run the attractor spot-check and exit")
    a = ap.parse_args()

    xw = EscoCrosswalk(a.esco, a.exposure)
    print(f"ESCO labels indexed: {len(xw.esco):,}  |  model: {MODEL_NAME}")

    if a.selfcheck or not a.silver:
        res = xw.map_titles(ATTRACTORS)
        print("\n--- attractor spot-check (title -> occupation @ cosine / method) ---")
        for t, r in zip(ATTRACTORS, res.to_dict("records")):
            print(f"  {t:34s} -> {str(r['occupation_name'])[:44]:44s} "
                  f"{r['match_score']:.3f} {r['match_method']}")
        return

    df = pd.read_csv(a.silver)
    mapped = xw.map_titles(df[a.title_col].tolist())
    df = df.drop(columns=[c for c in mapped.columns if c in df.columns], errors="ignore")
    df = pd.concat([df.reset_index(drop=True), mapped], axis=1)
    if a.out:
        df.to_csv(a.out, index=False)

    n = len(df)
    vc = mapped["match_method"].value_counts()
    print("\n[coverage]")
    for m, c in vc.items():
        print(f"    {m:14s} {c:5d}  {c/n*100:5.1f}%")
    sem = mapped[mapped.match_method == "esco_semantic"]["match_score"]
    if len(sem):
        print("\n[semantic cosine histogram]")
        bins = np.arange(0.80, 1.001, 0.02)
        h, edges = np.histogram(sem, bins=bins)
        for cnt, lo, hi in zip(h, edges[:-1], edges[1:]):
            print(f"    {lo:.2f}-{hi:.2f}  {'#'*int(cnt/max(h.max(),1)*40):40s} {cnt}")
        print(f"    review band (<{ACCEPT}): {int((sem < ACCEPT).sum())} rows flagged needs_review")

if __name__ == "__main__":
    main()