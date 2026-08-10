#!/usr/bin/env python3
"""
03_nlp_skill_extraction.py
NLP pipeline: TF-IDF + spaCy NER entity ruler for skill extraction.
Matches thesis Section 3.5.

Requires: spacy, scikit-learn
    pip install spacy scikit-learn
    python -m spacy download de_core_news_sm
"""
import pandas as pd
import spacy
from spacy.pipeline import EntityRuler
from sklearn.feature_extraction.text import TfidfVectorizer

SKILL_VOCABULARY = [
    "Python","SQL","Excel","Power BI","Git","Azure","Tableau","Machine Learning",
    "AWS","Spark","PySpark","dbt","R","Airflow","GCP","BigQuery","Databricks",
    "Pandas","NumPy","Looker","Docker","Kubernetes","Scikit-learn","TensorFlow",
    "PyTorch","Jupyter","SAP","SSRS","Cognos","MicroStrategy","Hadoop","Kafka",
    "Terraform","FastAPI","Streamlit","MLflow","Kubeflow","Snowflake","Matplotlib",
    "Seaborn","Azure Data Factory","Azure Synapse","dbt Cloud","Apache Spark",
    "Microsoft Fabric","Power Query","Power Automate","SAP BW","SAP HANA",
    "SAP Analytics Cloud","AWS Glue","AWS Redshift","Google Cloud",
]

def build_ner_pipeline():
    nlp = spacy.blank("de")
    ruler = nlp.add_pipe("entity_ruler")
    patterns = [{"label": "TECH_SKILL", "pattern": skill} for skill in SKILL_VOCABULARY]
    patterns += [{"label": "TECH_SKILL", "pattern": skill.lower()} for skill in SKILL_VOCABULARY]
    ruler.add_patterns(patterns)
    return nlp

def extract_skills_ner(text: str, nlp) -> list:
    doc = nlp(text.lower())
    return list({ent.text.title() for ent in doc.ents if ent.label_ == "TECH_SKILL"})

def run_tfidf(df: pd.DataFrame):
    vec = TfidfVectorizer(ngram_range=(1,3), min_df=20, max_df=0.85,
                          token_pattern=r"(?u)\b[A-Za-z][A-Za-z0-9\+\#\-\.]{1,}\b")
    matrix = vec.fit_transform(df['description_clean'].fillna(""))
    return pd.DataFrame(matrix.toarray(), columns=vec.get_feature_names_out())

if __name__ == "__main__":
    df = pd.read_csv('data/job_postings_clean.csv')
    nlp = build_ner_pipeline()
    df['skills_extracted'] = df['description_clean'].apply(lambda t: '; '.join(extract_skills_ner(str(t), nlp)))
    df.to_csv('data/job_postings_clean.csv', index=False)
    print(f"Skill extraction complete. {len(df)} records updated.")
