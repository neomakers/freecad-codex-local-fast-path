$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Server = Join-Path $ScriptDir "freecad_rpc_server.py"
$FreeCAD = $env:FREECAD_PATH
if (-not $FreeCAD) {
    try { $FreeCAD = (Get-Command freecad.exe -ErrorAction Stop).Source } catch {}
}
if (-not $FreeCAD) {
    $patterns = @(
        "$env:ProgramFiles\FreeCAD*\bin\freecad.exe",
        "$env:ProgramW6432\FreeCAD*\bin\freecad.exe"
    )
    $patterns += @(Get-PSDrive -PSProvider FileSystem | ForEach-Object {
        Join-Path $_.Root "Program Files\FreeCAD*\bin\freecad.exe"
    })
    foreach ($pattern in $patterns) {
        $candidate = Get-ChildItem -Path $pattern -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($candidate) { $FreeCAD = $candidate.FullName; break }
    }
}
if (-not $FreeCAD -or -not (Test-Path -LiteralPath $FreeCAD)) {
    throw "FreeCAD was not found. Set FREECAD_PATH or pass a discoverable FreeCAD installation."
}

$Listening = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8765 -ErrorAction SilentlyContinue |
    Where-Object { $_.State -eq "Listen" } |
    Select-Object -First 1

if ($Listening) {
    Write-Host "FreeCAD RPC is already listening on http://127.0.0.1:8765"
    exit 0
}

Start-Process -FilePath $FreeCAD -ArgumentList @($Server) -WorkingDirectory $ScriptDir
Write-Host "Starting FreeCAD RPC on http://127.0.0.1:8765"
