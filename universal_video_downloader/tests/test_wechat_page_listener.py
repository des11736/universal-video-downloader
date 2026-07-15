"""微信视频号页面监听器的生命周期测试。"""

from __future__ import annotations

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
