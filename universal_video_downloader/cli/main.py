"""UVD 命令行入口。

基于 Typer 构建 ``uvd`` CLI,提供 download / batch / info / serve / config /
platforms 等子命令,封装适配器调度、配置管理与进度展示。对应 pyproject.toml
中声明的入口 ``uvd = "universal_video_downloader.cli.main:app"``。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import typer
import yaml
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from ..core.base import PlatformDownloader
from ..core.config import (
    DEFAULT_CONFIG_YAML,
    AppConfig,
    get_default_config_path,
    load_config,
)
from ..core.models import DownloadOptions, DownloadResult
from ..scheduler.dispatcher import create_dispatcher
from ..scheduler.registry import AdapterRegistry, create_default_registry

# 模块级 Typer 应用对象,即 pyproject.toml 声明的 `app` 入口
app = typer.Typer(name="uvd", help="通用流媒体视频下载器", no_args_is_help=True)

# 配置管理子命令组(`uvd config get/set/path`)
config_app = typer.Typer(help="配置管理")
app.add_typer(config_app, name="config")

# 共享的 rich 控制台,用于表格 / 进度输出
_console = Console()


# ---------------------------------------------------------------------------
# 进度回调(CLI 用)
# ---------------------------------------------------------------------------
class CliProgressCallback:
    """基于 rich.progress 的 CLI 进度回调。

    实现 ``ProgressCallback`` 协议,内部用 ``rich.progress.Progress`` 维护
    多个进度条(按 task_id 区分),可通过 ``with`` 语句自动启停进度展示。
    """

    def __init__(self) -> None:
        self._progress = Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
        )
        self._task_ids: dict[str, int] = {}

    def __enter__(self) -> "CliProgressCallback":
        self._progress.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._progress.stop()

    def on_progress(
        self, task_id: str, percent: float, speed: float = 0.0, eta: float = 0.0
    ) -> None:
        """下载进度更新:首次见到 task_id 时创建进度条,后续更新完成度。"""
        if task_id not in self._task_ids:
            self._task_ids[task_id] = self._progress.add_task(
                f"下载 {task_id[:8]}", total=100
            )
        self._progress.update(self._task_ids[task_id], completed=percent)

    def on_complete(self, task_id: str, file_path: str) -> None:
        """下载完成:进度条置满并标记绿色,打印保存路径。"""
        if task_id in self._task_ids:
            self._progress.update(
                self._task_ids[task_id],
                completed=100,
                description=f"[green]完成 {task_id[:8]}",
            )
        typer.echo(f"  保存到: {file_path}")

    def on_error(self, task_id: str, error_message: str) -> None:
        """下载出错:进度条标记红色,打印错误信息。"""
        if task_id in self._task_ids:
            self._progress.update(
                self._task_ids[task_id],
                description=f"[red]失败 {task_id[:8]}",
            )
        typer.echo(f"  错误: {error_message}", err=True)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def _load_app_config(config_path: Optional[Path]) -> AppConfig:
    """加载应用配置,失败时输出错误并以退出码 1 退出。"""
    try:
        return load_config(config_path)
    except Exception as e:
        typer.echo(f"加载配置失败: {e}", err=True)
        raise typer.Exit(1)


def _make_progress_callback(task_id: str) -> CliProgressCallback:
    """构造基于 rich.progress 的进度回调。

    返回的 ``CliProgressCallback`` 同时实现了 ``ProgressCallback`` 协议与
    上下文管理协议,调用方应使用 ``with`` 语句启停进度条。``task_id`` 参数
    保留用于接口一致性,回调内部按 task_id 自动维护进度条,无需在此预注册。
    """
    return CliProgressCallback()


def _build_download_options(
    config: AppConfig, quality: Optional[str], output: str
) -> DownloadOptions:
    """根据配置与命令行参数构造下载选项。"""
    return DownloadOptions(
        quality=quality,
        output_dir=output,
        filename_template=config.download.filenameTemplate,
        overwrite=False,
        extra_args=list(config.ytdlp.extraArgs),
    )


def _find_adapter_by_name(
    registry: AdapterRegistry, name: str
) -> Optional[PlatformDownloader]:
    """在注册表中按 name 查找适配器,未找到返回 None。"""
    for adapter in registry.list_adapters():
        if adapter.name == name:
            return adapter
    return None


def _safe_can_handle(adapter: PlatformDownloader, url: str) -> str:
    """安全调用 can_handle,返回 是/否/错误。"""
    try:
        return "是" if adapter.can_handle(url) else "否"
    except Exception:
        return "错误"


def _parse_scalar(value: str) -> Any:
    """将命令行字符串尝试解析为 bool/int/float,失败则保留字符串。"""
    low = value.strip().lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _get_config_by_key(config: AppConfig, key: str) -> Any:
    """按点号分隔的 key 路径从配置中读取值。"""
    current: Any = config.model_dump()
    for part in key.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            typer.echo(f"未找到配置项: {key}", err=True)
            raise typer.Exit(1)
    return current


def _set_config_by_key(key: str, value: str, config_path: Optional[Path]) -> None:
    """按点号分隔的 key 路径写回 YAML 配置文件。

    若配置文件不存在,先用 ``DEFAULT_CONFIG_YAML`` 创建,再读取、设值、写回。
    注意 YAML 往返会丢失注释,这是 ``yaml.safe_dump`` 的固有行为。
    """
    path = config_path if config_path is not None else get_default_config_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG_YAML, encoding="utf-8")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        data = {}
    parts = key.split(".")
    current: dict[str, Any] = data
    for part in parts[:-1]:
        node = current.get(part)
        if not isinstance(node, dict):
            node = {}
            current[part] = node
        current = node
    current[parts[-1]] = _parse_scalar(value)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# download 子命令
# ---------------------------------------------------------------------------
@app.command()
def download(
    url: str = typer.Argument(..., help="视频 URL"),
    quality: Optional[str] = typer.Option(
        None, "--quality", "-q", help="清晰度(format_id 或描述如 1080p)"
    ),
    output: str = typer.Option("./downloads", "--output", "-o", help="输出目录"),
    platform: Optional[str] = typer.Option(
        None, "--platform", "-p", help="指定平台(不指定自动判断)"
    ),
    cookies: Optional[Path] = typer.Option(
        None, "--cookies", help="cookies.txt 文件路径(用于会员内容)"
    ),
    cookies_from_browser: Optional[str] = typer.Option(
        None,
        "--cookies-from-browser",
        help="从浏览器读取 cookies: chrome/edge/firefox/safari",
    ),
    config_path: Optional[Path] = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """下载单个视频。"""
    config = _load_app_config(config_path)
    options = _build_download_options(config, quality, output)
    # cookies 设置:命令行优先,未传则从配置读取默认值
    options.cookies_file = str(cookies) if cookies else config.cookies.file
    options.cookies_from_browser = (
        cookies_from_browser if cookies_from_browser else config.cookies.browser
    )
    dispatcher = create_dispatcher(config)
    task_id = uuid4().hex

    # 用 rich.progress 创建进度条 callback,with 自动启停
    with _make_progress_callback(task_id) as callback:
        if platform:
            # 指定 --platform 时跳过自动选择,在注册表中按 name 查找适配器
            registry = create_default_registry()
            adapter = _find_adapter_by_name(registry, platform)
            if adapter is None:
                typer.echo(f"未找到平台适配器: {platform}", err=True)
                raise typer.Exit(1)
            result = adapter.download(url, options, callback, task_id)
        else:
            result = dispatcher.dispatch_sync(url, options, callback, task_id)

    # 输出结果到 stdout,失败时退出码 1
    if result.success:
        typer.echo(f"下载成功: {result.file_path}")
    else:
        typer.echo(f"下载失败: {result.error}", err=True)
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# batch 子命令
# ---------------------------------------------------------------------------
@app.command()
def batch(
    file: Path = typer.Argument(..., help="URL 列表文件(每行一个)"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """批量并发下载(从文件读取 URL 列表)。"""
    if not file.exists():
        typer.echo(f"文件不存在: {file}", err=True)
        raise typer.Exit(1)
    # 读取所有行,过滤空行与 # 开头注释
    lines = file.read_text(encoding="utf-8").splitlines()
    urls = [
        ln.strip()
        for ln in lines
        if ln.strip() and not ln.strip().startswith("#")
    ]
    if not urls:
        typer.echo("URL 列表为空", err=True)
        raise typer.Exit(1)

    config = _load_app_config(config_path)
    # 并发数取自 download.concurrency,经 dispatcher 内部 TaskQueue 限流
    dispatcher = create_dispatcher(config)
    options = DownloadOptions(
        output_dir=config.download.outputDir,
        filename_template=config.download.filenameTemplate,
        overwrite=False,
        extra_args=list(config.ytdlp.extraArgs),
    )

    async def _download_one(url: str) -> tuple[str, DownloadResult]:
        """单个 URL 的异步下载任务,打印开始/完成,返回 (url, result)。"""
        task_id = uuid4().hex
        typer.echo(f"[开始] {url} (task={task_id[:8]})")
        try:
            # dispatch_async 内部经 TaskQueue 限流,适配器 download 在线程池执行
            result = await dispatcher.dispatch_async(url, options, None, task_id)
        except Exception as e:
            result = DownloadResult(success=False, error=str(e), task_id=task_id)
        if result.success:
            typer.echo(f"[完成] {url} -> {result.file_path}")
        else:
            typer.echo(f"[失败] {url} -> {result.error}", err=True)
        return url, result

    async def _run_all() -> list[tuple[str, DownloadResult]]:
        return await asyncio.gather(*(_download_one(u) for u in urls))

    results = asyncio.run(_run_all())

    # 末尾汇总:成功数、失败数、失败 URL 列表
    success_count = sum(1 for _, r in results if r.success)
    failed_urls = [url for url, r in results if not r.success]
    typer.echo(f"\n汇总: 成功 {success_count}, 失败 {len(failed_urls)}")
    if failed_urls:
        typer.echo("失败 URL 列表:")
        for url in failed_urls:
            typer.echo(f"  - {url}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# info 子命令
# ---------------------------------------------------------------------------
@app.command()
def info(
    url: str = typer.Argument(..., help="视频 URL"),
    cookies: Optional[Path] = typer.Option(
        None, "--cookies", help="cookies.txt 文件路径(查询会员清晰度需要登录态)"
    ),
    cookies_from_browser: Optional[str] = typer.Option(
        None,
        "--cookies-from-browser",
        help="从浏览器读取 cookies: chrome/edge/firefox/safari",
    ),
    config_path: Optional[Path] = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """提取并打印视频元信息(不下载)。"""
    config = _load_app_config(config_path)
    # cookies 设置:命令行优先,未传则从配置读取默认值
    cookies_file = str(cookies) if cookies else config.cookies.file
    cookies_browser = (
        cookies_from_browser if cookies_from_browser else config.cookies.browser
    )
    registry = create_default_registry()
    try:
        adapter = registry.select(url)
        try:
            # 优先尝试传入 cookies 参数(适配支持 cookies 的适配器,如 ytdlp/cctv)
            video_info = adapter.extract_info(
                url,
                cookies_file=cookies_file,
                cookies_from_browser=cookies_browser,
            )
        except TypeError:
            # 适配器签名不支持 cookies 参数,回退到仅传 url
            video_info = adapter.extract_info(url)
    except Exception as e:
        typer.echo(f"提取视频信息失败: {e}", err=True)
        raise typer.Exit(1)

    # 基本信息表:标题、时长、上传者、平台
    info_table = Table(title="视频信息")
    info_table.add_column("字段", style="cyan", no_wrap=True)
    info_table.add_column("值")
    info_table.add_row("标题", video_info.title or "(无)")
    info_table.add_row(
        "时长", f"{video_info.duration:.0f}s" if video_info.duration else "(未知)"
    )
    info_table.add_row("上传者", video_info.uploader or "(未知)")
    info_table.add_row("平台", video_info.platform or "(未知)")
    _console.print(info_table)

    # 可用清晰度列表:format_id / ext / resolution / filesize
    if video_info.formats:
        fmt_table = Table(title="可用清晰度")
        fmt_table.add_column("format_id", style="cyan")
        fmt_table.add_column("ext")
        fmt_table.add_column("resolution")
        fmt_table.add_column("filesize", justify="right")
        for f in video_info.formats:
            size = f"{f.filesize / 1024 / 1024:.2f}MB" if f.filesize else "-"
            fmt_table.add_row(f.format_id, f.ext, f.resolution, size)
        _console.print(fmt_table)
    else:
        typer.echo("未解析到可用清晰度。")


# ---------------------------------------------------------------------------
# serve 子命令(启动 Web UI)
# ---------------------------------------------------------------------------
@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="监听地址"),
    port: int = typer.Option(8000, "--port", "-p", help="监听端口"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """启动 Web UI。"""
    import os

    import uvicorn

    from ..web.app import app as web_app

    # 把 config_path 写入环境变量供 web app 读取(简化,避免重新设计依赖注入)
    if config_path:
        os.environ["UVD_CONFIG_PATH"] = str(config_path)
    typer.echo(f"启动 Web UI: http://{host}:{port}")
    uvicorn.run(web_app, host=host, port=port)


# ---------------------------------------------------------------------------
# config 子命令组
# ---------------------------------------------------------------------------
@config_app.command("get")
def config_get(
    key: str = typer.Argument(..., help="如 download.outputDir"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """读取配置项(按点号分隔路径)。"""
    config = _load_app_config(config_path)
    value = _get_config_by_key(config, key)
    typer.echo(value)


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="如 download.outputDir"),
    value: str = typer.Argument(..., help="配置值(自动解析 bool/int/float/str)"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """设置配置项并写回 YAML 文件。"""
    _set_config_by_key(key, value, config_path)
    typer.echo(f"已设置 {key} = {value}")


@config_app.command("path")
def config_path_cmd() -> None:
    """打印默认配置文件路径。"""
    typer.echo(get_default_config_path())


# ---------------------------------------------------------------------------
# platforms 子命令
# ---------------------------------------------------------------------------
@app.command()
def platforms(
    config_path: Optional[Path] = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """列出所有已注册平台适配器。"""
    _load_app_config(config_path)
    registry = create_default_registry()
    adapters = registry.list_adapters()

    # 两个测试 URL,用于演示各适配器的 can_handle 结果
    test_youtube = "https://www.youtube.com/"
    test_wechat = "https://channels.weixin.qq.com/"

    table = Table(title="已注册平台适配器")
    table.add_column("name", style="cyan")
    table.add_column("priority", justify="right")
    table.add_column(f"can_handle({test_youtube})")
    table.add_column(f"can_handle({test_wechat})")
    for adapter in adapters:
        # list_adapters 不暴露 priority 数值,故该列留空(可空)
        table.add_row(
            adapter.name,
            "",
            _safe_can_handle(adapter, test_youtube),
            _safe_can_handle(adapter, test_wechat),
        )
    _console.print(table)


if __name__ == "__main__":
    app()
