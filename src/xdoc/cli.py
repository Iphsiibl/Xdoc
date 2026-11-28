"""命令行入口：xdoc read / xdoc plugin / xdoc doctor / xdoc serve。

CLI 与 MCP 共用同一套实现，输出结果一致。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from . import __version__
from .api import read_with_meta
from .errors import XdocError
from .options import ReadOptions, SearchSpec
from .plugins import PLUGINS, PluginManager


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xdoc",
        description="把 PDF/图片/音频/视频/Office/富文本 转成忠实文本，供 Agent 阅读。",
    )
    parser.add_argument("--version", action="version", version=f"xdoc {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    read_cmd = sub.add_parser("read", help="读取文件或目录")
    read_cmd.add_argument("path", help="文件路径（也可以是目录，会把目录里能读的文件合并）")
    read_cmd.add_argument("--format", default="markdown", choices=["markdown", "text", "json"],
                          help="输出格式（默认 markdown）")
    read_cmd.add_argument("--max-tokens", type=int, default=None, help="token 预算，超出即截断并给续读游标")
    read_cmd.add_argument("--cursor", default=None, help="续读游标（配合 --max-tokens 使用）")
    read_cmd.add_argument("--pages", default=None, help="页/幻灯片/表范围，例如 1-5,8")
    read_cmd.add_argument("--ocr", default="auto", choices=["auto", "on", "off", "vlm"],
                          help="OCR 开关（需安装 ocr 插件）")
    read_cmd.add_argument("--asr", default="auto",
                          choices=["auto", "on", "off", "zh", "whisper"],
                          help="语音转写：auto（自动挑引擎）/ zh（中文 FunASR）/ whisper（通用 faster-whisper）/ off")
    read_cmd.add_argument("--asr-model", default=None, help="ASR 模型名，如 small / large-v3")
    read_cmd.add_argument("--asr-language", default=None,
                          help="语音转写语言，如 zh / en（不填=自动识别）")
    read_cmd.add_argument("--asr-punc", default="auto", choices=["auto", "on", "off"],
                          help="中文转写要不要标点：auto（默认：自动模式快、点名引擎时准）/ on（准，慢 30 秒）/ off（快，没有标点）")
    read_cmd.add_argument("--tables", default="auto", choices=["auto", "on", "off"],
                          help="PDF 表格识别：auto（页面有竖线才识别，快）/ on（每页都按画线识别）/ off（不识别）")
    read_cmd.add_argument("--no-images", action="store_true", help="不提取内嵌图片")
    read_cmd.add_argument("--no-front-matter", action="store_true", help="不输出元数据头")
    read_cmd.add_argument("--outline", action="store_true",
                          help="只输出结构（标题+锚点），不输出正文；适合先看目录再定点读")
    read_cmd.add_argument("--no-cache", action="store_true", help="跳过解析缓存，强制重新解析")
    read_cmd.add_argument("-q", "--quiet", action="store_true", help="不显示进度提示")
    read_cmd.add_argument("-o", "--output", default=None, help="输出到文件而不是标准输出")

    grep_cmd = sub.add_parser("grep", help="在文件或目录里检索关键词，列出命中位置")
    grep_cmd.add_argument("pattern", help="要检索的词（默认按字面匹配、忽略大小写）")
    grep_cmd.add_argument("path", help="文件路径（也可以是目录，会在目录里所有能读的文件里检索）")
    grep_cmd.add_argument("--regex", action="store_true", help="按正则表达式匹配（默认按字面）")
    grep_cmd.add_argument("--case-sensitive", action="store_true", help="区分大小写（默认忽略）")
    grep_cmd.add_argument("--context", type=int, default=0, help="命中行前后各带几行上下文（默认不带）")
    grep_cmd.add_argument("--limit", type=int, default=50, help="最多返回多少条命中（默认 50）")
    grep_cmd.add_argument("--format", default="markdown", choices=["markdown", "text", "json"],
                          help="输出格式（默认 markdown）")
    grep_cmd.add_argument("--max-tokens", type=int, default=None, help="token 预算，超出即截断并给续读游标")
    grep_cmd.add_argument("--no-cache", action="store_true", help="跳过解析缓存，强制重新解析")
    grep_cmd.add_argument("-q", "--quiet", action="store_true", help="不显示进度提示")
    grep_cmd.add_argument("-o", "--output", default=None, help="输出到文件而不是标准输出")
    grep_cmd.add_argument("--asr", default="auto",
                           choices=["auto", "on", "off", "zh", "whisper"],
                           help="语音转写：auto（自动挑引擎）/ zh（中文 FunASR）/ whisper（通用 faster-whisper）/ off")
    grep_cmd.add_argument("--asr-model", default=None, help="ASR 模型名，如 small / large-v3")
    grep_cmd.add_argument("--asr-language", default=None,
                           help="语音转写语言，如 zh / en（不填=自动识别）")
    grep_cmd.add_argument("--asr-punc", default="auto", choices=["auto", "on", "off"],
                           help="中文转写要不要标点：auto（默认：自动模式快、点名引擎时准）/ on（准，慢 30 秒）/ off（快，没有标点）")

    plugin_cmd = sub.add_parser("plugin", help="可选引擎插件管理（安装/卸载/查看）")
    plugin_sub = plugin_cmd.add_subparsers(dest="plugin_command", required=True)
    plugin_sub.add_parser("list", help="列出插件及安装状态")
    add_cmd = plugin_sub.add_parser("add", help="安装插件（按需下载）")
    add_cmd.add_argument("name", help=f"插件名（{', '.join(sorted(PLUGINS))}）")
    rm_cmd = plugin_sub.add_parser("remove", help="卸载插件")
    rm_cmd.add_argument("name", help=f"插件名（{', '.join(sorted(PLUGINS))}）")
    # 同义词：install/download ≈ add，uninstall ≈ remove
    for alias, help_text in (("install", "安装插件（add 的同义词）"),
                              ("download", "下载并安装插件（add 的同义词）"),
                              ("uninstall", "卸载插件（remove 的同义词）")):
        alias_cmd = plugin_sub.add_parser(alias, help=help_text)
        alias_cmd.add_argument("name", help=f"插件名（{', '.join(sorted(PLUGINS))}）")

    sub.add_parser("doctor", help="检查环境与依赖")
    sub.add_parser("serve", help="以 stdio 方式启动 MCP 服务")
    demo_cmd = sub.add_parser("demo", help="用内置示例跑一遍，看 xdoc 到底能干什么")
    demo_cmd.add_argument("-q", "--quiet", action="store_true", help="不显示进度提示")
    sub.add_parser("setup", help="体检 + 打印接上 Agent 的方法（只读，不改你的文件）")

    cache_cmd = sub.add_parser("cache", help="解析缓存（查看占用 / 清理）")
    cache_sub = cache_cmd.add_subparsers(dest="cache_command", required=True)
    cache_sub.add_parser("info", help="查看缓存占用")
    cache_sub.add_parser("clear", help="清空解析缓存")
    return parser


def _progress(quiet: bool):
    """进度提示回调：写 stderr（stdout 是给文档的，不能污染）。"""
    if quiet:
        return None

    def emit(message: str) -> None:
        print(message, file=sys.stderr, flush=True)

    return emit


def _summary_line(doc, elapsed: float) -> str:
    cache = {"hit": "命中缓存", "miss": "未命中缓存"}.get(doc.meta.get("cache", ""), "")
    tail = f"，{cache}" if cache else ""
    return f"完成：{len(doc.sections)} 节 / {doc.chars} 字符（{elapsed:.1f}s{tail}）"


def _cmd_read(args) -> int:
    options = ReadOptions(
        format=args.format,
        max_tokens=args.max_tokens,
        cursor=args.cursor,
        pages=args.pages,
        ocr=args.ocr,
        asr=args.asr,
        asr_model=args.asr_model,
        asr_language=args.asr_language,
        asr_punc=args.asr_punc,
        tables=args.tables,
        images="none" if args.no_images else "refs",
        front_matter=not args.no_front_matter,
        outline=args.outline,
        use_cache=not args.no_cache,
        on_progress=_progress(args.quiet),
    )
    started = time.perf_counter()
    text, doc = read_with_meta(args.path, options)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"written: {args.output}  ({doc.chars} chars, {len(doc.sections)} sections)")
    else:
        sys.stdout.write(text)
    if not args.quiet:
        print(_summary_line(doc, time.perf_counter() - started), file=sys.stderr)
    return 0


def _cmd_grep(args) -> int:
    options = ReadOptions(
        format=args.format,
        max_tokens=args.max_tokens,
        use_cache=not args.no_cache,
        front_matter=True,
        asr=args.asr,
        asr_model=args.asr_model,
        asr_language=args.asr_language,
        asr_punc=args.asr_punc,
        search=SearchSpec(
            pattern=args.pattern,
            regex=args.regex,
            ignore_case=not args.case_sensitive,
            context=max(0, args.context),
            limit=max(1, args.limit),
        ),
        on_progress=_progress(args.quiet),
    )
    started = time.perf_counter()
    text, doc = read_with_meta(args.path, options)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"written: {args.output}  ({doc.chars} chars, {len(doc.sections)} sections)")
    else:
        sys.stdout.write(text)
    if not args.quiet:
        info = doc.meta.get("search") or {}
        total = info.get("total", 0)
        shown = info.get("returned", 0)
        print(
            f"命中 {total} 处（返回 {shown} 处，用时 {time.perf_counter() - started:.1f}s）",
            file=sys.stderr,
        )
    return 0


def _cmd_cache(args) -> int:
    from .cache import cache_root, clear, usage

    root = cache_root()
    if args.cache_command == "clear":
        removed = clear(root)
        print(f"已清理解析缓存: {removed} 个条目（{root}）")
        return 0
    count, size = usage(root)
    print(f"缓存目录: {root}")
    print(f"条目数: {count}    占用: {size / 1024 / 1024:.1f} MB")
    return 0


def _cmd_plugin(args) -> int:
    manager = PluginManager()
    if args.plugin_command == "list":
        items = manager.list()
        print("插件状态:")
        for item in items:
            mark = "已安装" if item["installed"] else "未安装"
            real = f"  实际占用 {item['size_mb']}MB" if item["installed"] else ""
            print(f"  [{mark:4s}] {item['name']:6s} {item['title']}  ({item['approx_size']}){real}")
        print("\n安装: xdoc plugin add|install <name>    卸载: xdoc plugin remove|uninstall <name>")
        return 0
    if args.plugin_command in ("add", "install", "download"):
        spec = PLUGINS.get(args.name)
        if spec is not None:
            print(f"正在安装 {args.name}（{spec.approx_size}）… 下载与安装可能要几分钟，请耐心等待。",
                  file=sys.stderr, flush=True)
        result = manager.install(args.name)
        print(f"{args.name}: {result['status']}")
        return 0
    if args.plugin_command in ("remove", "uninstall"):
        result = manager.uninstall(args.name)
        print(f"{args.name}: {result['status']}")
        return 0
    return 1


def _cmd_demo(args) -> int:
    from .demo import run_demo

    print(run_demo(quiet=args.quiet))
    return 0


def _cmd_setup() -> int:
    from .setup import setup_report

    print(setup_report())
    return 0


def _cmd_doctor() -> int:
    import importlib
    import shutil

    from .setup import CORE_DEPENDENCIES

    print(f"xdoc {__version__}")
    print(f"python: {sys.executable}")

    print("\n核心依赖:")
    missing: list[str] = []
    for module, label in CORE_DEPENDENCIES:
        try:
            importlib.import_module(module)
            print(f"  [ok]   {module:14s} {label}")
        except ImportError:
            missing.append(module)
            print(f"  [缺失] {module:14s} {label}")

    print("\n外部工具（可选，缺失不影响基础能力）:")
    from .converters.legacy import find_soffice
    soffice = find_soffice()
    print(f"  [{'ok' if soffice else '缺失'}] LibreOffice  {soffice or '（旧版 .doc/.ppt/.xls 转换需要；装 LibreOffice 即可）'}")
    manager = PluginManager()
    ffmpeg = manager.ffmpeg_path()
    print(f"  [{'ok' if ffmpeg else '缺失'}] ffmpeg       {ffmpeg or '（视频抽帧需要；运行 xdoc plugin add media 即可获得）'}")

    print("\n插件（可选，按需安装）:")
    for item in manager.list():
        mark = "已装" if item["installed"] else "未装"
        hint = "" if item["installed"] else f"    → 安装: xdoc plugin add {item['name']}"
        real = f"    实际占用 {item['size_mb']}MB" if item["installed"] else ""
        print(f"  [{mark}] {item['name']:6s} {item['title']}  {item['approx_size']}{real}{hint}")

    print("\n命令是否可用:")
    exe = shutil.which("xdoc")
    if exe:
        print(f"  [ok]   xdoc  {exe}")
    else:
        print("  [注意] 当前 shell 里敲 xdoc 找不到命令")
        print(f"         可执行文件在: {Path(sys.executable).parent}")
        print("         把这个目录加进 PATH 就能直接用；或者直接用 python -m xdoc.cli")

    from .cache import cache_root, usage

    count, size = usage(cache_root())
    print(f"\n解析缓存: {cache_root()}")
    print(f"  条目数: {count}    占用: {size / 1024 / 1024:.1f} MB（xdoc cache clear 可清空）")
    print("  分两层存：基础解析（跟插件无关）+ OCR/转写增强；装了新插件只重算增强层")

    print("\n终端编码:")
    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    if encoding in ("utf-8", "utf8"):
        print("  [ok]   UTF-8，中文能正常显示")
    else:
        print(f"  [注意] 当前终端编码是 {encoding or '未知'}，中文可能显示成乱码")
        print("         换个 UTF-8 终端，或在 Windows 上先执行 chcp 65001")

    if missing:
        print(f"\n核心依赖缺失: {', '.join(missing)}")
        print("  修复: 重新安装 xdoc-tools（pip install -U xdoc-tools 或 uv tool install --force xdoc-tools）")
        return 1
    print("\n核心依赖齐全，基础能力可用。")
    return 0


def _setup_console() -> None:
    """Windows 控制台默认代码页可能是 cp936/cp1252，直接写中文会抛 UnicodeEncodeError。

    统一改成 UTF-8 输出、无法编码的字符降级为替换符——宁可显示成 ?，也不能因为编码崩掉。
    MCP 的 serve 模式走 stdio 协议，不碰标准流。
    """
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:  # pragma: no cover - 老终端不支持就算了
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover - 已被替换的流
            pass


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    # 必须在 parse_args 之前修好控制台编码：argparse 打印中文帮助时，
    # 若 stdout 是 cp936/cp1252 会直接抛 UnicodeEncodeError（--help 直接崩）。
    # serve 走 stdio 协议，不碰标准流。
    if not args_list or args_list[0] != "serve":
        _setup_console()

    parser = build_parser()
    args = parser.parse_args(args_list)

    try:
        if args.command == "read":
            return _cmd_read(args)
        if args.command == "grep":
            return _cmd_grep(args)
        if args.command == "plugin":
            return _cmd_plugin(args)
        if args.command == "cache":
            return _cmd_cache(args)
        if args.command == "doctor":
            return _cmd_doctor()
        if args.command == "demo":
            return _cmd_demo(args)
        if args.command == "setup":
            return _cmd_setup()
        if args.command == "serve":
            from .mcp_server import main as serve_main

            return serve_main()
    except XdocError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    except (ValueError, OSError) as exc:
        # 这些异常不该甩给用户看堆栈
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:  # pragma: no cover
        print("已取消", file=sys.stderr)
        return 130
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
