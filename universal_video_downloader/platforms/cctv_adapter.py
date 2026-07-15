"""央视频适配器。

委托 ``YtDlpAdapter`` 执行实际的视频信息提取与下载,仅负责识别央视频相关
URL(如 ``tv.cctv.com``、``yangshipin.cctv.cn`` 等)并将 ``platform`` 标记
为 ``"cctv"``。央视频通常无需登录,因此 cookies 参数一般不需要,但为兼容
``YtDlpAdapter`` 未来可能的签名扩展,这里优先尝试传入 cookies 参数,若 ytdlp
适配器签名不支持则回退到仅传 url。
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

from ..core.base import PlatformDownloader, ProgressCallback
from ..core.models import DownloadOptions, DownloadResult, VideoInfo
from .ytdlp_adapter import YtDlpAdapter

# 央视频支持的精确域名集合
# - cctv.com:央视网主站
# - tv.cctv.com:央视节目库
# - yangshipin.cctv.cn:央视频 App 网页版
# - tv.cctv.cn:央视网(备用域名)
CCTV_DOMAINS = {"cctv.com", "tv.cctv.com", "yangshipin.cctv.cn", "tv.cctv.cn"}


class CctvAdapter(PlatformDownloader):
    """央视频适配器,委托 YtDlpAdapter 执行实际下载。

    ``can_handle`` 仅识别央视频相关域名,``extract_info`` / ``download`` /
    ``cancel`` 全部委托给内部的 ``YtDlpAdapter`` 实例,并在返回的
    ``VideoInfo`` 上把 ``platform`` 改写为 ``"cctv"``。
    """

    name: str = "cctv"

    def __init__(self) -> None:
        # 实际下载委托给 ytdlp 适配器
        self._ytdlp = YtDlpAdapter()

    def can_handle(self, url: str) -> bool:
        """判断 URL 是否属于央视频。

        匹配规则(逐条短路判断,避免误命中 youtube/bilibili 等域名):

        1. 主机名精确命中 ``CCTV_DOMAINS``(如 ``tv.cctv.com``、
           ``yangshipin.cctv.cn``);
        2. 主机名以 ``.cctv.com`` 结尾(覆盖 ``www.cctv.com``、
           ``news.cctv.com`` 等 cctv.com 任意子域);
        3. 主机名为央视频 App 网页版 ``yangshipin.cctv.cn`` 或其子域
           (如 ``m.yangshipin.cctv.cn``)。

        其余域名(如 ``youtube.com``、``bilibili.com``)一律返回 False。
        """
        try:
            host = urlparse(url).hostname or ""
        except Exception:
            # URL 解析异常时拒绝处理,避免误判
            return False

        host = host.lower()

        # 1. 精确匹配已知央视频域名
        if host in CCTV_DOMAINS:
            return True
        # 2. cctv.com 的任意子域(如 www.cctv.com、news.cctv.com)
        if host.endswith(".cctv.com"):
            return True
        # 3. 央视频 App 网页版 yangshipin.cctv.cn 及其子域
        #    注意:cctv.cn 不做宽匹配,仅放行 yangshipin 相关子域
        if host == "yangshipin.cctv.cn" or host.endswith(".yangshipin.cctv.cn"):
            return True
        return False

    def extract_info(
        self,
        url: str,
        cookies_file: Optional[str] = None,
        cookies_from_browser: Optional[str] = None,
    ) -> VideoInfo:
        """提取视频元信息,委托 ytdlp 并把 platform 改写为 cctv。

        央视频通常无需登录,cookies 参数多数情况下不传。为兼容
        ``YtDlpAdapter`` 未来可能新增的 cookies 形参,这里优先尝试传入
        cookies 参数;若 ytdlp 适配器签名不支持(抛 ``TypeError``)则回退
        到仅传 url。提取失败时返回仅含 url 与 platform 的空 VideoInfo。
        """
        try:
            try:
                # 优先尝试传入 cookies 参数(兼容支持 cookies 的 ytdlp 适配器)
                info = self._ytdlp.extract_info(
                    url,
                    cookies_file=cookies_file,
                    cookies_from_browser=cookies_from_browser,
                )
            except TypeError:
                # ytdlp 适配器签名不支持 cookies 参数,回退到仅传 url
                info = self._ytdlp.extract_info(url)
        except Exception:
            # 提取失败不抛错,返回空信息让上层决策,但 platform 标记为 cctv
            return VideoInfo(url=url, title="", platform="cctv")

        # 委托 ytdlp 提取成功后,把 platform 改写为 cctv
        info.platform = "cctv"
        return info

    def download(
        self,
        url: str,
        options: DownloadOptions,
        callback: Optional[ProgressCallback] = None,
        task_id: str = "",
    ) -> DownloadResult:
        """执行下载,完全委托 ytdlp 适配器。"""
        return self._ytdlp.download(url, options, callback, task_id)

    def cancel(self, task_id: str) -> bool:
        """取消指定任务的下载,委托 ytdlp 适配器。"""
        return self._ytdlp.cancel(task_id)
