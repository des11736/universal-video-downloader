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

# 安装依赖
pip install -e .
```

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

#### 方式一:Web UI 上下载(推荐)

**第 1 步:首次运行前,先用 CLI 生成并安装证书**

```bash
uvd download --platform wechat "https://channels.weixin.qq.com"
```

终端会输出证书路径并等待你安装证书(按回车继续)。**完成证书安装后再继续**:

- **Windows**:双击 `certs/ca.crt` → 安装证书 → 本地计算机 → 受信任的根证书颁发机构
- **macOS**:双击 `certs/ca.pem` → 钥匙串访问 → 右键证书 → 显示简介 → 信任 → 始终信任

> 证书只需安装一次,后续无需重复。

**第 2 步:设置系统代理**

将系统代理设为 `127.0.0.1:8888`:

- **Windows**:设置 → 网络和 Internet → 代理 → 手动设置代理 → `127.0.0.1:8888`
- **macOS**:系统设置 → 网络 → Wi-Fi → 详细信息 → 代理 → HTTP/HTTPS 代理 → `127.0.0.1:8888`

**第 3 步:在 Web UI 中提交下载**

1. 打开 Web UI(http://127.0.0.1:8000)
2. 在输入框粘贴视频号链接,例如:`https://channels.weixin.qq.com/web/pages/feed/xxxxx`
3. 点击「下载」按钮(**注意:不要点「分析」**,视频号不支持预分析)
4. 任务状态变为 RUNNING,显示「等待视频信息...」(进度条在 5%-20% 之间)

**第 4 步:在浏览器中播放视频**

1. 打开浏览器(Chrome / Edge / Firefox)
2. 访问你要下载的视频号页面
3. **播放视频**,MITM 代理会自动拦截并捕获视频信息
4. 捕获成功后,下载进度会从 20% 跳到实际下载进度
5. 下载完成后,进度条显示 100%,文件保存在 `downloads/` 目录

**第 5 步:完成后取消系统代理**

下载完成后,记得在系统设置中关闭代理,否则无法正常上网。

#### 方式二:CLI 命令行下载

```bash
# 首次运行(生成证书 + 提示安装)
uvd download --platform wechat "https://channels.weixin.qq.com/web/pages/feed/xxxxx"
```

首次运行终端会提示:
1. 安装根证书(按上文步骤)
2. 设置系统代理为 `127.0.0.1:8888`
3. 按回车继续

然后在浏览器中访问视频号页面并播放视频,程序会自动捕获并下载。

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
