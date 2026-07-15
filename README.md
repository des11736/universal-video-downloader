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

微信视频号没有公开的视频 URL,无法像其他平台一样直接粘贴链接下载。适配器采用 **MITM 代理**方案,通过拦截浏览器与微信服务器之间的 HTTPS 流量来捕获视频信息。

#### 工作原理

```
浏览器 ←→ MITM 代理(127.0.0.1:8888) ←→ 微信视频号服务器
                ↓
         注入 JS 脚本 → 捕获视频 URL + 解密密钥
                ↓
         多线程下载加密视频 → ISAAC 解密 → 输出 mp4
```

1. 程序在本地启动 MITM 代理(端口 8888)
2. 动态生成 SSL 根证书,需手动安装到系统信任库
3. 用户手动设置系统代理指向 `127.0.0.1:8888`
4. 在浏览器中访问视频号页面并播放视频
5. 代理注入 JS 脚本,捕获视频 URL 和解密密钥
6. 多线程下载加密视频分片,使用 ISAAC 算法解密,合并为 mp4

#### 操作位置与准备工作

视频号下载需要同时操作三个位置，请不要把命令粘贴到浏览器地址栏：

| 操作位置 | 用途 | 要做什么 |
| --- | --- | --- |
| **终端 A（Windows PowerShell / CMD）** | 运行 `uvd`、启动代理并显示下载进度 | 全程保持打开，不能在下载期间关闭 |
| **Windows 系统设置** | 将系统代理临时指向本地代理 | 代理地址为 `127.0.0.1:8888` |
| **浏览器（Chrome / Edge / Firefox）** | 登录视频号、打开页面并播放视频 | 必须实际点击播放，程序才可捕获视频流 |

以下示例以 Windows 为例。所有 `uvd` 命令都在**终端 A**中、项目根目录执行。已经成功启动过一次 `scripts/start_uvd.bat` 时，依赖和 `uvd` 命令已自动安装，无需再次执行安装命令：

```powershell
# 进入项目目录
cd "D:\\codex_project\\视频号视频爬取"

# 可选：确认命令已可用
uvd --help
```

> 如果尚未运行过启动脚本，或显示“`uvd` 不是内部或外部命令”，请先双击 `scripts/start_uvd.bat` 完成自动安装；也可手动依次执行 `python -m pip install --upgrade pip` 和 `python -m pip install -e .` 后重新打开终端。请使用完整的视频页面链接，例如 `https://channels.weixin.qq.com/web/pages/feed/xxxxx`，不要只使用首页链接。

#### 第一次使用：安装本地根证书

1. **在终端 A**执行下面命令。无需指定 `--platform`，程序会自动识别视频号；如需强制指定，正确的名称是 `wechat_channels`，不是 `wechat`。

   ```powershell
   uvd download "https://channels.weixin.qq.com/web/pages/feed/xxxxx"
   # 等价的强制指定写法：
   # uvd download "https://channels.weixin.qq.com/web/pages/feed/xxxxx" --platform wechat_channels
   ```

   > `uvd download --platform wechat "..."` 会报“未找到平台适配器: wechat”，因为 `wechat` 不是有效名称。

2. **仍在终端 A**，程序会打印类似“已生成 CA 根证书”的完整文件路径，并显示“按回车继续”。先不要按回车。

3. **在 Windows 文件资源管理器**中，打开终端打印的目录，双击 `ca.crt`，按以下选项安装：

   ```text
   安装证书 → 本地计算机 → 将所有证书放入下列存储 → 浏览
   → 受信任的根证书颁发机构 → 完成
   ```

4. 证书安装完成后，可在**终端 A**按 `Ctrl+C` 结束这次初始化命令；证书会保留，后续不需要重新安装。

#### 每次下载前：设置代理

1. **在 Windows 系统设置**中打开：`设置 → 网络和 Internet → 代理 → 手动设置代理`。
2. 打开“使用代理服务器”，填写：

   ```text
   地址：127.0.0.1
   端口：8888
   ```

3. 保持该设置开启，直到本次下载完成。若 8888 端口已被其他程序占用，请先关闭占用该端口的程序。

#### 方式一：使用 Web UI 下载

1. **在终端 A**执行并保持运行：

   ```powershell
   uvd serve
   ```

2. **在浏览器**打开 `http://127.0.0.1:8000`。在 Web UI 中粘贴完整的视频号页面链接，点击「下载」；**不要点击「分析」**，视频号不支持预分析。
3. **回到终端 A**。首次在当前 Web 服务中提交视频号任务时，终端会再次显示证书/代理提示；证书已安装且代理已设置后，按回车继续，让代理开始监听。
4. **在浏览器的另一个标签页**打开同一视频号页面，登录后**实际播放视频**。终端和 Web UI 会先显示“等待视频信息”，捕获成功后进度会开始增长。
5. 下载完成后，Web UI 中可点击「预览」或「打开目录」；文件默认保存在 `downloads/`。

#### 方式二：直接在 CLI 下载

1. **在终端 A**执行，并保持该终端不要关闭：

   ```powershell
   uvd download "https://channels.weixin.qq.com/web/pages/feed/xxxxx"
   ```

2. 若终端提示“按回车继续”，确认根证书已安装、系统代理已设置为 `127.0.0.1:8888` 后，**在终端 A 按回车**。
3. **在浏览器**打开同一个视频号页面并播放视频。终端捕获到视频信息后会开始下载，成功时输出 `下载成功: ...`。

#### 下载完成后：关闭系统代理

**在 Windows 系统设置**中回到 `设置 → 网络和 Internet → 代理`，关闭“使用代理服务器”。否则其他网站可能无法正常访问。

#### 注意事项

- 证书只需安装一次,后续使用无需重复安装
- MITM 代理端口固定为 **8888**,确保该端口未被占用
- 下载过程中需要**保持浏览器打开**并播放视频,程序通过代理捕获视频流
- 超时时间为 **5 分钟**,超时后任务自动失败
- 下载完成后记得**关闭系统代理**
- ISAAC 解密基于公开算法规范实现,与微信客户端原版的兼容性需用真实视频样本验证
- 如需取消下载,在 Web UI 中等待超时,或在 CLI 中按 `Ctrl+C`

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
