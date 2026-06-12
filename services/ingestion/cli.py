"""CLI adapter for JSON/stdin capture ingestion."""
from __future__ import annotations

import argparse
import json
import sys

from services.ingestion.emit import emit_capture


def _payload(args: argparse.Namespace) -> dict:
    text = args.json if args.json is not None else sys.stdin.read()
    text = text.strip()
    if not text:
        raise SystemExit("ingest: JSON payload required on stdin or --json")
    value = json.loads(text)
    if not isinstance(value, dict):
        raise SystemExit("ingest: payload must be a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ingest")
    parser.add_argument("--json", help="inline JSON payload")
    args = parser.parse_args(argv)
    result = emit_capture(_payload(args))
    out = {"status": result.status}
    if result.capture_id:
        out["capture_id"] = result.capture_id
    if result.reason:
        out["reason"] = result.reason
    print(json.dumps(out, ensure_ascii=False))
    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

