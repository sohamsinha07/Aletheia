"""
embed_cluster.py — Step 2 of the NewsLens pipeline.
Generates embeddings for each article, then clusters articles covering
the same story using cosine similarity + DBSCAN.
"""

import os
import numpy as np
from dotenv import load_dotenv
load_dotenv()

EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Lowered from 0.75 to 0.68 — catches more related articles in the same cluster
SIMILARITY_THRESHOLD = 0.68


def embed_openai(texts: list[str]) -> np.ndarray:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    all_embeddings = []
    for i in range(0, len(texts), 100):
        batch = texts[i:i+100]
        response = client.embeddings.create(model="text-embedding-3-small", input=batch)
        all_embeddings.extend([item.embedding for item in response.data])
    return np.array(all_embeddings)


_local_model = None

def embed_local(texts: list[str]) -> np.ndarray:
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer
        print("[EMBED] Loading local embedding model (first run may take ~30s to download)...")
        _local_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _local_model.encode(texts, show_progress_bar=False, batch_size=32)


def get_embeddings(texts: list[str]) -> np.ndarray:
    if EMBEDDING_PROVIDER == "openai" and OPENAI_API_KEY:
        print(f"[EMBED] Using OpenAI embeddings for {len(texts)} texts...")
        return embed_openai(texts)
    else:
        print(f"[EMBED] Using local sentence-transformers for {len(texts)} texts...")
        return embed_local(texts)


def cluster_articles(articles: list[dict]) -> list[list[dict]]:
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


def tag_genres(clusters: list[list[dict]]) -> list[list[dict]]:
    """Tag each cluster with a genre based on keyword matching against titles + body."""

    KEYWORD_GENRES = {
        "politics": [
            "election", "congress", "senate", "president", "democrat", "republican",
            "white house", "vote", "legislation", "bill", "law", "government", "policy",
            "trump", "biden", "harris", "campaign", "political", "party", "supreme court",
            "executive order", "filibuster", "impeach", "cabinet", "administration"
        ],
        "economy": [
            "economy", "inflation", "fed", "federal reserve", "interest rate", "recession",
            "gdp", "unemployment", "stock", "market", "trade", "tariff", "budget", "debt",
            "deficit", "treasury", "dollar", "price", "cost", "wages", "jobs", "hiring",
            "layoff", "mortgage", "housing", "consumer", "spending", "retail"
        ],
        "tech": [
            "ai", "artificial intelligence", "tech", "apple", "google", "meta", "microsoft",
            "openai", "startup", "software", "hardware", "cyber", "hack", "data", "chip",
            "semiconductor", "robot", "automation", "algorithm", "machine learning", "nvidia",
            "amazon", "tesla", "spacex", "social media", "app", "platform", "cloud"
        ],
        "world": [
            "war", "ukraine", "russia", "china", "israel", "gaza", "nato", "united nations",
            "foreign", "international", "treaty", "sanctions", "diplomat", "iran", "north korea",
            "middle east", "europe", "africa", "asia", "pacific", "india", "border", "refugee",
            "military", "troops", "conflict", "ceasefire", "occupation"
        ],
        "health": [
            "health", "hospital", "disease", "vaccine", "fda", "drug", "cancer", "mental",
            "pandemic", "virus", "medicine", "clinical", "doctor", "patient", "healthcare",
            "insurance", "medicaid", "medicare", "opioid", "abortion", "surgery", "trial",
            "cdc", "who", "outbreak", "treatment", "diagnosis", "wellness"
        ],
        "climate": [
            "climate", "environment", "carbon", "emissions", "fossil fuel", "solar", "renewable",
            "wildfire", "flood", "drought", "epa", "greenhouse", "paris agreement", "net zero",
            "clean energy", "wind power", "oil", "gas", "pollution", "biodiversity",
            "deforestation", "ocean", "temperature", "glacier", "extreme weather"
        ],
        "business": [
            "company", "merger", "acquisition", "ceo", "earnings", "revenue", "profit", "ipo",
            "layoff", "hire", "industry", "corporate", "wall street", "investor", "fund",
            "venture", "startup", "brand", "retail", "supply chain", "manufacturing",
            "executive", "board", "shareholder", "quarterly", "valuation"
        ],
        "science": [
            "science", "nasa", "space", "research", "study", "discovery", "physics", "biology",
            "experiment", "university", "scientist", "journal", "findings", "genome", "dna",
            "fossil", "astronomy", "planet", "telescope", "lab", "chemistry", "evolution",
            "psychology", "neuroscience", "math", "quantum"
        ],
    }

    def keyword_tag(text: str) -> str:
        text_lower = text.lower()
        scores = {
            genre: sum(1 for kw in keywords if kw in text_lower)
            for genre, keywords in KEYWORD_GENRES.items()
        }
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "general"

    for cluster in clusters:
        # Use title + first 300 chars of body for better genre signal
        combined = " ".join(
            a["title"] + " " + a.get("body", "")[:300]
            for a in cluster
        )
        genre = keyword_tag(combined)
        for article in cluster:
            article["genre"] = genre

    return clusters


if __name__ == "__main__":
    from ingest import run_ingest
    articles = run_ingest()
    clusters = cluster_articles(articles)
    clusters = tag_genres(clusters)
    print(f"\nTop 5 clusters:")
    for i, cluster in enumerate(clusters[:5]):
        print(f"\n  Cluster {i+1} ({len(cluster)} articles, genre={cluster[0].get('genre')}):")
        for a in cluster:
            print(f"    [{a['lean']:10s}] {a['source_name']:20s} | {a['title'][:70]}")