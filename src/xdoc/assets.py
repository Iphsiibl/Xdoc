"""附件（图片等）落盘管理。

提取出来的图片要能被 Agent 真正读到（模型能看图），所以必须落成真实文件，
并给出稳定、可预测的路径。
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def default_assets_root() -> Path:
    base = Path.home() / ".local" / "share" / "xdoc" / "assets"
    base.mkdir(parents=True, exist_ok=True)
    return base


class AssetStore:
    """把提取出的二进制资源写入磁盘，返回相对路径。"""

    def __init__(self, root: Path | None = None, *, enabled: bool = True) -> None:
        self.root = Path(root) if root else default_assets_root()
        self.enabled = enabled
        self._rel_dir = ""

    def bind(self, source: Path) -> None:
        """按源文件绑定一个子目录，避免不同文件的同名图片互相覆盖。"""
        digest = hashlib.sha1(str(source.resolve()).encode()).hexdigest()[:10]
        stem = source.stem.replace(" ", "_")[:40]
        self._rel_dir = f"{stem}-{digest}"
        if self.enabled:
            (self.root / self._rel_dir).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _rel(path: str) -> str:
        """统一用 / 分隔的相对路径，且不带前导斜杠（否则会被当成绝对路径）。"""
        return path.replace("\\", "/").lstrip("/")

    def save(self, data: bytes, filename: str) -> str | None:
        if not self.enabled:
            return None
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / self._rel_dir / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return self._rel(f"{self._rel_dir}/{filename}")
