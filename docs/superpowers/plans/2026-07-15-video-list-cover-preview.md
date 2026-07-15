# 视频列表封面、预览与标题 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 让 Web UI 以分析媒体的首帧作为封面、可靠预览已下载视频，并用视频名称作为下载任务标题。

**Architecture:** YtDlpAdapter 从已解析的渐进式媒体格式中选择浏览器可播放的 URL，作为 VideoInfo.preview_url 返回给 Web API。前端将该 URL 放入静音视频元素以显示首帧，失败时回退现有缩略图；下载请求把标题保存至后端任务状态，任务列表优先呈现该标题。预览 API 只返回存在且浏览器可播放的本地媒体文件，前端重置播放器并处理错误事件。

**Tech Stack:** Python 3.10+, FastAPI/Starlette, Pydantic v2, pytest, vanilla HTML/CSS/JavaScript, yt-dlp。

## Global Constraints

- 不新增 FFmpeg、图像处理库或封面缓存目录。
- 不改变平台下载、解密或输出命名规则。
- 不改变现有多链接输入行为。
- 首帧不可取得时必须回退为平台缩略图或占位图。
- 标题回退顺序必须是分析标题、下载文件名（无扩展名）、原始 URL。

---

## File Structure

- Modify: universal_video_downloader/core/models.py — 为 VideoInfo 定义可选的分析媒体 URL。
- Modify: universal_video_downloader/platforms/ytdlp_adapter.py — 从 yt-dlp 格式中选择可在浏览器播放的渐进式视频 URL。
- Modify: universal_video_downloader/web/app.py — 在信息响应中公开媒体 URL，保存任务标题并收紧本地预览响应。
- Modify: universal_video_downloader/web/static/index.html — 首帧封面、任务名称与预览错误的呈现和交互。
- Modify: universal_video_downloader/tests/test_format_strategy.py — 覆盖适配器的媒体 URL 选择。
- Modify: universal_video_downloader/tests/test_web_api.py — 覆盖 API 数据契约、标题回退和预览媒体响应。

### Task 1: 分析媒体 URL 数据契约

**Files:**

- Modify: universal_video_downloader/core/models.py:35-45
- Modify: universal_video_downloader/platforms/ytdlp_adapter.py:48-123
- Test: universal_video_downloader/tests/test_format_strategy.py

**Interfaces:**

- Consumes: yt-dlp 的 info["formats"] 字典，其中可含 url、ext、vcodec、acodec、height。
- Produces: VideoInfo.preview_url: str；空字符串表示没有可供浏览器首帧加载的媒体流。

- [ ] **Step 1: 写入失败测试，要求仅选择带音视频的 MP4/WebM 流**

~~~python
@patch("universal_video_downloader.platforms.ytdlp_adapter.yt_dlp.YoutubeDL")
def test_extract_info_returns_progressive_preview_url(mock_ytdlp_class):
    mock_ytdlp_class.return_value.extract_info.return_value = {
        "title": "示例视频",
        "formats": [
            {"format_id": "137", "url": "https://cdn.example/video-only.mp4", "ext": "mp4", "vcodec": "avc1", "acodec": "none", "height": 1080},
            {"format_id": "18", "url": "https://cdn.example/progressive.mp4", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "height": 720},
        ],
    }

    info = YtDlpAdapter().extract_info("https://example.com/watch?v=1")

    assert info.preview_url == "https://cdn.example/progressive.mp4"
~~~

- [ ] **Step 2: 运行测试，确认当前模型没有 preview_url 字段**

Run: pytest universal_video_downloader/tests/test_format_strategy.py::test_extract_info_returns_progressive_preview_url -v

Expected: FAIL，提示 VideoInfo 没有属性 preview_url。

- [ ] **Step 3: 定义字段并选择可播放流**

~~~python
# core/models.py
class VideoInfo(BaseModel):
    preview_url: str = ""

# platforms/ytdlp_adapter.py
def _select_preview_url(formats: list[dict]) -> str:
    progressive = [
        item for item in formats
        if item.get("url")
        and item.get("ext") in {"mp4", "webm"}
        and item.get("vcodec") not in {None, "", "none"}
        and item.get("acodec") not in {None, "", "none"}
    ]
    if not progressive:
        return ""
    return str(max(progressive, key=lambda item: item.get("height") or 0)["url"])
~~~

