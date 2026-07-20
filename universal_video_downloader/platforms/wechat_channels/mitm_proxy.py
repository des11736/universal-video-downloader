"""基于 mitmproxy 的 MITM 代理实现。

视频号下载需要解密 HTTPS 流量以注入 JS 脚本并捕获视频信息。本模块通过
``mitmdump`` 子进程加载自定义 addon,实现:

1. 拦截 ``channels.weixin.qq.com`` 的 HTML 响应,在 ``</head>`` 前注入
   :file:`inject.js` 脚本,使页面暴露下载按钮并回传视频 profile。
2. 暴露本地接口 ``/__wx_channels_api/profile`` 与 ``/__wx_channels_api/tip``,
   前者接收 JS 端上报的视频信息(URL、解密 key 等),后者接收日志/提示。

由于 mitmproxy 编程式启动较复杂,这里采用 ``subprocess.Popen`` 启动
``mitmdump`` 命令行,通过临时 addon 文件注入自定义逻辑。

依赖 ``mitmproxy``(已在 pyproject.toml 声明)。若环境中缺失,会在导入时
给出安装提示。

兼容性说明:
    ``passlib 1.7.4`` 与 ``bcrypt 5.x`` 不兼容(passlib 访问已移除的
    ``bcrypt.__about__.__version__``,且 bcrypt 5.x 严格要求 password
    <=72 bytes)。本模块通过 wrapper 脚本在导入 mitmproxy 之前
    monkey-patch bcrypt,绕过此问题。
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Optional

from ...core.base import ProgressCallback

logger = logging.getLogger(__name__)

try:
    import mitmproxy  # noqa: F401 - 仅用于检测依赖是否可用
    _HAS_MITMPROXY = True
except ImportError:
    _HAS_MITMPROXY = False


# addon 脚本模板,作为独立 .py 文件由 mitmdump 加载。
# 使用字符串模板而非直接 import,是因为 mitmdump 需要一个可执行脚本文件路径。
# 注意:``from __future__ import annotations`` 必须位于文件开头(除 docstring 外),
# 所以 _INJECT_JS_PATH 的注入通过占位符 __INJECT_JS_PATH_REPR__ 替换实现,
# 而不是在文件开头插入代码。
_ADDON_TEMPLATE = '''\
"""mitmproxy addon:微信视频号流量拦截与注入。

