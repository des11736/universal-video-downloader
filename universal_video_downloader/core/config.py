"""配置加载与管理。

负责读取 / 创建 `~/.uvd/config.yaml` 配置文件,解析为 pydantic 模型 `AppConfig`。
首次启动(配置文件不存在)时自动创建默认配置,并将 `~` 展开为实际 home 路径。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field


class DownloadConfig(BaseModel):
    """下载相关配置,兼容原项目字段命名。"""

    defaultHighest: bool = True
    outputDir: str = "./downloads"
    concurrency: int = 3
    filenameTemplate: str = "%(title)s.%(ext)s"


class CookiesConfig(BaseModel):
    """cookies 配置,用于下载需要登录态的会员内容。

    `file` 指定 cookies.txt 文件路径,优先级高于 `browser`;
    `browser` 指定从哪个浏览器读取 cookies(chrome/edge/firefox/safari)。
    """

    # chrome/edge/firefox/safari,优先级低于 file
    browser: Optional[str] = None
    # cookies.txt 文件路径
    file: Optional[str] = None


class ProxyConfig(BaseModel):
    """MITM 代理配置,兼容原项目字段命名。"""

    system: bool = True
    port: int = 2023


class WechatDecryptConfig(BaseModel):
    """视频号解密配置。"""

    wasmUrl: str = (
        "https://res.wx.qq.com/t/wx_fed/cdn_libs/res/decrypt-video-core/"
        "1.3.0/wasm_video_decode.wasm"
    )


class WechatChannelsConfig(BaseModel):
    """微信视频号适配器配置。"""

    enabled: bool = True
    certDir: str = "~/.uvd/certs"
    jsAssetsDir: str = "./assets/wechat_channels"
    decrypt: WechatDecryptConfig = Field(default_factory=WechatDecryptConfig)


class YtdlpConfig(BaseModel):
    """yt-dlp 通用适配器配置。"""

    extraArgs: list[str] = Field(default_factory=list)


class AppConfig(BaseModel):
    """应用总配置,聚合各子模块配置。"""

    download: DownloadConfig = Field(default_factory=DownloadConfig)
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    wechat_channels: WechatChannelsConfig = Field(default_factory=WechatChannelsConfig)
    ytdlp: YtdlpConfig = Field(default_factory=YtdlpConfig)
    cookies: CookiesConfig = Field(default_factory=CookiesConfig)


# 默认配置 YAML 文本,与 spec 保持一致。首次启动时写入此内容。
DEFAULT_CONFIG_YAML = """\
config_version: 2

download:
  defaultHighest: true           # 兼容原项目
  outputDir: ./downloads
  concurrency: 3
  filenameTemplate: "%(title)s.%(ext)s"

proxy:
  system: true                   # 兼容原项目
  port: 2023

wechat_channels:
  enabled: true
  certDir: ~/.uvd/certs
  jsAssetsDir: ./assets/wechat_channels
  decrypt:
    wasmUrl: https://res.wx.qq.com/t/wx_fed/cdn_libs/res/decrypt-video-core/1.3.0/wasm_video_decode.wasm

ytdlp:
  extraArgs: []

cookies:
  browser: null        # chrome/edge/firefox/safari,优先级低于 file
  file: null           # cookies.txt 路径
"""


def get_default_config_path() -> Path:
    """返回默认配置文件路径 `~/.uvd/config.yaml`。"""
    return Path.home() / ".uvd" / "config.yaml"


def _expand_user_fields(data: dict[str, Any]) -> dict[str, Any]:
    """展开配置中 `~` 为实际 home 路径(作用于 certDir / jsAssetsDir 字段)。

    即使用户在自定义配置里写了 `~/xxx`,加载后也会得到绝对路径,便于后续
    适配器直接使用。
    """
    wechat = data.get("wechat_channels")
    if isinstance(wechat, dict):
        for key in ("certDir", "jsAssetsDir"):
            value = wechat.get(key)
            if isinstance(value, str):
                wechat[key] = os.path.expanduser(value)
    return data


def load_config(config_path: Optional[Path] = None) -> AppConfig:
    """加载或自动创建默认配置并返回 `AppConfig`。

    - 若 `config_path` 为 None,使用 `get_default_config_path()`。
    - 若配置文件不存在,自动创建父目录并写入 `DEFAULT_CONFIG_YAML`。
    - 解析 YAML 后,将 `wechat_channels.certDir` / `jsAssetsDir` 中的 `~`
      展开为实际 home 路径,再通过 pydantic v2 `model_validate` 构建模型。
    - 配置版本迁移:当 `config_version` 缺失或为 1 时,自动补全 `cookies`
      块(browser/file 默认 null),并将版本号升级为 2 后写回文件。
      迁移不会覆盖用户已设置的 `defaultHighest` 或 `cookies` 字段。
    """
    path = config_path if config_path is not None else get_default_config_path()

    # 首次启动:配置文件不存在则自动创建默认配置
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG_YAML, encoding="utf-8")

    raw_text = path.read_text(encoding="utf-8")
    data: dict[str, Any] = yaml.safe_load(raw_text) or {}

    # 配置版本迁移:旧版本(无 config_version 或为 1)补全 cookies 块并升级到 v2
    if data.get("config_version") in (None, 1):
        cookies = data.get("cookies")
        if not isinstance(cookies, dict):
            cookies = {}
            data["cookies"] = cookies
        # 仅在字段缺失时补默认值,不覆盖用户已设置的 cookies 字段
        cookies.setdefault("browser", None)
        cookies.setdefault("file", None)
        data["config_version"] = 2
        # 写回文件持久化迁移结果(注意:yaml.safe_dump 往返会丢失原有注释)
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    # 展开 ~ 为实际 home 路径
    data = _expand_user_fields(data)
    return AppConfig.model_validate(data)
