"""微信视频号页面监听器的生命周期测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from universal_video_downloader.web.wechat_listener import WechatPageListener


def test_listener_starts_one_proxy_and_stops_it(tmp_path) -> None:
    """监听器应复用一个代理进程，并在关闭时停止它。"""
    proxies = []

    class FakeProxy:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.started = False
            self.stopped = False
            proxies.append(self)

        def start(self) -> None:
            self.started = True

        def stop(self) -> None:
            self.stopped = True

        def is_running(self) -> bool:
            return self.started and not self.stopped

    listener = WechatPageListener(
        cert_dir=tmp_path / "certs",
        js_assets_dir=tmp_path / "assets",
        proxy_factory=FakeProxy,
        ensure_certificate=lambda cert_dir: (
            cert_dir / "ca.crt",
            cert_dir / "ca.key",
        ),
    )

    assert listener.start().name == "ca.crt"
    assert listener.is_running() is True

    listener.start()
    listener.stop()

    assert len(proxies) == 1
    assert proxies[0].kwargs["port"] == 8888
    assert proxies[0].stopped is True


def test_page_listener_certificate_directory_is_ignored() -> None:
    """本地 CA 私钥不能作为未跟踪文件留在项目中。"""
    project_root = Path(__file__).resolve().parents[2]
    ignore_rules = (project_root / ".gitignore").read_text(encoding="utf-8")

    assert "universal_video_downloader/certs/" in ignore_rules


def test_listener_reports_proxy_start_failure(tmp_path) -> None:
    """代理启动后立即退出时，应报告监听器启动失败。"""
    class FailingProxy:
        def __init__(self, **_kwargs) -> None:
            pass

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def is_running(self) -> bool:
            return False

    listener = WechatPageListener(
        cert_dir=tmp_path / "certs",
        js_assets_dir=tmp_path / "assets",
        proxy_factory=FailingProxy,
        ensure_certificate=lambda cert_dir: (
            cert_dir / "ca.crt",
            cert_dir / "ca.key",
        ),
    )

    with pytest.raises(RuntimeError, match="127.0.0.1:8888"):
        listener.start()
