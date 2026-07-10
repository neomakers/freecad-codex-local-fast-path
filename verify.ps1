param(
    [string]$FreeCADPath = "",
    [string]$PluginPath = ""
)

& (Join-Path $PSScriptRoot "install.ps1") -CheckOnly -FreeCADPath $FreeCADPath -PluginPath $PluginPath
exit $LASTEXITCODE
