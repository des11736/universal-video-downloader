"""微信视频号页面下载监听器。

Web 服务运行期间维护唯一的本地 MITM 代理。代理只负责向视频号页面
注入现有的浏览器端下载脚本，不参与后端下载任务的创建或轮询。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional, Protocol

from ..platforms.wechat_channels.certificate import ensure_ca_cert
from ..platforms.wechat_channels.mitm_proxy import WechatChannelsMitmProxy

logger = logging.getLogger(__name__)


def _get_current_system_proxy() -> Optional[str]:
    """获取当前系统代理设置,返回 http://host:port 格式或 None。

    优先读取环境变量 UVD_UPSTREAM_PROXY(由 start_uvd.bat 设置),
    这样可以在切换系统代理之前捕获用户原有的代理(如 VPN 7078)。

    用于将用户原有的代理作为 mitmproxy 的上游代理,
    这样 8888 代理会转发所有流量到用户原有代理,保持网络连通性。
    """
    import os

    # 优先使用环境变量(由启动脚本设置,包含切换前的原始代理)
    env_proxy = os.environ.get("UVD_UPSTREAM_PROXY")
    if env_proxy:
        logger.info("从环境变量获取上游代理: %s", env_proxy)
        return env_proxy

    # 回退:直接读取注册表(用于直接运行 uvicorn serve 的场景)
    import platform

    system = platform.system().lower()
    if system == "windows":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
                0,
                winreg.KEY_READ,
            )
            try:
                enable_val, _ = winreg.QueryValueEx(key, "ProxyEnable")
                if not enable_val:
                    return None
                server, _ = winreg.QueryValueEx(key, "ProxyServer")
                winreg.CloseKey(key)
                if server and ":" in server:
                    # server 格式: "host:port" 或 "http=host:port;https=host:port"
                    # 简单处理:取第一个分号前的部分
                    first = server.split(";")[0]
                    if "=" in first:
                        first = first.split("=", 1)[1]
                    return f"http://{first}"
            except FileNotFoundError:
                pass
        except Exception as e:
            logger.warning("读取系统代理失败: %s", e)
    return None


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
            # 获取用户当前系统代理(如 VPN 7078),作为 mitmproxy 的上游代理
            upstream_proxy = _get_current_system_proxy()
            if upstream_proxy:
                logger.info("检测到上游代理 %s,将转发所有流量", upstream_proxy)
            self._proxy = self._proxy_factory(
                port=8888,
                cert_dir=self._cert_dir,
                js_assets_dir=self._js_assets_dir,
                upstream_proxy=upstream_proxy,
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
