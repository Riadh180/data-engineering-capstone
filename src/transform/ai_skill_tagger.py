#!/usr/bin/env python3
"""AI-skill tagger (German + English) — two signals, anchors + guarded regex.

  has_ai_usage    : the job wants a human who can USE AI at work.
  has_ai_building : the job BUILDS AI/ML systems.

Returns (has_ai_usage, has_ai_building, sorted matched terms).

Precision design (grounded in reading real 2026 postings):
- Named tools / specific skill phrases = high-precision anchors.
- "KI-Anwendung(en)/KI-Funktionen/KI-basierte Anwendung" are re-added but GATED:
  they only count when a USAGE VERB is nearby (einsetzen, nutzen, arbeiten,
  Affinität, Umgang, erfassen) — so equipment ("KI-Oberfläche") and vague
  boilerplate don't fire.
- False friends excluded: bare 'prompt' (=pünktlich / screen prompts) dropped
  (keep 'prompt engineering'); 'generative' word-boundaried so 'regenerativ'
  doesn't match.
- Recruiter-process boilerplate excluded: "AI tools ... hiring/recruiting/
  application process" is about THEIR process, not the job's skills.
- bare 'ai'/'ki' never match alone; 'data science' excluded.
"""
import re

# ---------------- USAGE anchors: specific, high-precision ----------------
USAGE_ANCHORS = [
    # assistants / GenAI products
    "chatgpt", "copilot", "github copilot", "microsoft copilot", "m365 copilot",
    "microsoft 365 copilot", "copilot studio", "claude", "gemini", "google gemini",
    "mistral", "llama", "grok", "perplexity", "notebooklm", "notion ai", "jasper",
    "midjourney", "dall-e", "dall e", "stable diffusion", "runway", "synthesia",
    "openai", "azure openai",
    # generative / LLM concepts (generative handled via regex for boundary safety)
    "generative ki", "gen ai", "genai", "large language model", "sprachmodell",
    "conversational ai",
    # specific usage phrasing (EN)
    "prompt engineering", "ai literacy", "ai-powered", "ai assistant",
    "ai-assisted", "ai-augmented",
    # specific usage phrasing (DE) — tools/skills
    "ki-tools", "ki tools", "ki-gestützt", "ki gestützt", "ki-gestützte",
    "ki-gestützten", "ki-basiert", "ki-basierte", "ki-basierten",
    "ki-kompetenz", "ki-affinität", "ki-affin", "ki-assistent",
]
USAGE_TOKEN_RE = re.compile(r"\b(gpt-?4?o?|llm|llms|rag)\b", re.I)
# generative only as "generative ai/ki" or standalone word-bounded (NOT regenerativ)
GENERATIVE_RE = re.compile(r"\bgenerative(\s+(ai|ki|künstliche))?\b", re.I)
# KI/AI + tool/skill word (catches unseen tools)
USAGE_CTX_RE = re.compile(
    r"\b(ki|ai|genai)[\s\-]?"
    r"(tools?|kompetenz\w*|gestützt\w*|basiert\w*|affin\w*|assisten\w*|"
    r"literacy|powered|skills?)", re.I)
# GATED: KI-Anwendung/Funktion counts only near a usage verb
KI_APP_RE = re.compile(r"\bki[\s\-]?(anwendung\w*|funktion\w*)", re.I)
USAGE_VERB_RE = re.compile(
    r"(einsetz\w*|einzusetz\w*|nutz\w*|anwend\w*|arbeit\w*|affinität|umgang|"
    r"erfass\w*|erfahrung|kenntnis\w*|beherrsch\w*|versiert)", re.I)
# recruiter-process boilerplate to EXCLUDE (their hiring, not the job)
RECRUITER_RE = re.compile(
    r"ai tools?.{0,40}(hiring|recruit|application|bewerbung|auswahl)", re.I)

# ---------------- BUILDING anchors ----------------
BUILD_ANCHORS = [
    "machine learning", "deep learning", "maschinelles lernen", "maschinellem lernen",
    "neural network", "neuronale netze", "reinforcement learning", "computer vision",
    "natural language processing", "mlops", "mlflow", "kubeflow",
    "tensorflow", "pytorch", "keras", "scikit-learn", "scikit learn", "hugging face",
    "langchain", "model training", "modelltraining", "feature engineering",
    "fine-tuning", "fine tuning", "vector database", "vektordatenbank",
]


def detect_ai_skill(*texts):
    low = " ".join(t for t in texts if t).lower()
    terms = set()

    usage = False
    for p in USAGE_ANCHORS:
        if p in low:
            usage = True; terms.add(p)
    if USAGE_TOKEN_RE.search(low):
        usage = True; terms.add(USAGE_TOKEN_RE.search(low).group(0).lower())
    if GENERATIVE_RE.search(low):
        usage = True; terms.add("generative")
    for m in USAGE_CTX_RE.finditer(low):
        usage = True; terms.add(m.group(0).lower())
    # gated KI-Anwendung/Funktion: only if a usage verb appears in the text
    if KI_APP_RE.search(low) and USAGE_VERB_RE.search(low):
        usage = True; terms.add(KI_APP_RE.search(low).group(0).lower())

    # remove recruiter-process false positive if that was the ONLY thing matched
    if RECRUITER_RE.search(low):
        terms.discard("ai tools")
        # if nothing else set usage, and only the recruiter phrase existed, unflag
        real = [t for t in terms if t not in ("ai tools",)]
        if not real and not (USAGE_CTX_RE.search(low) or any(a in low for a in USAGE_ANCHORS if a != "ai tools")):
            usage = False

    building = False
    for p in BUILD_ANCHORS:
        if p in low:
            building = True; terms.add(p)

    return (usage, building, sorted(terms))


if __name__ == "__main__":
    tests = [
        ("Marketing", "Erfahrung mit ChatGPT und KI-Tools"),                       # usage
        ("Sachbearbeiter", "KI-gestützte Tools im Arbeitsalltag"),                 # usage
        ("Bürosachbearbeitung", "KI-basierte Anwendungen zielgerichtet einsetzen"),# usage (gated KI-Anwendung)
        ("Werkstudent", "Affinität für KI-Anwendungen mit"),                       # usage (gated)
        ("MTRA", "High-End-CT mit KI-Oberfläche"),                                 # NEITHER (equipment, no verb)
        ("Concierge", "verbinden Sicherheitstechnik mit KI-Anwendungen"),          # NEITHER (no usage verb)
        ("Kreditor", "we sometimes use AI tools to help with our hiring process"), # NEITHER (recruiter boilerplate)
        ("Sachbearbeiter", "prompte, schnelle Belieferung"),                       # NEITHER (prompt=pünktlich)
        ("Lagerlogistik", "Lösungen für die regenerative Medizin"),                # NEITHER (regenerativ)
        ("Online Shop", "Content-Optimierung für AI und LLM basierte Suche"),      # usage (llm)
        ("ML Engineer", "PyTorch, TensorFlow, MLOps"),                             # building
    ]
    print(f"{'usage':>5} {'build':>5}  title -> terms")
    for title, desc in tests:
        u, b, t = detect_ai_skill(title, desc)
        print(f"{str(u):>5} {str(b):>5}  {title:<20} -> {t}")