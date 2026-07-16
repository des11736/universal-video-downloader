"""yt-dlp 通用适配器。

作为兜底适配器,使用 yt-dlp 库处理任意 yt-dlp 支持的 URL。负责元信息提取、
带进度回调的下载、取消支持,以及与 `PlatformDownloader` 抽象基类的对接。
在适配器链中应放在最后,确保任何未被专用适配器匹配的 URL 都能由本适配器兜底。
"""

from __future__ import annotations

import os
import sys
import time
from typing import Optional

import typer
import yt_dlp
from yt_dlp.utils import DownloadError

from ..core.base import PlatformDownloader, ProgressCallback
from ..core.models import (
    DownloadOptions,
    DownloadResult,
    VideoFormat,
    VideoInfo,
)


_BROWSER_PREVIEW_EXTENSIONS = {"mp4", "webm"}


def _is_browser_playable_format(item: dict) -> bool:
    """仅保留主流浏览器可直接播放的音视频编解码组合。"""
    ext = str(item.get("ext") or "").lower()
    if ext not in _BROWSER_PREVIEW_EXTENSIONS:
        return False

    vcodec = str(item.get("vcodec") or "").lower()
    acodec = str(item.get("acodec") or "").lower()
    if ext == "mp4":
        return vcodec.startswith(("avc", "h264")) and acodec.startswith(
            ("mp4a", "aac")
        )
    return vcodec.startswith(("vp8", "vp08", "vp9", "vp09")) and acodec.startswith(
        ("opus", "vorbis")
    )


def _select_preview_url(formats: list[dict]) -> str:
    """选择带音视频且可被浏览器直接加载的渐进式媒体地址。"""
    progressive = [
        item
        for item in formats
        if isinstance(item.get("url"), str)
        and item["url"].startswith(("http://", "https://"))
        and item.get("protocol") in {"http", "https"}
        and _is_browser_playable_format(item)
    ]
    if not progressive:
        return ""
    return str(max(progressive, key=lambda item: item.get("height") or 0)["url"])


