@echo off
REM ============================================================
REM   UVD WebUI Launcher
REM   First-run: auto-installs Python dependencies and the UVD CLI
REM   Then starts the web server and opens the browser
REM ============================================================

setlocal enabledelayedexpansion

REM Set PYTHONPATH to project root (parent of scripts dir)
set PYTHONPATH=%~dp0..
set PROJECT_ROOT=%~dp0..
cd /d "%PROJECT_ROOT%"

REM 代理备份文件路径(用于异常退出后恢复)
set "PROXY_BACKUP_FILE=%TEMP%\uvd_proxy_backup.txt"

REM ---- Step 0: Recover from previous abnormal exit ----
REM 如果上次异常退出,备份文件还存在,先恢复原代理
if exist "%PROXY_BACKUP_FILE%" (
    echo [0/5] Recovering proxy from previous session...
    for /f "usebackq tokens=1,2 delims==" %%a in ("%PROXY_BACKUP_FILE%") do (
        if "%%a"=="enabled" set "RECOVER_ENABLED=%%b"
        if "%%a"=="server" set "RECOVER_SERVER=%%b"
    )
    set "PROXY_REG=HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    if defined RECOVER_SERVER (
        reg add "%PROXY_REG%" /v ProxyServer /t REG_SZ /d "!RECOVER_SERVER!" /f >nul
    )
    if defined RECOVER_ENABLED (
        reg add "%PROXY_REG%" /v ProxyEnable /t REG_DWORD /d "!RECOVER_ENABLED!" /f >nul
    )
    del "%PROXY_BACKUP_FILE%" >nul 2>&1
    echo   Proxy restored from backup.
    echo.
)

REM ---- Step 1: Verify Python is installed ----
echo ========================================
echo   UVD WebUI Launcher
echo ========================================
echo.
echo [1/4] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo   Python %PYVER% found.
echo.

REM ---- Step 2: Check dependencies and the current Python's UVD launcher ----
echo [2/4] Checking dependencies and UVD command...
python -c "import uvicorn, fastapi, mitmproxy, yt_dlp, websockets, multipart" >nul 2>&1
if errorlevel 1 (
    goto :install_deps
)

for /f "delims=" %%s in ('python -c "import sysconfig; print(sysconfig.get_path('scripts'))"') do set "PYTHON_SCRIPTS=%%s"
set "UVD_LAUNCHER=%PYTHON_SCRIPTS%\uvd.exe"
if not exist "%UVD_LAUNCHER%" (
    echo   UVD command is missing. Installing the project now...
    goto :install_deps
)

echo   All dependencies and the UVD command are installed.
goto :shortcut

:install_deps
echo.
echo   Dependencies are missing. Installing now...
echo   This may take a few minutes on first run. Please wait.
echo.
echo   Running: pip install -e .
echo.
REM Upgrade pip first to avoid SSL/build issues
python -m pip install --upgrade pip
if errorlevel 1 (
    echo   [WARNING] pip upgrade failed, continuing with current pip...
)
echo.
python -m pip install -e .
if errorlevel 1 (
    echo.
    echo   [ERROR] Failed to install dependencies.
    echo   Please check your internet connection and try again.
    echo   You can manually run: pip install -e .
    echo.
    pause
    exit /b 1
)
if not exist "%UVD_LAUNCHER%" (
    echo.
    echo   [ERROR] Installation finished but the UVD command was not created.
    echo   Expected command: %UVD_LAUNCHER%
    echo   Please close this window, reopen PowerShell, and run: python -m pip install -e .
    echo.
    pause
    exit /b 1
)
echo.
echo   Dependencies installed successfully.
echo.

:shortcut
REM ---- Step 3: Create desktop shortcut on first run ----
echo [3/4] Setting up desktop shortcut...
if not exist "%USERPROFILE%\Desktop\UVD WebUI.lnk" (
    powershell -ExecutionPolicy Bypass -File "%~dp0create_shortcut.ps1"
    if errorlevel 1 (
        echo   [WARNING] Shortcut creation failed, continuing anyway...
    ) else (
        echo   Desktop shortcut created.
    )
) else (
    echo   Shortcut already exists.
)
echo.

REM ---- Step 4: Backup current system proxy and set upstream proxy env ----
echo [4/5] Backing up system proxy settings...
set "PROXY_REG=HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
set "PROXY_ENABLED="
set "PROXY_SERVER="

for /f "tokens=3" %%a in ('reg query "%PROXY_REG%" /v ProxyEnable 2^>nul ^| findstr "REG_DWORD"') do set "PROXY_ENABLED=%%a"
for /f "tokens=2*" %%a in ('reg query "%PROXY_REG%" /v ProxyServer 2^>nul ^| findstr "REG_SZ"') do set "PROXY_SERVER=%%b"

