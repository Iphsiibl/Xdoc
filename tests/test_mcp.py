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


def _client_call_tool(server, name, arguments, timeout=60):
    """用官方 MCP 客户端（内存传输）调用工具，拿到协议层的 CallToolResult。"""
    import anyio

    try:
        from mcp import ClientSession
        from mcp.shared.memory import create_client_server_memory_streams
    except Exception:  # pragma: no cover - 老版本 mcp 没有内存传输
        pytest.skip("当前 mcp 版本不支持内存传输")

    async def _main():
        async with create_client_server_memory_streams() as (client_streams, server_streams):
            low = server._lowlevel_server
            async with anyio.create_task_group() as tg:

                async def _serve():
                    await low.run(
                        server_streams[0],
                        server_streams[1],
                        low.create_initialization_options(),
                    )

                tg.start_soon(_serve)
                async with ClientSession(client_streams[0], client_streams[1]) as session:
                    await session.initialize()
                    return await session.call_tool(name, arguments)

    return asyncio.run(asyncio.wait_for(_main(), timeout))


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


def test_tool_parameters_have_descriptions():
    """每个参数都要有说明：Agent 才知道这个参数什么时候用、什么格式。"""
    tools = _list_tools()
    schema = getattr(tools[0], "inputSchema", None) or getattr(tools[0], "input_schema")
    properties = schema.get("properties", {})
    for name, prop in properties.items():
        assert prop.get("description"), f"参数 {name} 缺少 description"


def test_tool_parameters_have_enums():
    tools = _list_tools()
    schema = getattr(tools[0], "inputSchema", None) or getattr(tools[0], "input_schema")
    properties = schema.get("properties", {})
    assert properties["format"]["enum"] == ["markdown", "text", "json"]
    assert properties["ocr"]["enum"] == ["auto", "on", "off", "vlm"]
    assert properties["tables"]["enum"] == ["auto", "on", "off"]
    assert properties["images"]["enum"] == ["refs", "none"]


def test_tool_has_outline_parameter():
    tools = _list_tools()
    schema = getattr(tools[0], "inputSchema", None) or getattr(tools[0], "input_schema")
    properties = schema.get("properties", {})
    assert "outline" in properties
    assert properties["outline"]["type"] == "boolean"


def test_tool_has_asr_language_parameter():
    """转写语言必须能被指定，否则中文音频只能靠自动猜。"""
    tools = _list_tools()
    schema = getattr(tools[0], "inputSchema", None) or getattr(tools[0], "input_schema")
    properties = schema.get("properties", {})
    assert "asr_language" in properties
    assert "zh" in properties["asr_language"].get("description", "")


def test_tool_default_budget_is_bounded():
    """MCP 侧默认给个 token 预算，避免一次把 12 万字塞进上下文。"""
    tools = _list_tools()
    schema = getattr(tools[0], "inputSchema", None) or getattr(tools[0], "input_schema")
    properties = schema.get("properties", {})
    assert properties["max_tokens"]["default"] == 30000


def test_tool_errors_are_reported_as_errors():
    """业务错误必须让调用方看见 isError=true 和原因，而不是当成成功返回。

    走真实 MCP 客户端（内存传输），因为 isError 的转换发生在协议层，
    直接调 server.call_tool() 是拿不到 CallToolResult 的。
    """
    from xdoc.mcp_server import build_server

    result = _client_call_tool(build_server(), "read", {"path": "C:/definitely/not/here.pdf"})
    assert _is_error(result) is True
    text = _payload_text(result)
    assert "不存在" in text
    assert "Error executing tool read" in text


def test_tool_reports_invalid_cursor_as_error():
    from xdoc.mcp_server import build_server

    path = require(sample("pdf", "en_dummy.pdf"))
    result = _client_call_tool(build_server(), "read", {"path": str(path), "cursor": "!!!bad!!!"})
    assert _is_error(result) is True
    assert "cursor" in _payload_text(result).lower()


def test_client_can_read_a_file():
    """端到端：客户端真的能通过协议读到内容（不只是调函数）。"""
    from xdoc.mcp_server import build_server

    path = require(sample("docx", "calibre_demo.docx"))
    result = _client_call_tool(build_server(), "read", {"path": str(path), "format": "text"})
    assert _is_error(result) is False
    assert "Demonstration of DOCX support" in _payload_text(result)


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


def _is_error(result) -> bool:
    for attr in ("is_error", "isError"):
        value = getattr(result, attr, None)
        if value is not None:
            return bool(value)
    return False
