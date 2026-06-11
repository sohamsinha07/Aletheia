"""
database.py — SQLite persistence layer for NewsLens.
Stores editions (pipeline runs) and story cards.
Uses sqlite-utils for a zero-config setup — no migrations needed.
"""

import json
import sqlite_utils
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "aletheia.db"


def get_db() -> sqlite_utils.Database:
    DB_PATH.parent.mkdir(exist_ok=True)
    db = sqlite_utils.Database(DB_PATH)

    if "editions" not in db.table_names():
        db["editions"].create({
            "id": int,
            "run_at": str,
            "story_count": int,
            "article_count": int,
            "status": str,
            "error": str,
        }, pk="id")

    if "stories" not in db.table_names():
        db["stories"].create({
            "id": int,
            "edition_id": int,
            "headline": str,
            "summary": str,
            "perspectives": str,
            "key_divergence": str,
            "sources": str,
            "genre": str,
            "article_count": int,
        }, pk="id")

    return db


def save_edition(stories: list[dict]) -> int:
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    total_articles = sum(s.get("article_count", 1) for s in stories)

    edition_id = db["editions"].insert({
        "run_at": now,
        "story_count": len(stories),
        "article_count": total_articles,
        "status": "complete",
        "error": None,
    }).last_pk

    for story in stories:
        db["stories"].insert({
            "edition_id": edition_id,
            "headline": story.get("headline", ""),
            "summary": story.get("summary", ""),
            "perspectives": json.dumps(story.get("perspectives", [])),
            "key_divergence": story.get("key_divergence", ""),
            "sources": json.dumps(story.get("sources", [])),
            "genre": story.get("genre", "general"),
            "article_count": story.get("article_count", 1),
        })

    print(f"[DB] Saved edition {edition_id} with {len(stories)} stories.")
    return edition_id


def get_latest_edition() -> dict | None:
    db = get_db()
    editions = list(db["editions"].rows_where(
        "status = 'complete'", order_by="id desc", limit=1
    ))
    if not editions:
        return None

    edition = editions[0]
    stories = list(db["stories"].rows_where(
        "edition_id = ?", [edition["id"]], order_by="article_count desc"
    ))
    for s in stories:
        s["perspectives"] = json.loads(s["perspectives"])
        s["sources"] = json.loads(s["sources"])

    return {
        "edition_id": edition["id"],
        "run_at": edition["run_at"],
        "story_count": edition["story_count"],
        "article_count": edition["article_count"],
        "stories": stories,
    }


def get_edition_by_id(edition_id: int) -> dict | None:
    db = get_db()
    editions = list(db["editions"].rows_where("id = ?", [edition_id]))
    if not editions:
        return None

    edition = editions[0]
    stories = list(db["stories"].rows_where(
        "edition_id = ?", [edition["id"]], order_by="article_count desc"
    ))
    for s in stories:
        s["perspectives"] = json.loads(s["perspectives"])
        s["sources"] = json.loads(s["sources"])

    return {
        "edition_id": edition["id"],
        "run_at": edition["run_at"],
        "story_count": edition["story_count"],
        "article_count": edition["article_count"],
        "stories": stories,
    }


def list_editions(limit: int = 10) -> list[dict]:
    db = get_db()
    return list(db["editions"].rows_where(
        "status = 'complete'", order_by="id desc", limit=limit
    ))