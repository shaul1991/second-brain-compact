"""Single capture write boundary."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from services.vault import (
    VaultConfig,
    atomic_write,
    init_vault,
    load_config,
    now_rfc3339,
    render_doc,
    slug_token,
)


@dataclass(frozen=True)
class EmitResult:
    status: str
    capture_id: str | None = None
    path: Path | None = None
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in {"written", "duplicate"}


def _capture_date(stamp: str) -> str:
    return stamp[:10].replace("-", "")


def _next_capture_id(capture_dir: Path, device: str, date: str) -> str:
    highest = 0
    if capture_dir.exists():
        for path in capture_dir.glob(f"CAP-{device}-{date}-*.md"):
            try:
                highest = max(highest, int(path.stem.rsplit("-", 1)[1]))
            except (IndexError, ValueError):
                continue
    return f"CAP-{device}-{date}-{highest + 1:04d}"


def _ledger_path(config: VaultConfig, key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return config.ledger_dir / f"{digest}.json"


def _idempotency_key(payload: Mapping[str, object]) -> str:
    session = str(payload.get("session_id") or "stdio")
    seq = payload.get("seq")
    if seq is not None:
        return f"mcp:{session}:{int(seq):04d}"
    body = str(payload.get("body") or "")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    return f"mcp:{session}:{digest}"


def _title(payload: Mapping[str, object]) -> str:
    explicit = str(payload.get("title") or "").strip()
    if explicit:
        return explicit[:120]
    for line in str(payload.get("body") or "").splitlines():
        clean = line.strip().lstrip("#").strip()
        if clean:
            return clean[:120]
    return "Untitled capture"


def emit_capture(payload: Mapping[str, object], config: VaultConfig | None = None) -> EmitResult:
    cfg = config or load_config()
    body = str(payload.get("body") or "").strip()
    if not body:
        return EmitResult(status="rejected", reason="body is required")

    init_vault(cfg)
    received_at = str(payload.get("received_at") or now_rfc3339())
    occurred_at = str(payload.get("occurred_at") or received_at)
    device = slug_token(str(payload.get("instance") or cfg.device), "local")
    key = _idempotency_key(payload)
    ledger = _ledger_path(cfg, key)
    if ledger.exists():
        try:
            existing = json.loads(ledger.read_text(encoding="utf-8"))
            capture_id = existing.get("capture_id")
        except json.JSONDecodeError:
            capture_id = None
        path = cfg.capture_dir / f"{capture_id}.md" if capture_id else None
        return EmitResult(status="duplicate", capture_id=capture_id, path=path)

    capture_id = _next_capture_id(cfg.capture_dir, device, _capture_date(received_at))
    tags = []
    for tag in list(payload.get("tags") or []) + ["ingested", "mcp"]:
        tag = str(tag).strip()
        if tag and tag not in tags:
            tags.append(tag)

    frontmatter: dict[str, object] = {
        "id": capture_id,
        "type": "capture",
        "status": "draft",
        "visibility": "restricted",
        "title": _title(payload),
        "owner": cfg.owner,
        "created_at": received_at,
        "updated_at": received_at,
        "source": "mcp",
        "related": list(payload.get("links") or []),
        "tags": tags,
        "classification": "untriaged",
        "promotion_target": "undecided",
        "ingestion_channel": "mcp",
        "ingestion_occurred_at": occurred_at,
        "idempotency_key": key,
    }
    if payload.get("request_id"):
        frontmatter["request_id"] = str(payload["request_id"])

    doc_body = (
        f"# Capture: {frontmatter['title']}\n\n"
        "## Raw Notes\n\n"
        f"{body}\n\n"
        "## Context\n\n"
        "- Ingested through the local MCP capture boundary.\n"
    )
    path = cfg.capture_dir / f"{capture_id}.md"
    atomic_write(path, render_doc(frontmatter, doc_body))
    atomic_write(ledger, json.dumps({"capture_id": capture_id}, ensure_ascii=False))
    return EmitResult(status="written", capture_id=capture_id, path=path)

