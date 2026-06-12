"""Read-only local status for the private-only vault."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from services.vault import load_config, split_frontmatter


def collect_status() -> dict:
    cfg = load_config()
    docs = []
    if cfg.data_root.exists():
        docs = [p for p in cfg.data_root.rglob("*.md") if ".git" not in p.parts]
    by_type: Counter[str] = Counter()
    by_visibility: Counter[str] = Counter()
    by_status: Counter[str] = Counter()
    capture_default = 0
    capture_triaged = 0
    capture_archive = 0
    untriaged = 0
    for path in docs:
        try:
            meta, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        by_type[str(meta.get("type") or "")] += 1
        by_visibility[str(meta.get("visibility") or "private")] += 1
        by_status[str(meta.get("status") or "")] += 1
        rel = path.relative_to(cfg.data_root).as_posix()
        if rel.startswith("capture/default/"):
            capture_default += 1
        if rel.startswith("capture/triaged/"):
            capture_triaged += 1
        if rel.startswith("capture/archive/"):
            capture_archive += 1
        if meta.get("type") == "capture" and meta.get("classification") == "untriaged":
            untriaged += 1
    return {
        "data_root": str(cfg.data_root),
        "runtime_root": str(cfg.runtime_root),
        "markdown_docs": len(docs),
        "capture_default": capture_default,
        "capture_triaged": capture_triaged,
        "capture_archive": capture_archive,
        "untriaged": untriaged,
        "requests": len(list((cfg.data_root / "requests").glob("REQ-*.md")))
        if (cfg.data_root / "requests").exists()
        else 0,
        "by_type": dict(sorted(by_type.items())),
        "by_visibility": dict(sorted(by_visibility.items())),
        "by_status": dict(sorted(by_status.items())),
    }


def render_text(snapshot: dict) -> str:
    return (
        "second-brain-compact status\n"
        f"  data_root={snapshot['data_root']}\n"
        f"  markdown_docs={snapshot['markdown_docs']} "
        f"capture/default={snapshot['capture_default']} "
        f"capture/triaged={snapshot['capture_triaged']} "
        f"capture/archive={snapshot['capture_archive']} "
        f"untriaged={snapshot['untriaged']} requests={snapshot['requests']}\n"
        f"  by_type={snapshot['by_type']}\n"
        f"  by_visibility={snapshot['by_visibility']}\n"
        f"  by_status={snapshot['by_status']}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="brain-status")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    snapshot = collect_status()
    print(json.dumps(snapshot, indent=2, ensure_ascii=False) if args.json else render_text(snapshot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

