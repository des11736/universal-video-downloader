"""微信视频号页面下载监听器。

Web 服务运行期间维护唯一的本地 MITM 代理。代理只负责向视频号页面
注入现有的浏览器端下载脚本，不参与后端下载任务的创建或轮询。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Protocol

from ..platforms.wechat_channels.certificate import ensure_ca_cert
from ..platforms.wechat_channels.mitm_proxy import WechatChannelsMitmProxy


class _Proxy(Protocol):
    """监听器需要的最小代理接口，便于隔离进程测试。"""

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def is_running(self) -> bool: ...


class WechatPageListener:
    """管理视频号 HTML 注入代理及其本地根证书。"""

    def __init__(
        self,
        *,
        cert_dir: Optional[Path] = None,
        js_assets_dir: Optional[Path] = None,
        proxy_factory: Callable[..., _Proxy] = WechatChannelsMitmProxy,
        ensure_certificate: Callable[[Path], tuple[Path, Path]] = ensure_ca_cert,
    ) -> None:
        package_dir = Path(__file__).resolve().parents[1]
        self._cert_dir = cert_dir or package_dir / "certs"
        self._js_assets_dir = (
            js_assets_dir or package_dir / "assets" / "wechat_channels"
        )
        self._proxy_factory = proxy_factory
        self._ensure_certificate = ensure_certificate
        self._proxy: Optional[_Proxy] = None

    def start(self) -> Path:
        """确保根证书存在，并启动唯一的页面注入代理。"""
        cert_path, _ = self._ensure_certificate(self._cert_dir)
        if self._proxy is None:
            self._proxy = self._proxy_factory(
                port=8888,
                cert_dir=self._cert_dir,
                js_assets_dir=self._js_assets_dir,
            )
        if not self._proxy.is_running():
            self._proxy.start()
        if not self._proxy.is_running():
            self._proxy.stop()
            raise RuntimeError(
                "视频号页面监听器未能在 127.0.0.1:8888 启动"
            )
        return cert_path

    def stop(self) -> None:
        """停止代理子进程并释放 8888 端口。"""
        if self._proxy is not None:
            self._proxy.stop()

    def is_running(self) -> bool:
        """返回代理子进程是否仍在运行。"""
        return self._proxy is not None and self._proxy.is_running()
