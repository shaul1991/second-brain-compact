"""Private-only vault paths, frontmatter, and initialization helpers."""
from __future__ import annotations

import ast
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

CAPTURE_ID_RE = re.compile(r"^CAP-(?:[a-z0-9]+-)?[0-9]{8}-[0-9]{4}$")
REQ_ID_RE = re.compile(r"^REQ-[0-9]{8}-[0-9]{4}$")
SENTINEL_REQ = "REQ-00000000-0001"


@dataclass(frozen=True)
class VaultConfig:
    data_root: Path
    runtime_root: Path
    capture_dir: Path
    ledger_dir: Path
    logs_dir: Path
    audit_log: Path
    device: str
    owner: str
    data_git_branch: str


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _path_from_env(name: str, fallback: str) -> Path:
    return Path(os.environ.get(name, fallback)).expanduser()


def load_config() -> VaultConfig:
    root = repo_root()
    data_root = _path_from_env("PRIVATE_REPO_PATH", str(root / "data"))
    runtime_root = _path_from_env("SECOND_BRAIN_RUNTIME_PATH", str(root / "runtime"))
    capture_dir = _path_from_env(
        "INGESTION_CAPTURE_PATH", str(data_root / "capture" / "default")
    )
    ledger_dir = _path_from_env(
        "INGESTION_LEDGER_PATH", str(runtime_root / "ingestion" / "seen-keys")
    )
    logs_dir = _path_from_env("RUNTIME_LOGS_PATH", str(runtime_root / "logs"))
    audit_log = _path_from_env(
        "MCP_AUDIT_LOG", str(runtime_root / "mcp" / "audit.log.jsonl")
    )
    return VaultConfig(
        data_root=data_root,
        runtime_root=runtime_root,
        capture_dir=capture_dir,
        ledger_dir=ledger_dir,
        logs_dir=logs_dir,
        audit_log=audit_log,
        device=os.environ.get("MCP_DEVICE", "local") or "local",
        owner=os.environ.get("SECOND_BRAIN_OWNER", "local") or "local",
        data_git_branch=os.environ.get("DATA_GIT_BRANCH", "main") or "main",
    )


def now_rfc3339() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def init_vault(config: VaultConfig | None = None) -> list[Path]:
    cfg = config or load_config()
    paths = [
        cfg.data_root / "capture" / "default",
        cfg.data_root / "capture" / "triaged",
        cfg.data_root / "capture" / "archive",
        cfg.data_root / "notes",
        cfg.data_root / "requests",
        cfg.logs_dir,
        cfg.ledger_dir,
        cfg.audit_log.parent,
    ]
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
    data_ignore = cfg.data_root / ".gitignore"
    if not data_ignore.exists():
        data_ignore.write_text(".DS_Store\n", encoding="utf-8")
    return paths


def split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end is None:
        return {}, text
    meta: dict[str, object] = {}
    for raw in lines[1:end]:
        if not raw or raw[0].isspace() or raw.lstrip().startswith("-"):
            continue
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "[]":
            meta[key] = []
        elif value.startswith("[") and value.endswith("]"):
            try:
                parsed = ast.literal_eval(value)
                meta[key] = parsed if isinstance(parsed, list) else value
            except (SyntaxError, ValueError):
                meta[key] = value
        else:
            meta[key] = value.strip('"').strip("'")
    body = "\n".join(lines[end + 1 :])
    if text.endswith("\n"):
        body += "\n"
    return meta, body


def _render_value(value: object) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(repr(str(item)) for item in value) + "]"
    text = str(value)
    if not text or any(ch in text for ch in [":", "#", "[", "]", "{", "}", "\n"]):
        return repr(text)
    return text


def render_doc(frontmatter: dict[str, object], body: str) -> str:
    lines = ["---"]
    for key, value in frontmatter.items():
        lines.append(f"{key}: {_render_value(value)}")
    lines.append("---")
    if body.startswith("\n"):
        return "\n".join(lines) + body
    return "\n".join(lines) + "\n\n" + body.lstrip("\n")


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text if text.endswith("\n") else text + "\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def safe_relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def iter_markdown(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*.md") if p.is_file())


def slug_token(value: str | None, fallback: str = "local") -> str:
    token = re.sub(r"[^a-z0-9]+", "", (value or "").lower())
    return token[:24] or fallback

