# Universal Video Downloader (UVD)

通用流媒体视频下载器,基于 Python + yt-dlp,保留微信视频号 MITM 解密能力。

## 特性

- **CLI / Web UI 双形态**:命令行工具与 Web 界面任选,满足不同使用场景
- **多平台支持**:YouTube、Bilibili、抖音、快手、小红书、微博视频、Twitter·X、Instagram、TikTok、Facebook
- **微信视频号专用方案**:MITM 代理 + 动态自签证书 + JS 注入 + ISAAC 解密 + 多线程分块下载
- **批量并发下载**:基于 asyncio 信号量的并发限流,可配置并发数
- **实时进度回调**:CLI 进度条(rich)+ WebSocket 事件推送(Web UI)
- **统一配置管理**:`~/.uvd/config.yaml`,首次运行自动生成默认配置

## 安装

```bash
pip install -e .
```

首次运行会自动创建 `~/.uvd/config.yaml` 默认配置文件。

## 快速开始

```bash
# 下载单个视频
uvd download https://www.youtube.com/watch?v=xxx

# 下载微信视频号(首次运行自动生成 CA 证书)
uvd download https://channels.weixin.qq.com/...

# 查看视频信息(不下载)
uvd info <url>

# 批量下载(每行一个 URL)
uvd batch urls.txt

# 启动 Web UI
uvd serve
```

## Windows 启动

- 双击 `scripts/start_uvd.bat` 启动 WebUI,自动打开默认浏览器到 `http://127.0.0.1:8000`
- 首次运行会自动在桌面创建「UVD WebUI」快捷方式(带图标),后续可直接双击快捷方式启动
- 按 `Ctrl+C` 停止服务
- 命令行用户也可用 `uvd serve`

## 默认下载策略

**不传 `--quality` 时**(默认行为,v2 起):

自动选择**最高分辨率 + 4K 优先 + 同分辨率最高码率**的视频流,与最佳音频流合并为 mp4。

策略对应 yt-dlp 的 `format_sort`:

- `res:4` 分辨率优先(4K > 1080p > 720p)
- `hdr:1` HDR 优先
- `vcodec:1` 视频编码质量
- `acodec:1` 音频编码质量
- `size:1` 文件大者优先(码率高)
- `br:1` 码率

示例:下载 B 站视频自动选 1080p 高码率 + opus 音频;若会员 4K 可用(配合 cookies)则自动选 4K HDR。

**传 `--quality` 时**:

直接使用指定的 format_id(可用 `uvd info <url>` 查询所有可选 format_id),不走自动策略。

## Cookies 与会员内容

**适用场景**:下载需要登录才能访问的内容(如 B 站会员 4K 视频、Twitter 私密推文等)。

**方式一:从浏览器提取 cookies**(推荐):

```bash
uvd download https://www.bilibili.com/video/BVxxx --cookies-from-browser chrome
```

支持的浏览器:chrome / edge / firefox / safari。会自动从浏览器本地存储提取目标站点的登录 cookies。

**方式二:使用 cookies.txt 文件**:

1. 安装浏览器扩展「Get cookies.txt LOCALLY」(Chrome/Edge)或「cookies.txt」(Firefox)
2. 在目标网站登录后,用扩展导出 cookies.txt
3. 下载时指定:

```bash
uvd download https://www.bilibili.com/video/BVxxx --cookies /path/to/cookies.txt
```

**Web UI 上传 cookies**:

在 Web UI 首页选择「Cookies 来源」→「上传文件」,选择 cookies.txt 上传,文件会保存到 `~/.uvd/cookies/`(权限 0600)。

**配置文件默认值**(在 `~/.uvd/config.yaml` 中):

```yaml
cookies:
  browser: null        # chrome/edge/firefox/safari,优先级低于 file
  file: null           # cookies.txt 路径
```

设置后所有下载默认使用该 cookies,无需每次传参。

**⚠️ 法律声明**:

> 使用 cookies 下载会员内容:请确保仅下载您已合法授权访问的内容。
> 禁止用于下载未授权付费内容、规避版权保护或商业用途。
> 使用者自行承担法律责任。

## 配置文件

配置文件位于 `~/.uvd/config.yaml`,首次运行自动生成:

