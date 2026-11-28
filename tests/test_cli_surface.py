"""CLI 表面测试：子命令、参数别名、插件命令。"""
from __future__ import annotations

from xdoc.cli import build_parser


def test_parser_has_expected_commands():
    parser = build_parser()
    actions = [a for a in parser._actions if a.dest == "command"]
    assert actions, "没有子命令"
    choices = set(actions[0].choices)
    assert {"read", "plugin", "cache", "doctor", "serve"} <= choices


def test_plugin_aliases_are_accepted():
    parser = build_parser()
    for alias in ("add", "install", "download", "remove", "uninstall"):
        args = parser.parse_args(["plugin", alias, "ocr"])
        assert args.name == "ocr"
        assert args.plugin_command == alias


def test_plugin_list_has_no_name_argument():
    parser = build_parser()
    args = parser.parse_args(["plugin", "list"])
    assert args.plugin_command == "list"


def test_read_options():
    parser = build_parser()
    args = parser.parse_args([
        "read", "a.pdf", "--format", "json", "--max-tokens", "1000",
        "--pages", "1-5,8", "--ocr", "on", "--asr", "zh", "--tables", "off",
    ])
    assert args.path == "a.pdf"
    assert args.format == "json"
    assert args.max_tokens == 1000
    assert args.pages == "1-5,8"
    assert args.ocr == "on"
    assert args.asr == "zh"
    assert args.tables == "off"


def test_read_outline_and_no_cache_flags():
    parser = build_parser()
    args = parser.parse_args(["read", "a.pdf", "--outline", "--no-cache"])
    assert args.outline is True
    assert args.no_cache is True
    plain = parser.parse_args(["read", "a.pdf"])
    assert plain.outline is False
    assert plain.no_cache is False


def test_cache_subcommands():
    parser = build_parser()
    info = parser.parse_args(["cache", "info"])
    assert info.cache_command == "info"
    clear = parser.parse_args(["cache", "clear"])
    assert clear.cache_command == "clear"
