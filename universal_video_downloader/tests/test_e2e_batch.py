"""批量下载端到端测试。

用 mock 适配器替代真实下载(避免网络依赖),验证 TaskQueue 的并发限流
与任务状态管理。3 个混合平台 URL(youtube/bilibili/wechat)并发提交,
验证全部完成与并发限制生效。
"""

from __future__ import annotations

import asyncio
import time

from universal_video_downloader.core.base import PlatformDownloader
from universal_video_downloader.core.models import (
    DownloadOptions,
    DownloadResult,
    VideoInfo,
)
from universal_video_downloader.scheduler.queue import TaskQueue, TaskStatus


class MockAdapter(PlatformDownloader):
    """mock 适配器:download 时 sleep 0.2s 后返回成功,避免网络依赖。"""

    def __init__(self, name: str = "mock") -> None:
        self.name = name

    def can_handle(self, url: str) -> bool:
        return True

    def extract_info(self, url: str) -> VideoInfo:
        return VideoInfo(url=url, platform=self.name)

    def download(
        self,
        url: str,
        options: DownloadOptions,
        callback=None,
        task_id: str = "",
    ) -> DownloadResult:
        # 模拟下载耗时
        time.sleep(0.2)
        return DownloadResult(
            success=True,
            file_path=f"/tmp/{task_id}.mp4",
            task_id=task_id,
        )


def test_batch_download_mixed_platforms() -> None:
    """端到端:3 个混合平台 URL 批量下载,验证全部完成。

    用 TaskQueue(concurrency=2) 提交 3 个任务,
    asyncio.run + asyncio.gather 并发执行。
    """
    # 3 个混合平台 URL(分别假装是 youtube/bilibili/wechat)
    urls = [
        "https://www.youtube.com/watch?v=test1",
        "https://www.bilibili.com/video/BV1test2",
        "https://channels.weixin.qq.com/test3",
    ]
    adapter = MockAdapter()
    options = DownloadOptions(output_dir="./downloads")
    task_queue = TaskQueue(concurrency=2)

    async def run_batch():
        async def download_one(url: str, idx: int):
            task_id = f"task-{idx}"

            # coro_factory:无参函数返回 awaitable
            def _coro_factory():
                return asyncio.to_thread(
                    adapter.download, url, options, None, task_id
                )

            return await task_queue.submit(task_id, _coro_factory)

        return await asyncio.gather(
            *(download_one(url, i) for i, url in enumerate(urls))
        )

    results = asyncio.run(run_batch())

    # 断言:3 个任务全部成功
    assert len(results) == 3
    for r in results:
        assert r.success is True
    # 断言:全部任务状态为 DONE
    for status in task_queue.list_tasks():
        assert status.status == TaskStatus.DONE
    # 断言:list_tasks 长度 == 3
    assert len(task_queue.list_tasks()) == 3


def test_batch_concurrency_limit() -> None:
    """验证并发限制:concurrency=2 时 3 个任务(每个 sleep 0.2s)总耗时 > 0.4s。

    若 semaphore 未生效(3 个任务同时跑),总耗时约 0.2s;
    semaphore 生效时(最多 2 个同时),总耗时约 0.4s。
    """
    adapter = MockAdapter()
    options = DownloadOptions(output_dir="./downloads")
    task_queue = TaskQueue(concurrency=2)

    async def run_batch():
        async def download_one(idx: int):
            task_id = f"concur-task-{idx}"

            def _coro_factory():
                return asyncio.to_thread(
                    adapter.download,
                    f"https://example.com/{idx}",
                    options,
                    None,
                    task_id,
                )

            return await task_queue.submit(task_id, _coro_factory)

        return await asyncio.gather(*(download_one(i) for i in range(3)))

    start = time.monotonic()
    asyncio.run(run_batch())
    elapsed = time.monotonic() - start

    # concurrency=2,每个任务 0.2s,3 个任务至少需要 2 轮 = 0.4s
    assert elapsed > 0.4, f"并发限制未生效,总耗时仅 {elapsed:.3f}s(应 > 0.4s)"
