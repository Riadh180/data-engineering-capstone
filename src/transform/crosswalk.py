#!/usr/bin/env python3
"""
Job title  ->  ISCO-08 code  (German & English, multi-domain).

Two-stage mapping, transparent about how each row was resolved:
  1. keyword rules     - precise, ordered specific -> generic
  2. category fallback - if no keyword hits, map the Adzuna category to a coarse
                         ISCO code so the posting still gets classified
Anything unresolved is left 'unmapped' for review.

map_title_to_isco() returns (isco08_4digit, match_note) where match_note is the
matched keyword, 'CATEGORY:<tag>' for a fallback, or None when unmapped.
"""
import re
import unicodedata

GENDER_MARKERS = re.compile(
    r"\((?:all genders?|m/?w/?d|w/?m/?d|m/?w/?x|d/?m/?w|w/?m/?x|gn|m/?f/?d|m/?f/?x|d)\)",
    re.IGNORECASE)
SENIORITY = re.compile(
    r"\b(senior|junior|lead|principal|working student|werkstudent(?:in)?|praktikant(?:in)?|"
    r"intern|trainee|azubi|ausbildung)\b", re.IGNORECASE)

def normalize(title: str) -> str:
    t = (title or "").lower()
    t = GENDER_MARKERS.sub(" ", t)
    t = SENIORITY.sub(" ", t)
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()

# Ordered specific -> generic. (code, [keyword substrings])
RULES = [
    # ---- IT / software ----
    ("2514", ["anwendungsentwickl", "anwendungs entwickl", "applications programmer",
              "application developer", "fachinformatiker anwendungsentwicklung"]),
    ("2513", ["webentwickl", "web entwickl", "web developer", "frontend", "front end"]),
    ("2521", ["datenbankadministrator", "datenbank entwickl", "database administrator",
              "database developer", "dba"]),
    ("2522", ["systemadministrator", "system administrator", "sysadmin", "devops",
              "site reliability", "sre", "fachinformatiker systemintegration"]),
    ("2523", ["netzwerkadministrator", "netzwerk", "network engineer", "network administrator"]),
    ("2519", ["data engineer", "dateningenieur", "data scientist", "machine learning",
              "ml engineer", "big data", "data platform"]),
    ("2511", ["systemanalytiker", "systems analyst", "it business analyst", "data analyst",
              "business intelligence", "bi analyst"]),
    ("3512", ["it-support", "it support", "helpdesk", "help desk", "service desk",
              "anwenderbetreuung", "anwendungsbetreu", "user support", "1st level",
              "first level support", "it-administrator", "it administrator"]),
    ("1330", ["it-projektleiter", "it project manager", "head of it", "it manager",
              "it service manager"]),
    ("2356", ["it-trainer", "it trainer"]),
    ("2512", ["softwareentwickl", "software entwickl", "softwareingenieur", "software engineer",
              "software developer", "software architekt", "software architect",
              "softwarearchitekt", "programmierer", "programmer", "full stack", "fullstack",
              "full-stack", "backend", "coding", "software entwicklung", "entwickler",
              "developer"]),
    # ---- Finance / accounting ----
    ("2413", ["financial analyst", "finanzanalyst", "investment analyst"]),
    ("2411", ["buchhalter", "accountant", "controller", "steuerberat", "wirtschaftspruf",
              "bilanzbuchhalter"]),
    # ---- Sales / marketing ----
    ("2431", ["marketing manager", "marketing specialist", "online marketing", "seo", "content marketing"]),
    ("1221", ["sales manager", "vertriebsleiter", "head of sales"]),
    ("3322", ["vertrieb", "sales representative", "account manager", "sales consultant", "aussendienst"]),
    # ---- Engineering (non-IT) ----
    ("2144", ["maschinenbau", "mechanical engineer", "konstrukteur"]),
    ("2151", ["elektroingenieur", "electrical engineer", "elektrotechnik"]),
    ("2142", ["bauingenieur", "civil engineer"]),
    # ---- Healthcare ----
    ("2221", ["krankenpfleger", "krankenschwester", "pflegefachkraft", "nurse"]),
    ("2211", ["arzt", "physician", "facharzt"]),
    # ---- Admin / office ----
    ("4120", ["sekretar", "secretary", "assistenz der", "office assistant"]),
    ("4110", ["sachbearbeiter", "office clerk", "burokraft", "verwaltungsangestellte"]),
    # ---- HR ----
    ("2423", ["recruiter", "personalreferent", "hr business partner", "talent acquisition"]),
]

# Coarse ISCO per Adzuna category tag (used only when no keyword matches)
CATEGORY_FALLBACK = {
    "it-jobs": "2519", "engineering-jobs": "2149", "accounting-finance-jobs": "2411",
    "hr-jobs": "2423", "sales-jobs": "3322", "healthcare-nursing-jobs": "2221",
    "teaching-jobs": "2330", "legal-jobs": "2611", "admin-jobs": "4110",
    "logistics-warehouse-jobs": "4323", "customer-services-jobs": "4222",
    "creative-design-jobs": "2166", "pr-advertising-marketing-jobs": "2431",
    "scientific-qa-jobs": "2131", "consultancy-jobs": "2421",
}

def map_title_to_isco(title: str, category_tag: str = ""):
    norm = normalize(title)
    for code, keywords in RULES:
        for kw in keywords:
            if kw in norm:
                return code, kw
    if category_tag in CATEGORY_FALLBACK:
        return CATEGORY_FALLBACK[category_tag], f"CATEGORY:{category_tag}"
    return "unmapped", None

def match_method(note):
    if note is None:
        return "unmapped"
    return "category_fallback" if str(note).startswith("CATEGORY:") else "keyword"