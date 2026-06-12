from __future__ import annotations

from typing import Mapping

from scripts.brain_status import collect_status
from services.ingestion.emit import emit_capture
from services.retrieval.documents import get_note as read_note
from services.retrieval.documents import search
from services.vault import load_config


def recall(args: Mapping[str, object]) -> dict[str, object]:
    query = str(args.get("query") or "").strip()
    if not query:
        return {"error": "invalid_input", "reason": "query is required"}
    try:
        top_k = int(args.get("top_k", 5))
    except (TypeError, ValueError):
        return {"error": "invalid_input", "reason": "top_k must be an integer"}
    hits = search(query, top_k=top_k)
    return {"hits": hits, "count": len(hits)}


def get_note(args: Mapping[str, object]) -> dict[str, object]:
    doc_id = str(args.get("doc_id") or "").strip()
    if not doc_id:
        return {"error": "invalid_input", "reason": "doc_id is required"}
    note = read_note(doc_id)
    if note is None:
        return {"error": "not_accessible", "reason": "not found or restricted"}
    return note


def capture(args: Mapping[str, object]) -> dict[str, object]:
    cfg = load_config()
    payload = dict(args)
    payload.setdefault("instance", cfg.device)
    result = emit_capture(payload, cfg)
    return {
        "status": result.status,
        "capture_id": result.capture_id,
        "reason": result.reason,
    }


def status(args: Mapping[str, object]) -> dict[str, object]:
    return collect_status()


TOOLS = {
    "recall": recall,
    "get_note": get_note,
    "capture": capture,
    "status": status,
}

