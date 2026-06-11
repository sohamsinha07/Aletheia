import feedparser
import trafilatura
import httpx
import json
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SOURCES_PATH = Path(__file__).parent / "sources.json"
MAX_ARTICLES_PER_SOURCE = 15
FETCH_TIMEOUT = 10

def load_sources() -> list[dict]:
    with open(SOURCES_PATH) as f:
        return json.load(f)["sources"]

def fetch_full_text(url: str) -> Optional[str]:
    try:
        response = httpx.get(url, timeout=FETCH_TIMEOUT, follow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0 (compatible; Aletheia/1.0)"})
        text = trafilatura.extract(response.text, include_comments=False, include_tables=False)
        return text[:3000] if text else None
    except Exception:
        return None

def article_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]

def ingest_source(source: dict) -> list[dict]:
    articles = []
    print(f"  -> Fetching {source['name']} ({source['rss']})")
    try:
        response = httpx.get(source["rss"], timeout=FETCH_TIMEOUT, follow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0 (compatible; Aletheia/1.0)"})
        response.raise_for_status()
        feed = feedparser.parse(response.text)
    except Exception as e:
        print(f"    x Failed to fetch feed: {e}")
        return []
    entries = feed.entries[:MAX_ARTICLES_PER_SOURCE]
    for entry in entries:
        url = entry.get("link", "")
        if not url:
            continue
        title = entry.get("title", "").strip()
        summary = entry.get("summary", "").strip()
        full_text = fetch_full_text(url)
        body = full_text if full_text else summary
        if not title or not body:
            continue
        published = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).isoformat()
        else:
            published = datetime.now(timezone.utc).isoformat()
        articles.append({
            "id": article_id(url),
            "title": title,
            "url": url,
            "body": body,
            "source_name": source["name"],
            "source_domain": source["domain"],
            "lean": source["lean"],
            "lean_score": source["lean_score"],
            "published": published,
        })
        time.sleep(0.1)
    print(f"    Got {len(articles)} articles")
    return articles

def run_ingest() -> list[dict]:
    sources = load_sources()
    all_articles = []
    print(f"\n[INGEST] Fetching {len(sources)} sources...")
    for source in sources:
        articles = ingest_source(source)
        all_articles.extend(articles)
    seen = set()
    deduped = []
    for a in all_articles:
        if a["id"] not in seen:
            seen.add(a["id"])
            deduped.append(a)
    print(f"[INGEST] Done. {len(deduped)} unique articles collected.\n")
    return deduped

if __name__ == "__main__":
    articles = run_ingest()
    print(f"Sample article:\n{json.dumps(articles[0], indent=2)}")
