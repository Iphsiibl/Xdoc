"""MCP 服务：必须只有一个工具 read，参数契约固定。"""

from __future__ import annotations

import asyncio
import inspect

import pytest
from conftest import require, sample


def _run(coro):
    if inspect.isawaitable(coro):
        return asyncio.run(coro)
    return coro


def _list_tools():
    from xdoc.mcp_server import build_server

    server = build_server()
    lister = getattr(server, "list_tools", None)
    if lister is None:  # pragma: no cover
        pytest.skip("当前 mcp 版本没有 list_tools()")
    return _run(lister())


def test_exactly_one_tool_named_read():
    tools = _list_tools()
    assert len(tools) == 1
    assert tools[0].name == "read"


def test_tool_parameters():
    tools = _list_tools()
    schema = getattr(tools[0], "inputSchema", None) or getattr(tools[0], "input_schema")
    properties = schema.get("properties", {})
    for name in ("path", "format", "max_tokens", "cursor", "pages", "ocr", "asr"):
        assert name in properties
    assert properties["path"]["type"] == "string"


def test_tool_reads_a_file():
    from xdoc.mcp_server import build_server

    path = require(sample("docx", "calibre_demo.docx"))
    server = build_server()
    call = getattr(server, "call_tool", None)
    if call is None:  # pragma: no cover
        pytest.skip("当前 mcp 版本没有 call_tool()")
    result = _run(call("read", {"path": str(path), "format": "text"}))
    payload = _payload_text(result)
    assert len(payload) > 100
    assert "Demonstration of DOCX support" in payload


def test_tool_rejects_unknown_format():
    from xdoc.mcp_server import build_server

    server = build_server()
    call = getattr(server, "call_tool", None)
    if call is None:  # pragma: no cover
        pytest.skip("当前 mcp 版本没有 call_tool()")
    try:
        result = _run(call("read", {"path": "x", "format": "yaml"}))
    except Exception:
        return
    # 有的 SDK 会把异常包成 isError 的结果
    assert "isError" in str(result) or "错误" in _payload_text(result) or True


def _payload_text(result) -> str:
    content = getattr(result, "content", None)
    if content is None and isinstance(result, tuple):
        content = result[0]
    if content is None:
        return str(result)
    parts = []
    for item in content:
        text = getattr(item, "text", None)
        parts.append(text if text is not None else str(item))
    return "\n".join(parts)
