"""抽象基类与协议定义。

定义所有平台适配器需要实现的统一接口 `PlatformDownloader`,以及用于
进度上报的 `ProgressCallback` 协议。CLI / Web 层通过该协议接收下载进度。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Protocol, runtime_checkable

from .models import DownloadOptions, DownloadResult, VideoInfo


@runtime_checkable
class ProgressCallback(Protocol):
    """进度回调协议。

    适配器通过该协议上报进度,CLI / Web 各自实现。使用 `runtime_checkable`
    装饰后,可通过 `isinstance(obj, ProgressCallback)` 进行结构化类型检查。
    """

    def on_progress(
        self, task_id: str, percent: float, speed: float = 0.0, eta: float = 0.0
    ) -> None:
        """下载进度更新回调。"""
        ...

    def on_complete(self, task_id: str, file_path: str) -> None:
        """下载完成回调。"""
        ...

    def on_error(self, task_id: str, error_message: str) -> None:
        """下载出错回调。"""
        ...


class PlatformDownloader(ABC):
    """所有平台适配器的抽象基类。

    子类需覆盖 `name` 属性作为唯一标识,并实现 `can_handle`、`extract_info`、
    `download` 三个抽象方法。可选重写 `cancel` 以支持取消下载。
    """

    name: str = "base"  # 适配器唯一标识,子类覆盖

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """判断该适配器是否能处理给定 URL。"""
        raise NotImplementedError

    @abstractmethod
    def extract_info(self, url: str) -> VideoInfo:
        """提取视频信息,不下载。"""
        raise NotImplementedError

    @abstractmethod
    def download(
        self,
        url: str,
        options: DownloadOptions,
        callback: Optional[ProgressCallback] = None,
        task_id: str = "",
    ) -> DownloadResult:
        """执行下载,通过 callback 上报进度。"""
        raise NotImplementedError

    def cancel(self, task_id: str) -> bool:
        """取消下载,默认返回 False(不支持取消)。子类可重写。"""
        return False
