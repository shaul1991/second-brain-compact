"""Minimal JSON-RPC 2.0 stdio MCP server."""
from __future__ import annotations

import json
import sys
from typing import IO, Mapping

from services.mcp import audit
from services.mcp.tools import TOOLS
from services.vault import load_config

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "second-brain-compact", "version": "1"}

TOOL_DEFS = [
    {
        "name": "recall",
        "description": "Search the local private vault. Returns hits without bodies.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 50},
            },
        },
    },
    {
        "name": "get_note",
        "description": "Read a note by doc_id. Restricted notes are never returned.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["doc_id"],
            "properties": {"doc_id": {"type": "string", "minLength": 1}},
        },
    },
    {
        "name": "capture",
        "description": "Capture a note as restricted/draft/untriaged pending promotion.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["body"],
            "properties": {
                "body": {"type": "string", "minLength": 1},
                "title": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "links": {"type": "array", "items": {"type": "string"}},
                "format": {"enum": ["text", "markdown"]},
                "request_id": {"type": "string", "pattern": "^REQ-[0-9]{8}-[0-9]{4}$"},
                "session_id": {"type": "string"},
                "seq": {"type": "integer", "minimum": 0},
                "instance": {"type": "string"},
                "occurred_at": {"type": "string"},
            },
        },
    },
    {
        "name": "status",
        "description": "Read-only local vault status: counts and metadata only.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {},
        },
    },
]


def _result(request_id: object, result: object) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: object, code: int, message: str) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _call_tool(params: Mapping[str, object]) -> dict[str, object]:
    cfg = load_config()
    name = str(params.get("name") or "")
    args = params.get("arguments") or {}
    if not isinstance(args, dict):
        args = {}
    handler = TOOLS.get(name)
    if handler is None:
        payload = {"error": "unknown_tool", "reason": f"unknown tool: {name}"}
    else:
        payload = handler(args)
    audit.record(cfg.audit_log, cfg.device, name, args, payload)
    is_error = bool(payload.get("error")) or payload.get("status") == "rejected"
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
        "isError": is_error,
    }


def handle_message(message: Mapping[str, object]) -> dict[str, object] | None:
    method = message.get("method")
    request_id = message.get("id")
    if request_id is None:
        return None
    if method == "initialize":
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        requested = params.get("protocolVersion") if isinstance(params, dict) else None
        return _result(
            request_id,
            {
                "protocolVersion": requested or PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            },
        )
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": TOOL_DEFS})
    if method == "tools/call":
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        return _result(request_id, _call_tool(params))
    return _error(request_id, -32601, f"unknown method: {method}")


def serve(stdin: IO[str] = sys.stdin, stdout: IO[str] = sys.stdout) -> None:
    for raw in stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            stdout.write(json.dumps(_error(None, -32700, "parse error")) + "\n")
            stdout.flush()
            continue
        response = handle_message(message)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()


def main() -> None:
    serve()

