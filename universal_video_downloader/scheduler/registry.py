"""适配器注册表。

按优先级管理所有已注册的 ``PlatformDownloader`` 适配器,并提供按 URL 选择
适配器的功能。优先级数值越大越优先匹配;当所有适配器都拒绝处理某 URL 时,
回退到 ytdlp 兜底适配器(若已注册)。
"""

from __future__ import annotations

from ..core.base import PlatformDownloader


class AdapterRegistry:
    """适配器注册表,按优先级匹配适配器。

    内部以 ``[(priority, adapter), ...]`` 列表存储,priority 越大越优先。
    ``select`` 方法按优先级降序遍历,返回第一个 ``can_handle(url)=True``
    的适配器;若全部不匹配,回退到名为 ``"ytdlp"`` 的兜底适配器。
    """

    def __init__(self) -> None:
        # (priority, adapter) 列表,高优先级在前
        self._adapters: list[tuple[int, PlatformDownloader]] = []

    def register(self, adapter: PlatformDownloader, priority: int = 0) -> None:
        """注册适配器。priority 越大越优先。"""
        self._adapters.append((priority, adapter))
        # 按优先级降序排序,高优先级在前
        self._adapters.sort(key=lambda x: x[0], reverse=True)

    def select(self, url: str) -> PlatformDownloader:
        """按优先级遍历,返回第一个 can_handle(url)=True 的适配器。

        遍历过程中若某适配器 ``can_handle`` 抛异常则跳过。若全部不匹配,
        回退到名为 ``"ytdlp"`` 的兜底适配器(若已注册);否则抛出 ValueError。
        """
        for _, adapter in self._adapters:
            try:
                if adapter.can_handle(url):
                    return adapter
            except Exception:
                # can_handle 抛异常时跳过该适配器
                continue
        # 兜底:返回 ytdlp(若注册了),否则抛错
        for _, adapter in self._adapters:
            if adapter.name == "ytdlp":
                return adapter
        raise ValueError(f"无适配器可处理 URL: {url}")

    def list_adapters(self) -> list[PlatformDownloader]:
        """返回全部已注册适配器,按优先级降序。"""
        return [a for _, a in self._adapters]


def create_default_registry() -> AdapterRegistry:
    """创建默认注册表并注册内置适配器。

    注册顺序(按优先级从高到低):
        - ``WechatChannelsAdapter`` priority=100(视频号优先匹配)
        - ``CctvAdapter`` priority=80(央视频,介于视频号与 ytdlp 之间)
        - ``YtDlpAdapter`` priority=0(兜底)

    ``WechatChannelsAdapter`` 与 ``CctvAdapter`` 的注册均用 try/except 包装,
    因 mitmproxy 等依赖可能未安装,失败时跳过而不影响整体可用性。

    Returns:
        已注册默认适配器的 ``AdapterRegistry``。
    """
    # 延迟导入,使 registry 模块本身不依赖 yt-dlp / mitmproxy
    from ..platforms.ytdlp_adapter import YtDlpAdapter

    registry = AdapterRegistry()
    # ytdlp 作为兜底适配器,优先级最低
    registry.register(YtDlpAdapter(), priority=0)

    # 央视频适配器优先级介于视频号(100)与 ytdlp(0)之间
    try:
        from ..platforms.cctv_adapter import CctvAdapter

        registry.register(CctvAdapter(), priority=80)
    except Exception:
        # 央视频适配器注册失败时跳过,不影响其他适配器
        pass

    # 视频号适配器优先级最高,但可能因依赖缺失而注册失败
    try:
        from ..platforms.wechat_channels.adapter import WechatChannelsAdapter

        registry.register(WechatChannelsAdapter(), priority=100)
    except Exception:
        # mitmproxy 等依赖未安装时跳过视频号适配器
        pass

    return registry
