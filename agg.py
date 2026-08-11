import pandas as pd
d = pd.read_csv('data/silver/kaggle/dt=2026-08-10/de_jobs.csv')
d = d[d['isco08_4digit'].astype(str) != 'unmapped']
d['band'] = d['exposure_order'].apply(lambda o: 'High' if o>=3 else ('Low' if o<=0 else 'Mid'))
d['period'] = d['year'].apply(lambda y: '2022-2024' if y<=2024 else '2025-2026')
g = d.groupby(['band','period']).agg(
    postings=('has_ai_skill','size'),
    ai_pct=('has_ai_skill', lambda x: round(100*x.mean(),1))).reset_index()
print(g.to_string(index=False))
