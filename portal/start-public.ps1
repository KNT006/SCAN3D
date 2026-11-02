# SCAN3D public demo launcher. Runs only the packaged local server and cloudflared.
# No downloads, security-setting changes, or termination of unrelated processes.
$ErrorActionPreference = 'Stop'
$portalRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$dataRoot = Join-Path $portalRoot 'data'
$stateFile = Join-Path $dataRoot 'public-state.json'
$tunnelExe = Join-Path $portalRoot 'tools\cloudflared.exe'
$serverScript = Join-Path $portalRoot 'server.py'
$qrScript = Join-Path $portalRoot 'make_qr.py'
$launchedRecords = @()
$newStateSaved = $false

function Convert-SavedTimeToUtc($value) {
    # PowerShell 7 may deserialize ISO dates into DateTime; stringifying that
    # object loses its UTC Kind. Windows PowerShell 5.1 keeps ISO date strings.
    if ($value -is [DateTimeOffset]) { return $value.UtcDateTime }
    if ($value -is [DateTime]) {
        if ($value.Kind -eq [DateTimeKind]::Unspecified) { throw 'Saved process time has no timezone.' }
        return $value.ToUniversalTime()
    }
    if ([string]$value -notmatch '(?:Z|[+-]\d{2}:\d{2})$') { throw 'Saved process time has no timezone.' }
    return [DateTimeOffset]::Parse([string]$value, [Globalization.CultureInfo]::InvariantCulture).UtcDateTime
}

function Get-OwnedProcess($state, [string]$kind) {
    if ($state.project_root -ne $portalRoot -or $state.url -notmatch '^https://[a-z0-9-]+\.trycloudflare\.com$') { return $null }
    $portNumber = [int]$state.port
    if ($portNumber -lt 1024 -or $portNumber -gt 65535) { return $null }
    $processNumber = [int]$state.($kind + '_pid')
    if ($processNumber -le 0) { return $null }
    $record = Get-CimInstance Win32_Process -Filter "ProcessId=$processNumber"
    if (-not $record) { return $null }
    $savedTimeUtc = Convert-SavedTimeToUtc $state.($kind + '_created')
    if ([Math]::Abs(($record.CreationDate.ToUniversalTime() - $savedTimeUtc).TotalSeconds) -gt 1) { return $null }
    if ($kind -eq 'tunnel') {
        if ($record.ExecutablePath -ne $tunnelExe) { return $null }
        $target = [regex]::Escape("http://127.0.0.1:$portNumber")
        if ($record.CommandLine -notmatch "\btunnel\s+--url\s+$target(?:\s|$)") { return $null }
    } else {
        if ($record.ExecutablePath -ne $state.python_path) { return $null }
        $scriptArgument = '(?:"' + [regex]::Escape($serverScript) + '"|"?server\.py"?)'
        if ($record.CommandLine -notmatch ("\s" + $scriptArgument + "\s+--port\s+$portNumber(?:\s|$)")) { return $null }
        $originArgument = [regex]::Escape([string]$state.url)
        if ($record.CommandLine -notmatch "--public-origin\s+$originArgument(?:\s|$)") { return $null }
    }
    return $record
}