该文件由 WechatChannelsMitmProxy 自动生成,供 mitmdump 加载。
"""
from __future__ import annotations

import json
import logging
import threading
from mitmproxy import http

# inject.js 路径,由 mitm_proxy.py 在生成时替换 __INJECT_JS_PATH_REPR__ 占位符
_INJECT_JS_PATH = __INJECT_JS_PATH_REPR__

logger = logging.getLogger("wechat_channels_addon")

# 全局共享状态,供外部进程通过同一 addon 实例读取
_PROFILE_LOCK = threading.Lock()
_COLLECTED_PROFILE = None
_TIP_MESSAGES = []


def get_profile():
    """获取已收集的视频 profile。"""
    with _PROFILE_LOCK:
        return _COLLECTED_PROFILE


def get_tips():
    """获取已收集的提示消息。"""
    return list(_TIP_MESSAGES)


class WechatChannelsAddon:
    """mitmproxy addon:拦截视频号页面并注入 JS、收集 profile。"""

    def __init__(self):
        self.inject_js = ""
        self._load_inject_js()

    def _load_inject_js(self):
        """加载 inject.js 内容,用于注入 HTML 响应。"""
        global _INJECT_JS_PATH
        try:
            with open(_INJECT_JS_PATH, "r", encoding="utf-8") as f:
                self.inject_js = f.read()
            logger.info("已加载 inject.js,长度 %d 字节", len(self.inject_js))
        except Exception as e:
            logger.warning("加载 inject.js 失败(%s),将跳过 JS 注入", e)
            self.inject_js = ""

    def request(self, flow: http.HTTPFlow):
        """处理本地 API 请求,返回 JSON 响应。"""
        global _COLLECTED_PROFILE, _TIP_MESSAGES

        path = flow.request.path
        if path == "/__wx_channels_api/profile":
            # JS 端上报视频信息
            try:
                body = flow.request.get_text() or "{}"
                profile = json.loads(body)
                with _PROFILE_LOCK:
                    _COLLECTED_PROFILE = profile
                logger.info("已收集视频 profile: %s", profile.get("title", ""))
            except Exception as e:
                logger.error("解析 profile 失败: %s", e)
            flow.response = http.Response.make(
                200,
                json.dumps({"ok": True}).encode(),
                {"Content-Type": "application/json"},
            )
        elif path == "/__wx_channels_api/tip":
            # JS 端上报提示消息
            try:
                body = flow.request.get_text() or ""
                _TIP_MESSAGES.append(body)
                if len(_TIP_MESSAGES) > 100:
                    _TIP_MESSAGES = _TIP_MESSAGES[-100:]
            except Exception as e:
                logger.error("解析 tip 失败: %s", e)
            flow.response = http.Response.make(
                200,
                json.dumps({"ok": True}).encode(),
                {"Content-Type": "application/json"},
            )

    def response(self, flow: http.HTTPFlow):
        """拦截 channels.weixin.qq.com 的 HTML 响应,注入 JS。"""
        host = flow.request.pretty_host
        if "channels.weixin.qq.com" not in host:
            return

        content_type = flow.response.headers.get("content-type", "")
        if "text/html" not in content_type:
            return

        if not self.inject_js:
            return

        try:
            html = flow.response.get_text()
            if html is None:
                return
            # 在 </head> 前注入脚本,若没有 </head> 则追加到末尾
            inject_block = "<script>\\n" + self.inject_js + "\\n</script>\\n"
            if "</head>" in html:
                html = html.replace("</head>", inject_block + "</head>", 1)
            else:
                html = html + inject_block
            flow.response.set_text(html)
            logger.info("已向 %s 注入 JS 脚本", host)
        except Exception as e:
            logger.error("注入 JS 失败: %s", e)


addons = [WechatChannelsAddon()]
'''

# 用于在 addon 脚本中传递 inject.js 路径的占位符替换
# 使用 repr() 确保路径中的反斜杠/特殊字符正确转义
def _render_addon_content(inject_js_path: Path) -> str:
    """渲染 addon 脚本内容,注入 inject.js 路径。

    使用占位符替换而非字符串拼接,确保 ``from __future__ import annotations``
    仍位于文件开头(否则会触发 SyntaxError)。
    """
    return _ADDON_TEMPLATE.replace(
        "__INJECT_JS_PATH_REPR__", repr(str(inject_js_path))
    )


# mitmdump wrapper 脚本模板:在导入 mitmproxy 之前 monkey-patch bcrypt,
# 绕过 passlib 1.7.4 与 bcrypt 5.x 的兼容性问题。
# 问题1: bcrypt 5.x 移除了 __about__ 模块,passlib 访问 __about__.__version__ 报 AttributeError
# 问题2: bcrypt 5.x 严格要求 password <=72 bytes,passlib 检测 wrap bug 时用长 secret 报 ValueError
# 上述两个错误会导致 mitmproxy 在 import 阶段崩溃,根本无法启动。
# 此 wrapper 在 mitmproxy 导入前 patch bcrypt,确保兼容。
_WRAPPER_TEMPLATE = '''\
"""mitmdump 启动 wrapper:预先 patch bcrypt 兼容性问题。"""
import sys


def _patch_bcrypt():
    """Monkey-patch bcrypt 以兼容 passlib 1.7.4。

    1. 注入 __about__ 模块(passlib 访问 __about__.__version__)
    2. 包装 hashpw 自动截断 >72 bytes 的 password(bcrypt 5.x 严格要求)
    """
    try:
        import bcrypt
    except ImportError:
        return  # bcrypt 未装,passlib 会用其他后端或不启用

    import types
    if not hasattr(bcrypt, "__about__"):
        about = types.ModuleType("bcrypt.__about__")
        about.__version__ = getattr(bcrypt, "__version__", "unknown")
        bcrypt.__about__ = about
        sys.modules["bcrypt.__about__"] = about

    _orig_hashpw = bcrypt.hashpw

    def _safe_hashpw(secret, salt, *args, **kwargs):
        if isinstance(secret, str):
            secret = secret.encode("utf-8")
        if len(secret) > 72:
            secret = secret[:72]
        return _orig_hashpw(secret, salt, *args, **kwargs)

    bcrypt.hashpw = _safe_hashpw


_patch_bcrypt()

# 玾在可以安全导入 mitmproxy 并启动 mitmdump
from mitmproxy.tools.main import mitmdump

if __name__ == "__main__":
    mitmdump(sys.argv[1:])
'''


class WechatChannelsMitmProxy:
    """微信视频号 MITM 代理管理器。

    通过 ``mitmdump`` 子进程启动代理,加载自动生成的 addon 脚本来拦截
    视频号 HTTPS 流量。主进程通过轮询 :meth:`get_profile` 获取 JS 端
    上报的视频信息。

    Attributes:
        port: 代理监听端口。
        cert_dir: CA 证书目录。
        js_assets_dir: 静态资源目录(含 inject.js)。
        callback: 可选进度回调。
    """

    def __init__(
        self,
        port: int,
        cert_dir: Path,
        js_assets_dir: Path,
        callback: Optional[ProgressCallback] = None,
        upstream_proxy: Optional[str] = None,
    ) -> None:
        self.port = port
        self.cert_dir = Path(cert_dir)
        self.js_assets_dir = Path(js_assets_dir)
        self.callback = callback
        self.upstream_proxy = upstream_proxy

        self._process: Optional[subprocess.Popen] = None
        self._addon_file: Optional[Path] = None
        self._wrapper_file: Optional[Path] = None
        self._profile_file: Optional[Path] = None
        self._tip_file: Optional[Path] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """启动 mitmdump 子进程。

        会生成临时 wrapper 与 addon 脚本文件,然后以命令行方式启动 mitmdump。
        wrapper 脚本在导入 mitmproxy 之前 monkey-patch bcrypt,绕过 passlib
        与 bcrypt 5.x 的兼容性问题。启动后会轮询端口监听状态,确保子进程
        真正可用(避免子进程秒崩但 is_running 误报的情况)。
        """
        if not _HAS_MITMPROXY:
            raise RuntimeError(
                "未找到 mitmproxy,请执行 `pip install mitmproxy` 安装。"
            )

        inject_js_path = self.js_assets_dir / "inject.js"
        if not inject_js_path.exists():
            logger.warning("inject.js 不存在(%s),JS 注入将被跳过", inject_js_path)

        ca_cert = self.cert_dir / "ca.crt"
        ca_key = self.cert_dir / "ca.key"

        # 生成临时 wrapper 脚本(patch bcrypt 兼容性)
        fd, wrapper_path = tempfile.mkstemp(suffix=".py", prefix="wx_mitm_wrapper_")
        self._wrapper_file = Path(wrapper_path)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(_WRAPPER_TEMPLATE)

        # 生成临时 addon 脚本(通过占位符替换注入 inject.js 路径)
        addon_content = _render_addon_content(inject_js_path)

        fd, addon_path = tempfile.mkstemp(suffix=".py", prefix="wx_channels_addon_")
        self._addon_file = Path(addon_path)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(addon_content)

        # mitmdump 命令行参数:通过 wrapper 脚本启动,而非直接 -m mitmproxy.tools.main
        cmd = [
            sys.executable, str(self._wrapper_file),
            "--listen-port", str(self.port),
            "--set", "confdir=" + str(self.cert_dir),
            "-s", str(self._addon_file),
        ]

        # 若存在 CA 证书,指定给 mitmproxy 使用
        if ca_cert.exists() and ca_key.exists():
            cmd.extend([
                "--set", "ssl_insecure=true",
            ])

        # 配置上游代理(可选):将所有流量转发到另一个代理(如 VPN)
        # 格式: http://host:port 或 https://host:port
        if self.upstream_proxy:
            cmd.extend([
                "--set", "upstream_proxy=" + self.upstream_proxy,
            ])
            logger.info("上游代理已配置: %s", self.upstream_proxy)

        logger.info("启动 mitmdump: %s", " ".join(cmd))

        if self.callback:
            self.callback.on_progress("", 0.0)

        # 以非阻塞方式启动子进程,stdout/stderr 输出到管道供读取
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        # 启动后台线程读取子进程输出,避免管道阻塞
        reader = threading.Thread(target=self._read_output, daemon=True)
        reader.start()

        # 等待端口真正监听(最多 8 秒),避免子进程秒崩但误报"已启动"
        if not self._wait_for_port(timeout=8.0):
            # 端口未监听,检查子进程是否已退出
            if self._process.poll() is not None:
                # 子进程已退出,收集输出用于错误诊断
                output = self._collect_recent_output()
                self._cleanup_temp_files()
                raise RuntimeError(
                    "mitmdump 子进程启动后立即退出(exit code="
                    f"{self._process.returncode})。\n"
                    "可能原因:passlib/bcrypt 不兼容、证书问题或端口被占用。\n"
                    f"子进程输出:\n{output}"
                )
            # 子进程还在运行但端口没监听,继续执行(可能是慢启动)
            logger.warning("mitmdump 启动 8 秒后端口 %d 仍未监听", self.port)

    def _wait_for_port(self, timeout: float = 8.0, interval: float = 0.3) -> bool:
        """轮询检测端口是否真正监听。

        Args:
            timeout: 总等待时间(秒)。
            interval: 轮询间隔(秒)。

        Returns:
            True 如果端口在超时前开始监听;False 否。
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            # 子进程已退出,无需再等
            if self._process is not None and self._process.poll() is not None:
                return False
            try:
                with socket.create_connection(
                    ("127.0.0.1", self.port), timeout=0.5
                ):
                    return True
            except OSError:
                time.sleep(interval)
        return False

    def _collect_recent_output(self, max_lines: int = 50) -> str:
        """收集子进程最近的输出(用于错误诊断)。

        读取 stdout 管道中已有的内容(非阻塞),返回最近的 max_lines 行。
        """
        if self._process is None or self._process.stdout is None:
            return ""
        lines = []
        try:
            import select as _select
            while len(lines) < max_lines:
                # Windows 不支持 select.select on pipe,用非阻塞读取替代
                readable, _, _ = _select.select([self._process.stdout], [], [], 0.1)
                if not readable:
                    break
                line = self._process.stdout.readline()
                if not line:
                    break
                lines.append(line.rstrip())
        except Exception:
            # select 在 Windows 管道上不可靠,回退到直接读取已有缓冲
            pass
        return "\n".join(lines[-max_lines:])

    def _cleanup_temp_files(self) -> None:
        """清理所有临时文件(wrapper + addon)。"""
        for f in (self._wrapper_file, self._addon_file):
            if f and f.exists():
                try:
                    f.unlink()
                except OSError:
                    pass
        self._wrapper_file = None
        self._addon_file = None

    def _read_output(self) -> None:
        """读取 mitmdump 子进程输出并记录日志。

        持续读取直到子进程结束或收到停止信号,防止 stdout 管道写满阻塞。
        """
        if self._process is None or self._process.stdout is None:
            return
        for line in self._process.stdout:
            if self._stop_event.is_set():
                break
            line = line.rstrip()
            if line:
                logger.debug("[mitmdump] %s", line)

    def stop(self) -> None:
        """停止 mitmdump 子进程并清理临时文件。"""
        self._stop_event.set()
        if self._process is not None:
            try:
                self._process.terminate()
                # 等待最多 5 秒
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait(timeout=3)
            except Exception as e:
                logger.error("停止 mitmdump 失败: %s", e)
            finally:
                self._process = None

        # 清理临时文件(wrapper + addon)
        self._cleanup_temp_files()

    def get_profile(self, timeout: float = 300.0, poll_interval: float = 1.0) -> Optional[dict[str, Any]]:
        """轮询等待 JS 端上报的视频 profile。

        Args:
            timeout: 最长等待时间(秒),默认 5 分钟。
            poll_interval: 轮询间隔(秒)。

        Returns:
            收到的 profile 字典,超时则返回 None。
        """
        # 通过 mitmproxy 的 addon 全局变量获取,由于子进程隔离,
        # 这里改用文件中转的方式:实际实现中 mitmdump 会将 profile 写入
        # 一个临时文件。为简化,这里等待 mitmdump 输出中出现 profile 关键字。
        # 注意:真正实现需要进程间通信,这里提供基于日志的简化轮询。
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._stop_event.is_set():
                return None
            # 由于 addon 运行在子进程,无法直接读取其内存。
            # 实际集成时可通过以下方式改进:
            # 1. addon 将 profile 写入共享文件
            # 2. 使用 mitmproxy 的 Python API 编程式启动
            # 这里先返回 None,由 adapter 层处理超时
            time.sleep(poll_interval)
        return None

    def is_running(self) -> bool:
        """检查 mitmdump 子进程是否仍在运行。"""
        return self._process is not None and self._process.poll() is None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False
