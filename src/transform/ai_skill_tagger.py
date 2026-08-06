#!/usr/bin/env python3
"""
AI-skill tagger — detect whether a job posting demands AI skills.

Scans title + description (German & English) for AI/ML/GenAI terms.
Returns (has_ai_skill: bool, matched_terms: list[str]).

Precision note: short acronyms (ai, ki, ml, nlp, llm) are matched with WORD
BOUNDARIES so they don't fire inside words like "email", "training",
"picking". Longer phrases are matched as substrings. It still over/under-
counts at the margins — treat the rate as a trend, not an exact census.
"""
import re

# Distinctive multi-word / long terms — safe as plain substrings (lowercased)
AI_PHRASES = [
    "artificial intelligence", "machine learning", "deep learning",
    "large language model", "generative ai", "generative ki", "prompt engineering",
    "kunstliche intelligenz", "künstliche intelligenz", "maschinelles lernen",
    "sprachmodell", "langchain", "tensorflow", "pytorch", "mlops",
    "computer vision", "neural network", "data scientist", "data science",
    "hugging face", "scikit-learn", "chatgpt", "copilot",
]
# Short/risky tokens — require word boundaries so they don't match inside words
AI_WORD_RE = re.compile(r"\b(ai|ki|ml|nlp|llm|genai|gpt|gpt-4)\b", re.IGNORECASE)
# German/English compounds like "KI-Transformation", "AI-gestützt", "AI-driven"
AI_PREFIX_RE = re.compile(r"\b(ki|ai)-\w+", re.IGNORECASE)


def detect_ai_skill(*texts):
    """Return (has_ai_skill, sorted matched terms) across all given text fields."""
    low = " ".join(t for t in texts if t).lower()
    terms = set()
    for p in AI_PHRASES:
        if p in low:
            terms.add(p)
    for m in AI_WORD_RE.finditer(low):
        terms.add(m.group(0).lower())
    for m in AI_PREFIX_RE.finditer(low):
        terms.add(m.group(0).lower())
    return (len(terms) > 0, sorted(terms))


if __name__ == "__main__":
    tests = [
        ("Software Engineer", "Treiber der KI-Transformation, Erfahrung mit Machine Learning"),
        ("Buchhalter", "DATEV, Digitalisierung, Rechnungswesen"),          # no AI
        ("Data Scientist", "build LLM pipelines with LangChain and PyTorch"),
        ("Sachbearbeiter", "E-Mail Bearbeitung und Terminplanung"),         # 'mail' must NOT match 'ai'
        ("Consultant", "Azure AI, Conversational AI, generative KI"),
    ]
    for title, desc in tests:
        flag, terms = detect_ai_skill(title, desc)
        print(f"{str(flag):>5}  {title:<16} -> {terms}")