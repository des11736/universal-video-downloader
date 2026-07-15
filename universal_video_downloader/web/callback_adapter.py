"""Web 进度回调适配器。

实现 ``ProgressCallback`` 协议,将适配器在线程池中产生的进度事件通过
``call_soon_threadsafe`` 投递回事件循环所在的 ``asyncio.Queue``,供
WebSocket 广播给前端订阅者。
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional


class WebProgressCallback:
    """ProgressCallback 实现,将进度事件推入 asyncio.Queue 供 WebSocket 广播。

    适配器的 ``download`` 方法通过 ``asyncio.to_thread`` 在线程池中执行,
    因此 ``on_progress`` / ``on_complete`` / ``on_error`` 也会在线程池线程
    中被调用。直接向 ``asyncio.Queue`` 写入非线程安全,必须用
    ``loop.call_soon_threadsafe`` 将写操作调度回事件循环所在线程。

    同时将进度/状态写入 ``_task_statuses`` 字典,使 ``GET /api/tasks`` 能返回
    实时进度(修复刷新页面后进度丢失的问题)。
    """

    def __init__(
        self,
        task_id: str,
        queue: asyncio.Queue,
        loop: asyncio.AbstractEventLoop,
        task_statuses: Optional[dict] = None,
    ) -> None:
        self._task_id = task_id
        self._queue = queue
        self._loop = loop
        self._task_statuses = task_statuses

    def _update_status(self, **kwargs: Any) -> None:
        """线程安全地更新 _task_statuses(如果存在)。"""
        if self._task_statuses is None:
            return
        def _do_update():
            self._task_statuses.get(self._task_id, {}).update(kwargs)
        self._loop.call_soon_threadsafe(_do_update)

    def on_progress(
        self, task_id: str, percent: float, speed: float = 0.0, eta: float = 0.0
    ) -> None:
        """下载进度更新:构造 progress 事件并投递到事件循环,同时更新状态。"""
        event: dict[str, Any] = {
            "type": "progress",
            "task_id": task_id,
            "percent": percent,
            "speed": speed,
            "eta": eta,
        }
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
        self._update_status(percent=percent, status="RUNNING")

    def on_complete(self, task_id: str, file_path: str) -> None:
        """下载完成:构造 complete 事件并投递到事件循环,同时更新状态。"""
        event: dict[str, Any] = {
            "type": "complete",
            "task_id": task_id,
            "file_path": file_path,
        }
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
        self._update_status(percent=100.0, status="DONE", file_path=file_path)

    def on_error(self, task_id: str, error_message: str) -> None:
        """下载出错:构造 error 事件并投递到事件循环,同时更新状态。"""
        event: dict[str, Any] = {
            "type": "error",
            "task_id": task_id,
            "error": error_message,
        }
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
        self._update_status(status="FAILED", error=error_message)
