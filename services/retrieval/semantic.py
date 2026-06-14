"""supermemory REST backend for semantic recall — stdlib only, fail-safe.

Every network call targets a LOCAL supermemory service. Any failure (engine
down, timeout, non-local URL, bad response) raises ``EngineUnavailable`` so the
caller can fall back to keyword search. Nothing here ever blocks the core
capture/promote/recall flow, and nothing is ever sent to a non-local host.

No third-party packages: we speak the documented REST API over urllib to keep
second-brain-compact's zero-dependency posture.
"""
from __future__ import annotations

import ipaddress
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

from services.vault import VaultConfig, load_config

_CUSTOM_ID_RE = re.compile(r"[^A-Za-z0-9_-]+")
_LOOPBACK_HOSTS = {"localhost", "0.0.0.0"}


class EngineUnavailable(RuntimeError):
    """The semantic engine cannot be used right now; caller should fall back."""


def is_local_url(url: str) -> bool:
    """True only for loopback / private / docker-internal / *.local hosts.

    Enforces the "no external transmission" invariant (R-006 / AC-5): the client
    refuses to talk to anything that looks like a public endpoint.
    """
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False
    if host in _LOOPBACK_HOSTS or host.endswith(".local") or host.endswith(".internal"):
        return True
    # Single-label hostnames are docker-compose service names (e.g. "supermemory").
    if "." not in host and ":" not in host:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


def custom_id(doc_id: str) -> str:
    """Path/customId-safe form of a vault doc_id (alnum, '-', '_', max 100)."""
    return _CUSTOM_ID_RE.sub("_", doc_id)[:100]


@dataclass(frozen=True)
class SemanticClient:
    base_url: str
    container: str
    api_key: str | None
    timeout: float

    @classmethod
    def from_config(cls, cfg: VaultConfig | None = None) -> "SemanticClient":
        config = cfg or load_config()
        return cls(
            base_url=config.semantic_base_url.rstrip("/"),
            container=config.semantic_container,
            api_key=config.semantic_api_key,
            timeout=config.semantic_timeout,
        )

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        if not is_local_url(self.base_url):
            raise EngineUnavailable(f"refusing non-local base_url: {self.base_url}")
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise EngineUnavailable(str(exc)) from exc
        if not body:
            return {}
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise EngineUnavailable(f"bad response: {exc}") from exc

    def available(self) -> bool:
        try:
            self._request(
                "POST",
                "/v4/search",
                {"q": "healthcheck", "containerTag": self.container, "limit": 1},
            )
            return True
        except EngineUnavailable:
            return False

    def add(self, doc_id: str, content: str, *, title: str | None = None) -> dict:
        metadata: dict[str, object] = {"vault_doc_id": doc_id}
        if title:
            metadata["title"] = title
        payload = {
            "customId": custom_id(doc_id),
            "content": content,
            "containerTags": [self.container],
            "metadata": metadata,
        }
        return self._request("POST", "/v3/documents", payload)

    def remove(self, doc_id: str) -> dict:
        # Best-effort single delete by customId. reindex() reconciles if this misses.
        cid = urllib.parse.quote(custom_id(doc_id), safe="")
        return self._request("DELETE", f"/v3/documents/{cid}")

    def clear(self) -> dict:
        # Drop everything in this vault's container; used as the first reindex step.
        return self._request(
            "DELETE", "/v3/documents/bulk", {"containerTags": [self.container]}
        )

    def search(self, query: str, top_k: int = 5) -> list[dict[str, object]]:
        limit = max(1, min(int(top_k), 50))
        data = self._request(
            "POST",
            "/v4/search",
            {
                "q": query,
                "containerTag": self.container,
                "searchMode": "hybrid",
                "limit": limit,
                "rerank": True,
            },
        )
        hits: list[dict[str, object]] = []
        seen: set[str] = set()
        for item in data.get("results") or []:
            meta = item.get("metadata") or {}
            doc_id = meta.get("vault_doc_id")
            # Only surface results we can map back to a vault note.
            if not isinstance(doc_id, str) or doc_id in seen:
                continue
            seen.add(doc_id)
            score = round(float(item.get("score") or 0.0), 6)
            hits.append(
                {
                    "doc_id": doc_id,
                    "title": str(meta.get("title") or doc_id.rsplit("/", 1)[-1]),
                    "repo": "private",
                    "path": doc_id.split(":", 1)[1] if ":" in doc_id else doc_id,
                    "score": score,
                    "keyword_score": 0.0,
                    "vector_score": score,
                }
            )
        return hits
