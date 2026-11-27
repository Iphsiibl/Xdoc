"""CI 冒烟测试：造一个 docx，用 xdoc 读出来，确认最小闭环可用。

写成独立文件而不是内联 heredoc —— windows-latest 的默认 shell 是 pwsh，
不支持 `<<'PY'` 语法（见 CI #4 的 windows 失败）。
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile


def main() -> int:
    import docx

    marker = "冒烟测试"
    document = docx.Document()
    document.add_heading(marker, 0)
    document.add_paragraph("正文内容，用于验证 xdoc read 的最小闭环。")
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "smoke.docx"
        document.save(path)

        completed = subprocess.run(
            [sys.executable, "-m", "xdoc", "read", str(path), "--format", "text"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    print(completed.stdout)
    if completed.returncode != 0:
        print(completed.stderr, file=sys.stderr)
        return completed.returncode
    assert marker in completed.stdout, completed.stdout
    print("smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
