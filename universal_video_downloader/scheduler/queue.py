"""基于 asyncio 的任务队列。

提供 ``TaskQueue`` 用于限流并发下载任务,以及 ``TaskStatus`` 模型记录
每个任务的生命周期状态(PENDING/RUNNING/DONE/FAILED)。任务通过信号量
限制最大并发数,状态变更在异步锁保护下写入内部字典。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, ClassVar, Optional

from pydantic import BaseModel, Field


class TaskStatus(BaseModel):
    """任务状态模型。

    记录单个下载任务的生命周期信息,供 CLI / Web 层查询任务进度与结果。
    状态流转:PENDING → RUNNING → DONE / FAILED。
    """

    # 状态常量(非 pydantic 字段,用 ClassVar 标记避免被识别为模型字段)
    PENDING: ClassVar[str] = "PENDING"
    RUNNING: ClassVar[str] = "RUNNING"
    DONE: ClassVar[str] = "DONE"
    FAILED: ClassVar[str] = "FAILED"

    task_id: str
    # 状态:PENDING(等待信号量)、RUNNING(执行中)、DONE(成功)、FAILED(失败)
    status: str
    error: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    file_path: str = ""


class TaskQueue:
    """基于 asyncio 信号量的并发限流任务队列。

    通过 ``asyncio.Semaphore`` 限制同时执行的最大任务数。每个任务的状态
    记录在 ``_tasks`` 字典中,由 ``asyncio.Lock`` 保护写入。
    """

    def __init__(self, concurrency: int = 3) -> None:
        # 并发信号量
        self._sem = asyncio.Semaphore(concurrency)
        # task_id -> TaskStatus
        self._tasks: dict[str, TaskStatus] = {}
        # 保护 _tasks 写入的异步锁
        self._lock = asyncio.Lock()

    async def submit(self, task_id: str, coro_factory: Any) -> Any:
        """提交任务,coro_factory 是无参函数返回 awaitable。

        任务先以 PENDING 状态入队,获取信号量后转为 RUNNING 执行。
        执行成功置 DONE,异常置 FAILED 并重新抛出异常。
        """
        # 入队即记录 PENDING 状态(等待信号量)
        await self._set_status(task_id, TaskStatus.PENDING)
        async with self._sem:
            await self._set_status(task_id, TaskStatus.RUNNING)
            try:
                result = await coro_factory()
                await self._set_status(task_id, TaskStatus.DONE)
                return result
            except Exception as e:
                await self._set_status(task_id, TaskStatus.FAILED, error=str(e))
                raise

    async def _set_status(
        self,
        task_id: str,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        """更新任务状态(加锁保护)。

        首次记录时创建新的 ``TaskStatus``;已存在则更新状态字段。
        进入 DONE / FAILED 时记录 ``finished_at`` 时间戳。
        """
        async with self._lock:
            existing = self._tasks.get(task_id)
            if existing is None:
                # 首次记录:创建新状态
                self._tasks[task_id] = TaskStatus(
                    task_id=task_id,
                    status=status,
                    error=error or "",
                )
            else:
                existing.status = status
                if error is not None:
                    existing.error = error
                # 完成状态记录完成时间
                if status in (TaskStatus.DONE, TaskStatus.FAILED):
                    existing.finished_at = datetime.utcnow()

    def get_status(self, task_id: str) -> Optional[TaskStatus]:
        """返回指定任务的状态,不存在返回 None。"""
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[TaskStatus]:
        """返回全部任务状态列表。"""
        return list(self._tasks.values())
