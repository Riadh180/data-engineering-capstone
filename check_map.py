import pandas as pd
d = pd.read_csv('data/silver/kaggle/dt=2026-08-10/de_jobs.csv')
print(d[d['match_method']=='esco_fuzzy'][['normalized_title','occupation_name']]
      .drop_duplicates().sample(20).to_string(index=False))