```yaml
config_version: 2

download:
  defaultHighest: true           # v2 起默认 true,自动选最高分辨率
  outputDir: ./downloads
  concurrency: 3
  filenameTemplate: "%(title)s.%(ext)s"

proxy:
  system: true
  port: 2023

cookies:                          # v2 新增
  browser: null
  file: null

wechat_channels:
  enabled: true
  certDir: ~/.uvd/certs
  jsAssetsDir: ./assets/wechat_channels
  decrypt:
    wasmUrl: https://res.wx.qq.com/t/wx_fed/cdn_libs/res/decrypt-video-core/1.3.0/wasm_video_decode.wasm

ytdlp:
  extraArgs: []
```

### 字段说明

| 字段 | 说明 |
|------|------|
| `download.defaultHighest` | 是否默认选择最高清晰度 |
| `download.outputDir` | 下载文件保存目录 |
| `download.concurrency` | 并发下载数量 |
| `download.filenameTemplate` | 文件名模板(yt-dlp 格式,如 `%(title)s.%(ext)s`) |
| `proxy.system` | 是否启用系统代理(视频号 MITM 需要) |
| `proxy.port` | MITM 代理监听端口 |
| `wechat_channels.enabled` | 是否启用微信视频号适配器 |
| `wechat_channels.certDir` | CA 根证书存放目录 |
| `wechat_channels.jsAssetsDir` | JS 注入脚本资源目录 |
| `wechat_channels.decrypt.wasmUrl` | 视频解密 WASM 资源地址 |
| `ytdlp.extraArgs` | 传递给 yt-dlp 的额外命令行参数 |

可通过 `uvd config get <key>` 读取、`uvd config set <key> <value>` 修改配置项。

## 平台支持

| 平台 | 适配器 | URL 样例 | 备注 |
|------|--------|----------|------|
| YouTube | YtDlpAdapter | `https://www.youtube.com/watch?v=xxx` | yt-dlp 通用 |
| Bilibili | YtDlpAdapter | `https://www.bilibili.com/video/BVxxx` | yt-dlp 通用 |
| 抖音 | YtDlpAdapter | `https://www.douyin.com/video/xxx` | yt-dlp 通用 |
| 快手 | YtDlpAdapter | `https://www.kuaishou.com/short-video/xxx` | yt-dlp 通用 |
| 小红书 | YtDlpAdapter | `https://www.xiaohongshu.com/explore/xxx` | yt-dlp 通用 |
| 微博视频 | YtDlpAdapter | `https://weibo.com/xxx` | yt-dlp 通用 |
| Twitter·X | YtDlpAdapter | `https://x.com/xxx/status/xxx` | yt-dlp 通用 |
| Instagram | YtDlpAdapter | `https://www.instagram.com/p/xxx` | yt-dlp 通用 |
| TikTok | YtDlpAdapter | `https://www.tiktok.com/@xxx/video/xxx` | yt-dlp 通用 |
| Facebook | YtDlpAdapter | `https://www.facebook.com/xxx/videos/xxx` | yt-dlp 通用 |
| 央视频(cctv.com) | YtDlpAdapter | `https://tv.cctv.com/...` | 新闻、综艺、纪录片(通过 yt-dlp) |
| 央视频 App | YtDlpAdapter | `https://yangshipin.cctv.cn/...` | App 网页版内容(通过 yt-dlp) |
| 微信视频号 | WechatChannelsAdapter | `https://channels.weixin.qq.com/...` | MITM + ISAAC 解密 |

## 视频号首次使用步骤

首次运行 `uvd download --platform wechat <url>` 会自动生成 CA 证书到 `~/.uvd/certs/`。

### 1. 安装根证书(Windows)

1. 双击 `~/.uvd/certs/ca.crt`
2. 选择「安装证书」
3. 选择「本地计算机」
4. 选择「将所有的证书放入下列存储」
5. 点击「浏览」,选择「受信任的根证书颁发机构」
6. 完成安装向导

### 2. 设置系统代理

Windows 设置 → 网络和 Internet → 代理 → 手动设置代理 → `127.0.0.1:2023`

### 3. 浏览器访问

浏览器访问视频号页面,程序自动捕获并下载。

## 开发

```bash
# 运行全部测试
pytest tests/

# 运行特定测试文件
pytest tests/test_config.py

# 跳过需要网络的测试
pytest tests/ -m "not network"
```

## 致谢

- [ltaoo/wx_channels_download](https://github.com/ltaoo/wx_channels_download) - 微信视频号下载开源项目
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - 通用视频下载库
