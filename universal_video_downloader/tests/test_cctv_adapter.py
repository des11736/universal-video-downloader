"""央视频适配器(CctvAdapter)的单元测试。

覆盖 ``can_handle`` 域名匹配(含正例与反例)、调度器优先选中 CCTV 适配器、
以及 ``extract_info`` 将 ``platform`` 改写为 ``"cctv"`` 等场景。
``extract_info`` 测试通过 mock ``YtDlpAdapter`` 避免真实网络请求。
"""

from __future__ import annotations

from unittest.mock import patch

from universal_video_downloader.core.models import VideoInfo
from universal_video_downloader.platforms.cctv_adapter import CctvAdapter
from universal_video_downloader.scheduler.registry import create_default_registry


def test_can_handle_tv_cctv_com():
    """测试 1:tv.cctv.com 的节目页 URL 应被识别为央视频。"""
    adapter = CctvAdapter()
    assert adapter.can_handle("https://tv.cctv.com/2024/xx/xx/VIDEOxxx.shtml") is True


def test_can_handle_yangshipin_cctv_cn():
    """测试 2:yangshipin.cctv.cn(央视频 App 网页版)应被识别为央视频。"""
    adapter = CctvAdapter()
    assert adapter.can_handle("https://yangshipin.cctv.cn/some/page") is True


def test_can_handle_www_cctv_com():
    """测试 3:www.cctv.com(央视网主站子域)应被识别为央视频。"""
    adapter = CctvAdapter()
    assert adapter.can_handle("https://www.cctv.com/") is True


def test_can_handle_rejects_youtube():
    """测试 4:youtube.com 不应被识别为央视频(避免误命中)。"""
    adapter = CctvAdapter()
    assert adapter.can_handle("https://www.youtube.com/watch?v=xxx") is False


def test_can_handle_rejects_bilibili():
    """测试 5:bilibili.com 不应被识别为央视频(避免误命中)。"""
    adapter = CctvAdapter()
    assert adapter.can_handle("https://www.bilibili.com/video/BVxxx") is False


def test_registry_selects_cctv_for_cctv_url():
    """测试 6:默认注册表对 tv.cctv.com 的 URL 应选中名为 'cctv' 的适配器。

    使用真实 ``create_default_registry()``,CctvAdapter 优先级 80 高于
    ytdlp 兜底(0);视频号适配器(100)仅匹配 channels.weixin.qq.com,
    不会拦截央视频 URL。
    """
    registry = create_default_registry()
    selected = registry.select("https://tv.cctv.com/2024/01/01/VIDEOxxx.shtml")
    assert selected.name == "cctv"


@patch("universal_video_downloader.platforms.cctv_adapter.YtDlpAdapter")
def test_extract_info_marks_platform_as_cctv(mock_ytdlp_class):
    """测试 7:extract_info 返回的 VideoInfo.platform 应为 'cctv'。

    通过 mock ``YtDlpAdapter`` 避免真实网络请求:ytdlp 返回 platform='ytdlp'
    的 VideoInfo,期望被 CctvAdapter 改写为 'cctv'。
    """
    mock_instance = mock_ytdlp_class.return_value
    mock_instance.extract_info.return_value = VideoInfo(
        url="https://tv.cctv.com/2024/01/01/VIDEOxxx.shtml",
        title="测试央视频",
        platform="ytdlp",
    )

    adapter = CctvAdapter()
    info = adapter.extract_info("https://tv.cctv.com/2024/01/01/VIDEOxxx.shtml")

    # platform 被改写为 cctv
    assert info.platform == "cctv"
    # 其余字段保持 ytdlp 返回的内容
    assert info.title == "测试央视频"
    # 确实委托了 ytdlp 的 extract_info
    mock_instance.extract_info.assert_called_once()
