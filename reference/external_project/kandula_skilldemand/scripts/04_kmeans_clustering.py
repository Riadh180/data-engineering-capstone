#!/usr/bin/env python3
"""
04_kmeans_clustering.py
K-Means clustering on binary skill presence vectors.
PCA reduction + Elbow method + Silhouette analysis.
Matches thesis Section 3.6.

Output: data/kmeans_clusters.csv, figures/fig_elbow.png
"""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.preprocessing import normalize
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

SKILL_VOCABULARY = [
    "Python","SQL","Excel","Power BI","Git","Azure","Tableau","Machine Learning",
    "AWS","Spark","dbt","R","Airflow","GCP","Databricks","Pandas","Looker",
    "Docker","Scikit-learn","SAP","Kubernetes","TensorFlow","PyTorch","Jupyter",
    "NumPy","Snowflake","MLflow","Hadoop","Kafka","SSRS","MicroStrategy","Cognos",
]

def build_binary_matrix(df):
    mat = pd.DataFrame(0, index=df.index, columns=SKILL_VOCABULARY)
    for idx, row in df.iterrows():
        skills = [s.strip() for s in str(row.get('skills_extracted','')).split(';')]
        for skill in skills:
            if skill in SKILL_VOCABULARY:
                mat.at[idx, skill] = 1
    return mat

def run_clustering(df):
    mat = build_binary_matrix(df)
    mat_norm = normalize(mat.values, norm='l2')
    pca = PCA(n_components=20, random_state=42)
    X = pca.fit_transform(mat_norm)
    print(f"PCA variance retained: {pca.explained_variance_ratio_.sum():.2%}")

    wcss, sil = [], []
    for k in range(2, 13):
        km = KMeans(n_clusters=k, random_state=42, n_init=50)
        labels = km.fit_predict(X)
        wcss.append(km.inertia_)
        sil.append(silhouette_score(X, labels))
        print(f"k={k}  WCSS={km.inertia_:.0f}  Silhouette={silhouette_score(X,labels):.3f}")

    best_k = 4
    km_final = KMeans(n_clusters=best_k, random_state=42, n_init=50)
    df['cluster_id'] = km_final.fit_predict(X) + 1
    print(f"\nFinal model: k={best_k}, Silhouette={silhouette_score(X, km_final.labels_):.3f}")
    df.to_csv('data/kmeans_clusters.csv', index=False)

    # Elbow plot
    fig, ax = plt.subplots(figsize=(8,5))
    ax.plot(range(2,13), wcss, 'o-', color='#1F4E79')
    ax.axvline(x=4, color='#C00000', linestyle='--', label='Optimal k=4')
    ax.set_xlabel('Number of Clusters (k)'); ax.set_ylabel('WCSS')
    ax.set_title('Elbow Method — Optimal k Selection')
    ax.legend(); plt.tight_layout()
    plt.savefig('figures/fig_elbow.png', dpi=300, bbox_inches='tight')
    print("Elbow plot saved.")

if __name__ == "__main__":
    df = pd.read_csv('data/kmeans_clusters.csv')
    run_clustering(df)
