from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.ingestion.emit import emit_capture
from services.promotion.core import promote_capture
from services.retrieval import documents
from services.retrieval.semantic import is_local_url
from services.vault import init_vault, load_config


class FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc) -> bool:
        return False


class FakeEngine:
    """Records every request and emulates supermemory's documents/search API."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self.documents: dict[str, dict] = {}

    def __call__(self, req, timeout=None):
        method = req.get_method()
        url = req.full_url
        body = json.loads(req.data.decode("utf-8")) if req.data else None
        self.calls.append((method, url, body))
        if url.endswith("/v3/documents") and method == "POST":
            self.documents[body["customId"]] = body
            return FakeResponse({"id": body["customId"], "status": "queued"})
        if url.endswith("/v4/search") and method == "POST":
            # Emulate semantic recall: return all indexed docs regardless of the
            # exact query string (we cannot run real embeddings in a unit test).
            results = [
                {"content": doc["content"], "score": 0.9, "docId": cid,
                 "metadata": doc.get("metadata", {})}
                for cid, doc in self.documents.items()
            ]
            return FakeResponse({"results": results, "total": len(results)})
        if url.endswith("/v3/documents/bulk") and method == "DELETE":
            self.documents.clear()
            return FakeResponse({"status": "ok"})
        if "/v3/documents/" in url and method == "DELETE":
            return FakeResponse({"status": "ok"})
        return FakeResponse({})

    def added_bodies(self) -> list[dict]:
        return [b for m, u, b in self.calls if u.endswith("/v3/documents") and m == "POST" and b]


class SemanticEnvCase(unittest.TestCase):
    base_url = "http://supermemory:6767"

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = {
            "PRIVATE_REPO_PATH": str(self.root / "data"),
            "SECOND_BRAIN_RUNTIME_PATH": str(self.root / "runtime"),
            "INGESTION_CAPTURE_PATH": str(self.root / "data" / "capture" / "default"),
            "INGESTION_LEDGER_PATH": str(self.root / "runtime" / "ingestion" / "seen-keys"),
            "MCP_AUDIT_LOG": str(self.root / "runtime" / "mcp" / "audit.log.jsonl"),
            "RUNTIME_LOGS_PATH": str(self.root / "runtime" / "logs"),
            "MCP_DEVICE": "local",
            "DATA_GIT_BRANCH": "main",
            "SEMANTIC_SEARCH_ENABLED": "true",
            "SUPERMEMORY_BASE_URL": self.base_url,
            "SUPERMEMORY_CONTAINER_TAG": "sb-test",
            "PYTHONPATH": str(ROOT),
        }
        self.patch = mock.patch.dict(os.environ, self.env, clear=False)
        self.patch.start()
        init_vault(load_config())

    def tearDown(self) -> None:
        self.patch.stop()
        self.tmp.cleanup()

    def _promote(self, body: str, title: str) -> str:
        res = emit_capture({"body": body, "title": title})
        promote_capture(res.capture_id, target_dir="notes")
        return res.capture_id


class IsLocalUrlTests(unittest.TestCase):
    def test_local_hosts_allowed(self):
        for url in [
            "http://localhost:6767",
            "http://127.0.0.1:6767",
            "http://supermemory:6767",  # docker service name
            "http://10.0.0.5:6767",
            "http://192.168.1.9",
            "http://host.local",
        ]:
            self.assertTrue(is_local_url(url), url)

    def test_public_hosts_blocked(self):
        for url in [
            "https://api.supermemory.ai/v3",
            "http://example.com",
            "https://8.8.8.8",
        ]:
            self.assertFalse(is_local_url(url), url)


class SemanticRecallTests(SemanticEnvCase):
    def test_ac1_semantic_results_used_when_enabled(self):
        fake = FakeEngine()
        with mock.patch("urllib.request.urlopen", fake):
            self._promote("alpha private implementation note", "Alpha")
            # Query with words absent from the note — keyword search would miss,
            # but the semantic backend returns the mapped note.
            hits = documents.search("과일 무관한질의")
        self.assertEqual(len(hits), 1)
        self.assertTrue(hits[0]["doc_id"].startswith("private:notes/"))
        self.assertGreater(hits[0]["vector_score"], 0.0)

    def test_ac2_restricted_never_indexed_or_sent(self):
        fake = FakeEngine()
        with mock.patch("urllib.request.urlopen", fake):
            # A capture stays restricted and must never be sent to the engine.
            emit_capture({"body": "TOPSECRET restricted body", "title": "Secret"})
            # capture alone triggers no document POST.
            self.assertEqual(fake.added_bodies(), [])
            # A separate note is promoted, then we rebuild the index.
            self._promote("public knowledge note", "Public")
            documents.reindex()
        sent = json.dumps(fake.added_bodies(), ensure_ascii=False)
        self.assertNotIn("TOPSECRET", sent)
        self.assertIn("public knowledge note", sent)

    def test_ac3_fallback_when_engine_down(self):
        def boom(req, timeout=None):
            raise urllib.error.URLError("connection refused")

        with mock.patch("urllib.request.urlopen", boom):
            # promote still succeeds (indexing is best-effort)
            self._promote("alpha keyword note", "Alpha")
            hits = documents.search("alpha")
        self.assertEqual(len(hits), 1)
        self.assertGreater(hits[0]["keyword_score"], 0.0)
        self.assertEqual(hits[0]["vector_score"], 0.0)

    def test_ac4_reindex_clears_then_adds(self):
        fake = FakeEngine()
        with mock.patch("urllib.request.urlopen", fake):
            # Emit both before promoting so each gets a distinct capture id
            # (capture numbering reuses freed numbers once default empties).
            r1 = emit_capture({"body": "first note about cats", "title": "First"})
            r2 = emit_capture({"body": "second note about dogs", "title": "Second"})
            promote_capture(r1.capture_id, target_dir="notes")
            promote_capture(r2.capture_id, target_dir="notes")
            result = documents.reindex()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["added"], 2)
        # reindex must clear (bulk DELETE) before re-adding.
        methods = [(m, u) for m, u, _ in fake.calls]
        bulk = next(i for i, (m, u) in enumerate(methods) if m == "DELETE" and u.endswith("/bulk"))
        adds_after = [i for i, (m, u) in enumerate(methods)
                      if m == "POST" and u.endswith("/v3/documents") and i > bulk]
        self.assertEqual(len(adds_after), 2)


class EgressGuardTests(SemanticEnvCase):
    base_url = "https://api.supermemory.ai"

    def test_ac5_public_url_no_egress(self):
        fake = FakeEngine()
        with mock.patch("urllib.request.urlopen", fake):
            self._promote("alpha note for egress test", "Alpha")
            hits = documents.search("alpha")
        # The client must refuse the public URL: zero network calls made.
        self.assertEqual(fake.calls, [])
        # And recall still works via keyword fallback.
        self.assertEqual(len(hits), 1)
        self.assertGreater(hits[0]["keyword_score"], 0.0)


if __name__ == "__main__":
    unittest.main()
