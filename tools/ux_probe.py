"""体验探针：把「人和 Agent 会撞到」的路径跑一遍，记录真实输出。

用法：uv run python tools/ux_probe.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from xdoc.api import read, read_document  # noqa: E402
from xdoc.errors import XdocError  # noqa: E402
from xdoc.options import ReadOptions, SearchSpec  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT: list[str] = []


def show(title: str, body: str) -> None:
    OUT.append(f"\n===== {title} =====\n{body}")


def probe_error(title: str, fn) -> None:
    t0 = time.perf_counter()
    try:
        result = fn()
        show(title, f"[ok] {str(result)[:400]}")
    except XdocError as exc:
        show(title, f"[XdocError] {exc}")
    except Exception as exc:  # noqa: BLE001
        show(title, f"[{type(exc).__name__}] {exc}")
    show(title + " (耗时)", f"{time.perf_counter() - t0:.2f}s")


def cli(*args: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "xdoc.cli", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
        env=env,
    )


def main() -> None:
    # 1) 目录
    probe_error("1. 读目录", lambda: read(ROOT / "samples" / "pdf"))
    # 2) 不存在的文件
    probe_error("2. 读不存在的文件", lambda: read(ROOT / "samples" / "pdf" / "nope.pdf"))
    # 3) 相对路径（MCP 服务的 cwd 通常不是用户 cwd）
    probe_error("3. 相对路径解析", lambda: read("samples/pdf/en_dummy.pdf"))
    # 4) 坏 cursor：应该是 XdocError，不是裸 ValueError
    probe_error("4. 非法 cursor", lambda: read(
        ROOT / "samples" / "pdf" / "en_dummy.pdf",
        ReadOptions(cursor="!!!not-base64!!!", max_tokens=100),
    ))
    # 5) CLI 遇到坏 cursor：不该甩 traceback
    proc = cli("read", "samples/pdf/en_dummy.pdf", "--cursor", "!!!bad!!!")
    show("5. CLI 坏 cursor", f"exit={proc.returncode}\nstdout={proc.stdout.strip()}\nstderr={proc.stderr.strip()[:400]}")
    # 6) outline：结构先行
    outline = read(ROOT / "samples" / "pdf" / "zh_wiki_python.pdf", ReadOptions(outline=True))
    full = read(ROOT / "samples" / "pdf" / "zh_wiki_python.pdf", ReadOptions(tables="off", images="none"))
    show("6. outline vs 全文",
         f"outline={len(outline)} 字符 / 全文={len(full)} 字符（{len(outline) / len(full):.1%}）")
    # 7) 大 PDF 不给预算 → 一次性吐出多少
    t0 = time.perf_counter()
    text = read(ROOT / "samples" / "pdf" / "zh_wiki_python.pdf",
                ReadOptions(tables="off", images="none"))
    show("7. 64 页中文 PDF 无预算直出",
         f"chars={len(text)}  耗时={time.perf_counter() - t0:.2f}s\n"
         f"（模型上下文 128k，一次 read 就吃掉约 {len(text) / 128000:.0%}）")
    # 8) 重复读：缓存生效了吗
    t0 = time.perf_counter()
    read(ROOT / "samples" / "pdf" / "en_arxiv_attention.pdf", ReadOptions(tables="on"))
    first = time.perf_counter() - t0
    t0 = time.perf_counter()
    read(ROOT / "samples" / "pdf" / "en_arxiv_attention.pdf", ReadOptions(tables="on"))
    second = time.perf_counter() - t0
    show("8. 同一文件读两次", f"第一次 {first:.2f}s / 第二次 {second:.2f}s")
    # 9) Agent 视角：一次 MCP 调用返回体量
    payload = read(ROOT / "samples" / "xlsx" / "microsoft_sample.xlsx",
                   ReadOptions(format="json", images="none"))
    show("9. Excel 默认无预算的返回体量", f"{len(payload)} 字符")
    # 10) cache 命令
    proc = cli("cache", "info")
    show("10. xdoc cache info", f"exit={proc.returncode}\n{proc.stdout.strip()[:600]}")
    # 11) 检索：只给命中处
    doc = read(
        ROOT / "samples" / "pdf" / "zh_wiki_python.pdf",
        ReadOptions(search=SearchSpec(pattern="Transformer", limit=5)),
    )
    show("11. 检索命中", f"{len(doc)} 字符\n{doc[:600]}")
    # 12) CLI 检索
    proc = cli("grep", "Transformer", "samples/pdf/zh_wiki_python.pdf", "--limit", "3", "--context", "1")
    show("12. CLI 检索", f"exit={proc.returncode}\n{proc.stdout.strip()[:600]}\nstderr={proc.stderr.strip()[:200]}")
    # 13) 静默失败：页码越界 / 格式错，应该报错退出而不是假装成功
    for args in (("read", "samples/pdf/en_dummy.pdf", "--pages", "999"),
                 ("read", "samples/pdf/en_dummy.pdf", "--pages", "abc"),
                 ("plugin", "add", "nosuch")):
        proc = cli(*args)
        show(f"13. 静默失败检查 {' '.join(args[1:])}",
             f"exit={proc.returncode}（期望 2）\nstderr={proc.stderr.strip()[:200]}")
    # 14) 非中文 Windows 编码下 --help 不能崩
    proc = cli("--help", env_extra={"PYTHONIOENCODING": "cp1252"})
    show("14. cp1252 编码下 --help", f"exit={proc.returncode}（期望 0）\n{proc.stdout.strip()[:200]}")
    # 15) 渐进式输出：正文之前先给目录
    doc = read_document(ROOT / "samples" / "pdf" / "en_dummy.pdf", ReadOptions())
    toc = doc.meta.get("toc") or []
    show("15. front-matter 里的目录（toc）",
         f"{len(toc)} 条\n" + "\n".join(toc[:8]))
    # 16) 目录并行：跟串行读出来的结果一致
    serial = read_document(ROOT / "samples" / "pdf", ReadOptions())
    parallel = read_document(ROOT / "samples" / "pdf", ReadOptions())
    show("16. 目录并行解析",
         f"file_count={parallel.meta.get('file_count')}  "
         f"与串行一致={parallel.meta.get('files') == serial.meta.get('files')}")
    # 17) ASR 标点开关：auto 不要标点（快），点名引擎要标点（准）
    from xdoc.converters.media import _asr_payload
    show("17. ASR 标点开关",
         f"auto 模式 punc={_asr_payload('funasr', 'a.wav', ReadOptions(asr='auto'))['punc']}（期望 False）\n"
         f"--asr zh  punc={_asr_payload('funasr', 'a.wav', ReadOptions(asr='zh'))['punc']}（期望 True）")

    print("".join(OUT))


if __name__ == "__main__":
    main()
