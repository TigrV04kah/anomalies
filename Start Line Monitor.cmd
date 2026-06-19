@echo off
setlocal
set "ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '%ROOT%'; $code = Get-Content -LiteralPath '%ROOT%start_line_monitor.ps1' -Raw; Invoke-Expression $code"
if errorlevel 1 (
    echo.
    echo Start Line Monitor failed. See the error above.
    pause
)
endlocal
