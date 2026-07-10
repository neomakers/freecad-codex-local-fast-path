$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$Bridge = Join-Path $ScriptDir "codex_freecad_bridge.py"
$BridgeDir = Join-Path $env:LOCALAPPDATA "CodexFreeCADBridge"
$StableCodex = Join-Path $BridgeDir "codex.exe"
New-Item -ItemType Directory -Force -Path $BridgeDir | Out-Null

$Listening = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue
if ($Listening) {
    Write-Host "Codex FreeCAD bridge is already listening on http://127.0.0.1:8787/v1"
    exit 0
}

if (-not (Test-Path $StableCodex)) {
    $Candidates = @(
        "$env:LOCALAPPDATA\OpenAI\Codex\bin\codex.exe"
        "$env:LOCALAPPDATA\OpenAI\Codex\bin\*\codex.exe"
        "$env:TEMP\codex-cli-probe\codex.exe"
    )
    $Candidates += @(Get-ChildItem -Path "$env:LOCALAPPDATA\OpenAI\Codex\bin" -Filter "codex.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
    $Candidates += @(where.exe codex 2>$null | Where-Object { $_ -like "*.exe" })
    $Source = $Candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if (-not $Source) {
        throw "Codex CLI executable was not found. Open Codex Desktop once, or pass a codex.exe through CODEX_BRIDGE_CODEX_EXE."
    }
    Copy-Item -LiteralPath $Source -Destination $StableCodex -Force
}
$env:CODEX_BRIDGE_CODEX_EXE = $StableCodex
$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    $Python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $Python) {
    $freecadPython = Join-Path $env:FREECAD_BIN "python.exe"
    if (Test-Path -LiteralPath $freecadPython) {
        $Python = [pscustomobject]@{ Source = $freecadPython }
    }
}
if (-not $Python) {
    $pythonPatterns = @(
        "$env:ProgramFiles\FreeCAD*\bin\python.exe",
        "$env:ProgramW6432\FreeCAD*\bin\python.exe"
    )
    $pythonPatterns += @(Get-PSDrive -PSProvider FileSystem | ForEach-Object {
        Join-Path $_.Root "Program Files\FreeCAD*\bin\python.exe"
    })
    $freecadPython = Get-ChildItem -Path $pythonPatterns -File -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
    if ($freecadPython) {
        $Python = [pscustomobject]@{ Source = $freecadPython }
    }
}
if (-not $Python) {
    throw "Python was not found on PATH. Install Python or set FREECAD_BIN to the FreeCAD bin directory."
}
$StdoutLog = Join-Path $BridgeDir "bridge.stdout.log"
$StderrLog = Join-Path $BridgeDir "bridge.stderr.log"
$arguments = @($Bridge, "--host", "127.0.0.1", "--port", "8787")
$process = Start-Process -FilePath $Python.Source `
    -ArgumentList $arguments `
    -WorkingDirectory $ScriptDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $StdoutLog `
    -RedirectStandardError $StderrLog `
    -PassThru
Write-Host "Started Codex FreeCAD bridge (PID $($process.Id)) on http://127.0.0.1:8787/v1"