调用该辅助函数时先保存 raw_formats = info.get("formats", []) or []，以它构建现有 VideoFormat 列表，并将 preview_url=_select_preview_url(raw_formats) 传给 VideoInfo。保持下载格式筛选与其它元数据映射不变。

- [ ] **Step 4: 运行适配器测试**

Run: pytest universal_video_downloader/tests/test_format_strategy.py -v

Expected: PASS，现有下载策略断言与新增预览 URL 断言全部通过。

- [ ] **Step 5: 提交数据契约改动**

~~~bash
git add universal_video_downloader/core/models.py universal_video_downloader/platforms/ytdlp_adapter.py universal_video_downloader/tests/test_format_strategy.py
git commit -m "feat: expose progressive video URL for list covers"
~~~

### Task 2: Web API 的标题与可预览文件契约

**Files:**

- Modify: universal_video_downloader/web/app.py:24-248
- Test: universal_video_downloader/tests/test_web_api.py

**Interfaces:**

- Consumes: DownloadRequest.title: Optional[str] 与 VideoInfo.preview_url。
- Produces: /api/info 响应中的 preview_url；/api/tasks 每项中的 title；GET /api/preview/{task_id} 的 200/206、404、415 响应。

- [ ] **Step 1: 写入失败 API 测试**

~~~python
def test_download_task_keeps_supplied_title(monkeypatch):
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


def test_preview_rejects_missing_and_unsupported_files(monkeypatch, tmp_path):
    _setup_mock(monkeypatch)
    app_module._task_statuses["missing"] = {"file_path": str(tmp_path / "missing.mp4")}
    (tmp_path / "video.mkv").write_bytes(b"x")
    app_module._task_statuses["mkv"] = {"file_path": str(tmp_path / "video.mkv")}
    with TestClient(app) as client:
        assert client.get("/api/preview/missing").status_code == 404
        assert client.get("/api/preview/mkv").status_code == 415
~~~

再加入一个测试：向任务状态注册 video.mp4，请求头传 Range: bytes=0-3，断言响应为 206、content-type 为 video/mp4 且 accept-ranges 为 bytes。为 /api/info 使用含 preview_url 的 VideoInfo 适配器桩，断言 JSON 原样返回该字段。

- [ ] **Step 2: 运行新增 API 测试，确认当前实现不能满足状态码和字段要求**

Run: pytest universal_video_downloader/tests/test_web_api.py -k "title or preview or info" -v

Expected: FAIL，当前请求模型不接收标题，且缺失或不支持文件未返回 404/415。

- [ ] **Step 3: 最小化实现请求、状态与预览校验**

~~~python
from fastapi import HTTPException

_PREVIEW_MEDIA_TYPES = {".mp4": "video/mp4", ".webm": "video/webm"}

class DownloadRequest(BaseModel):
    url: str
    title: Optional[str] = None

# api_download 中创建任务状态
"title": (req.title or "").strip(),

# _run_download 成功分支
title = _task_statuses[task_id].get("title") or Path(result.file_path).stem
_task_statuses[task_id].update(status="DONE", file_path=result.file_path, title=title)

# api_preview
file_path = Path(status["file_path"])
if not file_path.is_file():
    raise HTTPException(status_code=404, detail="文件不存在")
media_type = _PREVIEW_MEDIA_TYPES.get(file_path.suffix.lower())
if media_type is None:
    raise HTTPException(status_code=415, detail="该文件格式无法在浏览器中预览")
return FileResponse(file_path, media_type=media_type, headers={"Content-Disposition": "inline"})
~~~

在 /api/info 返回字典增加 "preview_url": info.preview_url。保留 FileResponse，使 Starlette 继续处理标准范围请求。

- [ ] **Step 4: 运行 Web API 测试**

Run: pytest universal_video_downloader/tests/test_web_api.py -v

Expected: PASS，任务标题、媒体范围请求、错误状态与既有 Cookies/WebSocket 测试全部通过。

- [ ] **Step 5: 提交 Web API 改动**

~~~bash
git add universal_video_downloader/web/app.py universal_video_downloader/tests/test_web_api.py
git commit -m "feat: preserve video titles and harden preview API"
~~~

### Task 3: 首帧封面、任务标题与预览交互

**Files:**

- Modify: universal_video_downloader/web/static/index.html:140-146,384-390,599-856,870-930
- Test: universal_video_downloader/tests/test_web_api.py

**Interfaces:**

