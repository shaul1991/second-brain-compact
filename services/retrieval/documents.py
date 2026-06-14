from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

from services.vault import iter_markdown, load_config, safe_relative, split_frontmatter

TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣_+-]+")


@dataclass(frozen=True)
class Document:
    repo: str
    path: str
    metadata: dict[str, object]
    body: str

    @property
    def doc_id(self) -> str:
        return f"{self.repo}:{self.path}"

    @property
    def title(self) -> str:
        return str(self.metadata.get("title") or Path(self.path).stem)

    @property
    def visibility(self) -> str:
        return str(self.metadata.get("visibility") or "private")

    @property
    def search_text(self) -> str:
        fields = [
            self.title,
            str(self.metadata.get("type") or ""),
            str(self.metadata.get("status") or ""),
            str(self.metadata.get("tags") or ""),
            self.body,
        ]
        return "\n".join(fields)


def tokenize(text: str) -> list[str]:
    return [tok.lower() for tok in TOKEN_RE.findall(text)]


def collect_documents(*, include_restricted: bool = False) -> list[Document]:
    cfg = load_config()
    docs: list[Document] = []
    for path in iter_markdown(cfg.data_root):
        # Runtime data and internal git metadata never belong to retrieval.
        if ".git" in path.parts:
            continue
        try:
            meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        doc = Document(
            repo="private",
            path=safe_relative(path, cfg.data_root),
            metadata=meta,
            body=body,
        )
        if not include_restricted and doc.visibility == "restricted":
            continue
        docs.append(doc)
    return docs


def search(query: str, top_k: int = 5) -> list[dict[str, object]]:
    """Semantic-first recall with keyword fallback.

    When the semantic backend is enabled and reachable, recall returns its
    hybrid results (filling the previously-empty ``vector_score``). If the
    engine is disabled, unreachable, or errors, recall falls back to the
    local keyword search so the system always works (R-004 / R-005).
    """
    cfg = load_config()
    if cfg.semantic_enabled:
        try:
            from services.retrieval.semantic import EngineUnavailable, SemanticClient

            return SemanticClient.from_config(cfg).search(query, top_k=top_k)
        except EngineUnavailable:
            pass  # engine down → keyword fallback
        except Exception:
            pass  # never let the optional backend break recall
    return _keyword_search(query, top_k=top_k)


def _keyword_search(query: str, top_k: int = 5) -> list[dict[str, object]]:
    terms = tokenize(query)
    if not terms:
        return []
    hits = []
    for doc in collect_documents(include_restricted=False):
        tokens = tokenize(doc.search_text)
        if not tokens:
            continue
        counts = {term: tokens.count(term) for term in set(terms)}
        matched = sum(1 for count in counts.values() if count)
        if not matched:
            continue
        tf = sum(counts.values()) / max(len(tokens), 1)
        title_boost = 0.25 if any(term in tokenize(doc.title) for term in terms) else 0.0
        score = matched / math.sqrt(len(set(terms))) + tf + title_boost
        hits.append(
            {
                "doc_id": doc.doc_id,
                "title": doc.title,
                "repo": doc.repo,
                "path": doc.path,
                "score": round(score, 6),
                "keyword_score": round(score, 6),
                "vector_score": 0.0,
            }
        )
    hits.sort(key=lambda item: item["score"], reverse=True)
    return hits[: max(1, min(int(top_k), 50))]


def get_note(doc_id: str) -> dict[str, object] | None:
    for doc in collect_documents(include_restricted=False):
        if doc.doc_id == doc_id:
            return {
                "doc_id": doc.doc_id,
                "visibility": doc.visibility,
                "frontmatter": doc.metadata,
                "body": doc.body,
            }
    return None


def reindex() -> dict[str, object]:
    """Rebuild the semantic index from the vault (R-003 / AC-4).

    Clears this vault's container, then re-adds every non-restricted note.
    This is the source of truth for index/vault consistency: incremental
    add/remove hooks are best-effort, but reindex always reconciles.
    """
    cfg = load_config()
    if not cfg.semantic_enabled:
        return {"status": "disabled"}
    from services.retrieval.semantic import EngineUnavailable, SemanticClient

    client = SemanticClient.from_config(cfg)
    try:
        client.clear()
    except EngineUnavailable as exc:
        return {"status": "unavailable", "reason": str(exc)}
    docs = collect_documents(include_restricted=False)
    added = 0
    failed = 0
    for doc in docs:
        try:
            client.add(doc.doc_id, doc.body, title=doc.title)
            added += 1
        except EngineUnavailable:
            failed += 1
    return {"status": "ok", "added": added, "failed": failed, "total": len(docs)}

