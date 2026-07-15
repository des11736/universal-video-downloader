"""数据模型定义。

使用 pydantic v2 定义视频下载器核心数据结构,包括视频元信息、下载选项、
下载结果与进度事件等。所有适配器、调度器、CLI / Web 层共享这些模型。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class VideoFormat(BaseModel):
    """单个清晰度选项。

    对应 yt-dlp 解析出的每个 format 条目,或视频号适配器解析出的清晰度选项。
    """

    format_id: str
    ext: str = ""
    resolution: str = ""  # 如 "1280x720"
    fps: Optional[float] = None
    vcodec: str = ""
    acodec: str = ""
    filesize: Optional[int] = None
    note: str = ""  # yt-dlp 的 format_note


class VideoInfo(BaseModel):
    """视频元信息。

    由适配器 `extract_info` 方法返回,描述一个可下载视频的基本信息。
    """

    url: str
    title: str = ""
    duration: Optional[float] = None  # 秒
    uploader: str = ""
    platform: str = ""  # 适配器名,如 "ytdlp" / "wechat_channels"
    formats: list[VideoFormat] = Field(default_factory=list)
    thumbnail: str = ""
    description: str = ""


class DownloadOptions(BaseModel):
    """下载参数。

    由调用方构造,传递给适配器的 `download` 方法以控制下载行为。
    """

    quality: Optional[str] = None  # format_id 或描述如 "1080p"
    output_dir: str = "./downloads"
    filename_template: str = "%(title)s.%(ext)s"
    overwrite: bool = False
    extra_args: list[str] = Field(default_factory=list)
    # cookies.txt 文件路径,用于下载需要登录态的会员内容
    cookies_file: Optional[str] = None
    # 从浏览器读取 cookies 的浏览器名:chrome/edge/firefox/safari
    cookies_from_browser: Optional[str] = None


class DownloadResult(BaseModel):
    """下载结果。

    适配器 `download` 方法返回,描述下载是否成功及产物路径。
    """

    success: bool
    file_path: str = ""
    error: str = ""
    task_id: str = ""
    duration_seconds: float = 0.0


class ProgressEvent(BaseModel):
    """进度事件。

    内部进度数据结构,可被 CLI / Web 层转换为用户可见的进度展示。
    """

    task_id: str
    percent: float = 0.0  # 0-100
    speed: float = 0.0  # bytes/sec
    eta: float = 0.0  # 秒
    downloaded_bytes: int = 0
    total_bytes: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
