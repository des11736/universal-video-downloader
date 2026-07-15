#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""手动下载 uvicorn/fastapi wheel 并本地安装。"""
import json
import os
import re
import ssl
import sys
import urllib.request
from html.parser import HTMLParser

PYTHON_TAG = "cp310"  # Python 3.10
ABI_TAG = "cp310"
PLATFORM_TAG = "win_amd64"

# 需要的包及其依赖(顺序:被依赖的在前)
PACKAGES = [
    "starlette",
    "anyio",
    "sniffio",
    "idna",
    "typing-extensions",
    "typing_extensions",
    "colorama",
    "fastapi",
    "uvicorn",
    "click",
    "h11",
    "websockets",
    "watchfiles",
    "httptools",
    "python-dotenv",
    "pyyaml",
]


def _ssl_ctx():
    return ssl.create_default_context()


def _list_wheels(pkg):
    """从 pypi.org/simple/<pkg>/ 获取 wheel 文件名列表。"""
    url = f"https://pypi.org/simple/{pkg.lower().replace('_','-')}/"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.pypi.simple.v1+json"})
    ctx = _ssl_ctx()
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        data = json.loads(r.read().decode("utf-8"))
    return [f["filename"] for f in data.get("files", []) if f["filename"].endswith(".whl")]


def _pick_wheel(wheels):
    """从 wheel 列表里挑出 cp310/win_amd64 兼容的最新稳定版(非 alpha/dev/rc)。"""
    import re as _re

    def _version_key(name):
        # wheel 文件名格式:<pkg>-<ver>-<pythontag>-<abitag>-<platformtag>.whl
        # 或 <pkg>-<ver>-<pythontag>-<platformtag>.whl
        parts = name.split("-")
        if len(parts) < 2:
            return (0, [])
        ver = parts[1]
        # 跳过 pre-release
        low = ver.lower()
        if any(x in low for x in ["a", "b", "rc", "dev", ".0a", ".0b"]):
            # 但要允许类似 0.10.0 这种正常版本
            # 只在版本号末尾出现 a/b/rc/dev 才算 pre-release
            if _re.search(r"[abcd](\d|$)", low) or "dev" in low or "rc" in low:
                return (-1, [])
        # 解析数字版本
        nums = _re.findall(r"\d+", ver)
        return (1, [int(n) for n in nums])

    # 优先精确匹配 cp310-cp310-win_amd64
    cands = [w for w in wheels if PYTHON_TAG in w and ABI_TAG in w and PLATFORM_TAG in w]
    if cands:
        cands.sort(key=_version_key, reverse=True)
        return cands[0]
    # 次选 cp310-abi3-win_amd64
    cands = [w for w in wheels if PYTHON_TAG in w and "abi3" in w and PLATFORM_TAG in w]
    if cands:
        cands.sort(key=_version_key, reverse=True)
        return cands[0]
    # 再次 py3-none-any
    cands = [w for w in wheels if "py3-none-any" in w]
    if cands:
        cands.sort(key=_version_key, reverse=True)
        return cands[0]
    # 最后 py2.py3-none-any
    cands = [w for w in wheels if "py2.py3-none-any" in w]
    if cands:
        cands.sort(key=_version_key, reverse=True)
        return cands[0]
    return None


def main():
    import subprocess
    python = sys.executable
    dl_dir = os.path.join(os.path.dirname(__file__), "_wheels")
    os.makedirs(dl_dir, exist_ok=True)

    installed = []
    for pkg in PACKAGES:
        try:
            wheels = _list_wheels(pkg)
        except Exception as e:
            print(f"[SKIP] {pkg}: list failed {e}")
            continue
        if not wheels:
            print(f"[SKIP] {pkg}: no wheels")
            continue
        # 只看稳定版(不含 +local 等),取最新(列表按时间倒序)
        wheel = _pick_wheel(wheels)
        if not wheel:
            print(f"[SKIP] {pkg}: no compatible wheel among {len(wheels)} candidates")
            continue
        # 下载
        # 从 pypi simple JSON 拿 url
        url2 = f"https://pypi.org/simple/{pkg.lower().replace('_','-')}/"
        req = urllib.request.Request(url2, headers={"Accept": "application/vnd.pypi.simple.v1+json"})
        ctx = _ssl_ctx()
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            data = json.loads(r.read().decode("utf-8"))
        dl_url = None
        for f in data.get("files", []):
            if f["filename"] == wheel:
                dl_url = f["url"]
                break
        if not dl_url:
            print(f"[SKIP] {pkg}: url not found for {wheel}")
            continue
        dest = os.path.join(dl_dir, wheel)
        if not os.path.exists(dest):
            print(f"[DL] {wheel} <- {dl_url}")
            with urllib.request.urlopen(dl_url, timeout=120, context=ctx) as r, open(dest, "wb") as out:
                out.write(r.read())
        else:
            print(f"[CACHED] {wheel}")
        installed.append(dest)

    # 本地安装
    if installed:
        print(f"\n[INSTALL] {len(installed)} wheels")
        cmd = [python, "-m", "pip", "install", "--no-deps", "--user", *installed]
        print(" ".join(f'"{c}"' if " " in c else c for c in cmd))
        r = subprocess.run(cmd, capture_output=True, text=True)
        print(r.stdout[-2000:])
        print(r.stderr[-1000:])


if __name__ == "__main__":
    main()
