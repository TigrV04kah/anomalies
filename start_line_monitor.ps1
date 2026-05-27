$ErrorActionPreference = "Stop"

$Root = if ($MyInvocation.MyCommand.Path) {
    Split-Path -Parent $MyInvocation.MyCommand.Path
} else {
    (Get-Location).Path
}
Set-Location $Root

$Python = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Node = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}
if (-not (Test-Path -LiteralPath $Node)) {
    $Node = "node"
}

foreach ($Name in @("LINE_MONGO_URI", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_PUBLISHABLE_KEY")) {
    if (-not [Environment]::GetEnvironmentVariable($Name, "Process")) {
        $Value = [Environment]::GetEnvironmentVariable($Name, "User")
        if ($Value) {
            [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
        }
    }
}

$env:PORT = "8766"

function Start-LocalUi {
    Write-Host "Starting local UI..."
    Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" |
        Where-Object { $_.CommandLine -like "*local_vercel_preview.js*" -and $_.CommandLine -like "*$Root*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

    Start-Process -FilePath $Node `
        -ArgumentList "local_vercel_preview.js" `
        -WorkingDirectory $Root `
        -WindowStyle Hidden

    Start-Sleep -Seconds 2
    Start-Process "http://127.0.0.1:8766/"
    Write-Host "Line Monitor UI: http://127.0.0.1:8766/"
}

Start-LocalUi

while ($true) {
    $StartedAt = Get-Date
    Write-Host ""
    Write-Host "[$($StartedAt.ToString('yyyy-MM-dd HH:mm:ss'))] Running full line monitor..."

    try {
        & $Python "run_line_monitor.py"
        if ($LASTEXITCODE -ne 0) {
            throw "run_line_monitor.py failed with exit code $LASTEXITCODE"
        }
        $FinishedAt = Get-Date
        $Duration = [Math]::Round(($FinishedAt - $StartedAt).TotalSeconds, 1)
        Write-Host "[$($FinishedAt.ToString('yyyy-MM-dd HH:mm:ss'))] Run finished in $Duration seconds."
    } catch {
        $FailedAt = Get-Date
        Write-Host "[$($FailedAt.ToString('yyyy-MM-dd HH:mm:ss'))] Run failed: $($_.Exception.Message)" -ForegroundColor Red
    }

    $NextRun = (Get-Date).AddMinutes(10)
    Write-Host "Next run: $($NextRun.ToString('yyyy-MM-dd HH:mm:ss')). Keep this window open. Press Ctrl+C to stop."
    Start-Sleep -Seconds 600
}
