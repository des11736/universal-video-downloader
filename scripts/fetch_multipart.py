#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""下载 python-multipart wheel。"""
import re
import ssl
import json
import urllib.request
import os

ctx = ssl.create_default_context()
pkg = "python-multipart"
url = f"https://pypi.org/simple/{pkg}/"
req = urllib.request.Request(url, headers={"Accept": "application/vnd.pypi.simple.v1+json"})
with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
    data = json.loads(r.read().decode())

cands = [f for f in data["files"] if f["filename"].endswith(".whl") and "py3-none-any" in f["filename"]]


def vk(f):
    v = f["filename"].split("-")[1]
    low = v.lower()
    if re.search(r"[abcd]\d", low) or "dev" in low or "rc" in low:
        return (-1, [])
    return (1, [int(n) for n in re.findall(r"\d+", v)])


cands.sort(key=vk, reverse=True)
f = cands[0]
fname = f["filename"]
dest_dir = r"D:\codex_project\视频号视频爬取\scripts\_wheels"
os.makedirs(dest_dir, exist_ok=True)
dest = os.path.join(dest_dir, fname)
print(f"Downloading {fname} ...")
with urllib.request.urlopen(f["url"], timeout=60, context=ctx) as r, open(dest, "wb") as out:
    out.write(r.read())
print(f"Saved to {dest}")
