"""默认下载策略与 cookies 支持的单元测试。

覆盖 `YtDlpAdapter.download` 的画质自动选择策略(format_sort / 合并 mp4)与
cookies 注入(cookiefile / cookiesfrombrowser / 法律声明)行为。通过 mock
`yt_dlp.YoutubeDL` 避免真实网络请求,仅校验传给 YoutubeDL 的选项 dict。
"""

from __future__ import annotations

from unittest.mock import patch

from universal_video_downloader.core.models import DownloadOptions
from universal_video_downloader.platforms.ytdlp_adapter import YtDlpAdapter


@patch("universal_video_downloader.platforms.ytdlp_adapter.yt_dlp.YoutubeDL")
def test_no_quality_uses_auto_format_sort(mock_ytdlp_class):
    """测试 1:未传 quality 时,应使用自动 format_sort 与 bestvideo+bestaudio 合并为 mp4。"""
    adapter = YtDlpAdapter()
    options = DownloadOptions(
        output_dir="./downloads", filename_template="%(title)s.%(ext)s"
    )

    result = adapter.download("https://example.com/watch?v=abc", options)

    # YoutubeDL 构造时传入的 opts 为第一个位置参数
    opts = mock_ytdlp_class.call_args[0][0]
    assert opts["format_sort"] == [
        "res:4",
        "hdr:1",
        "vcodec:1",
        "acodec:1",
        "size:1",
        "br:1",
    ]
    assert opts["format"] == "bestvideo*+bestaudio/best"
    assert opts["merge_output_format"] == "mp4"
    assert result.success is True


@patch("universal_video_downloader.platforms.ytdlp_adapter.yt_dlp.YoutubeDL")
def test_with_quality_uses_format_id(mock_ytdlp_class):
    """测试 2:传 quality 时,不走自动 sort,format 等于 quality 值。"""
    adapter = YtDlpAdapter()
    options = DownloadOptions(
        quality="137+140",
        output_dir="./downloads",
        filename_template="%(title)s.%(ext)s",
    )

    adapter.download("https://example.com/watch?v=abc", options)

    opts = mock_ytdlp_class.call_args[0][0]
    # 传 quality 时不应触发自动 sort 与合并格式
    assert "format_sort" not in opts
    assert "merge_output_format" not in opts
    assert opts["format"] == "137+140"


@patch("universal_video_downloader.platforms.ytdlp_adapter.yt_dlp.YoutubeDL")
def test_cookies_file_sets_cookiefile(mock_ytdlp_class):
    """测试 3:传 cookies_file 时,选项应包含 cookiefile。"""
    adapter = YtDlpAdapter()
    options = DownloadOptions(
        cookies_file="/tmp/cookies.txt",
        output_dir="./downloads",
        filename_template="%(title)s.%(ext)s",
    )

    adapter.download("https://example.com/watch?v=abc", options)

    opts = mock_ytdlp_class.call_args[0][0]
    assert opts["cookiefile"] == "/tmp/cookies.txt"


@patch("universal_video_downloader.platforms.ytdlp_adapter.yt_dlp.YoutubeDL")
def test_cookies_from_browser_sets_tuple(mock_ytdlp_class):
    """测试 4:传 cookies_from_browser 时,选项应包含 cookiesfrombrowser 元组。"""
    adapter = YtDlpAdapter()
    options = DownloadOptions(
        cookies_from_browser="chrome",
        output_dir="./downloads",
        filename_template="%(title)s.%(ext)s",
    )

    adapter.download("https://example.com/watch?v=abc", options)

    opts = mock_ytdlp_class.call_args[0][0]
    # yt-dlp 要求 cookiesfrombrowser 为元组形式
    assert opts["cookiesfrombrowser"] == ("chrome",)


@patch("universal_video_downloader.platforms.ytdlp_adapter.yt_dlp.YoutubeDL")
def test_cookies_prints_legal_notice_to_stderr(mock_ytdlp_class, capsys):
    """测试 5:传 cookies 时,法律声明应被输出到 stderr。"""
    adapter = YtDlpAdapter()
    options = DownloadOptions(
        cookies_file="/tmp/cookies.txt",
        output_dir="./downloads",
        filename_template="%(title)s.%(ext)s",
    )

    adapter.download("https://example.com/watch?v=abc", options)

    captured = capsys.readouterr()
    # 法律声明应输出到 stderr,包含关键提示语
    assert "使用 cookies" in captured.err
    assert "法律责任" in captured.err