echo   Current proxy enabled: !PROXY_ENABLED!
echo   Current proxy server: !PROXY_SERVER!

REM 写入备份文件(用于异常退出后恢复)
REM 格式: enabled=0x0/0x1
REM       server=host:port
(
    echo enabled=!PROXY_ENABLED!
    echo server=!PROXY_SERVER!
) > "%PROXY_BACKUP_FILE%"

REM 设置上游代理环境变量(供 mitmproxy 使用)
REM 格式: http://host:port
if defined PROXY_SERVER (
    set "UVD_UPSTREAM_PROXY=http://!PROXY_SERVER!"
    echo   Upstream proxy env: !UVD_UPSTREAM_PROXY!
)
echo.

REM ---- Step 4b: Install CA certificate to system trust store ----
REM 浏览器不信任 MITM 自签名证书会导致 TLS 握手失败,需将 CA 安装到系统受信任根证书
REM mitmproxy 默认使用 mitmproxy-ca-cert.cer,而非我们生成的 ca.crt
set "CA_CERT_PATH=%PROJECT_ROOT%\universal_video_downloader\certs\mitmproxy-ca-cert.cer"
if not exist "%CA_CERT_PATH%" set "CA_CERT_PATH=%PROJECT_ROOT%\universal_video_downloader\certs\ca.crt"
if exist "%CA_CERT_PATH%" (
    REM 检查证书是否已安装(通过 certutil 查找 mitmproxy)
    certutil -store Root "mitmproxy" 2>nul | findstr /C:"mitmproxy" >nul
    if errorlevel 1 (
        echo [4b/5] Installing CA certificate to system trust store...
        echo   CA cert: %CA_CERT_PATH%
        REM 需要管理员权限,若失败会提示用户
        certutil -addstore -f Root "%CA_CERT_PATH%" >nul 2>&1
        if errorlevel 1 (
            echo   [WARNING] Failed to install CA automatically. Trying user store...
            REM 退而求其次:安装到当前用户证书存储(不需要管理员权限)
            certutil -user -addstore -f Root "%CA_CERT_PATH%" >nul 2>&1
            if errorlevel 1 (
                echo   [ERROR] Cannot install CA cert. Please manually install:
                echo          %CA_CERT_PATH%
                echo          Restart your browser after installation.
            ) else (
                echo   CA certificate installed to user trust store.
            )
        ) else (
            echo   CA certificate installed to system trust store.
        )
    ) else (
        echo [4b/5] CA certificate already installed.
    )
) else (
    echo [4b/5] CA certificate not found at %CA_CERT_PATH%. Will be generated on first start.
)
echo.

REM ---- Step 5: Start the server ----
echo [5/5] Starting UVD WebUI...
echo.
echo ========================================
echo   UVD WebUI is running!
echo   URL: http://127.0.0.1:8000
echo   WeChat page listener: 127.0.0.1:8888
echo   System proxy switched to 127.0.0.1:8888
echo   Press Ctrl+C to stop (proxy will be restored)
echo ========================================
echo.

REM Switch system proxy to MITM proxy
reg add "%PROXY_REG%" /v ProxyServer /t REG_SZ /d "127.0.0.1:8888" /f >nul
reg add "%PROXY_REG%" /v ProxyEnable /t REG_DWORD /d 1 /f >nul

REM Notify system of proxy change
powershell -ExecutionPolicy Bypass -Command "[System.Net.WebRequest]::DefaultWebProxy = New-Object System.Net.WebProxy('127.0.0.1:8888'); [System.Net.WebRequest]::DefaultWebProxy.Credentials = [System.Net.CredentialCache]::DefaultCredentials" >nul 2>&1

REM Open default browser after 3 seconds (non-blocking)
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:8000"

REM Start uvicorn server
python -m universal_video_downloader.cli.main serve --host 127.0.0.1 --port 8000

REM ---- Cleanup: Restore original proxy ----
echo.
echo Restoring system proxy...

if defined PROXY_SERVER (
    reg add "%PROXY_REG%" /v ProxyServer /t REG_SZ /d "%PROXY_SERVER%" /f >nul
)
if defined PROXY_ENABLED (
    reg add "%PROXY_REG%" /v ProxyEnable /t REG_DWORD /d "%PROXY_ENABLED%" /f >nul
)

REM 删除备份文件(正常退出,无需恢复)
if exist "%PROXY_BACKUP_FILE%" del "%PROXY_BACKUP_FILE%" >nul 2>&1

REM Notify system of proxy restore
powershell -ExecutionPolicy Bypass -Command "$p = New-Object System.Net.WebProxy(''); [System.Net.WebRequest]::DefaultWebProxy = $p" >nul 2>&1

echo   Proxy restored.
echo   Original enabled: !PROXY_ENABLED!
echo   Original server: !PROXY_SERVER!
echo.
pause
