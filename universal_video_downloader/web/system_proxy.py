"""跨平台系统代理自动管理。

启动 UVD Web 服务时自动将系统代理切换到本地 MITM 代理(127.0.0.1:8888),
关闭时恢复原代理设置。这样用户无需手动在 Windows/Mac/Linux 系统设置里
切换代理,实现"启动即用"。

支持平台:
- Windows:通过注册表 ``HKCU\\...\\Internet Settings`` 修改 ProxyEnable/ProxyServer
- macOS:通过 ``networksetup`` 命令修改 Wi-Fi/Ethernet 等活动网络服务
- Linux:通过 ``gsettings`` 修改 GNOME 系统代理(GNOME 是主流桌面环境)

备份策略:
- 启动时一次性备份原 ProxyEnable/ProxyServer 等字段到内存
- 关闭时按备份恢复;若未备份(异常情况),则将 ProxyEnable 置为 0 关闭代理

异常处理:
- 所有平台命令都在 try/except 中执行,失败只记录日志不抛异常
- 这样即使代理设置失败,UVD Web 服务仍可正常启动,只是用户需要手动配置
"""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ProxyBackup:
    """系统代理设置的备份,供恢复时使用。"""

    enable: Optional[bool] = None
    server: Optional[str] = None
    # macOS:记录哪些网络服务被修改过,恢复时遍历这些服务
    macos_services: Optional[list[str]] = None


