#!/usr/bin/env python3
"""AI-skill tagger (German + English) — detect AI/ML/GenAI demand in job text.
Returns (has_ai_skill, sorted matched terms). Word-boundaries guard short acronyms."""
import re

AI_PHRASES = [
    # English
    "artificial intelligence", "machine learning", "deep learning",
    "large language model", "generative ai", "prompt engineering", "computer vision",
    "natural language processing", "neural network", "data scientist", "data science",
    "reinforcement learning", "predictive model", "recommendation system",
    # tools / frameworks
    "tensorflow", "pytorch", "keras", "scikit-learn", "scikit learn", "hugging face",
    "langchain", "mlops", "chatgpt", "copilot", "openai", "stable diffusion",
    # German
    "kunstliche intelligenz", "künstliche intelligenz", "maschinelles lernen",
    "generative ki", "ki-kenntnisse", "ki kenntnisse", "erfahrung mit ki",
    "ki-gestutzt", "ki gestutzt", "sprachmodell", "neuronale netze",
    "maschinellem lernen", "datenwissenschaft", "ki-losungen", "ki-modelle",
    "ki-anwendung", "ki-technologien", "ki-tools",
]
AI_WORD_RE = re.compile(r"\b(ai|ki|ml|nlp|llm|genai|gpt|gpt-4|nlu)\b", re.IGNORECASE)
AI_PREFIX_RE = re.compile(r"\b(ki|ai)-\w+", re.IGNORECASE)

def detect_ai_skill(*texts):
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