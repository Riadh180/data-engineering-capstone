import pandas as pd
d = pd.read_csv('data/silver/kaggle/dt=2026-08-10/de_jobs.csv')
hits = d[d['has_ai_skill'] == True]
print('AI-skill postings:', len(hits))
print(hits[['normalized_title', 'ai_skill_terms']].head(15).to_string())
