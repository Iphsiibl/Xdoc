"""MCP 服务：单个工具 `read`（用户明确要求"一个入口"）。

stdio 传输，命令示例：
    xdoc serve
或直接：
    python -m xdoc.mcp_server
"""

from __future__ import annotations

from .api import read_with_meta
from .errors import XdocError
from .options import ReadOptions

TOOL_DESCRIPTION = """\
把一个文件转成忠实文本，供你阅读与提取信息。

支持：PDF（含扫描件→OCR）、DOCX、PPTX、XLSX/CSV、HTML/Markdown/文本、EPUB、图片、音频、视频。

规则：
- 只转换，不摘要、不改写；金额、日期、编号原样保留。
- PDF 按页、PPT 按幻灯片、Excel 按工作表、音频视频按时间戳给出锚点，便于引用。
- 输出默认 Markdown（可用 format 切换 text / json）。
- 内容过长时传 max_tokens，返回内容会截断并给出 next_cursor，用 cursor 续读。
- OCR / 语音转写 / 视频抽帧需要本地插件（ocr、asr、asr-zh、media）；未安装时会明确报出安装命令。
"""


def build_server():
    """构造 MCP server。

    兼容两代官方 SDK：mcp 1.x 的 FastMCP 与 mcp 2.x 的 MCPServer（2.x 里 FastMCP 被改名）。
    两者的 `@server.tool(...)` 装饰器与 `run()` 用法一致。
    """
    try:  # mcp >= 2
        from mcp.server.mcpserver import MCPServer as _Server
    except ImportError:  # pragma: no cover - mcp 1.x
        from mcp.server.fastmcp import FastMCP as _Server

    server = _Server("xdoc")

    @server.tool(name="read", description=TOOL_DESCRIPTION)
    def read(
        path: str,
        format: str = "markdown",
        max_tokens: int | None = None,
        cursor: str | None = None,
        pages: str | None = None,
        ocr: str = "auto",
        asr: str = "auto",
        asr_model: str | None = None,
        tables: str = "auto",
        images: str = "refs",
        front_matter: bool = True,
    ) -> str:
        """读取并转换一个文件。path 支持本地路径。"""
        if format not in ("markdown", "text", "json"):
            raise ValueError("format 只能是 markdown / text / json")
        options = ReadOptions(
            format=format,
            max_tokens=max_tokens,
            cursor=cursor,
            pages=pages,
            ocr=ocr,
            asr=asr,
            asr_model=asr_model,
            tables=tables,
            images=images,
            front_matter=front_matter,
        )
        try:
            text, _doc = read_with_meta(path, options)
        except XdocError as exc:
            return f"[xdoc 错误] {exc}"
        return text

    return server


def main() -> int:
    server = build_server()
    server.run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
