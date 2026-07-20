#!/usr/bin/env bash
# ============================================================
#   UVD WebUI Launcher (macOS / Linux)
#   First-run: auto-installs Python dependencies and the UVD CLI
#   Then starts the web server and opens the browser
#
#   Usage:
#     chmod +x scripts/start_uvd.sh
#     ./scripts/start_uvd.sh
# ============================================================

set -e

# 切换到项目根目录(脚本所在目录的上一级)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT"

# 代理备份文件路径(用于异常退出后恢复)
PROXY_BACKUP_FILE="/tmp/uvd_proxy_backup.txt"

# ---- Step 0: Recover from previous abnormal exit ----
# 如果上次异常退出,备份文件还存在,先恢复原代理
if [ -f "$PROXY_BACKUP_FILE" ]; then
    echo "[0/5] Recovering proxy from previous session..."
    RECOVER_MODE=$(grep "^mode=" "$PROXY_BACKUP_FILE" | cut -d= -f2)
    RECOVER_HOST=$(grep "^host=" "$PROXY_BACKUP_FILE" | cut -d= -f2)
    RECOVER_PORT=$(grep "^port=" "$PROXY_BACKUP_FILE" | cut -d= -f2)

    case "$(uname -s)" in
        Darwin*)
            for svc in $(networksetup -listallnetworkservices | tail -n +2); do
                if [ "$RECOVER_MODE" = "manual" ] && [ -n "$RECOVER_HOST" ] && [ -n "$RECOVER_PORT" ]; then
                    networksetup -setwebproxy "$svc" "$RECOVER_HOST" "$RECOVER_PORT" >/dev/null 2>&1
                    networksetup -setsecurewebproxy "$svc" "$RECOVER_HOST" "$RECOVER_PORT" >/dev/null 2>&1
                    networksetup -setwebproxystate "$svc" on >/dev/null 2>&1
                    networksetup -setsecurewebproxystate "$svc" on >/dev/null 2>&1
                else
                    networksetup -setwebproxystate "$svc" off >/dev/null 2>&1
                    networksetup -setsecurewebproxystate "$svc" off >/dev/null 2>&1
                fi
            done
            ;;
        Linux*)
            gsettings set org.gnome.system.proxy mode "$RECOVER_MODE" >/dev/null 2>&1
            if [ "$RECOVER_MODE" = "manual" ] && [ -n "$RECOVER_HOST" ] && [ -n "$RECOVER_PORT" ]; then
                gsettings set org.gnome.system.proxy.http host "$RECOVER_HOST" >/dev/null 2>&1
                gsettings set org.gnome.system.proxy.http port "$RECOVER_PORT" >/dev/null 2>&1
                gsettings set org.gnome.system.proxy.https host "$RECOVER_HOST" >/dev/null 2>&1
                gsettings set org.gnome.system.proxy.https port "$RECOVER_PORT" >/dev/null 2>&1
            fi
            ;;
    esac

    rm -f "$PROXY_BACKUP_FILE"
    echo "  Proxy restored from backup."
    echo ""
fi

echo "========================================"
echo "  UVD WebUI Launcher"
echo "========================================"
echo ""

# ---- Step 1: 检测 Python ----
echo "[1/4] Checking Python..."
if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo ""
    echo "[ERROR] Python is not installed or not in PATH."
    echo "Please install Python 3.10+ from https://www.python.org/downloads/"
    echo ""
    exit 1
fi
PYVER=$($PYTHON --version 2>&1 | awk '{print $2}')
echo "  Python $PYVER found."
echo ""

# ---- Step 2: 检测依赖 ----
echo "[2/4] Checking dependencies..."
if ! $PYTHON -c "import uvicorn, fastapi, mitmproxy, yt_dlp, websockets, multipart" >/dev/null 2>&1; then
    echo "  Dependencies are missing. Installing now..."
    echo "  This may take a few minutes on first run. Please wait."
    echo ""
    $PYTHON -m pip install --upgrade pip || echo "  [WARNING] pip upgrade failed, continuing..."
    $PYTHON -m pip install -e .
    echo ""
    echo "  Dependencies installed successfully."
