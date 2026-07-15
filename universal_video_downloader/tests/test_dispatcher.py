"""调度器模块的单元测试。

覆盖适配器注册表优先级匹配、任务队列并发限流、同步调度错误处理等场景。
使用 stdlib ``unittest.mock`` 模拟适配器与 yt-dlp,不引入新依赖。
"""

from __future__ import annotations

import asyncio
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from universal_video_downloader.core.base import PlatformDownloader
from universal_video_downloader.core.models import (
    DownloadOptions,
    DownloadResult,
    VideoInfo,
)
from universal_video_downloader.scheduler.dispatcher import Dispatcher
from universal_video_downloader.scheduler.queue import TaskQueue, TaskStatus
from universal_video_downloader.scheduler.registry import AdapterRegistry


class MockAdapter(PlatformDownloader):
    """用于测试的 mock 适配器,可控制 can_handle 与 download 的返回值。"""

    def __init__(
        self,
        can_handle_result: bool = True,
        download_result: Optional[DownloadResult] = None,
        name: str = "mock",
    ) -> None:
        self.name = name
        self._can_handle_result = can_handle_result
        self._download_result = download_result

    def can_handle(self, url: str) -> bool:
        return self._can_handle_result

    def extract_info(self, url: str) -> VideoInfo:
        return VideoInfo(url=url, platform=self.name)

    def download(
        self,
        url: str,
        options: DownloadOptions,
        callback=None,
        task_id: str = "",
    ) -> DownloadResult:
        if self._download_result is not None:
            return self._download_result
        return DownloadResult(success=True, file_path="/tmp/mock.mp4", task_id=task_id)


def test_registry_select_prefers_high_priority():
    """测试 1:registry.select 优先返回高优先级且 can_handle=True 的适配器。"""
    registry = AdapterRegistry()
    low = MockAdapter(can_handle_result=True, name="low")
    high = MockAdapter(can_handle_result=True, name="high")
    registry.register(low, priority=0)
    registry.register(high, priority=100)

    selected = registry.select("https://example.com/video")
    # 高优先级的 high 应被选中
    assert selected is high
    assert selected.name == "high"


def test_registry_fallback_to_ytdlp():
    """测试 2:所有 can_handle=False 时降级到 ytdlp。"""
    registry = AdapterRegistry()
    # 注册一个 can_handle=False 的 mock 适配器(高优先级)
    mock = MockAdapter(can_handle_result=False, name="mock")
    # 注册一个假的 ytdlp 适配器(can_handle=False,但 name="ytdlp")
    fake_ytdlp = MockAdapter(can_handle_result=False, name="ytdlp")
    registry.register(mock, priority=100)
    registry.register(fake_ytdlp, priority=0)

    selected = registry.select("https://example.com/video")
    # 全部 can_handle=False 时应回退到 ytdlp
    assert selected is fake_ytdlp
    assert selected.name == "ytdlp"


def test_task_queue_concurrency():
    """测试 3:TaskQueue 在 concurrency=2 下并发提交 5 个任务,验证全部完成、状态正确。"""
    queue = TaskQueue(concurrency=2)
    task_ids = [f"task-{i}" for i in range(5)]

    async def run_all():
        async def make_task(tid: str):
            async def _coro():
                await asyncio.sleep(0.1)
                return tid
            return await queue.submit(tid, _coro)

        # 并发提交 5 个任务,由信号量限流到 2 个同时执行
        results = await asyncio.gather(*(make_task(tid) for tid in task_ids))
        return results

    results = asyncio.run(run_all())

    # 全部任务完成,结果与 task_ids 一一对应
    assert results == task_ids
    # 全部状态为 DONE,且 finished_at 已记录
    for tid in task_ids:
        status = queue.get_status(tid)
        assert status is not None
        assert status.status == TaskStatus.DONE
        assert status.finished_at is not None
    # list_tasks 返回全部 5 个任务
    assert len(queue.list_tasks()) == 5


def test_dispatch_sync_returns_error_on_failure():
    """测试 4:dispatch_sync 用真实 YtDlpAdapter,通过 mock 使下载失败,验证返回包含 error。"""
    # yt_dlp 是核心依赖,但若环境缺失则跳过该测试
    pytest.importorskip("yt_dlp")
    from universal_video_downloader.platforms.ytdlp_adapter import YtDlpAdapter
    from yt_dlp.utils import DownloadError

    registry = AdapterRegistry()
    adapter = YtDlpAdapter()
    registry.register(adapter, priority=0)

    dispatcher = Dispatcher(registry, TaskQueue(concurrency=1))
    options = DownloadOptions(output_dir="./downloads")

    # mock yt_dlp.YoutubeDL 使其 download 抛出 DownloadError
    with patch(
        "universal_video_downloader.platforms.ytdlp_adapter.yt_dlp.YoutubeDL"
    ) as mock_ydl:
        mock_instance = MagicMock()
        mock_instance.download.side_effect = DownloadError("invalid url")
        mock_ydl.return_value = mock_instance

        result = dispatcher.dispatch_sync(
            "https://invalid.example.com/video", options, task_id="test-task"
        )

    # 验证返回失败结果且包含 error
    assert isinstance(result, DownloadResult)
    assert result.success is False
    assert result.error != ""
    assert result.task_id == "test-task"
