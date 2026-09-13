# فعال‌سازی محیط پروژه (venv + SUMO_HOME) برای پاورشل
# استفاده: در ریشهٔ پروژه اجرا کن:  . .\scripts\env.ps1
$root = Split-Path -Parent $PSScriptRoot
& "$root\.venv\Scripts\Activate.ps1"
$env:SUMO_HOME = "$root\.venv\Lib\site-packages\sumo"
$env:PATH = "$env:SUMO_HOME\bin;$env:PATH"
Write-Host "SUMO_HOME = $env:SUMO_HOME"
Write-Host "sumo version:" (& "$env:SUMO_HOME\bin\sumo.exe" --version | Select-Object -First 1)
