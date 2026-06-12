from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _redact_args(args: Mapping[str, object]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in args.items():
        if key == "body":
            out["body_chars"] = len(str(value))
        elif isinstance(value, str):
            out[key] = value[:200] + ("..." if len(value) > 200 else "")
        elif isinstance(value, list):
            out[key] = value[:20]
        else:
            out[key] = value
    return out


def record(path: Path | None, device: str, tool: str, args: Mapping[str, object], payload: Mapping[str, object]) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        outcome = payload.get("status") or ("error" if payload.get("error") else "ok")
        row = {
            "ts": _now(),
            "device": device,
            "tool": tool,
            "args": _redact_args(args),
            "outcome": outcome,
        }
        if payload.get("capture_id"):
            row["capture_id"] = payload["capture_id"]
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        return

