#!/usr/bin/env python3
"""AI-skill tagger (German + English) — two signals, anchors + generalizing regex.

  has_ai_usage    : the job wants a human who can USE AI at work (named tools,
                    GenAI products, KI-Kompetenz/-gestützt, prompt, ...).
  has_ai_building : the job BUILDS AI/ML (frameworks, ML engineering).

Returns (has_ai_usage, has_ai_building, sorted matched terms).

PRECISION NOTE: generic HR-boilerplate phrases that now appear in ads for ANY
role ("Umgang mit KI", "Einsatz von KI", "KI-Anwendung") were REMOVED — they
flagged truck-driver / kindergarten / physiotherapy jobs and inflated the count
without signalling real demand. We keep only SPECIFIC signals: named tools,
KI-gestützt / KI-Tools / KI-Kompetenz, prompt engineering, LLM, generative AI.
Track generic KI-mentions separately if you want a "cultural penetration" signal.
"""
import re

# ---------------- USAGE: specific AI-as-a-tool signals ----------------
USAGE_ANCHORS = [
    # assistants / GenAI products (specific -> high precision)
    "chatgpt", "copilot", "github copilot", "microsoft copilot", "m365 copilot",
    "microsoft 365 copilot", "copilot studio", "claude", "gemini", "google gemini",
    "mistral", "llama", "grok", "perplexity", "notebooklm", "notion ai", "jasper",
    "midjourney", "dall-e", "dall e", "stable diffusion", "runway", "synthesia",
    "openai", "azure openai",
    # generative / LLM concepts
    "generative ai", "generative ki", "generative künstliche intelligenz",
    "gen ai", "genai", "large language model", "sprachmodell", "conversational ai",
    # SPECIFIC usage phrasing (EN)
    "prompt engineering", "prompting", "ai literacy", "ai tools", "ai-powered",
    "ai assistant", "ai-assisted", "ai-augmented",
    # SPECIFIC usage phrasing (DE) — tools/skills, NOT generic "Umgang mit KI"
    "ki-tools", "ki tools", "ki-gestützt", "ki gestützt", "ki-gestützte",
    "ki-gestützten", "ki-basiert", "ki-basierte", "ki-basierten",
    "ki-kompetenz", "ki-affinität", "ki-affin", "ki-assistent",
]
# REMOVED as boilerplate: "umgang mit ki", "einsatz von ki", "ki im arbeitsalltag",
#                         "ki-anwendung", "ki-anwendungen", "ki-technologien",
#                         "ki-lösungen", "ki-verständnis"
# REMOVED as too generic on their own: "künstliche intelligenz", "artificial
#   intelligence" (fire on company boilerplate; the named-tool/skill anchors and
#   the context regex below carry the real signal).

# short tokens — word-boundaried
USAGE_TOKEN_RE = re.compile(r"\b(gpt-?4?o?|llm|llms|rag)\b", re.I)

# tier-2 generalizer: KI/AI attached to a TOOL/SKILL word (catches unseen tools)
# — deliberately does NOT include generic verbs like umgang/einsatz/anwendung.
USAGE_CTX_RE = re.compile(
    r"\b(ki|ai|genai)[\s\-]?"
    r"(tools?|kompetenz\w*|gestützt\w*|basiert\w*|affin\w*|"
    r"assisten\w*|literacy|powered|skills?)", re.I)

# ---------------- BUILDING: engineering AI/ML systems ----------------
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
    m = USAGE_TOKEN_RE.search(low)
    if m:
        usage = True; terms.add(m.group(0).lower())
    for m in USAGE_CTX_RE.finditer(low):
        usage = True; terms.add(m.group(0).lower())

    building = False
    for p in BUILD_ANCHORS:
        if p in low:
            building = True; terms.add(p)

    return (usage, building, sorted(terms))


if __name__ == "__main__":
    tests = [
        ("Marketing Manager", "Erfahrung mit ChatGPT und KI-Tools von Vorteil"),   # usage
        ("Sachbearbeiter", "Sie nutzen KI-gestützte Tools im Arbeitsalltag"),      # usage
        ("Assistenz", "KI-Kompetenz und KI-Affinität erwünscht"),                  # usage (regex)
        ("Redakteur", "Umgang mit Claude, Gemini oder Mistral"),                   # usage (tools)
        ("LKW Fahrer", "Offenheit im Umgang mit KI erwünscht"),                    # NEITHER now (boilerplate)
        ("Erzieher", "auch im Umgang mit KI"),                                     # NEITHER now (boilerplate)
        ("Concierge", "KI-Anwendungen im Empfang"),                                # NEITHER now (boilerplate)
        ("ML Engineer", "PyTorch, TensorFlow, model training, MLOps"),             # building
        ("Data Scientist", "Machine Learning und Copilot"),                        # both
        ("Consultant", "AI literacy and prompt engineering required"),             # usage
    ]
    print(f"{'usage':>5} {'build':>5}  title -> terms")
    for title, desc in tests:
        u, b, t = detect_ai_skill(title, desc)
        print(f"{str(u):>5} {str(b):>5}  {title:<18} -> {t}")