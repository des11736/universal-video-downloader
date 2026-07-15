"""`config.py` 的单元测试。

使用 pytest 的 `tmp_path` fixture 隔离测试,确保不污染真实 home 目录。
"""

from pathlib import Path

import pytest

from universal_video_downloader.core.config import (
    DEFAULT_CONFIG_YAML,
    AppConfig,
    get_default_config_path,
    load_config,
)


def test_load_config_creates_file_when_missing(tmp_path: Path) -> None:
    """测试 1:配置文件不存在时调用 load_config 应自动创建文件。"""
    config_path = tmp_path / "config.yaml"
    assert not config_path.exists()

    # 调用 load_config,内部应自动创建配置文件
    load_config(config_path)

    # 文件应已被创建,内容应与默认 YAML 一致
    assert config_path.exists()
    assert config_path.read_text(encoding="utf-8") == DEFAULT_CONFIG_YAML


def test_load_config_default_fields(tmp_path: Path) -> None:
    """测试 2:加载后的 AppConfig 默认字段正确。"""
    config_path = tmp_path / "config.yaml"

    config = load_config(config_path)

    assert isinstance(config, AppConfig)
    # download 配置
    assert config.download.defaultHighest is True
    assert config.download.outputDir == "./downloads"
    assert config.download.concurrency == 3
    # proxy 配置
    assert config.proxy.system is True
    assert config.proxy.port == 2023
    # wechat_channels 配置
    assert config.wechat_channels.enabled is True
    assert config.wechat_channels.jsAssetsDir == "./assets/wechat_channels"
    # ytdlp 配置
    assert config.ytdlp.extraArgs == []


def test_load_config_custom_yaml(tmp_path: Path) -> None:
    """测试 3:写入自定义 YAML 后能正确反序列化(改 proxy.port 为 8888)。"""
    config_path = tmp_path / "config.yaml"
    custom_yaml = """
download:
  defaultHighest: true
  outputDir: /tmp/my_videos
  concurrency: 5
  filenameTemplate: "%(uploader)s-%(title)s.%(ext)s"

proxy:
  system: false
  port: 8888

wechat_channels:
  enabled: false
  certDir: ~/custom/certs
  jsAssetsDir: ./custom/assets
  decrypt:
    wasmUrl: https://example.com/custom.wasm

ytdlp:
  extraArgs:
    - "--no-playlist"
    - "--retries"
    - "10"
"""
    config_path.write_text(custom_yaml, encoding="utf-8")

    config = load_config(config_path)

    # 验证自定义字段被正确反序列化
    assert config.download.defaultHighest is True
    assert config.download.outputDir == "/tmp/my_videos"
    assert config.download.concurrency == 5
    assert config.proxy.system is False
    assert config.proxy.port == 8888
    assert config.wechat_channels.enabled is False
    # certDir 中的 ~ 应被展开为实际 home 路径
    assert config.wechat_channels.certDir == str(Path.home() / "custom" / "certs")
    assert config.wechat_channels.decrypt.wasmUrl == "https://example.com/custom.wasm"
    assert config.ytdlp.extraArgs == ["--no-playlist", "--retries", "10"]


def test_get_default_config_path() -> None:
    """默认配置路径应为 `~/.uvd/config.yaml`。"""
    expected = Path.home() / ".uvd" / "config.yaml"
    assert get_default_config_path() == expected
