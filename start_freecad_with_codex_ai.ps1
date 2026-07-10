param(
    [string]$FreeCADPath = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$BridgeScript = Join-Path $ScriptDir "start_codex_freecad_bridge.ps1"

if (-not $FreeCADPath) {
    try { $FreeCADPath = (Get-Command freecad.exe -ErrorAction Stop).Source } catch {}
}
if (-not $FreeCADPath) {
    $patterns = @(
        "$env:ProgramFiles\FreeCAD*\bin\freecad.exe",
        "$env:ProgramW6432\FreeCAD*\bin\freecad.exe"
    )
    $patterns += @(Get-PSDrive -PSProvider FileSystem | ForEach-Object {
        Join-Path $_.Root "Program Files\FreeCAD*\bin\freecad.exe"
    })
    foreach ($pattern in $patterns) {
        $candidate = Get-ChildItem -Path $pattern -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($candidate) { $FreeCADPath = $candidate.FullName; break }
    }
}
if (-not $FreeCADPath -or -not (Test-Path -LiteralPath $FreeCADPath)) {
    throw "FreeCAD was not found. Pass -FreeCADPath C:\Path\to\freecad.exe."
}
$env:FREECAD_BIN = Split-Path -Parent $FreeCADPath

$Listening = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8787 -ErrorAction SilentlyContinue |
    Where-Object { $_.State -eq "Listen" } |
    Select-Object -First 1

if (-not $Listening) {
    Start-Process -FilePath "powershell" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $BridgeScript) `
        -WorkingDirectory $ScriptDir `
        -WindowStyle Hidden
    Start-Sleep -Seconds 3
}

Start-Process -FilePath $FreeCADPath -WorkingDirectory $ScriptDir
