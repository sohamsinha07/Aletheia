"""
synthesize.py — Step 3 of the NewsLens pipeline.
Guarantees coverage across all genres before filling remaining slots
with the largest multi-source clusters.
"""

import os
import json
from dotenv import load_dotenv
load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MAX_CLUSTERS = int(os.getenv("MAX_CLUSTERS", "25"))
MIN_STORIES_PER_GENRE = int(os.getenv("MIN_STORIES_PER_GENRE", "2"))

LEAN_LABELS = {
    "left": "Left-leaning",
    "lean_left": "Lean Left",
    "center": "Center",
    "lean_right": "Lean Right",
    "right": "Right-leaning",
}

ALL_GENRES = ["politics", "economy", "tech", "world", "health", "climate", "business", "science"]

SYNTHESIS_PROMPT = """You are a professional news editor producing a multi-perspective digest.
You will receive one or more articles about a news story, potentially from sources across the political spectrum.
Your job is to produce a fair, grounded synthesis.

RULES:
1. Only use facts stated in the provided articles. Do NOT add outside knowledge.
2. Do not express your own opinion or take sides.
3. Be concise. The digest reader wants the key facts fast.
4. When coverage diverges, describe the divergence neutrally.
5. Always cite the source name when attributing a specific framing or claim.
6. If only one source is provided, write the summary from that source and note in key_divergence that only one source covered this story.

OUTPUT FORMAT (JSON only, no markdown):
{
  "headline": "A single neutral headline for this story (max 15 words)",
  "summary": "2-3 sentence factual summary of what happened, based only on the provided articles",
  "perspectives": [
    {
      "lean": "left | lean_left | center | lean_right | right",
      "framing": "1-2 sentences describing how sources with this lean frame the story"
    }
  ],
  "key_divergence": "1-2 sentences on the most significant framing difference, or note if only one source covered it.",
  "genre": "the genre tag from the articles"
}"""


def build_prompt(cluster: list[dict]) -> str:
    articles_text = ""
    for i, article in enumerate(cluster[:8], 1):
        lean_label = LEAN_LABELS.get(article["lean"], article["lean"])
        articles_text += f"""
--- Article {i} ---
Source: {article['source_name']} ({lean_label})
Title: {article['title']}
Body: {article['body'][:800]}
"""
    return f"{SYNTHESIS_PROMPT}\n\nARTICLES:\n{articles_text}\n\nRespond with JSON only."


def call_openai(prompt: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    return response.choices[0].message.content


def call_anthropic(prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return response.content[0].text


def synthesize_cluster(cluster: list[dict]) -> dict | None:
    prompt = build_prompt(cluster)
    try:
        if LLM_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
            raw = call_anthropic(prompt)
        elif OPENAI_API_KEY:
            raw = call_openai(prompt)
        else:
            raise ValueError("No LLM API key configured. Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env")

        result = json.loads(raw)
        result["sources"] = [
            {
                "name": a["source_name"],
                "url": a["url"],
                "lean": a["lean"],
                "lean_score": a["lean_score"],
                "title": a["title"],
                "published": a["published"],
            }
            for a in cluster
        ]
        result["article_count"] = len(cluster)
        result["genre"] = cluster[0].get("genre", "general")
        return result

    except json.JSONDecodeError as e:
        print(f"  x JSON parse error: {e}")
        return None
    except Exception as e:
        print(f"  x Synthesis error: {e}")
        return None


def select_clusters(clusters: list[list[dict]]) -> list[list[dict]]:
    """
    Selection strategy:
    1. Guarantee MIN_STORIES_PER_GENRE for every genre (floor).
    2. Fill remaining slots with largest unselected clusters regardless of genre —
       so popular genres like politics/tech naturally get more stories.
    """
    by_genre: dict[str, list[list[dict]]] = {g: [] for g in ALL_GENRES}
    by_genre["general"] = []

    for cluster in clusters:
        genre = cluster[0].get("genre", "general")
        if genre in by_genre:
            by_genre[genre].append(cluster)
        else:
            by_genre["general"].append(cluster)

    for genre in by_genre:
        by_genre[genre].sort(key=lambda c: len(c), reverse=True)

    selected = []
    selected_ids = set()

    def cluster_id(c):
        return c[0]["id"]

    # Step 1: guarantee the floor for every genre
    for genre in ALL_GENRES:
        picked = 0
        for cluster in by_genre[genre]:
            if picked >= MIN_STORIES_PER_GENRE:
                break
            cid = cluster_id(cluster)
            if cid not in selected_ids:
                selected.append(cluster)
                selected_ids.add(cid)
                picked += 1

    # Step 2: fill remaining slots naturally by cluster size —
    # politics/tech will dominate here because they have the most articles
    remaining_slots = MAX_CLUSTERS - len(selected)
    if remaining_slots > 0:
        all_sorted = sorted(clusters, key=lambda c: len(c), reverse=True)
        for cluster in all_sorted:
            if remaining_slots <= 0:
                break
            cid = cluster_id(cluster)
            if cid not in selected_ids:
                selected.append(cluster)
                selected_ids.add(cid)
                remaining_slots -= 1

    return selected


def run_synthesis(clusters: list[list[dict]]) -> list[dict]:
    eligible = select_clusters(clusters)
    print(f"[SYNTHESIZE] Processing {len(eligible)} clusters (genre-balanced)...")

    # Print genre breakdown
    genre_counts: dict[str, int] = {}
    for c in eligible:
        g = c[0].get("genre", "general")
        genre_counts[g] = genre_counts.get(g, 0) + 1
    for g, count in sorted(genre_counts.items()):
        print(f"  {g:12s}: {count} clusters")

    stories = []
    for i, cluster in enumerate(eligible, 1):
        sources_list = ", ".join(a["source_name"] for a in cluster[:4])
        print(f"  [{i}/{len(eligible)}] {cluster[0]['title'][:55]}... ({len(cluster)} src: {sources_list})")
        story = synthesize_cluster(cluster)
        if story:
            stories.append(story)

    print(f"[SYNTHESIZE] Done. {len(stories)} story cards generated.\n")
    return stories


if __name__ == "__main__":
    from ingest import run_ingest
    from embed_cluster import cluster_articles, tag_genres
    articles = run_ingest()
    clusters = cluster_articles(articles)
    clusters = tag_genres(clusters)
    stories = run_synthesis(clusters)
    print(f"\nSample story card:\n{json.dumps(stories[0], indent=2)}")