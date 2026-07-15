"""YouTube 真实下载端到端测试。

用 YtDlpAdapter 真实下载一个小视频(Rick Astley - Never Gonna Give You Up),
验证完整下载流程:适配器下载 -> 进度回调 -> 文件落盘。
通过 skip 条件避免网络不稳定或 yt_dlp 缺失时 CI 失败。
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest


def _yt_dlp_available() -> bool:
    """检查 yt_dlp 是否可导入。"""
    try:
        import yt_dlp  # noqa: F401

        return True
    except ImportError:
        return False


def _network_available() -> bool:
    """检查网络连通性(能否解析 www.youtube.com)。"""
    try:
        socket.gethostbyname("www.youtube.com")
        return True
    except Exception:
        return False


# 预计算 skip 条件,避免在 skipif 中重复调用
_YT_DLP_OK = _yt_dlp_available()
_NETWORK_OK = _network_available()

# skip 条件:yt_dlp 不可导入 或 网络不通时跳过,避免 CI 失败
# 同时标记为 network 测试,便于按标记过滤(如 pytest -m "not network")
pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        not (_YT_DLP_OK and _NETWORK_OK),
        reason="yt_dlp 不可用或网络不可用,跳过真实下载测试",
    ),
]


class MockProgressCallback:
    """收集进度事件的 mock 回调,用于断言回调被正确调用。"""

    def __init__(self) -> None:
        self.progress_events: list[tuple] = []
        self.complete_events: list[tuple] = []
        self.error_events: list[tuple] = []

    def on_progress(
        self, task_id: str, percent: float, speed: float = 0.0, eta: float = 0.0
    ) -> None:
        """记录进度事件。"""
        self.progress_events.append((task_id, percent, speed, eta))

    def on_complete(self, task_id: str, file_path: str) -> None:
        """记录完成事件。"""
        self.complete_events.append((task_id, file_path))

    def on_error(self, task_id: str, error_message: str) -> None:
        """记录错误事件。"""
        self.error_events.append((task_id, error_message))


def test_youtube_real_download(tmp_path: Path) -> None:
    """端到端:用 YtDlpAdapter 真实下载 YouTube 视频(Rick Astley)。

    使用最低清晰度(--format worst)加速下载,验证:
    - 下载结果 success 为 True
    - file_path 非空
    - 文件存在且大于 0 字节
    - 回调至少收到 1 次 on_progress 与 1 次 on_complete
    """
    from universal_video_downloader.core.models import DownloadOptions
    from universal_video_downloader.platforms.ytdlp_adapter import YtDlpAdapter

    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    adapter = YtDlpAdapter()
    options = DownloadOptions(
        output_dir=str(tmp_path),
        filename_template="test_%(id)s.%(ext)s",
        extra_args=["--playlist-items", "1", "--format", "worst"],
    )
    callback = MockProgressCallback()
    task_id = "e2e-youtube-test"

    result = adapter.download(url, options, callback, task_id)

    # 断言下载成功
    assert result.success is True, f"下载失败: {result.error}"
    # 断言文件路径非空
    assert result.file_path, "file_path 为空"
    # 断言文件存在且大于 0 字节
    file_path = Path(result.file_path)
    assert file_path.exists(), f"文件不存在: {file_path}"
    assert file_path.stat().st_size > 0, "文件大小为 0 字节"
    # 断言回调至少收到 1 次 on_progress 与 1 次 on_complete
    assert len(callback.progress_events) >= 1, "未收到 on_progress 回调"
    assert len(callback.complete_events) >= 1, "未收到 on_complete 回调"
