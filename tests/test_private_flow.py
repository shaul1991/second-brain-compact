from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.ingestion.emit import emit_capture
from services.mcp import server
from services.promotion.core import promote_capture
from services.retrieval.documents import get_note, search
from services.vault import init_vault, load_config, split_frontmatter


class EnvCase(unittest.TestCase):
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
            "PYTHONPATH": str(ROOT),
        }
        self.patch = mock.patch.dict(os.environ, self.env, clear=False)
        self.patch.start()

    def tearDown(self) -> None:
        self.patch.stop()
        self.tmp.cleanup()


class PrivateFlowTests(EnvCase):
    def test_init_capture_promote_recall_get_note(self):
        init_vault(load_config())
        result = emit_capture({"body": "alpha private implementation note", "title": "Alpha"})
        self.assertEqual(result.status, "written")
        self.assertTrue(result.path and result.path.exists())
        meta, _ = split_frontmatter(result.path.read_text(encoding="utf-8"))
        self.assertEqual(meta["visibility"], "restricted")
        self.assertEqual(meta["status"], "draft")
        self.assertEqual(meta["classification"], "untriaged")
        self.assertEqual(meta["promotion_target"], "undecided")

        self.assertEqual(search("alpha"), [])
        promoted = promote_capture(result.capture_id, target_dir="notes")
        self.assertEqual(promoted.outcome, "promoted")
        hits = search("alpha")
        self.assertEqual(len(hits), 1)
        note = get_note(hits[0]["doc_id"])
        self.assertIsNotNone(note)
        self.assertEqual(note["visibility"], "private")
        self.assertIn("alpha private", note["body"])

    def test_mcp_dispatch(self):
        init_vault(load_config())
        init = server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(init["result"]["serverInfo"]["name"], "second-brain-compact")
        tools = server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual({t["name"] for t in tools["result"]["tools"]}, {"recall", "get_note", "capture", "status"})
        status = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "status", "arguments": {}},
            }
        )
        self.assertFalse(status["result"]["isError"])
        self.assertIn("markdown_docs", status["result"]["structuredContent"])

    def test_capture_idempotent(self):
        init_vault(load_config())
        args = {"body": "dedup note", "session_id": "s1", "seq": 1}
        first = emit_capture(args)
        second = emit_capture(args)
        self.assertEqual(first.status, "written")
        self.assertEqual(second.status, "duplicate")
        self.assertEqual(first.capture_id, second.capture_id)


class DataGitTests(EnvCase):
    def _brain(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(ROOT / "bin" / "brain"), *args],
            cwd=ROOT,
            env={**os.environ, **self.env},
            text=True,
            capture_output=True,
            check=False,
        )

    def test_data_git_remote_push_pull(self):
        init = self._brain("data", "init")
        self.assertEqual(init.returncode, 0, init.stderr)
        bare = self.root / "remote.git"
        subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
        remote = self._brain("data", "remote", "add", str(bare))
        self.assertEqual(remote.returncode, 0, remote.stderr)

        capture = self._brain("ingest", "--json", '{"body":"git backed note"}')
        self.assertEqual(capture.returncode, 0, capture.stderr)
        commit = self._brain("data", "commit", "-m", "backup: test")
        self.assertEqual(commit.returncode, 0, commit.stderr)
        push = self._brain("data", "push")
        self.assertEqual(push.returncode, 0, push.stderr)
        pull = self._brain("data", "pull")
        self.assertEqual(pull.returncode, 0, pull.stderr)


if __name__ == "__main__":
    unittest.main()

