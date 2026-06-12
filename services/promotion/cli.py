from __future__ import annotations

import argparse
import json

from services.promotion.core import PromotionError, archive_capture, promote_capture


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="promotion")
    sub = parser.add_subparsers(dest="command", required=True)

    promote = sub.add_parser("promote")
    promote.add_argument("--id", required=True)
    promote.add_argument("--target", default="notes")
    promote.add_argument("--dry-run", action="store_true")

    archive = sub.add_parser("archive")
    archive.add_argument("--id", required=True)
    archive.add_argument("--reason", default="manual archive")
    archive.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "promote":
            result = promote_capture(args.id, target_dir=args.target, dry_run=args.dry_run)
        else:
            result = archive_capture(args.id, reason=args.reason, dry_run=args.dry_run)
    except PromotionError as exc:
        print(json.dumps({"outcome": "rejected", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {
                "outcome": result.outcome,
                "capture_id": result.capture_id,
                "target": str(result.target),
                "breadcrumb": str(result.breadcrumb) if result.breadcrumb else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

