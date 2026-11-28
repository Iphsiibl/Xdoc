"""自检 PyPI Trusted Publisher 是否可用：只换 token，不上传任何东西。

在 GitHub Actions 里跑（需要 permissions: id-token: write）：
    - 取 GitHub 的 OIDC JWT（audience 取自 PyPI 的 /_/oidc/audience）
    - 拿 JWT 去 PyPI 的 /_/oidc/mint-token 换一个 15 分钟有效的上传 token
    - 成功 → 说明 publisher 配好了；失败 → 把 PyPI 的原话打到 ::error:: 注解里

本地跑（没有 OIDC 环境变量）会直接跳过并返回 0，方便塞进 CI 的通用步骤里。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

PYPI = "https://pypi.org"


def get_audience() -> str:
    with urllib.request.urlopen(f"{PYPI}/_/oidc/audience", timeout=30) as resp:
        return json.load(resp)["audience"]


def get_oidc_token(audience: str) -> str:
    url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    token = os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(
        f"{url}{sep}audience={urllib.parse.quote(audience)}",
        headers={"Authorization": f"bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)["value"]


def mint(oidc_token: str) -> tuple[int, str]:
    body = json.dumps({"token": oidc_token}).encode("utf-8")
    req = urllib.request.Request(
        f"{PYPI}/_/oidc/mint-token", data=body, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if not (os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL") and os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")):
        print("不在 GitHub Actions 的 OIDC 环境里，跳过 Trusted Publisher 自检。")
        return 0

    try:
        audience = get_audience()
        oidc_token = get_oidc_token(audience)
    except Exception as exc:  # 拿不到 OIDC token：CI 权限或环境不对
        print(f"::error::拿不到 GitHub OIDC token：{exc}")
        return 1

    status, body = mint(oidc_token)
    if status >= 400:
        # PyPI 的原话最有用：常见是 "no active publishers found for ..."（publisher 还是 pending）
        print(f"::error::Trusted Publisher 不可用（HTTP {status}）：{body.strip()}")
        return 1

    print("Trusted Publisher 可用：已从 PyPI 换到上传 token（内容不打印）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