function Save-State($state) {
    $state.updated = [DateTimeOffset]::Now.ToString('o')
    $temporaryFile = $stateFile + '.tmp'
    [IO.File]::WriteAllText($temporaryFile, ($state | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporaryFile -Destination $stateFile -Force
}

try {
    foreach ($required in @($tunnelExe, $serverScript, $qrScript)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Required local file is missing: $required" }
    }
    New-Item -ItemType Directory -Path $dataRoot -Force | Out-Null
    # Fail before launching anything if process identity cannot be inspected.
    Get-CimInstance Win32_Process -Filter "ProcessId=$PID" | Out-Null
    $bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    $pythonExe = if (Test-Path -LiteralPath $bundledPython) { $bundledPython } else { (Get-Command python -CommandType Application).Source }
    $state = $null
    if (Test-Path -LiteralPath $stateFile) {
        try { $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json }
        catch { throw 'The saved state file is unreadable. Keep it for review; no processes have been changed.' }
    }
    $portalProcess = if ($state) { Get-OwnedProcess $state 'portal' } else { $null }
    $tunnelProcess = if ($state) { Get-OwnedProcess $state 'tunnel' } else { $null }
    if ($portalProcess -and $tunnelProcess) {
        Write-Host 'Reusing the verified SCAN3D server and tunnel.'
    } else {
        # A remaining process is stopped only after its PID, creation time, path,
        # project, port and arguments all match this project's saved state.
        foreach ($remaining in @($portalProcess, $tunnelProcess)) {
            if ($remaining) { Stop-Process -Id $remaining.ProcessId -ErrorAction Stop }
        }
        $probe = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
        try { $probe.Start(); $portNumber = $probe.LocalEndpoint.Port }
        finally { $probe.Stop() }
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $tunnelLog = Join-Path $dataRoot "tunnel-$portNumber-$stamp.log"
        $tunnelOut = Join-Path $dataRoot "tunnel-$portNumber-$stamp-out.log"
        $portalLog = Join-Path $dataRoot "public-$portNumber-$stamp.log"
        $portalError = Join-Path $dataRoot "public-$portNumber-$stamp-error.log"
        $tunnelArguments = "tunnel --url http://127.0.0.1:$portNumber --protocol http2 --no-autoupdate"
        $newTunnel = Start-Process -FilePath $tunnelExe -ArgumentList $tunnelArguments -WorkingDirectory $portalRoot -WindowStyle Hidden -RedirectStandardOutput $tunnelOut -RedirectStandardError $tunnelLog -PassThru
        $launchedRecords += Get-CimInstance Win32_Process -Filter "ProcessId=$($newTunnel.Id)"
        $publicUrl = $null
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            if ($newTunnel.HasExited) { throw "The tunnel exited. Inspect $tunnelLog" }
            if (Test-Path -LiteralPath $tunnelLog) {
                $match = [regex]::Match([string](Get-Content -LiteralPath $tunnelLog -Raw), 'https://[a-z0-9-]+\.trycloudflare\.com')
                if ($match.Success) { $publicUrl = $match.Value; break }
            }
            Start-Sleep -Seconds 1
        }
        if (-not $publicUrl) { throw "No public URL was received. Inspect $tunnelLog" }
        $serverArguments = '"' + $serverScript + '" --port ' + $portNumber + ' --public-origin ' + $publicUrl
        $newPortal = Start-Process -FilePath $pythonExe -ArgumentList $serverArguments -WorkingDirectory $portalRoot -WindowStyle Hidden -RedirectStandardOutput $portalLog -RedirectStandardError $portalError -PassThru
        $serverRecord = Get-CimInstance Win32_Process -Filter "ProcessId=$($newPortal.Id)"
        $launchedRecords += $serverRecord
        $tunnelRecord = Get-CimInstance Win32_Process -Filter "ProcessId=$($newTunnel.Id)"
        if (-not $serverRecord -or -not $tunnelRecord) { throw "A process exited during startup. Inspect $portalError and $tunnelLog" }
        $state = [pscustomobject]@{
            schema = 1; project_root = $portalRoot; url = $publicUrl; port = $portNumber
            portal_pid = $newPortal.Id; tunnel_pid = $newTunnel.Id
            portal_created = $serverRecord.CreationDate.ToUniversalTime().ToString('o')
            tunnel_created = $tunnelRecord.CreationDate.ToUniversalTime().ToString('o')
            python_path = $pythonExe; tunnel_path = $tunnelExe
            portal_log = $portalLog; portal_error = $portalError; tunnel_log = $tunnelLog
            updated = ''
        }
        Save-State $state
        $newStateSaved = $true
    }

    Write-Host ('PUBLIC URL: ' + $state.url)
    $healthy = $false
    for ($attempt = 0; $attempt -lt 12; $attempt++) {
        $currentPortal = Get-OwnedProcess $state 'portal'
        $currentTunnel = Get-OwnedProcess $state 'tunnel'
        if (-not $currentPortal -or -not $currentTunnel) {
            throw ('The project process is no longer running. If its port was taken, rerun this launcher for a new free port. No other application is stopped. Server log: ' + $state.portal_error)
        }
        try {
            $local = Invoke-RestMethod -Uri ("http://127.0.0.1:" + $state.port + '/api/status') -TimeoutSec 5
            $public = Invoke-RestMethod -Uri ($state.url + '/api/status') -TimeoutSec 10
            if ($local.service -eq 'scan3d-portal' -and $public.service -eq 'scan3d-portal' -and $public.setup -eq $false) { $healthy = $true; break }
        } catch { Write-Host 'Waiting for HTTPS connectivity...' }
        Start-Sleep -Seconds 2
    }
    if (-not $healthy) { throw 'HTTPS status did not pass. No new QR was generated. Keep the logs and retry when connectivity recovers.' }
    & $pythonExe $qrScript $state.url
    if ($LASTEXITCODE -ne 0) { throw 'QR generation or decode check failed; do not distribute a new QR yet.' }
    Save-State $state
    Write-Host 'Public status check and QR decode check passed.' -ForegroundColor Green
    Write-Host ('QR files: ' + (Join-Path $dataRoot 'public-delivery'))
    Write-Host 'Keep this computer awake and online. Recreating the tunnel changes the URL and QR.'
    Write-Host 'This window may be closed. Use stop-public.ps1 to stop only the verified project processes.'
    exit 0
} catch {
    $startupFailure = $_.Exception.Message
    # Before a usable state file exists, clean up only processes this invocation
    # created, and only if their full identity still matches the original record.
    if (-not $newStateSaved) {
        foreach ($launched in $launchedRecords) {
            if (-not $launched) { continue }
            try {
                $current = Get-CimInstance Win32_Process -Filter "ProcessId=$($launched.ProcessId)"
                if ($current -and $current.ExecutablePath -eq $launched.ExecutablePath -and $current.CommandLine -eq $launched.CommandLine -and $current.CreationDate -eq $launched.CreationDate) {
                    Stop-Process -Id $current.ProcessId -ErrorAction Stop
                }
            } catch { Write-Host 'A newly created process could not be checked; it was left untouched.' }
        }
    }
    Write-Host ('[FAILED] ' + $startupFailure) -ForegroundColor Red
    Write-Host 'Public readiness was not confirmed. Do not use an old QR as proof that the website is online.'
    exit 1
}
