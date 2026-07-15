"""微信视频号下载适配器。

移植自原 Go 项目,实现 ``PlatformDownloader`` 接口。通过 MITM 代理拦截
``channels.weixin.qq.com`` 的 HTTPS 流量,注入 JS 脚本以捕获视频信息
(URL、解密 key),再用多线程分块下载并解密视频文件。

典型流程::

    1. can_handle(url) 判断是否为视频号 URL
    2. download():
       a. ensure_ca_cert() 生成 CA 证书(首次运行)
       b. 启动 WechatChannelsMitmProxy
       c. 等待浏览器访问视频号页面,JS 上报 profile
       d. MultiThreadDownloader 下载加密视频
       e. isaac_decrypt.decrypt_data 解密
       f. 写出最终文件
    3. finally 块停止 MITM 代理
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from ...core.base import PlatformDownloader, ProgressCallback
from ...core.models import DownloadOptions, DownloadResult, VideoInfo
from .certificate import ensure_ca_cert
from .downloader import MultiThreadDownloader
from .mitm_proxy import WechatChannelsMitmProxy

logger = logging.getLogger(__name__)

# 视频号页面域名
_CHANNELS_HOST = "channels.weixin.qq.com"

# 资源目录(相对于本文件向上一级再到 assets/wechat_channels)
_ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "wechat_channels"

# 默认证书目录
_DEFAULT_CERT_DIR = Path(__file__).resolve().parent.parent.parent / "certs"

# 等待 profile 的超时时间(秒),5 分钟
_PROFILE_TIMEOUT = 300


class WechatChannelsAdapter(PlatformDownloader):
    """微信视频号下载适配器。

    通过 MITM 代理捕获视频号页面的视频信息,下载后用 ISAAC 解密。

    Attributes:
        name: 适配器标识,固定为 ``"wechat_channels"``。
    """

    name = "wechat_channels"

    def __init__(
        self,
        cert_dir: Optional[Path] = None,
        js_assets_dir: Optional[Path] = None,
        proxy_port: int = 8888,
    ) -> None:
        """初始化适配器。

        Args:
            cert_dir: CA 证书目录,默认为包内 ``certs`` 子目录。
            js_assets_dir: JS 资源目录,默认为包内 ``assets/wechat_channels``。
            proxy_port: MITM 代理端口,默认 8888。
        """
        self.cert_dir = Path(cert_dir) if cert_dir else _DEFAULT_CERT_DIR
        self.js_assets_dir = Path(js_assets_dir) if js_assets_dir else _ASSETS_DIR
        self.proxy_port = proxy_port

        # 多线程下载器实例(复用以支持取消)
        self._downloader = MultiThreadDownloader(workers=4)
        # MITM 代理实例(按需创建)
        self._proxy: Optional[WechatChannelsMitmProxy] = None
        # 是否已提示过证书安装(避免重复阻塞)
        self._cert_prompted = False

    # ------------------------------------------------------------------
    # PlatformDownloader 接口实现
    # ------------------------------------------------------------------
    def can_handle(self, url: str) -> bool:
        """判断 URL 是否为微信视频号页面。

        匹配 host 为 ``channels.weixin.qq.com`` 的 URL。
        """
        try:
            parsed = urlparse(url)
            host = parsed.hostname or ""
            return _CHANNELS_HOST in host
        except Exception:
            return False

    def extract_info(self, url: str) -> VideoInfo:
        """提取视频信息。

        视频号需要先在浏览器中访问页面才能获取视频信息,因此这里只返回
        基本字段,实际信息在 :meth:`download` 中通过 MITM 代理获取。
        """
        return VideoInfo(
            url=url,
            platform=self.name,
            title="",
        )

    def download(
        self,
        url: str,
        options: DownloadOptions,
        callback: Optional[ProgressCallback] = None,
        task_id: str = "",
    ) -> DownloadResult:
        """执行视频号下载。

        流程:
            1. 确保 CA 证书存在(首次运行生成并提示安装)
            2. 启动 MITM 代理
            3. 等待浏览器访问视频号页面,JS 上报 profile
            4. 用多线程下载器下载加密视频
            5. 用 ISAAC 解密
            6. 写出最终文件

        Args:
            url: 视频号页面 URL。
            options: 下载选项(主要用 output_dir)。
            callback: 进度回调。
            task_id: 任务 ID。

        Returns:
            DownloadResult。
        """
        start_time = time.time()

        try:
            # 1. 确保 CA 证书(首次运行阻塞提示安装)
            if callback:
                callback.on_progress(task_id, 0.0)

            cert_path, key_path = ensure_ca_cert(self.cert_dir)
            if not self._cert_prompted:
                self._prompt_cert_install(cert_path)
                self._cert_prompted = True

            # 2. 启动 MITM 代理
            if callback:
                callback.on_progress(task_id, 5.0)

            self._proxy = WechatChannelsMitmProxy(
                port=self.proxy_port,
                cert_dir=self.cert_dir,
                js_assets_dir=self.js_assets_dir,
                callback=callback,
            )
            self._proxy.start()

            logger.info(
                "MITM 代理已启动(端口 %d),请在浏览器中设置代理 127.0.0.1:%d "
                "并访问视频号页面: %s",
                self.proxy_port,
                self.proxy_port,
                url,
            )

            # 3. 等待 JS 上报 profile
            profile = self._wait_for_profile(task_id, callback)
            if profile is None:
                return DownloadResult(
                    success=False,
                    error="等待视频信息超时,请确认已正确设置代理并访问视频号页面",
                    task_id=task_id,
                    duration_seconds=time.time() - start_time,
                )

            # 4. 提取视频 URL 与解密 key
            video_url = profile.get("url", "")
            decode_key = profile.get("key", "")
            title = profile.get("title", "") or task_id or "wechat_channels_video"

            if not video_url:
                return DownloadResult(
                    success=False,
                    error="profile 中缺少视频 URL",
                    task_id=task_id,
                    duration_seconds=time.time() - start_time,
                )

            logger.info("已获取视频信息: title=%s, url=%s", title, video_url)

            # 5. 下载加密视频到临时文件
            if callback:
                callback.on_progress(task_id, 10.0)

            output_dir = Path(options.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            # 加密视频临时文件
            encrypted_path = output_dir / f".{title}.encrypted.mp4"
            result = self._downloader.download(
                video_url,
                encrypted_path,
                callback=callback,
                task_id=task_id,
            )

            if not result.success:
                return DownloadResult(
                    success=False,
                    error=f"下载失败: {result.error}",
                    task_id=task_id,
                    duration_seconds=time.time() - start_time,
                )

            # 6. 解密视频
            if decode_key:
                if callback:
                    callback.on_progress(task_id, 90.0)

                logger.info("开始解密视频,种子: %s", decode_key)
                from .isaac_decrypt import decrypt_data

                encrypted_data = encrypted_path.read_bytes()
                decrypted_data = decrypt_data(
                    encrypted_data, decode_key.encode("utf-8")
                )

                # 写出最终文件
                final_path = output_dir / f"{title}.mp4"
                final_path.write_bytes(decrypted_data)

                # 清理加密临时文件
                encrypted_path.unlink(missing_ok=True)
            else:
                # 无需解密,直接重命名
                final_path = output_dir / f"{title}.mp4"
                encrypted_path.rename(final_path)

            if callback:
                callback.on_complete(task_id, str(final_path))

            logger.info("视频下载完成: %s", final_path)
            return DownloadResult(
                success=True,
                file_path=str(final_path),
                task_id=task_id,
                duration_seconds=time.time() - start_time,
            )

        except Exception as e:
            logger.error("视频号下载失败: %s", e)
            if callback:
                callback.on_error(task_id, str(e))
            return DownloadResult(
                success=False,
                error=str(e),
                task_id=task_id,
                duration_seconds=time.time() - start_time,
            )
        finally:
            # 确保 MITM 代理被停止
            if self._proxy is not None:
                self._proxy.stop()
                self._proxy = None

    def cancel(self, task_id: str) -> bool:
        """取消下载。

        委托给 MultiThreadDownloader 的取消逻辑。
        """
        return self._downloader.cancel(task_id)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    def _prompt_cert_install(self, cert_path: Path) -> None:
        """输出 CA 证书安装指引并阻塞等待用户确认。

        仅在首次运行时调用,提示用户:
        1. 双击 ca.crt 安装到"受信任的根证书颁发机构"
        2. 设置系统代理为 127.0.0.1:port
        """
        print("=" * 60)
        print("【微信视频号下载 - 首次运行配置】")
        print("=" * 60)
        print()
        print(f"已生成 CA 根证书: {cert_path}")
        print()
        print("请完成以下配置后继续:")
        print()
        print("1. 安装根证书(Windows):")
        print(f"   双击 {cert_path}")
        print("   → 选择「安装证书」")
        print("   → 选择「本地计算机」")
        print("   → 选择「将所有的证书放入下列存储」")
        print("   → 点击「浏览」,选择「受信任的根证书颁发机构」")
        print("   → 完成安装向导")
        print()
        print(f"2. 设置系统代理为 127.0.0.1:{self.proxy_port}")
        print("   Windows: 设置 → 网络和 Internet → 代理")
        print(f"   手动设置代理: 127.0.0.1:{self.proxy_port}")
        print()
        print("3. 在浏览器中访问视频号页面,下载按钮将自动出现")
        print()
        try:
            input("按回车继续...")
        except EOFError:
            # 非交互环境(如测试)下跳过阻塞
            logger.warning("非交互环境,跳过证书安装确认")

    def _wait_for_profile(
        self,
        task_id: str,
        callback: Optional[ProgressCallback],
    ) -> Optional[dict]:
        """等待 JS 端通过 MITM 代理上报视频 profile。

        轮询代理的 :meth:`get_profile`,超时返回 None。

        Args:
            task_id: 任务 ID。
            callback: 进度回调。

        Returns:
            收到的 profile 字典,超时返回 None。
        """
        if self._proxy is None:
            return None

        # 由于代理运行在子进程,profile 通过子进程内存隔离。
        # 简化实现:等待代理返回 profile(实际集成时需进程间通信)
        deadline = time.time() + _PROFILE_TIMEOUT
        while time.time() < deadline:
            if self._proxy is None:
                return None
            profile = self._proxy.get_profile(timeout=1.0)
            if profile is not None:
                return profile
            if callback:
                # 上报等待进度
                elapsed = _PROFILE_TIMEOUT - (deadline - time.time())
                percent = min(10.0 + (elapsed / _PROFILE_TIMEOUT) * 10.0, 20.0)
                callback.on_progress(task_id, percent)
        return None
