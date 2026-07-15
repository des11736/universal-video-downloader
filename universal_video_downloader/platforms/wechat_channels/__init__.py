"""微信视频号下载适配器包。

导出适配器与核心工具,供上层通过
``from universal_video_downloader.platforms.wechat_channels import WechatChannelsAdapter``
方式引用。
"""

from __future__ import annotations

from .adapter import WechatChannelsAdapter
from .downloader import MultiThreadDownloader, calculate_chunks
from .isaac_decrypt import ISAAC64, decrypt_data

__all__ = [
    "WechatChannelsAdapter",
    "MultiThreadDownloader",
    "calculate_chunks",
    "ISAAC64",
    "decrypt_data",
]
