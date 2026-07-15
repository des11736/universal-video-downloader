"""Windows 启动脚本的回归测试。"""

from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LAUNCHER = _PROJECT_ROOT / "scripts" / "start_uvd.bat"


def test_launcher_installs_project_when_uvd_command_is_missing() -> None:
    """第三方依赖齐全但缺少 uvd 启动器时，也应自动安装项目。"""
    content = _LAUNCHER.read_text(encoding="utf-8")

    assert "sysconfig.get_path('scripts')" in content
    assert "mitmproxy" in content
    assert 'set "UVD_LAUNCHER=%PYTHON_SCRIPTS%\\uvd.exe"' in content
    assert content.count('if not exist "%UVD_LAUNCHER%"') >= 2
    assert "UVD command is missing" in content
    assert "python -m pip install -e ." in content


def test_launcher_describes_wechat_page_listener() -> None:
    """启动横幅应说明视频号页面监听器和代理地址。"""
    content = _LAUNCHER.read_text(encoding="utf-8")

    assert "WeChat page listener" in content
    assert "127.0.0.1:8888" in content