else
    echo "  All dependencies are installed."
fi
echo ""

# ---- Step 3: 创建桌面快捷方式(macOS) ----
echo "[3/4] Setting up launcher..."
case "$(uname -s)" in
    Darwin*)
        # macOS: 创建桌面 .app 快捷方式
        APP_DIR="$HOME/Applications/UVD WebUI.app"
        if [ ! -d "$APP_DIR" ]; then
            mkdir -p "$APP_DIR/Contents/MacOS"
            cat > "$APP_DIR/Contents/MacOS/run.sh" <<EOF
#!/bin/bash
cd "$PROJECT_ROOT"
exec "$SCRIPT_DIR/start_uvd.sh"
EOF
            chmod +x "$APP_DIR/Contents/MacOS/run.sh"
            cat > "$APP_DIR/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>UVD WebUI</string>
    <key>CFBundleExecutable</key><string>run.sh</string>
    <key>CFBundleIdentifier</key><string>com.uvd.webui</string>
</dict>
</plist>
EOF
            echo "  Launcher created at $HOME/Applications/UVD WebUI.app"
        else
            echo "  Launcher already exists."
        fi
        ;;
    Linux*)
        # Linux: 创建桌面 .desktop 文件
        DESKTOP_FILE="$HOME/.local/share/applications/uvd-webui.desktop"
        if [ ! -f "$DESKTOP_FILE" ]; then
            mkdir -p "$(dirname "$DESKTOP_FILE")"
            cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=UVD WebUI
Comment=Universal Video Downloader
Exec=$SCRIPT_DIR/start_uvd.sh
Terminal=true
Type=Application
Categories=Network;
EOF
            chmod +x "$DESKTOP_FILE"
            echo "  Desktop entry created at $DESKTOP_FILE"
        else
            echo "  Desktop entry already exists."
        fi
        ;;
esac
echo ""

# ---- Step 4: Backup current system proxy ----
echo "[4/5] Backing up system proxy settings..."
PROXY_MODE=""
PROXY_HOST=""
PROXY_PORT=""
PROXY_SERVICES=""

case "$(uname -s)" in
    Darwin*)
        # macOS: get current proxy state
        for svc in $(networksetup -listallnetworkservices | tail -n +2); do
            state=$(networksetup -getwebproxystate "$svc" 2>/dev/null | awk '{print $2}')
            if [ "$state" = "On" ]; then
                PROXY_SERVICES="$PROXY_SERVICES $svc"
                PROXY_HOST=$(networksetup -getwebproxy "$svc" 2>/dev/null | grep "Server:" | awk '{print $2}')
                PROXY_PORT=$(networksetup -getwebproxy "$svc" 2>/dev/null | grep "Port:" | awk '{print $2}')
                PROXY_MODE="manual"
                break
            fi
        done
        ;;
    Linux*)
        # Linux GNOME: get current proxy state
        PROXY_MODE=$(gsettings get org.gnome.system.proxy mode 2>/dev/null | tr -d "'")
        if [ "$PROXY_MODE" = "manual" ]; then
            PROXY_HOST=$(gsettings get org.gnome.system.proxy.http host 2>/dev/null | tr -d "'")
            PROXY_PORT=$(gsettings get org.gnome.system.proxy.http port 2>/dev/null)
        fi
        ;;
esac

echo "  Current proxy mode: $PROXY_MODE"
echo "  Current proxy host: $PROXY_HOST"
echo "  Current proxy port: $PROXY_PORT"

# 写入备份文件(用于异常退出后恢复)
cat > "$PROXY_BACKUP_FILE" <<EOF
mode=$PROXY_MODE
host=$PROXY_HOST
port=$PROXY_PORT
EOF

# 设置上游代理环境变量(供 mitmproxy 使用)
if [ -n "$PROXY_HOST" ] && [ -n "$PROXY_PORT" ]; then
    export UVD_UPSTREAM_PROXY="http://$PROXY_HOST:$PROXY_PORT"
    echo "  Upstream proxy env: $UVD_UPSTREAM_PROXY"
