"""
api.py — FastAPI backend for NewsLens.
Endpoints:
  GET  /api/edition/latest        → Latest cached edition
  GET  /api/edition/:id           → Specific edition by ID
  GET  /api/editions              → List recent editions
  POST /api/pipeline/run          → Trigger a fresh pipeline run (async)
  GET  /api/pipeline/status       → Is a pipeline run currently in progress?
"""

import os
import threading
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from database import get_latest_edition, get_edition_by_id, list_editions

app = FastAPI(title="NewsLens API", version="1.0.0")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline_state = {
    "running": False,
    "started_at": None,
    "last_error": None,
}
_pipeline_lock = threading.Lock()


def _run_pipeline_thread():
    from pipeline import run_pipeline
    try:
        run_pipeline()
        with _pipeline_lock:
            pipeline_state["running"] = False
            pipeline_state["last_error"] = None
    except Exception as e:
        with _pipeline_lock:
            pipeline_state["running"] = False
            pipeline_state["last_error"] = str(e)
        print(f"[API] Pipeline failed: {e}")


@app.get("/api/edition/latest")
def get_latest():
    edition = get_latest_edition()
    if not edition:
        raise HTTPException(status_code=404, detail="No editions found. Run the pipeline first.")
    return edition


@app.get("/api/edition/{edition_id}")
def get_edition(edition_id: int):
    edition = get_edition_by_id(edition_id)
    if not edition:
        raise HTTPException(status_code=404, detail=f"Edition {edition_id} not found.")
    return edition


@app.get("/api/editions")
def get_editions(limit: int = 10):
    return list_editions(limit=limit)


@app.post("/api/pipeline/run")
def trigger_pipeline():
    with _pipeline_lock:
        if pipeline_state["running"]:
            return {
                "status": "already_running",
                "message": "A pipeline run is already in progress.",
                "started_at": pipeline_state["started_at"],
            }
        pipeline_state["running"] = True
        pipeline_state["started_at"] = datetime.now(timezone.utc).isoformat()
        pipeline_state["last_error"] = None

    thread = threading.Thread(target=_run_pipeline_thread, daemon=True)
    thread.start()

    return {
        "status": "started",
        "message": "Pipeline run started. Poll /api/pipeline/status for updates.",
        "started_at": pipeline_state["started_at"],
    }


@app.get("/api/pipeline/status")
def pipeline_status():
    with _pipeline_lock:
        return {
            "running": pipeline_state["running"],
            "started_at": pipeline_state["started_at"],
            "last_error": pipeline_state["last_error"],
        }


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)