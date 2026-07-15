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
| 微信视频号 | wechat_channels | 启动 WebUI 后配置代理，在页面点击注入的下载按钮 |

## 快速开始

### 1. 安装

#### Windows

```bash
# 克隆仓库
git clone https://github.com/des11736/universal-video-downloader.git
cd universal-video-downloader

# 首次启动：自动检查 Python、安装缺失依赖并启动 Web UI
.\scripts\start_uvd.bat
```

也可以直接双击 `scripts/start_uvd.bat`。脚本会自动完成以下操作：

1. 检查 Python 是否已安装；需要 **Python 3.10+**，且安装 Python 时必须勾选“Add Python to PATH”。
2. 检测 `fastapi`、`uvicorn`、`yt-dlp` 等依赖；仅在缺失时自动运行 `python -m pip install --upgrade pip` 和 `python -m pip install -e .`。
3. 创建桌面快捷方式并启动 Web UI，随后自动打开 `http://127.0.0.1:8000`。
4. 同时启动视频号页面监听器（`127.0.0.1:8888`）；首次使用视频号时仍需按下文安装根证书并设置 Windows 系统代理。

> 因此 Windows 用户通常**不需要先手动执行**安装命令。只有启动脚本明确提示安装失败时，才在 PowerShell/CMD 中进入项目目录后依次执行：`python -m pip install --upgrade pip` 和 `python -m pip install -e .`。

#### macOS

```bash
# 克隆仓库
git clone https://github.com/des11736/universal-video-downloader.git
cd universal-video-downloader

# macOS 自带 Python 3,建议先升级 pip
python3 -m pip install --upgrade pip

# 安装依赖
python3 -m pip install -e .

# 如果缺少 ffi 库(编译某些依赖时需要),先装:
# brew install libffi
```

#### Linux

```bash
git clone https://github.com/des11736/universal-video-downloader.git
cd universal-video-downloader

# 确保有 Python 3.10+
python3 --version

# 安装依赖(建议用虚拟环境)
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# 如缺少编译工具链,先装:
# Ubuntu/Debian: sudo apt install gcc python3-dev
# CentOS/RHEL: sudo yum install gcc python3-devel
```

### 2. 使用 Web UI(推荐)

#### Windows

双击 `scripts/start_uvd.bat` 即可,首次运行会自动创建桌面快捷方式。

#### macOS / Linux

```bash
# 启动 Web 服务
uvd serve

# 或指定 host 和端口
uvd serve --host 0.0.0.0 --port 8000
```

启动后浏览器访问 http://127.0.0.1:8000

> **macOS 提示**:如果遇到「无法验证开发者」安全提示,在「系统设置 → 隐私与安全性」中点击「仍要打开」即可。

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

视频号使用**页面下载按钮**，不使用 Web UI 的 URL 输入框或命令行下载任务。启动脚本已随 WebUI 常驻启动本地页面监听器；浏览器访问视频号页面时，监听器会注入「下载」按钮，文件由浏览器直接下载并解密。

#### 工作原理

```
浏览器 ←→ 页面监听代理(127.0.0.1:8888) ←→ 微信视频号服务器
                   ↓
            注入「下载」按钮
                   ↓
       浏览器 fetch → 解密 → 保存 mp4
```

#### 每次使用：按顺序操作

1. **启动程序（项目目录）**：双击 `scripts\start_uvd.bat`，或在项目根目录运行它。首次启动会自动安装依赖。保持这个 UVD 窗口运行；它同时运行 WebUI 和视频号页面监听器。
2. **首次使用时安装证书（Windows 文件资源管理器）**：启动后打开项目中的 `universal_video_downloader\certs\ca.crt`，双击并按以下选项安装。选择“当前用户”即可，不必为了安装证书以管理员身份运行程序。

   ```text
   安装证书 → 当前用户 → 将所有证书放入下列存储 → 浏览
   → 受信任的根证书颁发机构 → 完成
   ```

3. **设置系统代理（Windows 设置）**：打开 `设置 → 网络和 Internet → 代理 → 手动设置代理`，启用“使用代理服务器”，填写：

   ```text
   地址：127.0.0.1
   端口：8888
   ```

4. **打开并播放视频（已登录的浏览器）**：打开真实的视频详情页，例如 `https://channels.weixin.qq.com/web/pages/feed/xxxxx`，不要只打开首页。页面通过代理加载后会自动出现「下载」按钮；如未立即出现，请刷新页面并开始播放视频。
5. **下载（视频号页面）**：点击注入的「下载」按钮。浏览器会直接获取、解密并保存视频文件；无需返回 WebUI 查看任务进度。
6. **结束后清理（Windows 设置和 UVD 窗口）**：关闭 UVD 窗口，再回到 `设置 → 网络和 Internet → 代理` 关闭“使用代理服务器”。否则其他网站可能无法正常访问。

#### 注意事项

- 证书只需安装一次；若删除 `universal_video_downloader\certs\ca.crt`，重新启动会生成新证书，需要重新安装。
- 监听器端口固定为 **8888**。若启动窗口提示监听失败，请先关闭占用 8888 的程序后重新启动 UVD。
- 视频号必须使用页面内的注入按钮；WebUI 的 URL 输入框和命令行下载任务都不适用于此流程。
- 请仅下载您拥有或获授权访问的内容，并遵守平台规则和适用法律。

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
