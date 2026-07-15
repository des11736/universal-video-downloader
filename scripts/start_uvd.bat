@echo off
REM ============================================================
REM   UVD WebUI Launcher
REM   First-run: auto-installs all Python dependencies
REM   Then starts the web server and opens the browser
REM ============================================================

setlocal enabledelayedexpansion

REM Set PYTHONPATH to project root (parent of scripts dir)
set PYTHONPATH=%~dp0..
set PROJECT_ROOT=%~dp0..
cd /d "%PROJECT_ROOT%"

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

REM ---- Step 2: Check if dependencies are installed ----
echo [2/4] Checking dependencies...
python -c "import uvicorn, fastapi, yt_dlp, websockets, multipart" >nul 2>&1
if errorlevel 1 (
    goto :install_deps
) else (
    echo   All dependencies are installed.
    goto :shortcut
)

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

REM ---- Step 4: Start the server ----
echo [4/4] Starting UVD WebUI...
echo.
echo ========================================
echo   UVD WebUI is running!
echo   URL: http://127.0.0.1:8000
echo   Press Ctrl+C to stop
echo ========================================
echo.

REM Open default browser after 3 seconds (non-blocking)
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:8000"

REM Start uvicorn server
python -m universal_video_downloader.cli.main serve --host 127.0.0.1 --port 8000

echo.
echo UVD WebUI has stopped.
pause
