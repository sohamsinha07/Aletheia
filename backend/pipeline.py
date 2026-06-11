"""
pipeline.py — Orchestrates the full NewsLens pipeline end to end.
Can be run directly (python pipeline.py) or called from the API.
"""

import sys
from ingest import run_ingest
from embed_cluster import cluster_articles, tag_genres
from synthesize import run_synthesis
from database import save_edition, get_latest_edition


def run_pipeline() -> dict:
    """
    Full pipeline: ingest → embed → cluster → synthesize → save.
    Returns the edition dict on success, raises on failure.
    """
    print("=" * 60)
    print("NewsLens Pipeline Starting")
    print("=" * 60)

    articles = run_ingest()
    if not articles:
        raise RuntimeError("Ingest returned no articles. Check RSS feeds and network.")

    clusters = cluster_articles(articles)
    clusters = tag_genres(clusters)

    if not clusters:
        raise RuntimeError("Clustering produced no clusters.")

    stories = run_synthesis(clusters)
    if not stories:
        raise RuntimeError("Synthesis produced no story cards. Check your LLM API key.")

    edition_id = save_edition(stories)
    edition = get_latest_edition()

    print("=" * 60)
    print(f"Pipeline complete! Edition {edition_id}: {len(stories)} stories")
    print("=" * 60)
    return edition


if __name__ == "__main__":
    try:
        edition = run_pipeline()
        print(f"\nTop stories:")
        for i, story in enumerate(edition["stories"][:5], 1):
            print(f"  {i}. [{story['genre']:10s}] {story['headline']}")
    except Exception as e:
        print(f"\nPipeline failed: {e}")
        sys.exit(1)