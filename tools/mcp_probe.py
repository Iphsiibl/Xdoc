"""探针：用官方 MCP 客户端连上 xdoc serve，看 Agent 实际看到的工具 schema。

用法：uv run --extra dev python tools/mcp_probe.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


async def main() -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "xdoc.mcp_server"],
        env=None,
        cwd=str(ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            for tool in tools.tools:
                print("=== 工具名:", tool.name, "===")
                print("--- description ---")
                print(tool.description)
                print("--- inputSchema ---")
                schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None)
                print(json.dumps(schema, ensure_ascii=False, indent=2))

            print("\n=== 调用：读一个 PDF ===")
            result = await session.call_tool(
                "read", {"path": str(ROOT / "samples" / "pdf" / "en_dummy.pdf")}
            )
            print("isError:", result.is_error)
            for block in result.content:
                print(getattr(block, "text", block))

            print("\n=== 调用：非法 cursor ===")
            result = await session.call_tool(
                "read",
                {
                    "path": str(ROOT / "samples" / "pdf" / "en_dummy.pdf"),
                    "cursor": "!!!bad!!!",
                },
            )
            print("isError:", result.is_error)
            for block in result.content:
                print(getattr(block, "text", block))

            print("\n=== 调用：文件不存在 ===")
            result = await session.call_tool(
                "read", {"path": str(ROOT / "samples" / "pdf" / "nope.pdf")}
            )
            print("isError:", result.is_error)
            for block in result.content:
                print(getattr(block, "text", block))

            print("\n=== 调用：目录 ===")
            result = await session.call_tool("read", {"path": str(ROOT / "samples")})
            print("isError:", result.is_error)
            for block in result.content:
                print(getattr(block, "text", block))

            print("\n=== 调用：检索（grep）===")
            result = await session.call_tool(
                "read",
                {
                    "path": str(ROOT / "samples" / "html"),
                    "grep": "wikipedia",
                    "grep_limit": 3,
                    "grep_context": 1,
                },
            )
            print("isError:", result.is_error)
            for block in result.content:
                print(getattr(block, "text", block))


if __name__ == "__main__":
    asyncio.run(main())
