#!/usr/bin/env python3
"""AI-skill tagger (German + English) — detect AI/ML/GenAI demand in job text.
Returns (has_ai_skill, sorted matched terms).

Tightened to reduce false positives: bare 'ai'/'ki' are NOT matched on their own
(they fire on incidental company mentions). Instead we require either a strong
phrase/tool, or 'ki'/'ai' in a SKILL CONTEXT (ki-Kenntnisse, ki-Entwicklung, ...).
"""
import re

# Strong, unambiguous phrases & tools — safe as plain substrings (lowercased)
AI_PHRASES = [
    # English concepts
    "artificial intelligence", "machine learning", "deep learning",
    "large language model", "generative ai", "prompt engineering", "computer vision",
    "natural language processing", "neural network", "reinforcement learning",
    "data scientist", "data science",
    # tools / frameworks
    "tensorflow", "pytorch", "keras", "scikit-learn", "scikit learn", "hugging face",
    "langchain", "mlops", "chatgpt", "openai", "stable diffusion",
    # German concepts
    "kunstliche intelligenz", "künstliche intelligenz", "maschinelles lernen",
    "maschinellem lernen", "generative ki", "sprachmodell", "neuronale netze",
    "datenwissenschaft", "mlflow", "kubeflow",
]

# 'ki'/'ai' ONLY when attached to a skill-context word (not bare mentions)
AI_CONTEXT_RE = re.compile(
    r"\b(ki|ai)[\s-]?(kenntnisse|erfahrung|skills?|entwicklung|entwickl\w*|"
    r"modelle?|basiert\w*|engineer|spezialist|"
    r"experte|kompetenz\w*|technologien?)", re.I)

def detect_ai_skill(*texts):
    low = " ".join(t for t in texts if t).lower()
    terms = set()
    for p in AI_PHRASES:
        if p in low:
            terms.add(p)
    for m in AI_CONTEXT_RE.finditer(low):
        terms.add(m.group(0).lower())          # e.g. "ki-kenntnisse", "ai tools"
    return (len(terms) > 0, sorted(terms))


if __name__ == "__main__":
    tests = [
        ("Data Scientist", "Erfahrung mit Machine Learning und PyTorch"),          # True
        ("Empfangsmitarbeiter", "Wir setzen auf KI in unserem Unternehmen"),       # False now (bare KI)
        ("ML Engineer", "KI-Kenntnisse und KI-Entwicklung erforderlich"),          # True
        ("Buchhalter", "DATEV, Rechnungswesen, Excel"),                            # False
        ("Bauleiter", "AI-Fitness Programm als Benefit"),                          # False now (was FP)
    ]
    for title, desc in tests:
        flag, terms = detect_ai_skill(title, desc)
        print(f"{str(flag):>5}  {title:<20} -> {terms}")