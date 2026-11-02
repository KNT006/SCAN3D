$ErrorActionPreference = 'Stop'
try {
    $running = Invoke-RestMethod -Uri 'http://127.0.0.1:8840/api/status' -TimeoutSec 2
    if ($running.service -ne 'scan3d-portal' -and $null -eq $running.setup) {
        throw 'Port 8840 is occupied by another service.'
    }
    Write-Host 'SCAN3D is already running: http://127.0.0.1:8840'
    if ($running.setup -and (Test-Path (Join-Path $PSScriptRoot 'data/server.log'))) {
        Get-Content (Join-Path $PSScriptRoot 'data/server.log')
    }
    Start-Process 'http://127.0.0.1:8840'
    exit 0
} catch {
    # No local portal yet; start it below.
}
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (Test-Path -LiteralPath $bundledPython) {
    & $bundledPython (Join-Path $PSScriptRoot 'server.py')
} else {
    python (Join-Path $PSScriptRoot 'server.py')
}
