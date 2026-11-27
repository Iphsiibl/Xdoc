"""通用异常。"""

from __future__ import annotations


class XdocError(Exception):
    """xdoc 的通用错误（对外可读，不带堆栈）。"""


class PluginError(XdocError):
    """插件相关错误（未安装、运行失败等）。"""