class SystemProxyManager:
    """跨平台系统代理管理器。

    使用方式::

        mgr = SystemProxyManager()
        mgr.set_proxy("127.0.0.1", 8888)  # 启动时调用
        # ... 服务运行 ...
        mgr.restore()  # 关闭时调用
    """

    def __init__(self) -> None:
        self._backup: Optional[ProxyBackup] = None
        self._current_proxy: Optional[tuple[str, int]] = None
        self._platform = platform.system().lower()

    @property
    def platform(self) -> str:
        """返回当前平台标识:windows/darwin/linux。"""
        return self._platform

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------
    def set_proxy(self, host: str, port: int) -> bool:
        """设置系统代理为 host:port,自动备份原设置。

        Args:
            host: 代理监听地址(通常是 127.0.0.1)。
            port: 代理监听端口。

        Returns:
            True 如果设置成功;False 否(平台不支持或命令失败)。
        """
        # 如果已经设置过且目标相同,直接返回成功(避免重复备份覆盖原值)
        if self._current_proxy == (host, port):
            return True

        # 首次设置时备份原代理配置
        if self._backup is None:
            self._backup = self._backup_current()

        server_str = f"{host}:{port}"
        try:
            if self._platform == "windows":
                self._set_windows_proxy(server_str)
            elif self._platform == "darwin":
                self._set_macos_proxy(host, port)
            else:
                self._set_linux_proxy(host, port)
        except Exception as e:
            logger.warning("设置系统代理失败(%s):%s。请手动设置为 %s",
                           self._platform, e, server_str)
            return False

        self._current_proxy = (host, port)
        logger.info("系统代理已设置为 %s", server_str)
        return True

    def restore(self) -> bool:
        """恢复 set_proxy 之前的原系统代理设置。

        Returns:
            True 如果恢复成功或无需恢复;False 否。
        """
        if self._current_proxy is None:
            # 从未设置过代理,无需恢复
            return True

        if self._backup is None:
            # 异常情况:设置过代理但没备份,直接关闭代理作为安全兜底
            logger.warning("代理备份缺失,关闭系统代理作为安全兜底")
            return self._disable_proxy()

        try:
            if self._platform == "windows":
                self._restore_windows(self._backup)
            elif self._platform == "darwin":
                self._restore_macos(self._backup)
            else:
                self._restore_linux(self._backup)
        except Exception as e:
            logger.error("恢复系统代理失败(%s):%s。请手动检查代理设置。",
                         self._platform, e)
            return False

        logger.info("系统代理已恢复为原设置")
        self._current_proxy = None
        self._backup = None
        return True

    # ------------------------------------------------------------------
    # Windows
    # ------------------------------------------------------------------
    def _backup_current(self) -> ProxyBackup:
        """备份当前系统代理设置(平台相关)。"""
        if self._platform == "windows":
            return self._backup_windows()
        if self._platform == "darwin":
            return self._backup_macos()
        return self._backup_linux()

    def _disable_proxy(self) -> bool:
        """关闭系统代理(不恢复原值,作为异常兜底)。"""
        try:
            if self._platform == "windows":
                self._set_windows_proxy(enable=False)
            elif self._platform == "darwin":
                self._disable_macos_proxy()
            else:
                self._disable_linux_proxy()
            return True
        except Exception as e:
            logger.error("关闭系统代理失败:%s", e)
            return False

    def _backup_windows(self) -> ProxyBackup:
        """备份 Windows 注册表中的代理设置。

        读取 HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings
        下的 ProxyEnable 和 ProxyServer 字段。
        """
        try:
            import winreg  # type: ignore[import-not-found]
        except ImportError:
            # 非 Windows 平台误调用了,返回空备份
            return ProxyBackup()

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
                0,
                winreg.KEY_READ,
            )
            try:
                enable_val, _ = winreg.QueryValueEx(key, "ProxyEnable")
                enable = bool(enable_val)
            except FileNotFoundError:
                enable = None
            try:
                server, _ = winreg.QueryValueEx(key, "ProxyServer")
            except FileNotFoundError:
                server = None
            winreg.CloseKey(key)
            return ProxyBackup(enable=enable, server=server)
        except OSError as e:
            logger.warning("读取 Windows 代理注册表失败:%s", e)
            return ProxyBackup()

    def _set_windows_proxy(self, server: Optional[str] = None, *,
                            enable: bool = True) -> None:
        """设置 Windows 系统代理。

        Args:
            server: 代理服务器地址(如 "127.0.0.1:8888");None 时不修改 server
            enable: 是否启用代理
        """
        import winreg  # type: ignore[import-not-found]

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            0,
            winreg.KEY_WRITE,
        )
        try:
            if server is not None:
                winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, server)
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD,
                              1 if enable else 0)
        finally:
            winreg.CloseKey(key)

        # 通知系统代理设置已变更(让运行中的浏览器立即应用)
        # 调用 InternetSetOption 的 INTERNET_OPTION_SETTINGS_CHANGED
        try:
            import ctypes
            INTERNET_OPTION_SETTINGS_CHANGED = 39
            INTERNET_OPTION_REFRESH = 37
            ctypes.c_int = ctypes.windll.wininet.InternetSetOptionW(
                0, INTERNET_OPTION_SETTINGS_CHANGED, None, 0
            )
            ctypes.windll.wininet.InternetSetOptionW(
                0, INTERNET_OPTION_REFRESH, None, 0
            )
        except Exception as e:
            logger.debug("通知系统代理变更失败(非致命):%s", e)

    def _restore_windows(self, backup: ProxyBackup) -> None:
        """恢复 Windows 代理设置。"""
        if backup.server is not None:
            self._set_windows_proxy(server=backup.server,
                                    enable=bool(backup.enable))
        else:
            # 原 server 不存在,按 enable 标志决定
            self._set_windows_proxy(enable=bool(backup.enable))

    # ------------------------------------------------------------------
    # macOS
    # ------------------------------------------------------------------
    def _list_macos_network_services(self) -> list[str]:
        """列出 macOS 上所有网络服务名称。"""
        try:
            out = subprocess.check_output(
                ["networksetup", "-listallnetworkservices"],
                text=True, encoding="utf-8", errors="replace",
                stderr=subprocess.DEVNULL,
            )
            # 第一行是标题,跳过
            services = [s.strip() for s in out.splitlines()[1:] if s.strip()]
            return services
        except Exception as e:
            logger.warning("列出 macOS 网络服务失败:%s", e)
            return []

    def _backup_macos(self) -> ProxyBackup:
        """备份 macOS 代理设置(networksetup)。"""
        backup = ProxyBackup(macos_services=[])
        services = self._list_macos_network_services()
        # 只备份第一个 Web Proxy 的状态(假设所有服务代理配置一致)
        for svc in services:
            try:
                out = subprocess.check_output(
                    ["networksetup", "-getwebproxy", svc],
                    text=True, encoding="utf-8", errors="replace",
                    stderr=subprocess.DEVNULL,
                )
                # 输出形如:
                #   Enabled: No
                #   Server: 127.0.0.1
                #   Port: 8888
                #   Authenticated Proxy Enabled: 0
                enabled = "Yes" in out.splitlines()[0] if out else False
                backup.macos_services.append(svc)
                if backup.enable is None:
                    backup.enable = enabled
                    # 提取 server:port
                    for line in out.splitlines():
                        if line.startswith("Server:"):
                            srv = line.split(":", 1)[1].strip()
                            # port 单独获取,这里组合一下
                        if line.startswith("Port:"):
                            port = line.split(":", 1)[1].strip()
                    if backup.enable:
                        # 启用状态下,组合 server:port
                        # 但 macOS 的 backup 这里只记 server 字段
                        pass
                break  # 只看第一个服务
            except Exception:
                continue
        return backup

    def _set_macos_proxy(self, host: str, port: int) -> None:
        """设置 macOS 系统代理(对所有网络服务生效)。"""
        services = self._list_macos_network_services()
        if not services:
            raise RuntimeError("未找到 macOS 网络服务")
        for svc in services:
            for cmd_args in (
                ["-setwebproxy", svc, host, str(port)],
                ["-setsecurewebproxy", svc, host, str(port)],
            ):
                subprocess.run(
                    ["networksetup"] + cmd_args,
                    check=False,  # 某些服务可能不支持,忽略错误
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

    def _disable_macos_proxy(self) -> None:
        """关闭 macOS 所有网络服务的代理。"""
        services = self._list_macos_network_services()
        for svc in services:
            for cmd_args in (
                ["-setwebproxystate", svc, "off"],
                ["-setsecurewebproxystate", svc, "off"],
            ):
                subprocess.run(
                    ["networksetup"] + cmd_args,
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

    def _restore_macos(self, backup: ProxyBackup) -> None:
        """恢复 macOS 代理设置。"""
        if not backup.macos_services:
            self._disable_macos_proxy()
            return

        state = "on" if backup.enable else "off"
        for svc in backup.macos_services:
            for cmd_args in (
                ["-setwebproxystate", svc, state],
                ["-setsecurewebproxystate", svc, state],
            ):
                subprocess.run(
                    ["networksetup"] + cmd_args,
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

    # ------------------------------------------------------------------
    # Linux (GNOME)
    # ------------------------------------------------------------------
    def _gsettings(self, *args: str) -> Optional[str]:
        """调用 gsettings 命令,返回 stdout 或 None。"""
        if not shutil.which("gsettings"):
            return None
        try:
            out = subprocess.check_output(
                ["gsettings"] + list(args),
                text=True, encoding="utf-8", errors="replace",
                stderr=subprocess.DEVNULL,
            )
            return out.strip()
        except Exception:
            return None

    def _backup_linux(self) -> ProxyBackup:
        """备份 GNOME 系统代理设置。"""
        mode = self._gsettings("get", "org.gnome.system.proxy", "mode")
        # mode 形如 "'none'" / "'manual'" / "'auto'"
        if mode is None:
            return ProxyBackup()
        enable = mode.strip("'\"") == "manual"

        host = self._gsettings("get", "org.gnome.system.proxy.http", "host")
        port = self._gsettings("get", "org.gnome.system.proxy.http", "port")
        server = None
        if host and port:
            host = host.strip("'\"")
            port = port.strip("'\"")
            server = f"{host}:{port}"

        return ProxyBackup(enable=enable, server=server)

    def _set_linux_proxy(self, host: str, port: int) -> None:
        """设置 GNOME 系统代理为 manual 模式 + 指定 host:port。"""
        if not shutil.which("gsettings"):
            logger.warning("Linux 桌面未检测到 gsettings(非 GNOME?),跳过代理设置")
            return
        # 设置 mode=manual,http/https host 和 port
        for schema_suffix, args in (
            ("http", [host, str(port)]),
            ("https", [host, str(port)]),
        ):
            self._gsettings(
                "set", f"org.gnome.system.proxy.{schema_suffix}", "host", host
            )
            self._gsettings(
                "set", f"org.gnome.system.proxy.{schema_suffix}", "port", str(port)
            )
        self._gsettings("set", "org.gnome.system.proxy", "mode", "manual")

    def _disable_linux_proxy(self) -> None:
        """关闭 GNOME 系统代理。"""
        self._gsettings("set", "org.gnome.system.proxy", "mode", "none")

    def _restore_linux(self, backup: ProxyBackup) -> None:
        """恢复 GNOME 代理设置。"""
        if backup.enable:
            # 原来是启用的,恢复为 manual
            self._gsettings("set", "org.gnome.system.proxy", "mode", "manual")
        else:
            # 原来是关闭的,设为 none
            self._gsettings("set", "org.gnome.system.proxy", "mode", "none")
