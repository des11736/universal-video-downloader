"""UVD Web UI 后端。

基于 FastAPI 实现的 HTTP + WebSocket 接口,提供:

- ``POST /api/download``:提交下载任务,立即返回 task_id,后台异步执行;
- ``GET /api/tasks``:查询全部任务状态;
- ``WebSocket /ws/progress``:订阅进度事件广播。

下载任务通过 ``Dispatcher.dispatch_async`` 调度,适配器在线程池中执行,
进度回调经 ``call_soon_threadsafe`` 投递回事件循环并广播给 WebSocket 订阅者。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import (
    FastAPI,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..core.config import AppConfig, load_config
from ..core.models import DownloadOptions
from ..scheduler.dispatcher import Dispatcher, create_dispatcher
from ..scheduler.registry import create_default_registry
from .callback_adapter import WebProgressCallback
from .wechat_listener import WechatPageListener

app = FastAPI(title="UVD Web UI")
logger = logging.getLogger(__name__)


@app.middleware("http")
async def no_cache_html(request: Any, call_next: Any):
    """为 HTML 页面设置 no-cache 头,防止浏览器缓存旧版前端代码。

    只对 text/html 响应生效,静态资源(CSS/JS/图片)不受影响。
    这解决了用户修改前端后浏览器仍使用缓存旧版本的问题。
    """
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# 全局状态(单进程内)
_dispatcher: Optional[Dispatcher] = None  # 懒加载的调度器
_config: Optional[AppConfig] = None  # 与调度器配套的应用配置
_task_statuses: dict[str, dict] = {}  # task_id -> 状态 dict
_progress_subscribers: set[WebSocket] = set()  # WebSocket 订阅者集合
_progress_events: asyncio.Queue = asyncio.Queue()  # 进度事件广播队列
_wechat_page_listener = WechatPageListener()

# 静态资源目录(本文件同级的 static/)
_STATIC_DIR = Path(__file__).parent / "static"
_PREVIEW_MEDIA_TYPES = {
    ".m4v": "video/x-m4v",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}

# Cookies 使用法律声明:提醒用户仅下载合法授权内容
LEGAL_NOTICE = (
    "⚠️ 使用 cookies 下载会员内容:请确保仅下载您已合法授权访问的内容。"
    "禁止用于下载未授权付费内容、规避版权保护或商业用途。使用者自行承担法律责任。"
)


# ---------------------------------------------------------------------------
# 请求 / 响应模型
# ---------------------------------------------------------------------------
class DownloadRequest(BaseModel):
    """下载请求体。"""

    url: str
    title: Optional[str] = None
    quality: Optional[str] = None
    output_dir: str = "./downloads"
    filename_template: Optional[str] = None
    # cookies.txt 文件路径(已上传的文件路径)
    cookies_file: Optional[str] = None
    # 从浏览器读取 cookies 的浏览器名:chrome/edge/firefox
    cookies_from_browser: Optional[str] = None


class DownloadResponse(BaseModel):
    """下载提交响应体。"""

    task_id: str
    status: str


class InfoRequest(BaseModel):
    """视频信息分析请求体。"""

    url: str
    cookies_file: Optional[str] = None
    cookies_from_browser: Optional[str] = None


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def _get_dispatcher() -> Dispatcher:
    """懒加载调度器。

    首次访问时读取环境变量 ``UVD_CONFIG_PATH`` 决定配置文件路径,
    调用 ``load_config`` 加载配置,再用 ``create_dispatcher`` 构造调度器。
    后续调用直接返回缓存实例。
    """
    global _dispatcher, _config
    if _dispatcher is None:
        # CLI 的 serve 子命令会把 --config 写入环境变量,便于此处读取
        config_path_env = os.environ.get("UVD_CONFIG_PATH")
        config_path = Path(config_path_env) if config_path_env else None
        _config = load_config(config_path)
        _dispatcher = create_dispatcher(_config)
    return _dispatcher


def _is_wechat_channels_url(url: str) -> bool:
    """判断 URL 是否属于需要页面下载按钮的视频号站点。"""
    return urlparse(url).hostname == "channels.weixin.qq.com"


def _start_wechat_page_listener() -> None:
    """启动页面注入代理；失败时不影响其他平台的 Web 下载。"""
    try:
        cert_path = _wechat_page_listener.start()
        logger.warning(
            "视频号页面监听已启动（127.0.0.1:8888）。根证书：%s",
            cert_path,
        )
    except Exception as exc:
        logger.warning(
            "视频号页面监听启动失败，其他下载功能不受影响：%s",
            exc,
        )


def _stop_wechat_page_listener() -> None:
    """在 Web 服务退出时停止页面注入代理。"""
    _wechat_page_listener.stop()


async def _run_download(task_id: str, req: DownloadRequest) -> None:
    """后台下载任务:构造选项,异步派发,完成后更新任务状态。

    - 成功:状态置 DONE,记录 file_path;
    - 失败(返回 success=False 或抛异常):状态置 FAILED,记录 error。

    进度事件通过 ``WebProgressCallback`` 推入 ``_progress_events`` 队列,
    由 WebSocket 广播协程消费。
    """
    dispatcher = _get_dispatcher()
    # 配置中提供的默认 filenameTemplate 与 extraArgs 合并到下载选项
    assert _config is not None  # _get_dispatcher 已确保 _config 被填充
    options = DownloadOptions(
        quality=req.quality,
        output_dir=req.output_dir,
        filename_template=(
            req.filename_template or _config.download.filenameTemplate
        ),
        overwrite=False,
        extra_args=list(_config.ytdlp.extraArgs),
        # 透传 cookies 配置,供适配器注入登录态
        cookies_file=req.cookies_file,
        cookies_from_browser=req.cookies_from_browser,
    )
    # 取当前事件循环,供回调适配器跨线程投递事件
    loop = asyncio.get_running_loop()
    callback = WebProgressCallback(task_id, _progress_events, loop, _task_statuses)
    # 标记为运行中(dispatcher 内部队列也会维护状态,这里同步给 API 层)
    _task_statuses[task_id]["status"] = "RUNNING"
    _task_statuses[task_id]["percent"] = 0.0
    try:
        result = await dispatcher.dispatch_async(
            req.url, options, callback, task_id
        )
    except Exception as e:
        # dispatch_async 在异常时会重新抛出(TaskQueue 标记 FAILED)
        _task_statuses[task_id].update(status="FAILED", error=str(e))
        return
    if result.success:
        title = _task_statuses[task_id].get("title") or Path(
            result.file_path
        ).stem
        _task_statuses[task_id].update(
            status="DONE", file_path=result.file_path, title=title
        )
    else:
        _task_statuses[task_id].update(
            status="FAILED", error=result.error or "下载失败"
        )


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------
@app.post("/api/download", response_model=DownloadResponse)
async def api_download(req: DownloadRequest) -> DownloadResponse:
    """提交下载任务。

    生成 task_id,在 ``_task_statuses`` 中登记 PENDING 状态,然后用
    ``asyncio.create_task`` 在后台执行下载,立即返回 task_id 给前端。
    """
    if _is_wechat_channels_url(req.url):
        raise HTTPException(
            status_code=409,
            detail=(
                "视频号请设置 127.0.0.1:8888 系统代理后，"
                "在视频页面点击页面下载按钮。"
            ),
        )

    task_id = uuid4().hex
    _task_statuses[task_id] = {
        "task_id": task_id,
        "status": "PENDING",
        "error": "",
        "file_path": "",
        "url": req.url,
        "title": (req.title or "").strip(),
        "percent": 0.0,
    }
    asyncio.create_task(_run_download(task_id, req))
    return DownloadResponse(task_id=task_id, status="PENDING")


@app.get("/api/tasks")
async def api_tasks() -> list[dict[str, Any]]:
    """返回全部任务的当前状态列表(含实时进度)。"""
    return list(_task_statuses.values())


@app.post("/api/info")
async def api_info(req: InfoRequest):
    """分析视频 URL,返回视频元信息与可选清晰度列表。

    调用适配器注册表的 ``select`` 选择适配器,执行 ``extract_info``
    获取视频信息。在线程池中执行(避免阻塞事件循环)。
    """
    dispatcher = _get_dispatcher()
    assert _config is not None
    registry = create_default_registry()
    adapter = registry.select(req.url)

    def _extract():
        try:
            return adapter.extract_info(
                req.url,
                cookies_file=req.cookies_file,
                cookies_from_browser=req.cookies_from_browser,
            )
        except TypeError:
            return adapter.extract_info(req.url)

    try:
        info = await asyncio.to_thread(_extract)
    except Exception as e:
        return {"error": str(e)}

    # 过滤出有视频流的格式(排除纯音频)
    formats = []
    for f in info.formats:
        # 跳过纯音频(dash 音频流)和没有分辨率的格式
        if f.vcodec and f.vcodec != "none":
            formats.append({
                "format_id": f.format_id,
                "ext": f.ext,
                "resolution": f.resolution,
                "fps": f.fps,
                "vcodec": f.vcodec,
                "acodec": f.acodec,
                "filesize": f.filesize,
                "note": f.note,
            })

    return {
        "title": info.title,
        "duration": info.duration,
        "uploader": info.uploader,
        "platform": info.platform,
        "thumbnail": info.thumbnail,
        "preview_url": info.preview_url,
        "formats": formats,
    }


@app.get("/api/preview/{task_id}")
async def api_preview(task_id: str):
    """返回视频文件供预览播放。

    从 ``_task_statuses`` 取出文件路径,以 FileResponse 返回,
    Content-Type 自动根据扩展名推断。
    """
    status = _task_statuses.get(task_id)
    if not status or not status.get("file_path"):
        raise HTTPException(status_code=404, detail="文件不存在")
    file_path = Path(status["file_path"])
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    media_type = _PREVIEW_MEDIA_TYPES.get(file_path.suffix.lower())
    if media_type is None:
        raise HTTPException(
            status_code=415, detail="该文件格式无法在浏览器中预览"
        )
    return FileResponse(
        file_path,
        media_type=media_type,
        headers={"Content-Disposition": "inline"},
    )


@app.post("/api/open-folder/{task_id}")
async def api_open_folder(task_id: str):
    """在文件管理器中打开并选中已下载的文件。

    Windows: ``explorer /select,"path"``
    macOS: ``open -R "path"``
    Linux: ``xdg-open "dir"``
    """
    status = _task_statuses.get(task_id)
    if not status or not status.get("file_path"):
        return {"error": "文件不存在"}
    file_path = status["file_path"]
    if not os.path.exists(file_path):
        return {"error": "文件不存在"}

    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", file_path])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", file_path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(file_path)])
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/cookies/upload")
async def api_cookies_upload(file: UploadFile = File(...)):
    """上传 cookies.txt 文件。

    保存到 ``~/.uvd/cookies/`` 目录,权限设为 ``0600``(仅属主可读写),
    防止其他用户读取敏感的登录态 cookies。

    - 防路径穿越:仅取文件名,忽略任何目录部分;
    - 文件名不以 ``.txt`` 结尾时自动补齐扩展名;
    - 响应附带法律声明 ``legal_notice``,前端需向用户展示。
    """
    # 保存到 ~/.uvd/cookies/(运行时计算 home,便于测试 monkeypatch)
    cookies_dir = Path.home() / ".uvd" / "cookies"
    cookies_dir.mkdir(parents=True, exist_ok=True)
    # 防路径穿越:仅用文件名,丢弃任何目录前缀
    safe_name = Path(file.filename).name
    if not safe_name.endswith(".txt"):
        safe_name = safe_name + ".txt"
    dest = cookies_dir / safe_name
    content = await file.read()
    dest.write_bytes(content)
    # 设置权限 0600(Windows 上 os.chmod 限制较大,但调用不报错即可)
    os.chmod(dest, stat.S_IRUSR | stat.S_IWUSR)
    return {
        "saved": True,
        "path": str(dest),
        "filename": safe_name,
        "legal_notice": LEGAL_NOTICE,
    }


@app.get("/api/cookies/list")
async def api_cookies_list():
    """列出已上传的 cookies.txt 文件名。

    扫描 ``~/.uvd/cookies/`` 目录,返回所有 ``.txt`` 文件名列表,
    响应附带法律声明 ``legal_notice``。
    """
    cookies_dir = Path.home() / ".uvd" / "cookies"
    if not cookies_dir.exists():
        return {"files": [], "legal_notice": LEGAL_NOTICE}
    files = [
        f.name
        for f in cookies_dir.iterdir()
        if f.is_file() and f.name.endswith(".txt")
    ]
    return {"files": files, "legal_notice": LEGAL_NOTICE}


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------
@app.websocket("/ws/progress")
async def ws_progress(ws: WebSocket) -> None:
    """进度事件 WebSocket 端点。

    接受连接后加入订阅者集合,循环从 ``_progress_events`` 队列取出事件,
    广播给所有当前订阅者。连接断开时从集合中移除。
    """
    await ws.accept()
    _progress_subscribers.add(ws)
    try:
        while True:
            event = await _progress_events.get()
            # 广播给所有订阅者;发送失败的视为已断开,从集合中移除
            for sub in list(_progress_subscribers):
                try:
                    await sub.send_text(json.dumps(event))
                except Exception:
                    _progress_subscribers.discard(sub)
    except WebSocketDisconnect:
        _progress_subscribers.discard(ws)


# ---------------------------------------------------------------------------
# 生命周期:启动时预初始化调度器
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def _on_startup() -> None:
    """启动时触发调度器初始化,避免首个请求承担加载延迟。

    顺带启动微信视频号页面监听器(本地 MITM 代理,端口 8888)。
    系统代理切换由启动脚本(start_uvd.bat/start_uvd.sh)负责。
    """
    _get_dispatcher()
    _start_wechat_page_listener()


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    """停止 Web 服务关联的页面监听器。"""
    _stop_wechat_page_listener()


# ---------------------------------------------------------------------------
# 静态资源(挂在最后,避免拦截 /api 与 /ws 路由)
# ---------------------------------------------------------------------------
app.mount(
    "/",
    StaticFiles(directory=str(_STATIC_DIR), html=True),
    name="static",
)
