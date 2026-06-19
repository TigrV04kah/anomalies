$ErrorActionPreference = "Stop"

$Root = if ($MyInvocation.MyCommand.Path) {
    Split-Path -Parent $MyInvocation.MyCommand.Path
} else {
    (Get-Location).Path
}
Set-Location $Root

$Node = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"

if (-not (Test-Path -LiteralPath $Node)) {
    $Node = "node"
}

function Test-PythonRuntime {
    param([Parameter(Mandatory = $true)][string]$Executable)

    $RequiredModules = "pandas,numpy,requests,pymongo"
    $CheckScript = @"
import importlib.util
import sys

missing = [name for name in "$RequiredModules".split(",") if importlib.util.find_spec(name) is None]
if missing:
    print("missing modules: " + ", ".join(missing))
    sys.exit(1)
print(sys.executable)
"@

    try {
        $Output = & $Executable -c $CheckScript 2>&1
        if ($LASTEXITCODE -eq 0) {
            return $true
        }
        Write-Host "Python candidate '$Executable' is not suitable: $Output" -ForegroundColor Yellow
        return $false
    } catch {
        Write-Host "Python candidate '$Executable' failed: $($_.Exception.Message)" -ForegroundColor Yellow
        return $false
    }
}

function Resolve-PythonRuntime {
    $Candidates = @(
        "python",
        (Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe")
    )

    foreach ($Candidate in $Candidates) {
        if ($Candidate -ne "python" -and -not (Test-Path -LiteralPath $Candidate)) {
            continue
        }
        if (Test-PythonRuntime -Executable $Candidate) {
            return $Candidate
        }
    }

    throw "No Python runtime with required modules found. Install pandas, numpy, requests and pymongo for the Python used by this script."
}

$Python = Resolve-PythonRuntime
Write-Host "Using Python: $Python"

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

    $NextRun = (Get-Date).AddMinutes(5)
    Write-Host "Next run: $($NextRun.ToString('yyyy-MM-dd HH:mm:ss')). Keep this window open. Press Ctrl+C to stop."
    Start-Sleep -Seconds 300
}
