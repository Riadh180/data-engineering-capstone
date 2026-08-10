#!/usr/bin/env python3
"""
ESCO-based crosswalk: German job title -> ESCO occupation -> ISCO-08 code.

Matches each title against ESCO's German occupation labels (preferred + alternative),
so the ISCO code comes from the official taxonomy, not hand-written guesses.

Tier 1: exact normalized match against an ESCO label   -> high confidence
Tier 2: fuzzy match (token_set_ratio) above threshold   -> medium confidence
Below threshold -> 'unmapped'.
"""
import csv
import re
import unicodedata
from functools import lru_cache
from rapidfuzz import process, fuzz

ESCO_FILE = "reference/esco/occupations_de.csv"
FUZZY_THRESHOLD = 88          # 0-100; higher = stricter

GENDER = re.compile(r"\((?:all genders?|m/?w/?d|w/?m/?d|m/?w/?x|d/?m/?w|w/?m/?x|gn|d)\)", re.I)
SENIOR = re.compile(r"\b(senior|junior|lead|werkstudent\w*|praktikant\w*|aushilfe|quereinsteiger|azubi|ausbildung)\b", re.I)

def normalize(t: str) -> str:
    t = (t or "").lower()
    t = GENDER.sub(" ", t)
    t = SENIOR.sub(" ", t)
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()

# ---- load ESCO into: normalized_label -> isco4 ------------------------------
_LABEL2ISCO = {}
_CHOICES = []

def _load():
    global _CHOICES
    if _LABEL2ISCO:
        return
    with open(ESCO_FILE, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            isco = str(row["iscoGroup"]).strip()
            labels = [row["preferredLabel"]] + (row.get("altLabels") or "").split("\n")
            for lab in labels:
                # german labels often are "maskulin/feminin" -> split on / too
                for part in re.split(r"/", lab):
                    n = normalize(part)
                    if len(n) >= 3 and n not in _LABEL2ISCO:
                        _LABEL2ISCO[n] = isco
    _CHOICES = list(_LABEL2ISCO.keys())

@lru_cache(maxsize=50000)
def map_title_to_isco(title: str, category_tag: str = ""):
    _load()
    norm = normalize(title)
    if not norm:
        return "unmapped", None
    if norm in _LABEL2ISCO:                              # tier 1: exact
        return _LABEL2ISCO[norm], f"ESCO_EXACT:{norm}"
    hit = process.extractOne(norm, _CHOICES, scorer=fuzz.token_set_ratio,
                             score_cutoff=FUZZY_THRESHOLD)   # tier 2: fuzzy
    if hit:
        label, score, _ = hit
        return _LABEL2ISCO[label], f"ESCO_FUZZY:{label}:{int(score)}"
    return "unmapped", None

def match_method(note):
    if note is None:
        return "unmapped"
    s = str(note)
    if s.startswith("ESCO_EXACT"):
        return "esco_exact"
    if s.startswith("ESCO_FUZZY"):
        return "esco_fuzzy"
    return "unmapped"

if __name__ == "__main__":
    for t in ["Verkäufer (m/w/d)", "Produktionsmitarbeiter", "Altenpfleger",
              "Softwareentwickler Java", "Reinigungskraft", "Data Scientist",
              "Fachkraft für Lagerlogistik", "Berufskraftfahrer"]:
        code, note = map_title_to_isco(t)
        print(f"{code:>8}  {match_method(note):<11} {t}  <- {note}")