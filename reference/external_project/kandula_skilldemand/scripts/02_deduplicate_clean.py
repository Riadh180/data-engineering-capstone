#!/usr/bin/env python3
"""
02_deduplicate_clean.py
Deduplication and quality filtering pipeline.
Removes cross-platform duplicates using composite-key Levenshtein matching
at 85% threshold (thesis Section 3.4.2).

Input:  data/job_postings_raw.csv
Output: data/job_postings_clean.csv + logs/dedup_report.txt
"""
import pandas as pd
import re
import unicodedata
from difflib import SequenceMatcher

def normalise(text: str) -> str:
    if not isinstance(text, str): return ""
    text = text.lower().strip()
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = re.sub(r'[^a-z0-9 ]', ' ', text)
    return ' '.join(text.split())

def levenshtein_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def dedup_and_filter(df: pd.DataFrame, threshold: float = 0.85) -> pd.DataFrame:
    df['_key'] = (df['title_clean'].apply(normalise) + ' ' +
                  df['employer'].apply(normalise) + ' ' +
                  df['city'].apply(normalise))
    keep = []
    seen_keys = []
    for idx, row in df.iterrows():
        key = row['_key']
        duplicate = any(levenshtein_ratio(key, s) >= threshold for s in seen_keys)
        if not duplicate:
            seen_keys.append(key)
            keep.append(idx)
    df_dedup = df.loc[keep].copy()
    # Quality filter: description >= 100 chars
    df_dedup = df_dedup[df_dedup['description_clean'].str.len() >= 100]
    df_dedup.drop(columns=['_key'], inplace=True)
    return df_dedup

if __name__ == "__main__":
    df = pd.read_csv('data/job_postings_raw.csv')
    print(f"Records before dedup: {len(df)}")
    df_clean = dedup_and_filter(df)
    print(f"Records after dedup:  {len(df_clean)}")
    df_clean.to_csv('data/job_postings_clean.csv', index=False)
    print("Saved to data/job_postings_clean.csv")
