import pandas as pd, re
from collections import Counter
d = pd.read_csv('data/bronze/kaggle/job_postings_raw.csv')
text = " ".join(d['skills_extracted'].fillna('').astype(str)).lower()
# count all distinct skills (they're ; separated)
skills = Counter(s.strip() for s in text.replace('\n',';').split(';') if s.strip())
print("TOP 60 skills in the data:")
for s, n in skills.most_common(60):
    print(f"{n:>5}  {s}")