- Consumes: 分析响应的 preview_url、thumbnail、title 及任务项的 title、file_path。
- Produces: .video-cover 首帧元素、.task-title 视频名称、#preview-error 可见预览错误。

- [ ] **Step 1: 写入静态页面契约测试**

~~~python
def test_web_page_contains_cover_title_and_preview_error_hooks():
    html = (Path(app_module._STATIC_DIR) / "index.html").read_text(encoding="utf-8")
    assert 'class="video-cover"' in html
    assert "data-thumbnail" in html
    assert 'class="task-title"' in html
    assert 'id="preview-error"' in html
    assert "previewVideo.load()" in html
~~~

- [ ] **Step 2: 运行静态页面测试，确认当前页面缺少所需钩子**

Run: pytest universal_video_downloader/tests/test_web_api.py::test_web_page_contains_cover_title_and_preview_error_hooks -v

Expected: FAIL，当前 HTML 不包含 video-cover、任务标题和预览错误区域。

- [ ] **Step 3: 实现首帧封面与回退**

~~~javascript
function coverFallbackHtml(thumbnail) {
  return thumbnail
    ? '<img class="video-cover" src="' + escapeHtml(thumbnail) + '" alt="视频封面" />'
    : '<div class="video-cover video-cover-placeholder" aria-label="无可用封面">...</div>';
}

function renderCover(data) {
  if (!data.preview_url) return coverFallbackHtml(data.thumbnail);
  return '<video class="video-cover" muted playsinline preload="auto" data-thumbnail="' +
    escapeHtml(data.thumbnail || "") + '" src="' + escapeHtml(data.preview_url) + '"></video>';
}
~~~

把视频卡片里的旧 thumbnailHtml 替换为 renderCover(data)。在 videoList.innerHTML 更新后为每个 video.video-cover 注册 loadeddata 监听器以暂停视频，并注册 error 监听器以 replaceWith 替换成 coverFallbackHtml(video.dataset.thumbnail) 创建的节点。CSS 让 img.video-cover 与 video.video-cover 共用现有 120×68 尺寸与 object-fit: cover。

- [ ] **Step 4: 实现标题和预览错误交互**

~~~javascript
async function submitDownload(url, formatId, title) {
  const body = {
    url,
    title: title || "",
    quality: formatId === "best" ? null : formatId,
    output_dir: "./downloads",
  };
  // 保留既有 cookies 与 fetch 逻辑
}

function taskDisplayTitle(task) {
  if (task.title) return task.title;
  if (task.file_path) return task.file_path.split(/[\\/]/).pop().replace(/\.[^.]+$/, "");
  return task.url || "(等待 URL)";
}
~~~

单个与批量下载分别把 v.data.title 传给 submitDownload；创建、刷新和 WebSocket 维护的任务对象均包含 title。在任务顶部渲染 .task-title，原始 URL 放为次级文本。预览弹窗在视频元素下增加 <p id="preview-error" role="alert"></p>；打开前清空提示并重置来源，设置 /api/preview/{taskId} 后调用 previewVideo.load()。为 previewVideo 的 error 事件显示“无法播放该文件，请确认文件未被移动且浏览器支持该格式”。关闭弹窗复用同一重置函数清空播放器和错误。

- [ ] **Step 5: 运行静态页面与完整回归测试**

Run: pytest universal_video_downloader/tests/test_web_api.py -v

Expected: PASS，页面钩子与 API 回归测试全部通过。

Run: pytest universal_video_downloader/tests -v

Expected: PASS，全部单元与集成测试通过；网络端到端测试如被标记为跳过，应保持 SKIPPED 而不是失败。

- [ ] **Step 6: 提交前端改动**

~~~bash
git add universal_video_downloader/web/static/index.html universal_video_downloader/tests/test_web_api.py
git commit -m "feat: show video first frames and download titles"
~~~

## Self-Review

- Spec coverage: Task 1 提供首帧需要的可信媒体地址；Task 2 保存标题并保障预览文件契约；Task 3 呈现首帧、标题和错误。四项回退与非目标均在全局约束和对应任务中实现。
- Completeness scan: 每个实现步骤包含明确的文件、接口、测试命令和代码片段；没有未定义的后续工作。
- Type consistency: VideoInfo.preview_url 由适配器写入、API 返回、前端读取；DownloadRequest.title 由前端提交并进入任务 title；预览 API 始终使用 task_id 和 file_path。
