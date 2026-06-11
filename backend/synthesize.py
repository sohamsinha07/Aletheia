"""
synthesize.py — Step 3 of the NewsLens pipeline.
For each story cluster, makes one LLM call to produce a multi-perspective
synthesis: shared facts + where left/right coverage diverges.
"""

import os
import json
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MAX_CLUSTERS = int(os.getenv("MAX_CLUSTERS", "10"))
MIN_CLUSTER_SIZE = int(os.getenv("MIN_CLUSTER_SIZE", "2"))


LEAN_LABELS = {
    "left": "Left-leaning",
    "lean_left": "Lean Left",
    "center": "Center",
    "lean_right": "Lean Right",
    "right": "Right-leaning",
}

SYNTHESIS_PROMPT = """You are a professional news editor producing a multi-perspective digest.
You will receive several articles about the same news story from sources across the political spectrum.
Your job is to produce a fair, grounded synthesis.

RULES:
1. Only use facts stated in the provided articles. Do NOT add outside knowledge.
2. Do not express your own opinion or take sides.
3. Be concise. The digest reader wants the key facts fast.
4. When coverage diverges, describe the divergence neutrally — "Left-leaning outlets emphasize X, while right-leaning outlets emphasize Y."
5. Always cite the source name when attributing a specific framing or claim.

OUTPUT FORMAT (JSON only, no markdown):
{
  "headline": "A single neutral headline for this story (max 15 words)",
  "summary": "2-3 sentence factual summary of what happened, based only on the provided articles",
  "perspectives": [
    {
      "lean": "left | lean_left | center | lean_right | right",
      "framing": "1-2 sentences describing how sources with this lean frame the story (omit leans with no coverage)"
    }
  ],
  "key_divergence": "1-2 sentences identifying the most significant difference in framing or emphasis between left and right coverage. If all sources agree, write 'All sources reported this story similarly with no significant framing differences.'",
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
        print(f"  ✗ JSON parse error: {e}")
        return None
    except Exception as e:
        print(f"  ✗ Synthesis error: {e}")
        return None


def run_synthesis(clusters: list[list[dict]]) -> list[dict]:
    eligible = [c for c in clusters if len(c) >= MIN_CLUSTER_SIZE]
    eligible = eligible[:MAX_CLUSTERS]

    print(f"[SYNTHESIZE] Processing {len(eligible)} multi-source clusters...")
    stories = []
    for i, cluster in enumerate(eligible, 1):
        sources_list = ", ".join(a["source_name"] for a in cluster[:4])
        print(f"  [{i}/{len(eligible)}] {cluster[0]['title'][:60]}... ({len(cluster)} sources: {sources_list})")
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