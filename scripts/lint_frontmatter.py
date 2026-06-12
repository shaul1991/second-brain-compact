"""Small frontmatter linter used by tests and future CI."""
from __future__ import annotations

import argparse
from pathlib import Path

from services.vault import split_frontmatter


REQUIRED = {
    "capture": {
        "id",
        "type",
        "status",
        "visibility",
        "title",
        "owner",
        "created_at",
        "updated_at",
        "source",
        "classification",
        "promotion_target",
    }
}


def lint_path(path: Path) -> list[str]:
    meta, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    doc_type = str(meta.get("type") or "")
    missing = REQUIRED.get(doc_type, set()) - set(meta)
    return [f"{path}: missing {name}" for name in sorted(missing)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lint-frontmatter")
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)
    findings: list[str] = []
    for raw in args.paths:
        root = Path(raw)
        paths = root.rglob("*.md") if root.is_dir() else [root]
        for path in paths:
            findings.extend(lint_path(path))
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

