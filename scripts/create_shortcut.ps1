# Create UVD WebUI desktop shortcut
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$batPath = Join-Path $scriptDir "start_uvd.bat"
$iconPath = Join-Path $projectRoot "assets\icons\uvd.ico"
$shortcutPath = Join-Path $env:USERPROFILE "Desktop\UVD WebUI.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $batPath
$shortcut.IconLocation = $iconPath
$shortcut.WindowStyle = 7  # Minimized
$shortcut.WorkingDirectory = $scriptDir
$shortcut.Description = "UVD WebUI Launcher"
$shortcut.Save()

Write-Host "Shortcut created: $shortcutPath"
Write-Host "Icon: $iconPath"
