"""MCP 服务：单个工具 `read`（用户明确要求"一个入口"）。

stdio 传输，命令示例：
    xdoc serve
或直接：
    python -m xdoc.mcp_server
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from .api import read_with_meta
from .errors import XdocError
from .options import ReadOptions, SearchSpec

TOOL_DESCRIPTION = """\
把本地文件（或整个目录）转成忠实文本，供你阅读与提取信息。

支持：PDF（含扫描件→OCR）、DOCX、PPTX、XLSX/CSV、HTML/Markdown/文本、EPUB、图片、音频、视频。

规则：
- 只转换，不摘要、不改写；金额、日期、编号原样保留。
- PDF 按页、PPT 按幻灯片、Excel 按工作表、音频视频按时间戳给出锚点，便于引用。
- 输出默认 Markdown（format 可切 text / json）。

怎么用（省 token 的推荐顺序）：
1. 先 read(path, outline=true) 看清结构（只要标题和锚点，不给正文）；
2. 再 read(path, pages="7-9") 或读某个具体范围，把正文取回来；
3. 内容太长会被截断并返回 next_cursor，用 cursor 参数续读；
4. 知道要找什么词时，直接 read(path, grep="关键词")：只返回命中的位置和原文片段
   （带锚点），比读全文省得多；grep_regex=true 时按正则匹配，grep_context=1 带上前后各一行。

默认只给 30000 token（足够读几十页）；确实要全文时传 max_tokens=0 表示不限。

path 也可以是目录：会把目录里所有能读的文件合成一份，锚点形如
<!-- file:report.pdf page 3 -->，front-matter 的 files 字段列出每个文件。
对目录用 grep 会在所有能读的文件里一起检索，结果里标明命中来自哪个文件。

OCR / 语音转写 / 视频抽帧需要本地插件（ocr、asr、asr-zh、media）；未安装时会明确报出安装命令。
"""

DEFAULT_MAX_TOKENS = 30000


def _tool_error(message: str):
    """构造 SDK 认识的工具错误：调用方能看到 isError=true 和完整原因。"""
    try:  # mcp >= 2
        from mcp.server.mcpserver.exceptions import ToolError
    except ImportError:  # pragma: no cover - mcp 1.x
        try:
            from mcp.server.fastmcp.exceptions import ToolError
        except ImportError:  # pragma: no cover - 没有装 mcp
            return RuntimeError(message)
    return ToolError(message)


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
        path: Annotated[
            str,
            Field(description="要读取的文件路径，或目录路径（目录会合并成一份文档）"),
        ],
        format: Annotated[
            Literal["markdown", "text", "json"],
            Field(description="输出格式：markdown（默认）、text（纯文本）、json（结构化）"),
        ] = "markdown",
        max_tokens: Annotated[
            int,
            Field(
                ge=0,
                description="本次返回的 token 上限，超出会截断并返回 next_cursor；0 表示不限",
            ),
        ] = DEFAULT_MAX_TOKENS,
        cursor: Annotated[
            str | None,
            Field(description="续读游标：用上一步返回的 next_cursor 原样传回，即可接着读"),
        ] = None,
        pages: Annotated[
            str | None,
            Field(description='要读的页/幻灯片/表范围，如 "1-5,8"；省略表示全部'),
        ] = None,
        outline: Annotated[
            bool,
            Field(description="只要结构不要正文：返回标题和锚点，适合先摸清文档结构再定点读"),
        ] = False,
        ocr: Annotated[
            Literal["auto", "on", "off", "vlm"],
            Field(description="扫描件 OCR：auto（按需，默认）/ on（强制）/ off / vlm"),
        ] = "auto",
        asr: Annotated[
            Literal["auto", "on", "off", "zh", "whisper"],
            Field(description="音视频转写：auto（自动挑引擎）/ zh（中文）/ whisper（通用）/ off"),
        ] = "auto",
        asr_model: Annotated[
            str | None,
            Field(description="ASR 模型名，如 small / base / large-v3"),
        ] = None,
        tables: Annotated[
            Literal["auto", "on", "off"],
            Field(description="PDF 表格识别：auto（页面有画线才识别，快）/ on（每页都识别，慢）/ off"),
        ] = "auto",
        images: Annotated[
            Literal["refs", "none"],
            Field(description="内嵌图片：refs（导出并给出路径，默认）/ none（不导出）"),
        ] = "refs",
        front_matter: Annotated[
            bool,
            Field(description="是否带元数据头（source/kind/sections/chars 等），默认带"),
        ] = True,
        grep: Annotated[
            str | None,
            Field(description="只返回含这个词的位置与原文片段（带锚点）；省略表示读全文"),
        ] = None,
        grep_regex: Annotated[
            bool,
            Field(description="grep 按正则表达式匹配（默认按字面匹配）"),
        ] = False,
        grep_context: Annotated[
            int,
            Field(ge=0, description="命中行前后各带几行上下文（默认 0，只给命中行）"),
        ] = 0,
        grep_limit: Annotated[
            int,
            Field(ge=1, description="最多返回多少条命中（默认 50）"),
        ] = 50,
    ) -> str:
        """读取并转换一个文件（或目录）。path 支持本地路径。"""
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
            outline=outline,
            search=(
                SearchSpec(
                    pattern=grep,
                    regex=grep_regex,
                    context=grep_context,
                    limit=grep_limit,
                )
                if grep
                else None
            ),
        )
        try:
            text, _doc = read_with_meta(path, options)
        except XdocError as exc:
            # 业务错误必须变成工具错误：调用方要能看见 isError=true 和原因，
            # 否则 SDK 会把原因吞掉，Agent 只看到"调用成功但内容是错误"。
            raise _tool_error(str(exc)) from exc
        except (ValueError, OSError) as exc:
            # 同上：这些也不该让 Agent 拿到一个没有原因的错误
            raise _tool_error(f"{type(exc).__name__}: {exc}") from exc
        return text

    return server


def main() -> int:
    server = build_server()
    server.run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
