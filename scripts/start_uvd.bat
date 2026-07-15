@echo off
REM UVD WebUI Launcher
REM Set PYTHONPATH to project root (parent of scripts dir)
set PYTHONPATH=%~dp0..
cd /d %~dp0..

REM Create desktop shortcut on first run
if not exist "%USERPROFILE%\Desktop\UVD WebUI.lnk" (
    powershell -ExecutionPolicy Bypass -File "%~dp0create_shortcut.ps1"
)

echo ========================================
echo   UVD WebUI starting...
echo   URL: http://127.0.0.1:8000
echo   Press Ctrl+C to stop
echo ========================================
echo.

REM Open default browser after 3 seconds
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:8000"

REM Start uvicorn server
python -m universal_video_downloader.cli.main serve --host 127.0.0.1 --port 8000

pause
