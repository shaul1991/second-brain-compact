from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from services.vault import (
    CAPTURE_ID_RE,
    VaultConfig,
    atomic_write,
    init_vault,
    load_config,
    now_rfc3339,
    render_doc,
    split_frontmatter,
)


class PromotionError(ValueError):
    pass


@dataclass(frozen=True)
class MoveResult:
    outcome: str
    capture_id: str
    target: Path
    breadcrumb: Path | None = None


def _capture_path(capture_id: str, cfg: VaultConfig) -> Path:
    if not CAPTURE_ID_RE.match(capture_id):
        raise PromotionError(f"invalid capture id: {capture_id}")
    path = cfg.data_root / "capture" / "default" / f"{capture_id}.md"
    if not path.exists():
        raise PromotionError(f"capture not found: {path}")
    return path


def _read_capture(path: Path) -> tuple[dict[str, object], str]:
    meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
    if meta.get("type") != "capture":
        raise PromotionError("source is not a type:capture document")
    return meta, body


def promote_capture(
    capture_id: str,
    *,
    target_dir: str = "notes",
    dry_run: bool = False,
    cfg: VaultConfig | None = None,
) -> MoveResult:
    config = cfg or load_config()
    init_vault(config)
    src = _capture_path(capture_id, config)
    meta, body = _read_capture(src)
    now = now_rfc3339()
    target_dir = target_dir.strip("/ ") or "notes"
    if target_dir.startswith("capture/") or target_dir.startswith("../") or "/../" in target_dir:
        raise PromotionError("target must be a private vault directory outside capture/")

    filename = f"{capture_id}.md"
    target = config.data_root / target_dir / filename
    breadcrumb = config.data_root / "capture" / "triaged" / filename
    promoted = dict(meta)
    promoted.update(
        {
            "status": "draft",
            "visibility": "private",
            "classification": "private",
            "promotion_target": "private",
            "updated_at": now,
            "promoted_at": now,
            "promoted_to": f"private:{target_dir}/{filename}",
        }
    )
    triaged = dict(meta)
    triaged.update(
        {
            "status": "archived",
            "visibility": "restricted",
            "classification": "private",
            "promotion_target": "private",
            "updated_at": now,
            "promoted_at": now,
            "promoted_to": f"private:{target_dir}/{filename}",
        }
    )
    if dry_run:
        return MoveResult("dry-run", capture_id, target, breadcrumb)
    if target.exists():
        raise PromotionError(f"target already exists: {target}")
    atomic_write(target, render_doc(promoted, body))
    pointer = f"# Promoted Capture\n\nPromoted to `private:{target_dir}/{filename}`.\n"
    atomic_write(breadcrumb, render_doc(triaged, pointer))
    src.unlink()
    return MoveResult("promoted", capture_id, target, breadcrumb)


def archive_capture(
    capture_id: str,
    *,
    reason: str = "manual archive",
    dry_run: bool = False,
    cfg: VaultConfig | None = None,
) -> MoveResult:
    config = cfg or load_config()
    init_vault(config)
    src = _capture_path(capture_id, config)
    meta, body = _read_capture(src)
    now = now_rfc3339()
    target = config.data_root / "capture" / "archive" / f"{capture_id}.md"
    archived = dict(meta)
    archived.update(
        {
            "status": "archived",
            "visibility": "restricted",
            "classification": "archived",
            "promotion_target": "archive",
            "updated_at": now,
            "archived_at": now,
            "archive_reason": reason,
        }
    )
    if dry_run:
        return MoveResult("dry-run", capture_id, target)
    if target.exists():
        raise PromotionError(f"archive target already exists: {target}")
    atomic_write(target, render_doc(archived, body))
    src.unlink()
    return MoveResult("archived", capture_id, target)

