"""多线程分块下载器。

移植自原 Go 项目的 `MultiThreadingDownload` 与 `calculate_chunks`。通过
``concurrent.futures.ThreadPoolExecutor`` 并发下载各分块,每个分块以 HTTP
Range 请求获取,写入临时文件后合并为最终产物。

使用标准库 ``urllib.request`` 发起请求,避免引入额外依赖(requests)。
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from ...core.base import ProgressCallback
from ...core.models import DownloadResult

logger = logging.getLogger(__name__)

# 默认每个分块的最小大小(字节),避免分块过小导致请求开销过大
_MIN_CHUNK_SIZE = 1024 * 1024  # 1 MiB


def calculate_chunks(total_size: int, chunk_count: int) -> list[tuple[int, int]]:
    """计算分块范围。

    将 ``total_size`` 划分为 ``chunk_count`` 个尽量均匀的区间,返回
    ``[(start, end), ...]`` 列表,其中 ``end`` 为闭区间上界(即最后一个
    字节的偏移),用于 HTTP ``Range: bytes=start-end`` 请求头。

    Args:
        total_size: 文件总大小(字节)。
        chunk_count: 期望分块数。若文件过小,实际分块数可能少于该值。

    Returns:
        分块范围列表,每个元素为 ``(start_offset, end_offset)`` 闭区间。
        若 ``total_size <= 0`` 返回空列表。
    """
    if total_size <= 0 or chunk_count <= 0:
        return []

    # 限制实际分块数,避免每个分块过小
    max_chunks = max(1, total_size // _MIN_CHUNK_SIZE)
    actual_count = min(chunk_count, max_chunks)
    if actual_count < 1:
        actual_count = 1

    chunk_size = total_size // actual_count
    ranges: list[tuple[int, int]] = []
    for i in range(actual_count):
        start = i * chunk_size
        # 最后一个分块负责剩余所有字节
        if i == actual_count - 1:
            end = total_size - 1
        else:
            end = start + chunk_size - 1
        ranges.append((start, end))

    return ranges


class MultiThreadDownloader:
    """多线程分块下载器。

    用 ``ThreadPoolExecutor`` 并发下载各分块到临时文件,完成后合并为最终
    文件。通过 :class:`threading.Event` 支持取消,通过 callback 上报进度
    (每秒一次)。

    Attributes:
        workers: 并发线程数。
    """

    def __init__(self, workers: int = 4) -> None:
        self.workers = max(1, workers)
        # 取消标志:task_id -> Event
        self._cancel_events: dict[str, threading.Event] = {}
        # 进度上报限频时间戳:task_id -> 上次上报时间
        self._last_report_time: dict[str, float] = {}

    def download(
        self,
        url: str,
        output_path: Path,
        callback: Optional[ProgressCallback] = None,
        task_id: str = "",
    ) -> DownloadResult:
        """下载指定 URL 到 output_path。

        Args:
            url: 视频 URL。
            output_path: 最终输出文件路径。
            callback: 进度回调,每秒上报一次。
            task_id: 任务 ID,用于取消。

        Returns:
            DownloadResult,success 为 True 表示成功。
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        cancel_event = threading.Event()
        if task_id:
            self._cancel_events[task_id] = cancel_event

        start_time = time.time()

        try:
            # 1. 获取文件总大小
            total_size = self._get_content_length(url)
            if total_size <= 0:
                # 不支持 Range 或未知大小,退化为单线程下载
                logger.info("无法获取文件大小或服务器不支持 Range,使用单线程下载")
                return self._single_thread_download(
                    url, output_path, callback, task_id, cancel_event, start_time
                )

            # 2. 计算分块
            chunks = calculate_chunks(total_size, self.workers)
            logger.info(
                "文件大小 %d 字节,分为 %d 块下载", total_size, len(chunks)
            )

            # 3. 并发下载各分块到临时文件
            temp_dir = output_path.parent / f".{output_path.name}.parts"
            temp_dir.mkdir(exist_ok=True)

            downloaded_bytes = [0] * len(chunks)
            chunk_files: list[Optional[Path]] = [None] * len(chunks)
            errors: list[Optional[str]] = [None] * len(chunks)

            def download_chunk(index: int, start: int, end: int) -> None:
                if cancel_event.is_set():
                    return
                chunk_path = temp_dir / f"part_{index}"
                try:
                    size = self._download_range(
                        url, start, end, chunk_path, cancel_event,
                        progress_cb=lambda n: self._update_progress(
                            downloaded_bytes, index, n, total_size,
                            callback, task_id, start_time, cancel_event,
                        ),
                    )
                    downloaded_bytes[index] = size
                    chunk_files[index] = chunk_path
                except Exception as e:
                    errors[index] = str(e)
                    logger.error("分块 %d 下载失败: %s", index, e)

            with ThreadPoolExecutor(max_workers=self.workers) as executor:
                futures = {
                    executor.submit(download_chunk, i, s, e): i
                    for i, (s, e) in enumerate(chunks)
                }
                for future in as_completed(futures):
                    future.result()  # 触发异常传播

            # 检查取消
            if cancel_event.is_set():
                self._cleanup_temp(temp_dir)
                return DownloadResult(
                    success=False,
                    error="下载已取消",
                    task_id=task_id,
                    duration_seconds=time.time() - start_time,
                )

            # 检查错误
            failed = [i for i, e in enumerate(errors) if e is not None]
            if failed:
                self._cleanup_temp(temp_dir)
                return DownloadResult(
                    success=False,
                    error=f"分块 {failed} 下载失败",
                    task_id=task_id,
                    duration_seconds=time.time() - start_time,
                )

            # 4. 合并分块文件
            with open(output_path, "wb") as out_f:
                for i, chunk_path in enumerate(chunk_files):
                    if chunk_path and chunk_path.exists():
                        with open(chunk_path, "rb") as in_f:
                            while True:
                                data = in_f.read(1024 * 1024)
                                if not data:
                                    break
                                out_f.write(data)

            self._cleanup_temp(temp_dir)

            elapsed = time.time() - start_time
            if callback:
                callback.on_complete(task_id, str(output_path))

            return DownloadResult(
                success=True,
                file_path=str(output_path),
                task_id=task_id,
                duration_seconds=elapsed,
            )

        except Exception as e:
            logger.error("下载失败: %s", e)
            return DownloadResult(
                success=False,
                error=str(e),
                task_id=task_id,
                duration_seconds=time.time() - start_time,
            )
        finally:
            if task_id:
                self._cancel_events.pop(task_id, None)

    def cancel(self, task_id: str) -> bool:
        """取消指定任务的下载。

        Args:
            task_id: 要取消的任务 ID。

        Returns:
            True 表示已设置取消标志。
        """
        event = self._cancel_events.get(task_id)
        if event:
            event.set()
            return True
        return False

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    def _get_content_length(self, url: str) -> int:
        """通过 HEAD 请求获取文件总大小。

        返回 0 表示服务器不支持 Range 或无法获取大小。
        """
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=30) as resp:
                # 检查是否支持 Range
                accept_ranges = resp.headers.get("Accept-Ranges", "")
                content_length = resp.headers.get("Content-Length", "")
                if content_length:
                    size = int(content_length)
                    # 即使服务器没显式声明 Accept-Ranges,只要有 Content-Length 就尝试分块
                    if accept_ranges.lower() == "bytes" or size > 0:
                        return size
                return 0
        except Exception as e:
            logger.debug("HEAD 请求失败(%s),尝试 Range 探测", e)
            # 退化:发一个 Range: bytes=0-0 探测是否支持
            try:
                req = urllib.request.Request(url)
                req.add_header("Range", "bytes=0-0")
                with urllib.request.urlopen(req, timeout=30) as resp:
                    content_range = resp.headers.get("Content-Range", "")
                    # 格式:bytes 0-0/12345
                    if "/" in content_range:
                        total = content_range.rsplit("/", 1)[-1]
                        return int(total)
                    return 0
            except Exception:
                return 0

    def _download_range(
        self,
        url: str,
        start: int,
        end: int,
        output_path: Path,
        cancel_event: threading.Event,
        progress_cb=None,
    ) -> int:
        """下载指定字节范围到文件。

        Args:
            url: 视频 URL。
            start: 起始字节偏移(含)。
            end: 结束字节偏移(含)。
            output_path: 分块临时文件路径。
            cancel_event: 取消事件。
            progress_cb: 进度回调,参数为已下载字节数。

        Returns:
            实际下载的字节数。
        """
        req = urllib.request.Request(url)
        req.add_header("Range", f"bytes={start}-{end}")
        req.add_header("User-Agent", "UniversalVideoDownloader/1.0")

        downloaded = 0
        with urllib.request.urlopen(req, timeout=60) as resp:
            with open(output_path, "wb") as f:
                while True:
                    if cancel_event.is_set():
                        break
                    chunk = resp.read(64 * 1024)  # 64 KiB 缓冲
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded)
        return downloaded

    def _update_progress(
        self,
        downloaded_bytes: list[int],
        index: int,
        current: int,
        total_size: int,
        callback: Optional[ProgressCallback],
        task_id: str,
        start_time: float,
        cancel_event: threading.Event,
    ) -> None:
        """更新分块进度并按限频(每秒一次)上报。

        使用闭包共享的 ``last_report_time`` 避免频繁回调。
        """
        downloaded_bytes[index] = current
        if callback is None:
            return

        # 每秒最多上报一次
        now = time.time()
        last = self._last_report_time.get(task_id, 0.0)
        if now - last < 1.0:
            return
        self._last_report_time[task_id] = now

        total_downloaded = sum(downloaded_bytes)
        percent = (total_downloaded / total_size * 100) if total_size > 0 else 0.0
        elapsed = now - start_time
        speed = total_downloaded / elapsed if elapsed > 0 else 0.0
        remaining = total_size - total_downloaded
        eta = remaining / speed if speed > 0 else 0.0

        callback.on_progress(task_id, percent, speed, eta)

    def _single_thread_download(
        self,
        url: str,
        output_path: Path,
        callback: Optional[ProgressCallback],
        task_id: str,
        cancel_event: threading.Event,
        start_time: float,
    ) -> DownloadResult:
        """不支持 Range 时的单线程降级下载。"""
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "UniversalVideoDownloader/1.0")

        downloaded = 0
        with urllib.request.urlopen(req, timeout=60) as resp:
            total_size = int(resp.headers.get("Content-Length", 0))
            with open(output_path, "wb") as f:
                last_report = 0.0
                while True:
                    if cancel_event.is_set():
                        return DownloadResult(
                            success=False,
                            error="下载已取消",
                            task_id=task_id,
                            duration_seconds=time.time() - start_time,
                        )
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    # 每秒上报一次进度
                    now = time.time()
                    if callback and now - last_report >= 1.0:
                        last_report = now
                        percent = (
                            downloaded / total_size * 100 if total_size > 0 else 0.0
                        )
                        elapsed = now - start_time
                        speed = downloaded / elapsed if elapsed > 0 else 0.0
                        remaining = total_size - downloaded
                        eta = remaining / speed if speed > 0 else 0.0
                        callback.on_progress(task_id, percent, speed, eta)

        if callback:
            callback.on_complete(task_id, str(output_path))

        return DownloadResult(
            success=True,
            file_path=str(output_path),
            task_id=task_id,
            duration_seconds=time.time() - start_time,
        )

    @staticmethod
    def _cleanup_temp(temp_dir: Path) -> None:
        """清理临时分块目录。"""
        try:
            if temp_dir.exists():
                for f in temp_dir.iterdir():
                    f.unlink(missing_ok=True)
                temp_dir.rmdir()
        except OSError as e:
            logger.warning("清理临时目录失败: %s", e)