fi
echo ""

# ---- Step 5: Start the server ----
echo "[5/5] Starting UVD WebUI..."
echo ""
echo "========================================"
echo "  UVD WebUI is running!"
echo "  URL: http://127.0.0.1:8000"
echo "  WeChat page listener: 127.0.0.1:8888"
echo "  System proxy switched to 127.0.0.1:8888"
echo "  Press Ctrl+C to stop (proxy will be restored)"
echo "========================================"
echo ""

# Switch system proxy to MITM proxy
case "$(uname -s)" in
    Darwin*)
        for svc in $(networksetup -listallnetworkservices | tail -n +2); do
            networksetup -setwebproxy "$svc" 127.0.0.1 8888 >/dev/null 2>&1
            networksetup -setsecurewebproxy "$svc" 127.0.0.1 8888 >/dev/null 2>&1
            networksetup -setwebproxystate "$svc" on >/dev/null 2>&1
            networksetup -setsecurewebproxystate "$svc" on >/dev/null 2>&1
        done
        ;;
    Linux*)
        gsettings set org.gnome.system.proxy.http host '127.0.0.1' >/dev/null 2>&1
        gsettings set org.gnome.system.proxy.http port 8888 >/dev/null 2>&1
        gsettings set org.gnome.system.proxy.https host '127.0.0.1' >/dev/null 2>&1
        gsettings set org.gnome.system.proxy.https port 8888 >/dev/null 2>&1
        gsettings set org.gnome.system.proxy mode 'manual' >/dev/null 2>&1
        ;;
esac

# 3 秒后打开默认浏览器
(
    sleep 3
    case "$(uname -s)" in
        Darwin*) open "http://127.0.0.1:8000" ;;
        Linux*) xdg-open "http://127.0.0.1:8000" >/dev/null 2>&1 || true ;;
    esac
) &

# 启动 uvicorn 服务
$PYTHON -m universal_video_downloader.cli.main serve --host 127.0.0.1 --port 8000

# ---- Cleanup: Restore original proxy ----
echo ""
echo "Restoring system proxy..."

case "$(uname -s)" in
    Darwin*)
        if [ "$PROXY_MODE" = "manual" ] && [ -n "$PROXY_HOST" ] && [ -n "$PROXY_PORT" ]; then
            for svc in $(networksetup -listallnetworkservices | tail -n +2); do
                networksetup -setwebproxy "$svc" "$PROXY_HOST" "$PROXY_PORT" >/dev/null 2>&1
                networksetup -setsecurewebproxy "$svc" "$PROXY_HOST" "$PROXY_PORT" >/dev/null 2>&1
                networksetup -setwebproxystate "$svc" on >/dev/null 2>&1
                networksetup -setsecurewebproxystate "$svc" on >/dev/null 2>&1
            done
        else
            for svc in $(networksetup -listallnetworkservices | tail -n +2); do
                networksetup -setwebproxystate "$svc" off >/dev/null 2>&1
                networksetup -setsecurewebproxystate "$svc" off >/dev/null 2>&1
            done
        fi
        ;;
    Linux*)
        gsettings set org.gnome.system.proxy mode "$PROXY_MODE" >/dev/null 2>&1
        if [ "$PROXY_MODE" = "manual" ] && [ -n "$PROXY_HOST" ] && [ -n "$PROXY_PORT" ]; then
            gsettings set org.gnome.system.proxy.http host "$PROXY_HOST" >/dev/null 2>&1
            gsettings set org.gnome.system.proxy.http port "$PROXY_PORT" >/dev/null 2>&1
            gsettings set org.gnome.system.proxy.https host "$PROXY_HOST" >/dev/null 2>&1
            gsettings set org.gnome.system.proxy.https port "$PROXY_PORT" >/dev/null 2>&1
        fi
        ;;
esac

# 删除备份文件(正常退出,无需恢复)
rm -f "$PROXY_BACKUP_FILE"

echo "  Proxy restored."
echo "  Original mode: $PROXY_MODE"
echo "  Original host: $PROXY_HOST"
echo "  Original port: $PROXY_PORT"
echo ""
