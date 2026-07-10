param(
    [string]$ManifestPath = ""
)

$ErrorActionPreference = "Stop"
if (-not $ManifestPath) {
    $roots = Get-ChildItem (Join-Path $env:APPDATA "FreeCAD") -Directory -Recurse -Filter "codex-freecad-integration.json" -ErrorAction SilentlyContinue
    $ManifestPath = ($roots | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
}
if (-not $ManifestPath -or -not (Test-Path -LiteralPath $ManifestPath)) {
    throw "No Codex-FreeCAD integration manifest was found."
}

$manifest = Get-Content -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
$backup = $manifest.backup_dir
$plugin = $manifest.freecad_ai_plugin
$versionRoot = $manifest.freecad_user_root
if (-not (Test-Path -LiteralPath $backup)) { throw "Backup directory is missing: $backup" }

function Restore-Optional([string]$Name, [string]$Destination) {
    $source = Join-Path $backup $Name
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination $Destination -Force
        Write-Host "Restored $Destination"
    }
}

Restore-Optional "chat_widget.py" (Join-Path $plugin "freecad_ai\ui\chat_widget.py")
Restore-Optional "local_fast_path.py" (Join-Path $plugin "freecad_ai\core\local_fast_path.py")
Restore-Optional "config.json" (Join-Path $versionRoot "FreeCADAI\config.json")
Write-Host "Rollback complete. The backup was kept at $backup."
