"""测试公用夹具。"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"


def sample(*parts: str) -> Path:
    return SAMPLES.joinpath(*parts)


def require(path: Path) -> Path:
    """样本不存在就跳过（样本是可选的下载产物）。"""
    if not path.exists():
        pytest.skip(f"缺少样本: {path}（先跑 tools/fetch_samples.py）")
    return path