class YtDlpAdapter(PlatformDownloader):
    """基于 yt-dlp 的通用兜底适配器。

    任何 URL 都会尝试通过 yt-dlp 处理,因此在适配器链中应放在最后作为兜底。
    支持:
    - 元信息提取(`extract_info`),失败时返回空信息而不抛错;
    - 带进度回调的下载(`download`),通过 `ProgressCallback` 上报进度/完成/错误;
    - 按 task_id 取消正在进行的下载(`cancel`)。
    """

    name: str = "ytdlp"

    def __init__(self) -> None:
        # 按 task_id 跟踪取消标志,供 progress_hooks 闭包检查
        self._cancelled: dict[str, bool] = {}

    def can_handle(self, url: str) -> bool:
        """兜底适配器:始终返回 True,任何 URL 都尝试处理。"""
        return True

    def extract_info(
        self,
        url: str,
        cookies_file: Optional[str] = None,
        cookies_from_browser: Optional[str] = None,
    ) -> VideoInfo:
        """提取视频元信息(不下载)。

        可选传入 cookies 参数,以查询需要登录态的会员清晰度列表。
        通过 yt-dlp 的 `extract_info(url, download=False)` 获取视频信息并映射
        到 `VideoInfo`。若返回为播放列表(含 `entries`),取第一个非空条目。
        提取失败时不抛异常,返回一个仅含 url 与 platform 的空 `VideoInfo`,
        由上层决定如何处理。
        """
        # 构建 yt-dlp 选项(查询元信息用)
        ydl_opts: dict = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }
        # cookies 支持:cookiefile 优先,其次从浏览器读取
        if cookies_file:
            ydl_opts["cookiefile"] = cookies_file
        if cookies_from_browser:
            ydl_opts["cookiesfrombrowser"] = (cookies_from_browser,)

        try:
            ydl = yt_dlp.YoutubeDL(ydl_opts)
            info = ydl.extract_info(url, download=False)
        except Exception:
            # 提取失败不抛错,返回空信息让上层决策
            return VideoInfo(url=url, title="", platform="ytdlp")

        if not isinstance(info, dict):
            return VideoInfo(url=url, title="", platform="ytdlp")

        # 播放列表:取第一个非空条目(entries 中可能含被过滤的 None)
        entries = info.get("entries")
        if entries:
            info = next((e for e in entries if e), info)

        # 映射 formats 列表
        raw_formats = info.get("formats", []) or []
        formats: list[VideoFormat] = []
        for f in raw_formats:
            # resolution 优先取 yt-dlp 的 resolution 字段,否则拼 width x height
            resolution = f.get("resolution") or ""
            if not resolution:
                width = f.get("width")
                height = f.get("height")
                if width and height:
                    resolution = f"{width}x{height}"
            # filesize 优先精确值,回退估算值
            filesize = f.get("filesize") or f.get("filesize_approx")
            formats.append(
                VideoFormat(
                    format_id=str(f.get("format_id") or ""),
                    ext=f.get("ext") or "",
                    resolution=resolution,
                    fps=f.get("fps"),
                    vcodec=f.get("vcodec") or "",
                    acodec=f.get("acodec") or "",
                    filesize=filesize,
                    note=f.get("format_note") or "",
                )
            )

        return VideoInfo(
            url=url,
            title=info.get("title") or "",
            duration=info.get("duration"),
            uploader=info.get("uploader") or "",
            platform="ytdlp",
            formats=formats,
            thumbnail=info.get("thumbnail") or "",
            preview_url=_select_preview_url(raw_formats),
            description=info.get("description") or "",
        )

    def download(
        self,
        url: str,
        options: DownloadOptions,
        callback: Optional[ProgressCallback] = None,
        task_id: str = "",
    ) -> DownloadResult:
        """执行下载,通过 callback 上报进度,支持按 task_id 取消。

        构建 yt-dlp 选项(含 outtmpl、进度钩子、quality、extra_args),调用
        `YoutubeDL.download([url])`。成功时回调 `on_complete`,失败时回调
        `on_error` 并返回失败结果。`duration_seconds` 由起止时间差得出。
        取消通过在 progress_hooks 闭包中检测 `self._cancelled` 标志实现,
        被取消时抛出 `RuntimeError("cancelled")` 中断下载。
        """
        # 用于在 progress_hooks 闭包中记录最终文件路径与错误信息(闭包只读外层不可变,
        # 故用 dict 容器承载可变状态)
        file_path_box: dict[str, str] = {"path": ""}
        error_box: dict[str, str] = {"msg": ""}
        # 记录实际选中的 format 描述(从 requested_formats 拼接),供下载完成后输出
        format_desc_box: dict[str, str] = {"desc": ""}

        def _progress_hook(d: dict) -> None:
            """yt-dlp 进度钩子闭包。

            根据 `d["status"]` 分发:downloading 上报进度,finished 记录文件路径,
            error 记录错误。每次回调先检查取消标志,若被取消则抛 RuntimeError
            中断下载流程。
            """
            # 取消检查:被取消则中断下载流程
            if self._cancelled.get(task_id, False):
                raise RuntimeError("cancelled")

            status = d.get("status")
            if status == "downloading":
                if callback is not None:
                    # 计算进度百分比:total_bytes 优先,回退 total_bytes_estimate,再回退 1
                    downloaded = d.get("downloaded_bytes", 0) or 0
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
                    percent = (downloaded / total) * 100 if total else 0.0
                    speed = d.get("speed", 0) or 0
                    eta = d.get("eta", 0) or 0
                    callback.on_progress(task_id, percent, float(speed), float(eta))
            elif status == "finished":
                # 记录下载完成的文件路径,留作返回
                file_path_box["path"] = d.get("filename", "") or ""
                # 从 info_dict.requested_formats 拼接实际选中格式描述(仅首次捕获)
                if not format_desc_box["desc"]:
                    info_dict = d.get("info_dict") or {}
                    requested = info_dict.get("requested_formats") or []
                    parts: list[str] = []
                    for f in requested:
                        note = f.get("format_note") or ""
                        resolution = f.get("resolution") or ""
                        ext = f.get("ext") or ""
                        # 拼接 format_note / resolution / ext 中非空的部分
                        segments = [s for s in (note, resolution, ext) if s]
                        if segments:
                            parts.append(" ".join(segments))
                    if parts:
                        format_desc_box["desc"] = " + ".join(parts)
            elif status == "error":
                # 记录错误信息(实际 on_error 回调在 except 块中统一调用)
                error_box["msg"] = str(d.get("error", "") or "download error")

        def _postprocessor_hook(d: dict) -> None:
            """在后处理完成后记录实际保留的最终文件路径。"""
            if d.get("status") != "finished":
                return
            final_path = (d.get("info_dict") or {}).get("filepath") or ""
            if final_path and os.path.isfile(final_path):
                file_path_box["path"] = final_path

        # 构建 yt-dlp 选项
        opts: dict = {
            "outtmpl": os.path.join(options.output_dir, options.filename_template),
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "overwrites": options.overwrite,
            "progress_hooks": [_progress_hook],
            "postprocessor_hooks": [_postprocessor_hook],
        }

        # 画质选择:
        # - quality 为空或 "best":自动选最佳画质(bestvideo+bestaudio 合并)
        # - quality 是单个 format_id:用 "format_id+bestaudio/best"
        #   既保留用户选的视频流,又自动补最佳音频流(DASH 平台视频流通常无音频)
        # - quality 是复杂表达式(含 + / , 等):直接使用
        #
        # 注意:不设置 format_sort,使用 yt-dlp 默认排序。
        # 之前用的 ["res:4", ...] 会干扰 bestvideo 的选择,
        # 导致 B站 1080p 可用时仍选了 640x360(yt-dlp 默认排序已正确选最高画质)。
        quality = (options.quality or "").strip()
        opts["merge_output_format"] = "mp4"
        if not quality or quality == "best":
            # 自动选最佳画质:优先 H.264/AVC 编码(浏览器原生支持预览),
            # 回退到任意编码的 bestvideo,最后回退到最佳渐进式流。
            # 之前用 "bestvideo+bestaudio/best" 会选到 AV1 编码,
            # 虽然画质相同但浏览器 <video> 可能无法播放(软解卡顿或编解码器缺失)。
            opts["format"] = (
                "bestvideo[vcodec^=avc]+bestaudio/"
                "bestvideo+bestaudio/best"
            )
        elif "+" in quality or "/" in quality or "," in quality:
            # 复杂格式表达式(如 "137+140" 或 "bestvideo+bestaudio"),直接使用
            opts["format"] = quality
        else:
            # 单个 format_id:补最佳音频流,确保下载的视频有声音
            opts["format"] = quality + "+bestaudio/best"

        # cookies 支持:cookiefile 优先,其次从浏览器读取
        using_cookies = False
        if options.cookies_file:
            opts["cookiefile"] = options.cookies_file
            using_cookies = True
        if options.cookies_from_browser:
            opts["cookiesfrombrowser"] = (options.cookies_from_browser,)
            using_cookies = True
        if using_cookies:
            # 法律声明输出到 stderr,提醒仅用于合法授权内容
            print(
                "⚠️  使用 cookies 下载会员内容:请确保仅下载您已合法授权访问的内容。\n"
                "    禁止用于下载未授权付费内容、规避版权保护或商业用途。\n"
                "    使用者自行承担法律责任。",
                file=sys.stderr,
            )

        # 合并 extra_args:list 形式的 CLI 参数,经 parse_options 展开为 dict 后并入
        if options.extra_args:
            try:
                parsed = yt_dlp.parse_options(list(options.extra_args))
                # 兼容不同 yt-dlp 版本:优先 all_opts(完整选项),回退 ie_opts,再回退元组首元素
                extra_opts = (
                    getattr(parsed, "all_opts", None)
                    or getattr(parsed, "ie_opts", None)
                    or (parsed[0] if isinstance(parsed, tuple) and parsed else None)
                )
                if isinstance(extra_opts, dict):
                    opts.update(extra_opts)
            except Exception:
                # extra_args 解析失败时忽略,避免影响主流程
                pass

        start_time = time.time()
        file_path = file_path_box["path"]

        try:
            ydl = yt_dlp.YoutubeDL(opts)
            ydl.download([url])
            # 下载结束后从闭包中取出最终文件路径
            file_path = file_path_box["path"]
        except DownloadError as e:
            # yt-dlp 下载错误:回调 on_error 并返回失败结果
            if callback is not None:
                callback.on_error(task_id, str(e))
            return DownloadResult(
                success=False,
                error=str(e),
                task_id=task_id,
                duration_seconds=time.time() - start_time,
            )
        except Exception as e:
            # 其它异常(含取消导致的 RuntimeError):回调 on_error 并返回失败结果
            if callback is not None:
                callback.on_error(task_id, str(e))
            return DownloadResult(
                success=False,
                error=str(e),
                task_id=task_id,
                duration_seconds=time.time() - start_time,
            )

        # 成功:回调 on_complete
        if callback is not None:
            callback.on_complete(task_id, file_path)

        # 输出实际选中的 format 描述(如「2160p HDR + opus 高码率」)
        if format_desc_box["desc"]:
            typer.echo(f"  实际选中格式: {format_desc_box['desc']}")

        return DownloadResult(
            success=True,
            file_path=file_path,
            task_id=task_id,
            duration_seconds=time.time() - start_time,
        )

    def cancel(self, task_id: str) -> bool:
        """取消指定任务的下载。

        设置取消标志,progress_hooks 闭包在下次回调时会检测到并抛出
        `RuntimeError("cancelled")` 中断下载。返回 True 表示已接受取消请求。
        """
        self._cancelled[task_id] = True
        return True
