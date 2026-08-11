import pandas as pd
d = pd.read_csv('data/silver/kaggle/dt=2026-08-10/de_jobs.csv')
it = d[d['isco08_4digit'].astype(str).str.startswith(('251', '252'))]
print('IT postings:', len(it))
print('marked has_ai_skill=False:', (~it['has_ai_skill']).sum())
print(it[it['has_ai_skill'] == False][['normalized_title']].head(10).to_string())