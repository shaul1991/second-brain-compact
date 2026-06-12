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

