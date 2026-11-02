# Stop only the two project processes identified by the saved state.
# No matching by port alone, process name alone, or broad process lists.
$ErrorActionPreference = 'Stop'
$portalRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$stateFile = Join-Path $portalRoot 'data\public-state.json'
$tunnelExe = Join-Path $portalRoot 'tools\cloudflared.exe'
$serverScript = Join-Path $portalRoot 'server.py'

function Convert-SavedTimeToUtc($value) {
    # Preserve a DateTime's Kind under PowerShell 7; parse ISO strings under 5.1.
    if ($value -is [DateTimeOffset]) { return $value.UtcDateTime }
    if ($value -is [DateTime]) {
        if ($value.Kind -eq [DateTimeKind]::Unspecified) { throw 'Saved process time has no timezone.' }
        return $value.ToUniversalTime()
    }
    if ([string]$value -notmatch '(?:Z|[+-]\d{2}:\d{2})$') { throw 'Saved process time has no timezone.' }
    return [DateTimeOffset]::Parse([string]$value, [Globalization.CultureInfo]::InvariantCulture).UtcDateTime
}

try {
    if (-not (Test-Path -LiteralPath $stateFile)) {
        Write-Host 'No saved public deployment state. No process was changed.'
        exit 0
    }
    $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    if ($state.project_root -ne $portalRoot -or $state.url -notmatch '^https://[a-z0-9-]+\.trycloudflare\.com$') {
        throw 'The saved state does not match this project. Nothing was stopped.'
    }
    $portNumber = [int]$state.port
    if ($portNumber -lt 1024 -or $portNumber -gt 65535) { throw 'Invalid saved port. Nothing was stopped.' }
    $verified = @()
    foreach ($kind in @('tunnel', 'portal')) {
        $processNumber = [int]$state.($kind + '_pid')
        if ($processNumber -le 0) { throw 'Invalid saved process ID. Nothing was stopped.' }
        $record = Get-CimInstance Win32_Process -Filter "ProcessId=$processNumber"
        if (-not $record) { Write-Host "$kind is already stopped."; continue }
        $savedTimeUtc = Convert-SavedTimeToUtc $state.($kind + '_created')
        if ([Math]::Abs(($record.CreationDate.ToUniversalTime() - $savedTimeUtc).TotalSeconds) -gt 1) {
            throw "$kind PID has been reused by another process. Nothing was stopped."
        }
        if ($kind -eq 'tunnel') {
            $target = [regex]::Escape("http://127.0.0.1:$portNumber")
            if ($record.ExecutablePath -ne $tunnelExe -or $record.CommandLine -notmatch "\btunnel\s+--url\s+$target(?:\s|$)") {
                throw 'Tunnel identity differs from the saved deployment. Nothing was stopped.'
            }
        } else {
            $scriptArgument = '(?:"' + [regex]::Escape($serverScript) + '"|"?server\.py"?)'
            $originArgument = [regex]::Escape([string]$state.url)
            if ($record.ExecutablePath -ne $state.python_path -or $record.CommandLine -notmatch ("\s" + $scriptArgument + "\s+--port\s+$portNumber(?:\s|$)") -or $record.CommandLine -notmatch "--public-origin\s+$originArgument(?:\s|$)") {
                throw 'Server identity differs from the saved deployment. Nothing was stopped.'
            }
        }
        $verified += $record
    }
    # Validate both identities before changing either process; then recheck each
    # exact record immediately before stopping to guard against PID reuse.
    foreach ($record in $verified) {
        $current = Get-CimInstance Win32_Process -Filter "ProcessId=$($record.ProcessId)"
        if (-not $current) { continue }
        if ($current.CreationDate -ne $record.CreationDate -or $current.ExecutablePath -ne $record.ExecutablePath -or $current.CommandLine -ne $record.CommandLine) {
            throw 'Process identity changed during verification; it was left untouched.'
        }
        Stop-Process -Id $current.ProcessId -ErrorAction Stop
    }
    Write-Host 'The verified public server and tunnel have been stopped.'
    Write-Host 'Accounts and original model files are preserved. The next startup creates a new URL and QR.'
    exit 0
} catch {
    Write-Host ('[STOP FAILED] ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
