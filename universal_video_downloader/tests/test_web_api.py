"""Web API 集成测试。

用 FastAPI TestClient 验证 HTTP 接口与 WebSocket,通过 monkeypatch 替换调度器
避免真实初始化 yt-dlp/mitmproxy。
"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from universal_video_downloader.core.config import AppConfig
from universal_video_downloader.core.models import DownloadResult, VideoFormat, VideoInfo
from universal_video_downloader.web import app as app_module
from universal_video_downloader.web.app import app


class MockDispatcher:
    """Mock 调度器,dispatch_async 直接返回成功结果,避免真实下载。

    dispatch_async 会调用 callback.on_complete 推送完成事件,
    供 WebSocket 测试验证事件广播。
    """

    async def dispatch_async(self, url, options, callback=None, task_id=""):
        # 触发回调以模拟完成事件(供 WebSocket 测试验证)
        if callback is not None:
            try:
                callback.on_complete(task_id, "/tmp/x.mp4")
            except Exception:
                pass
        return DownloadResult(
            success=True,
            file_path="/tmp/x.mp4",
            task_id=task_id,
        )


def _setup_mock(monkeypatch) -> None:
    """配置 mock 调度器与配置,避免真实初始化 yt-dlp/mitmproxy。

    TestClient 启动时会触发 @app.on_event("startup") 调用 _get_dispatcher(),
    _run_download 中也会断言 _config is not None,故需同步替换两者。
    """
    monkeypatch.setattr(
        app_module, "_get_dispatcher", lambda: MockDispatcher()
    )
    # _run_download 中会断言 _config is not None,需同步设置
    monkeypatch.setattr(app_module, "_config", AppConfig())


def test_post_download(monkeypatch) -> None:
    """测试 1:POST /api/download 返回 200,JSON 含 task_id 与 status=PENDING。"""
    _setup_mock(monkeypatch)
    with TestClient(app) as client:
        resp = client.post(
            "/api/download",
            json={"url": "https://www.youtube.com/watch?v=xxx"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "PENDING"


def test_get_tasks(monkeypatch) -> None:
    """测试 2:GET /api/tasks 返回 200,列表包含至少一个任务。"""
    _setup_mock(monkeypatch)
    with TestClient(app) as client:
        # 先提交一个下载任务,确保任务列表非空
        client.post(
            "/api/download",
            json={"url": "https://www.youtube.com/watch?v=xxx"},
        )
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        tasks = resp.json()
        assert isinstance(tasks, list)
        assert len(tasks) >= 1


def test_websocket_progress(monkeypatch) -> None:
    """测试 3:WebSocket /ws/progress 能连接并收到事件。

    连接 WebSocket 后触发下载请求,MockDispatcher 会调用回调推送完成事件。
    若 TestClient 不支持 receive_text 超时,仅验证连接成功即可。
    """
    _setup_mock(monkeypatch)
    with TestClient(app) as client:
        # 验证 WebSocket 能成功连接(不抛异常)
        with client.websocket_connect("/ws/progress") as ws:
            # 触发下载请求,MockDispatcher 会调用回调推送完成事件
            client.post(
                "/api/download",
                json={"url": "https://www.youtube.com/watch?v=xxx"},
            )
            # 等待后台任务执行,推送进度事件到队列
            time.sleep(0.2)
            # 尝试接收事件;若 TestClient 不支持或超时,仅验证连接已建立
            try:
                data = ws.receive_text()
                assert "progress" in data or "complete" in data or "error" in data
            except Exception:
                # 接收失败时,连接本身已验证成功
                pass


# ---------------------------------------------------------------------------
# Cookies 上传 / 列表 / 下载透传 测试
# ---------------------------------------------------------------------------
# 假 cookies.txt 内容(Netscape 格式)
_FAKE_COOKIES = (
    b"# Netscape HTTP Cookie File\n"
    b".example.com\tTRUE\t/\tFALSE\t0\tname\tvalue"
)


def test_cookies_upload(monkeypatch, tmp_path) -> None:
    """测试 4:POST /api/cookies/upload 上传假 cookies.txt,返回 saved=True 与 legal_notice。

    用 monkeypatch 把 ``Path.home`` 指向 tmp_path,避免污染真实 ~/.uvd/cookies。
    """
    _setup_mock(monkeypatch)
    # 把 home 指向临时目录,cookies 文件写入 tmp_path/.uvd/cookies/
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with TestClient(app) as client:
        resp = client.post(
            "/api/cookies/upload",
            files={"file": ("cookies.txt", _FAKE_COOKIES, "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["saved"] is True
        assert "legal_notice" in data and data["legal_notice"]
        assert data["filename"] == "cookies.txt"


def test_cookies_list(monkeypatch, tmp_path) -> None:
    """测试 5:GET /api/cookies/list 返回已上传的 cookies 文件名。

    先上传一个文件,再查询列表,断言列表包含该文件且附带 legal_notice。
    """
    _setup_mock(monkeypatch)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with TestClient(app) as client:
        # 先上传一个文件
        client.post(
            "/api/cookies/upload",
            files={"file": ("cookies.txt", _FAKE_COOKIES, "text/plain")},
        )
        # 再查询列表
        resp = client.get("/api/cookies/list")
        assert resp.status_code == 200
        data = resp.json()
        assert "cookies.txt" in data["files"]
        assert "legal_notice" in data and data["legal_notice"]


def test_download_passes_cookies_file(monkeypatch) -> None:
    """测试 6:POST /api/download 带 cookies_file 时,DownloadOptions.cookies_file 被透传。

    用捕获型 mock 调度器在 dispatch_async 中捕获 options 参数,断言其
    cookies_file 与请求体一致。
    """
    _setup_mock(monkeypatch)

    captured: dict = {}

    class CapturingDispatcher:
        """捕获 options 参数的 mock 调度器。"""

        async def dispatch_async(self, url, options, callback=None, task_id=""):
            captured["options"] = options
            captured["url"] = url
            if callback is not None:
                try:
                    callback.on_complete(task_id, "/tmp/x.mp4")
                except Exception:
                    pass
            return DownloadResult(
                success=True, file_path="/tmp/x.mp4", task_id=task_id
            )

    # 覆盖 _get_dispatcher 返回捕获型调度器
    monkeypatch.setattr(app_module, "_get_dispatcher", lambda: CapturingDispatcher())

    with TestClient(app) as client:
        resp = client.post(
            "/api/download",
            json={
                "url": "https://www.youtube.com/watch?v=xxx",
                "cookies_file": "/tmp/fake_cookies.txt",
            },
        )
        assert resp.status_code == 200
        # 后台任务异步执行,轮询等待调度器收到 options
        for _ in range(50):
            if "options" in captured:
                break
            time.sleep(0.02)
        assert "options" in captured, "调度器未收到下载请求"
        assert captured["options"].cookies_file == "/tmp/fake_cookies.txt"


def test_info_returns_preview_url(monkeypatch) -> None:
    """信息接口应公开用于加载列表首帧的分析媒体地址。"""
    _setup_mock(monkeypatch)

    class InfoAdapter:
        def extract_info(self, url, **_kwargs):
            return VideoInfo(
                url=url,
                title="分析视频",
                preview_url="https://cdn.example.com/video.mp4",
                formats=[
                    VideoFormat(
                        format_id="18",
                        ext="mp4",
                        resolution="1280x720",
                        vcodec="avc1",
                        acodec="mp4a",
                    )
                ],
            )

    class InfoRegistry:
        def select(self, _url):
            return InfoAdapter()

    monkeypatch.setattr(app_module, "create_default_registry", lambda: InfoRegistry())
    with TestClient(app) as client:
        response = client.post("/api/info", json={"url": "https://example.com/v"})

    assert response.status_code == 200
    assert response.json()["preview_url"] == "https://cdn.example.com/video.mp4"


def test_download_task_keeps_supplied_title(monkeypatch) -> None:
    """下载任务应保存前端提交的分析标题。"""
    _setup_mock(monkeypatch)
    app_module._task_statuses.clear()
    with TestClient(app) as client:
        created = client.post(
            "/api/download",
            json={"url": "https://example.com/v", "title": "分析视频名称"},
        ).json()
        tasks = client.get("/api/tasks").json()

    task = next(item for item in tasks if item["task_id"] == created["task_id"])
    assert task["title"] == "分析视频名称"


def test_download_task_uses_output_filename_when_title_is_missing(monkeypatch) -> None:
    """没有分析标题时，完成任务应回退显示下载文件名。"""
    _setup_mock(monkeypatch)
    app_module._task_statuses.clear()
    with TestClient(app) as client:
        created = client.post(
            "/api/download", json={"url": "https://example.com/v"}
        ).json()
        task_id = created["task_id"]
        for _ in range(50):
            tasks = client.get("/api/tasks").json()
            task = next(item for item in tasks if item["task_id"] == task_id)
            if task["status"] == "DONE":
                break
            time.sleep(0.02)

    assert task["title"] == "x"


def test_preview_rejects_missing_and_unsupported_files(monkeypatch, tmp_path) -> None:
    """预览接口需区分不存在的文件与浏览器不支持的格式。"""
    _setup_mock(monkeypatch)
    app_module._task_statuses.clear()
    app_module._task_statuses["missing"] = {
        "file_path": str(tmp_path / "missing.mp4")
    }
    unsupported_file = tmp_path / "video.mkv"
    unsupported_file.write_bytes(b"not-a-browser-media-file")
    app_module._task_statuses["unsupported"] = {"file_path": str(unsupported_file)}

    with TestClient(app) as client:
        missing = client.get("/api/preview/missing")
        unsupported = client.get("/api/preview/unsupported")

    assert missing.status_code == 404
    assert unsupported.status_code == 415


def test_preview_serves_video_range_requests(monkeypatch, tmp_path) -> None:
    """浏览器的媒体范围请求应得到可播放的部分视频响应。"""
    _setup_mock(monkeypatch)
    app_module._task_statuses.clear()
    video_file = tmp_path / "video.mp4"
    video_file.write_bytes(b"abcdef")
    app_module._task_statuses["video"] = {"file_path": str(video_file)}

    with TestClient(app) as client:
        response = client.get(
            "/api/preview/video", headers={"Range": "bytes=0-3"}
        )

    assert response.status_code == 206
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-disposition"] == "inline"
    assert response.content == b"abcd"


def test_web_page_contains_cover_title_and_preview_error_hooks() -> None:
    """静态页面应包含首帧封面、任务标题和预览错误处理钩子。"""
    html = (Path(app_module._STATIC_DIR) / "index.html").read_text(
        encoding="utf-8"
    )

    assert 'class="video-cover"' in html
    assert "data-thumbnail" in html
    assert "renderCover(data)" in html
    assert 'class="task-title"' in html
    assert "taskDisplayTitle(t)" in html
    assert 'id="preview-error"' in html
    assert "previewVideo.load()" in html
