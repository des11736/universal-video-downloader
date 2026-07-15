# UVD · 通用视频下载器

> 一个支持多平台的通用视频下载工具,提供 CLI 命令行和 Web UI 两种使用方式。

## 支持平台

| 平台 | 适配器 | 说明 |
|------|--------|------|
| B站 (Bilibili) | yt-dlp | 支持所有清晰度,含 4K/1080P |
| YouTube | yt-dlp | 支持所有清晰度,会员内容需 cookies |
| 央视频 (CCTV) | cctv | 覆盖 tv.cctv.com / yangshipin.cctv.cn |
| 抖音 / 快手 | yt-dlp | 短视频平台 |
| 小红书 / 微博 | yt-dlp | 社交媒体平台 |
| X (Twitter) / Instagram / TikTok / Facebook | yt-dlp | 海外平台 |
| 微信视频号 | wechat_channels | 需配合浏览器 + 证书安装 |

## 快速开始

### 1. 安装

```bash
# 克隆仓库
git clone https://github.com/des11736/universal-video-downloader.git
cd universal-video-downloader

# 安装依赖
pip install -e .
```

### 2. 使用 Web UI(推荐)

**Windows 用户**:双击 `scripts/start_uvd.bat` 即可,首次运行会自动创建桌面快捷方式。

**命令行启动**:

```bash
uvd serve
```

启动后浏览器访问 http://127.0.0.1:8000

#### Web UI 使用流程

1. **粘贴视频链接**到输入框
2. **点击「分析」** — 自动获取视频信息(标题、时长、上传者)和所有可选清晰度
3. **选择清晰度** — 默认勾选「最佳画质」(自动选最高分辨率+最高码率),也可手动选择
4. **点击「下载」** — 实时显示下载进度
5. **下载完成后**:
   - 点击「预览」在线播放视频
   - 点击「打开目录」在文件管理器中定位文件

#### 会员内容(如 B站 4K)

如需下载会员专属清晰度:

1. 在「Cookies 来源」下拉框选择浏览器(如 Chrome)
2. 或选择「上传 cookies.txt」上传导出的 cookies 文件
3. 确认法律声明后即可下载会员内容

### 3. 使用 CLI 命令行

```bash
# 下载视频(自动选择最高画质)
uvd download https://www.bilibili.com/video/BVxxxxx

# 指定清晰度
uvd download https://www.bilibili.com/video/BVxxxxx --quality 30064

# 下载会员 4K 内容(需 Chrome 已登录)
uvd download https://www.bilibili.com/video/BVxxxxx --cookies-from-browser chrome

# 查看视频信息与可选清晰度
uvd info https://www.bilibili.com/video/BVxxxxx

# 批量下载(每行一个 URL)
uvd batch urls.txt

# 查看支持的平台
uvd platforms

# 配置管理
uvd config get download.outputDir
uvd config set download.defaultHighest true
```

## 核心特性

### 自动选择最佳画质

不指定 `--quality` 时,默认按以下优先级自动选择:
- 分辨率最高(4K > 1080P > 720P)
- HDR 优先
- 视频码率最高 (vbr)
- 音频码率最高 (abr)
- 帧率最高 (fps)

策略为 `bestvideo+bestaudio` 合并输出 mp4,确保下载的是分离的最高画质视频流+音频流,而非低码率的组合流。

### Cookies 支持

- **浏览器读取**:直接从 Chrome / Edge / Firefox 读取已登录的 cookies
- **文件上传**:支持 Netscape 格式的 cookies.txt 文件
- Web UI 提供 cookies 上传与管理功能,文件存储在 `~/.uvd/cookies/`(权限 0600)

### 微信视频号

微信视频号适配器采用 MITM 代理方案:
- 动态生成 SSL 证书并自动安装到系统信任
- 拦截视频号网页请求,提取加密视频流
- 使用 ISAAC 解密算法还原原始视频
- 多线程分块下载

首次使用需安装证书,按终端提示操作即可。

## 配置

默认配置文件位于 `~/.uvd/config.yaml`:

```yaml
download:
  outputDir: ./downloads
  filenameTemplate: "%(title)s.%(ext)s"
  concurrency: 3
  defaultHighest: true

ytdlp:
  extraArgs: []

cookies:
  browser: ""
  file: ""
```

可通过 `uvd config` 命令或直接编辑文件修改。

## 项目结构

```
universal-video-downloader/
├── universal_video_downloader/
│   ├── core/           # 数据模型、抽象基类、配置
│   ├── platforms/      # 平台适配器
│   │   ├── ytdlp_adapter.py      # yt-dlp 通用适配器(兜底)
│   │   ├── cctv_adapter.py       # 央视频适配器
│   │   └── wechat_channels/      # 微信视频号(MITM + ISAAC)
│   ├── scheduler/      # 适配器注册表、任务队列、调度器
│   ├── cli/            # CLI 命令行入口
│   └── web/            # Web UI 后端 + 前端
├── scripts/            # 启动脚本、图标生成
├── assets/             # 图标资源
└── pyproject.toml      # 项目配置
```

## 法律声明

- 本工具仅供个人学习与备份无 DRM 内容使用
- **不支持**下载付费/DRM 保护内容
- 使用 cookies 下载会员内容时,请确保仅下载您已合法授权访问的内容
- 禁止用于下载未授权付费内容、规避版权保护或商业用途
- 使用者自行承担法律责任

## License

MIT
