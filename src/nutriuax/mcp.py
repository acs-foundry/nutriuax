"""Hardened JSON-RPC 2.0 STDIO MCP server for NutriUAX (Anything-Craft / `craft_box.py` compatible).

Security properties:
- Line-delimited JSON-RPC 2.0 over stdin/stdout with strict `MAX_MCP_LINE_BYTES = 8 MiB` cap
  (reads bounded chunks so an unbounded malicious line cannot exhaust memory).
- Strictly confines every filesystem read/write to `--automation-read-root` and
  `--automation-write-root` via `PathSandbox`.
- Never writes logs or banners to stdout; diagnostics only go to stderr.
- Exposes all 12 symmetrical NutriUAX commands (`nutriuax_<tool>` and dotted names supported).
"""
from __future__ import annotations

import json
import sys
from typing import Any, BinaryIO

from . import __version__
from .commands import COMMANDS, dispatch
from .sandbox import PathSandbox, SandboxError

MAX_MCP_LINE_BYTES = 8 * 1024 * 1024  # 8 MiB
SUPPORTED_PROTOCOL_VERSIONS = ("2025-03-26", "2024-11-05")


def _mcp_tool_name(cmd_id: str) -> str:
    return "nutriuax_" + cmd_id.replace(".", "_")


def _cmd_id_from_tool(tool_name: str) -> str:
    if tool_name in COMMANDS:
        return tool_name
    for cid in COMMANDS:
        if _mcp_tool_name(cid) == tool_name:
            return cid
    raise KeyError(f"Unknown MCP tool: {tool_name}")


def build_tools_list() -> list[dict[str, Any]]:
    return [
        {
            "name": _mcp_tool_name(spec.id),
            "description": f"[{spec.id}] {spec.summary}",
            "inputSchema": spec.input_schema,
        }
        for spec in COMMANDS.values()
    ]


def handle_request(req: dict[str, Any], sandbox: PathSandbox) -> dict[str, Any] | None:
    """Processes a single JSON-RPC 2.0 message and returns the response dict (or None for notifications)."""
    if not isinstance(req, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
    method = req.get("method")
    req_id = req.get("id")
    params = req.get("params") or {}

    if method is None:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32600, "message": "Missing method"}}

    # Notifications have no id and expect no reply
    if method == "notifications/initialized" or (req_id is None and str(method).startswith("notifications/")):
        return None

    if method == "initialize":
        client_ver = str(params.get("protocolVersion") or SUPPORTED_PROTOCOL_VERSIONS[0])
        chosen = client_ver if client_ver in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[0]
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": chosen,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "nutriuax-mcp", "version": __version__},
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": build_tools_list()}}

    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": "Tool arguments must be a JSON object."},
            }
        try:
            cid = _cmd_id_from_tool(name)
            result = dispatch(cid, arguments, sandbox)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
                    "isError": False,
                },
            }
        except KeyError as e:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": str(e)}}
        except (SandboxError, ValueError, FileNotFoundError, RuntimeError) as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"error": str(e)}, ensure_ascii=False)}],
                    "isError": True,
                },
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": f"Internal error: {e}"},
            }

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def read_bounded_line(stream: BinaryIO, max_bytes: int = MAX_MCP_LINE_BYTES) -> tuple[bytes | None, bool]:
    """Reads one newline-terminated line with a hard memory cap (`max_bytes`).

    Returns `(line_bytes, oversized)`. When `line_bytes is None`, EOF was reached.
    If oversized, discards remaining bytes up to the next newline without buffering them.
    """
    raw = stream.readline(max_bytes + 1)
    if not raw:
        return None, False
    if len(raw) > max_bytes and not raw.endswith(b"\n"):
        # Drain until newline or EOF without holding it in memory
        while True:
            chunk = stream.readline(65536)
            if not chunk or chunk.endswith(b"\n"):
                break
        return b"", True
    if len(raw) > max_bytes:
        return b"", True
    return raw, False


def serve_stdio(
    sandbox: PathSandbox,
    in_stream: BinaryIO | None = None,
    out_stream: BinaryIO | None = None,
) -> int:
    """Runs the blocking JSON-RPC 2.0 STDIO loop."""
    inp = in_stream or sys.stdin.buffer
    out = out_stream or sys.stdout.buffer

    while True:
        line, oversized = read_bounded_line(inp, MAX_MCP_LINE_BYTES)
        if line is None:
            break
        if oversized:
            resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": f"Request line exceeds {MAX_MCP_LINE_BYTES} bytes limit."},
            }
            out.write((json.dumps(resp) + "\n").encode("utf-8"))
            out.flush()
            continue
        stripped = line.strip()
        if not stripped:
            continue
        try:
            req = json.loads(stripped.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {e}"}}
            out.write((json.dumps(resp) + "\n").encode("utf-8"))
            out.flush()
            continue
        resp = handle_request(req, sandbox)
        if resp is not None:
            out.write((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
            out.flush()
    return 0
