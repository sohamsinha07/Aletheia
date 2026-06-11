"""
embed_cluster.py — Step 2 of the NewsLens pipeline.
Generates embeddings for each article, then clusters articles
covering the same story using cosine similarity + DBSCAN.
"""

import os
import numpy as np
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Similarity threshold: articles with cosine similarity above this
# are considered to be covering the same story.
# 0.75 = moderately strict; tune up if clusters are too broad.
SIMILARITY_THRESHOLD = 0.75


# ─── Embedding backends ──────────────────────────────────────────────────────

def embed_openai(texts: list[str]) -> np.ndarray:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    all_embeddings = []
    for i in range(0, len(texts), 100):
        batch = texts[i:i+100]
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=batch
        )
        all_embeddings.extend([item.embedding for item in response.data])
    return np.array(all_embeddings)


_local_model = None

def embed_local(texts: list[str]) -> np.ndarray:
    """Use sentence-transformers (runs locally, 100% free)."""
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer
        print("[EMBED] Loading local embedding model (first run may take ~30s to download)...")
        _local_model = SentenceTransformer("all-MiniLM-L6-v2")  # 80MB, fast, good quality
    return _local_model.encode(texts, show_progress_bar=False, batch_size=32)


def get_embeddings(texts: list[str]) -> np.ndarray:
    if EMBEDDING_PROVIDER == "openai" and OPENAI_API_KEY:
        print(f"[EMBED] Using OpenAI embeddings for {len(texts)} texts...")
        return embed_openai(texts)
    else:
        print(f"[EMBED] Using local sentence-transformers for {len(texts)} texts...")
        return embed_local(texts)


# ─── Clustering ───────────────────────────────────────────────────────────────

def cluster_articles(articles: list[dict]) -> list[list[dict]]:
    """
    Cluster articles by semantic similarity.
    Returns a list of clusters, each cluster is a list of article dicts.
    """
    if not articles:
        return []

    texts = [f"{a['title']}. {a['body'][:200]}" for a in articles]
    embeddings = get_embeddings(texts)

    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    embeddings_norm = embeddings / norms

    print(f"[CLUSTER] Clustering {len(articles)} articles...")

    from sklearn.cluster import DBSCAN

    eps = 1 - SIMILARITY_THRESHOLD
    clustering = DBSCAN(eps=eps, min_samples=1, metric="cosine").fit(embeddings_norm)
    labels = clustering.labels_

    cluster_map: dict[int, list[dict]] = {}
    for i, label in enumerate(labels):
        cluster_map.setdefault(label, []).append(articles[i])

    clusters = list(cluster_map.values())
    clusters.sort(key=lambda c: len(c), reverse=True)

    print(f"[CLUSTER] Found {len(clusters)} story clusters.")
    return clusters


def tag_genres(clusters: list[list[dict]], llm_tag: bool = False) -> list[list[dict]]:
    """Add a 'genre' field to each article based on keyword matching."""
    KEYWORD_GENRES = {
        "politics": ["election", "congress", "senate", "president", "democrat", "republican",
                     "white house", "vote", "legislation", "bill", "law", "government", "policy"],
        "economy": ["economy", "inflation", "fed", "interest rate", "recession", "gdp",
                    "unemployment", "stock", "market", "trade", "tariff", "budget", "debt"],
        "tech": ["ai", "artificial intelligence", "tech", "apple", "google", "meta", "microsoft",
                 "openai", "startup", "software", "hardware", "cyber", "hack", "data"],
        "world": ["war", "ukraine", "russia", "china", "israel", "gaza", "nato", "united nations",
                  "foreign", "international", "treaty", "sanctions", "diplomat"],
        "health": ["health", "hospital", "disease", "vaccine", "fda", "drug", "cancer", "mental",
                   "pandemic", "virus", "medicine", "clinical"],
        "climate": ["climate", "environment", "carbon", "emissions", "fossil fuel", "solar",
                    "renewable", "wildfire", "flood", "drought", "epa"],
        "business": ["company", "merger", "acquisition", "ceo", "earnings", "revenue", "profit",
                     "ipo", "layoff", "hire", "industry", "corporate"],
        "science": ["science", "nasa", "space", "research", "study", "discovery", "physics",
                    "biology", "experiment", "university"],
    }

    def keyword_tag(text: str) -> str:
        text_lower = text.lower()
        scores = {genre: sum(1 for kw in keywords if kw in text_lower)
                  for genre, keywords in KEYWORD_GENRES.items()}
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "general"

    for cluster in clusters:
        combined = " ".join(a["title"] for a in cluster)
        genre = keyword_tag(combined)
        for article in cluster:
            article["genre"] = genre

    return clusters


if __name__ == "__main__":
    from ingest import run_ingest
    articles = run_ingest()
    clusters = cluster_articles(articles)
    clusters = tag_genres(clusters)
    print(f"\nTop 3 clusters:")
    for i, cluster in enumerate(clusters[:3]):
        print(f"\n  Cluster {i+1} ({len(cluster)} articles, genre={cluster[0].get('genre')}):")
        for a in cluster:
            print(f"    [{a['lean']:10s}] {a['source_name']:20s} | {a['title'][:70]}")
