"""下载调度器。

将适配器注册表与任务队列组合,提供同步与异步两种调度入口:
- ``dispatch_sync``:同步选择适配器并执行下载,适合 CLI 直接调用;
- ``dispatch_async``:异步调度,经 TaskQueue 限流,适配器 download 在线程池中执行。
"""

from __future__ import annotations

import asyncio
from typing import Optional
from uuid import uuid4

from ..core.base import ProgressCallback
from ..core.config import AppConfig
from ..core.models import DownloadOptions, DownloadResult
from .queue import TaskQueue
from .registry import AdapterRegistry, create_default_registry


class Dispatcher:
    """下载调度器,组合注册表与任务队列。

    同步调度直接调用适配器 ``download``;异步调度经 ``TaskQueue`` 限流,
    并通过 ``asyncio.to_thread`` 在线程池中执行适配器的同步 ``download`` 方法。
    """

    def __init__(self, registry: AdapterRegistry, task_queue: TaskQueue) -> None:
        self._registry = registry
        self._queue = task_queue

    def dispatch_sync(
        self,
        url: str,
        options: DownloadOptions,
        callback: Optional[ProgressCallback] = None,
        task_id: str = "",
    ) -> DownloadResult:
        """同步调度:选择适配器并执行 download。适合 CLI 直接调用。"""
        adapter = self._registry.select(url)
        if not task_id:
            task_id = uuid4().hex
        return adapter.download(url, options, callback, task_id)

    async def dispatch_async(
        self,
        url: str,
        options: DownloadOptions,
        callback: Optional[ProgressCallback] = None,
        task_id: str = "",
    ) -> DownloadResult:
        """异步调度:经 TaskQueue 限流,适配器 download 在线程池中跑。"""
        if not task_id:
            task_id = uuid4().hex
        adapter = self._registry.select(url)

        async def _run() -> DownloadResult:
            # 适配器 download 是同步方法,通过 to_thread 放入线程池执行
            return await asyncio.to_thread(
                adapter.download, url, options, callback, task_id
            )

        return await self._queue.submit(task_id, _run)


def create_dispatcher(config: AppConfig) -> Dispatcher:
    """工厂函数:基于配置创建 Dispatcher。

    创建默认注册表与任务队列(并发数取自 ``config.download.concurrency``),
    返回组合好的 ``Dispatcher``。
    """
    registry = create_default_registry()
    task_queue = TaskQueue(concurrency=config.download.concurrency)
    return Dispatcher(registry, task_queue)
