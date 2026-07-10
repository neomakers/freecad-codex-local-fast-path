param(
    [switch]$InstallPlugin,
    [switch]$KeepProvider,
    [switch]$StartFreeCAD,
    [switch]$CheckOnly,
    [string]$FreeCADPath = "",
    [string]$PluginPath = "",
    [string]$FreeCADAIRepo = "https://github.com/ghbalf/freecad-ai.git"
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
$PayloadModule = Join-Path $RepoRoot "payload\freecad_ai\core\local_fast_path.py"
$PatchMarker = "# CODEX_FREECAD_FAST_PATH_V1"

function Write-Step([string]$Message) {
    Write-Host "[codex-freecad] $Message"
}

function Resolve-FreeCADExe {
    $candidates = @()
    if ($FreeCADPath) { $candidates += $FreeCADPath }
    try { $candidates += (Get-Command freecad.exe -ErrorAction Stop).Source } catch {}

    $patterns = @(
        "$env:ProgramFiles\FreeCAD*\bin\freecad.exe",
        "$env:ProgramW6432\FreeCAD*\bin\freecad.exe",
        "$env:ProgramFiles(x86)\FreeCAD*\bin\freecad.exe"
    )
    $patterns += @(Get-PSDrive -PSProvider FileSystem | ForEach-Object {
        Join-Path $_.Root "Program Files\FreeCAD*\bin\freecad.exe"
    })
    foreach ($pattern in $patterns) {
        $candidates += Get-ChildItem -Path $pattern -File -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty FullName
    }
    $found = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if (-not $found) {
        throw "FreeCAD was not found. Install FreeCAD or pass -FreeCADPath C:\Path\to\freecad.exe."
    }
    return (Resolve-Path -LiteralPath $found).Path
}

function Get-FreeCADVersionRoot([string]$Exe) {
    $cmd = [IO.Path]::ChangeExtension($Exe, "Cmd.exe")
    if (-not (Test-Path -LiteralPath $cmd)) { $cmd = Join-Path (Split-Path $Exe) "FreeCADCmd.exe" }
    $versionText = ""
    if (Test-Path -LiteralPath $cmd) {
        $versionText = (& $cmd --version 2>&1 | Out-String)
    }
    $match = [regex]::Match($versionText, "(\d+)\.(\d+)")
    if ($match.Success) {
        return Join-Path $env:APPDATA ("FreeCAD\v{0}-{1}" -f $match.Groups[1].Value, $match.Groups[2].Value)
    }

    $roots = Get-ChildItem (Join-Path $env:APPDATA "FreeCAD") -Directory -Filter "v*-*" -ErrorAction SilentlyContinue
    $root = $roots | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($root) { return $root.FullName }
    throw "Could not determine the FreeCAD user-data version directory."
}

function Resolve-FreeCADAIPlugin([string]$VersionRoot) {
    if ($PluginPath) {
        if (-not (Test-Path -LiteralPath $PluginPath)) { throw "Plugin path does not exist: $PluginPath" }
        return (Resolve-Path -LiteralPath $PluginPath).Path
    }

    $roots = @(
        (Join-Path $env:APPDATA "FreeCAD"),
        (Join-Path $env:LOCALAPPDATA "FreeCAD")
    ) | Where-Object { Test-Path -LiteralPath $_ }
    $found = foreach ($root in $roots) {
        Get-ChildItem -LiteralPath $root -Directory -Recurse -Filter "freecad-ai" -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "[\\/]Mod[\\/]freecad-ai$" }
    }
    $plugin = $found | Select-Object -First 1
    if ($plugin) { return $plugin.FullName }

    if (-not $InstallPlugin) {
        throw "FreeCAD AI was not found. Install it first, or rerun with -InstallPlugin."
    }

    $destination = Join-Path $VersionRoot "Mod\freecad-ai"
    New-Item -ItemType Directory -Force -Path (Split-Path $destination) | Out-Null
    if (Test-Path -LiteralPath $destination) {
        throw "The expected FreeCAD AI destination already exists but was not discovered: $destination"
    }

    $git = Get-Command git.exe -ErrorAction SilentlyContinue
    if ($git) {
        Write-Step "Cloning FreeCAD AI from $FreeCADAIRepo"
        & $git.Source clone --depth 1 $FreeCADAIRepo $destination
    } else {
        $zip = Join-Path $env:TEMP "freecad-ai.zip"
        $extract = Join-Path $env:TEMP "freecad-ai-extract"
        Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $extract -Recurse -Force -ErrorAction SilentlyContinue
        Write-Step "Downloading FreeCAD AI from $FreeCADAIRepo"
        Invoke-WebRequest -Uri ($FreeCADAIRepo.TrimEnd("/") + "/archive/refs/heads/main.zip") -OutFile $zip
        Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
        $source = Get-ChildItem -LiteralPath $extract -Directory | Select-Object -First 1
        if (-not $source) { throw "The downloaded FreeCAD AI archive was empty." }
        Move-Item -LiteralPath $source.FullName -Destination $destination
    }
    return $destination
}

function Read-Utf8([string]$Path) {
    return [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8)
}

function Write-Utf8([string]$Path, [string]$Text) {
    $utf8 = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, $Text, $utf8)
}

function Add-OrSetProperty($Object, [string]$Name, $Value) {
    if ($null -eq $Object.PSObject.Properties[$Name]) {
        $Object | Add-Member -MemberType NoteProperty -Name $Name -Value $Value
    } else {
        $Object.$Name = $Value
    }
}

function Update-FreeCADAIConfig([string]$ConfigPath) {
    if (Test-Path -LiteralPath $ConfigPath) {
        $config = (Read-Utf8 $ConfigPath | ConvertFrom-Json)
    } else {
        $config = [pscustomobject]@{}
    }
    if ($null -eq $config.provider) { Add-OrSetProperty $config "provider" ([pscustomobject]@{}) }
    if (-not $KeepProvider) {
        Add-OrSetProperty $config.provider "name" "custom"
        Add-OrSetProperty $config.provider "base_url" "http://127.0.0.1:8787/v1"
        Add-OrSetProperty $config.provider "model" "codex-cli"
        if ($null -eq $config.provider.api_key) { Add-OrSetProperty $config.provider "api_key" "" }
    }
    Add-OrSetProperty $config "mode" "act"
    Add-OrSetProperty $config "enable_tools" $true
    Add-OrSetProperty $config "tools_detected" $true
    New-Item -ItemType Directory -Force -Path (Split-Path $ConfigPath) | Out-Null
    Write-Utf8 $ConfigPath (($config | ConvertTo-Json -Depth 30) + [Environment]::NewLine)
}

function Get-ChatPatchMethod {
    return @'
    def _run_local_fast_path(self) -> bool:
        """Execute a safe local primitive plan without an LLM round trip."""
        if not self.registry:
            return False

        from ..core.local_fast_path import plan_local_tool

        plan = plan_local_tool(self.messages, self.registry)
        if plan is None:
            return False

        call_id = f"local-fast-{int(time.time() * 1000)}"
        self.tool_call_started.emit(plan.name, call_id)

        from ..hooks import fire_hook
        hook_result = fire_hook("pre_tool_use", {
            "tool_name": plan.name,
            "arguments": plan.arguments,
            "turn": 0,
        })
        started = time.time()
        if hook_result.get("block"):
            result = {
                "success": False,
                "output": "",
                "error": f"Blocked by hook: {hook_result.get('reason', '')}",
            }
        else:
            result = self._execute_tool_on_main_thread(plan.name, plan.arguments)

        elapsed = time.time() - started
        success = result.get("success", False)
        output = result.get("output", "")
        error = result.get("error", "")
        result_text = output if success else f"Error: {error}"
        self._tool_timeline.append({
            "name": plan.name,
            "success": success,
            "elapsed": elapsed,
            "turn": 0,
        })
        self.tool_call_finished.emit(plan.name, call_id, success, result_text)
        fire_hook("post_tool_use", {
            "tool_name": plan.name,
            "arguments": plan.arguments,
            "success": success,
            "output": output,
            "error": error,
            "turn": 0,
        })

        assistant_text = f"{plan.summary} ({elapsed * 1000:.1f} ms)"
        self._full_response = f"{assistant_text}\n\n{result_text}"
        self._tool_results.append({
            "assistant_text": assistant_text,
            "tool_calls": [{
                "id": call_id,
                "name": plan.name,
                "arguments": plan.arguments,
            }],
            "results": [{"tool_call_id": call_id, "content": result_text}],
        })
        self.token_received.emit(self._full_response)
        self.response_finished.emit(self._full_response)
        return True
'@
}

function Patch-ChatWidget([string]$ChatPath) {
    $text = Read-Utf8 $ChatPath
    if ($text.Contains($PatchMarker)) {
        Write-Step "Chat worker patch already present"
        return $false
    }

    # The original local prototype used the same worker method but did not
    # write a marker. Recognize it so this installer upgrades in place instead
    # of inserting a second copy.
    if ($text.Contains("def _run_local_fast_path(self) -> bool:") -and
        $text.Contains("if self.tools and self._run_local_fast_path():")) {
        Write-Utf8 $ChatPath ($PatchMarker + "`r`n" + $text)
        Write-Step "Recognized the existing local fast path and added its marker"
        return $true
    }

    $import = "            from ..llm.client import create_client_from_config, should_strip_thinking"
    if (-not $text.Contains($import)) {
        throw "Unsupported FreeCAD AI chat_widget.py: expected LLM worker anchor was not found. No patch was applied."
    }
    $runInsertion = @"
            $PatchMarker
            if self.tools and self._run_local_fast_path():
                return

$import
"@
    $text = $text.Replace($import, $runInsertion.TrimEnd())

    $methodAnchor = "    def _wrap_describe_fn(self, describe_fn):"
    if (-not $text.Contains($methodAnchor)) {
        throw "Unsupported FreeCAD AI chat_widget.py: method insertion anchor was not found."
    }
    $text = $text.Replace($methodAnchor, ((Get-ChatPatchMethod) + "`r`n`r`n" + $methodAnchor))
    Write-Utf8 $ChatPath $text
    Write-Step "Inserted the local fast path into chat_widget.py"
    return $true
}

function Start-Bridge {
    $bridgeScript = Join-Path $RepoRoot "start_codex_freecad_bridge.ps1"
    $listening = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue
    if (-not $listening) {
        Start-Process -FilePath powershell.exe -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $bridgeScript
        ) -WorkingDirectory $RepoRoot -WindowStyle Hidden
        Start-Sleep -Seconds 2
    }
}

if (-not (Test-Path -LiteralPath $PayloadModule)) {
    throw "Repository payload is missing: $PayloadModule"
}

$freecad = Resolve-FreeCADExe
$env:FREECAD_BIN = Split-Path -Parent $freecad
$versionRoot = Get-FreeCADVersionRoot $freecad
$plugin = Resolve-FreeCADAIPlugin $versionRoot
$chat = Join-Path $plugin "freecad_ai\ui\chat_widget.py"
$installedModule = Join-Path $plugin "freecad_ai\core\local_fast_path.py"
$configDir = Join-Path $versionRoot "FreeCADAI"
$config = Join-Path $configDir "config.json"
$manifest = Join-Path $configDir "codex-freecad-integration.json"

if (-not (Test-Path -LiteralPath $chat)) { throw "FreeCAD AI chat widget was not found: $chat" }

if ($CheckOnly) {
    $chatText = Read-Utf8 $chat
    $checks = [ordered]@{
        FreeCAD = $freecad
        FreeCADUserRoot = $versionRoot
        FreeCADAI = $plugin
        FastPathModule = (Test-Path -LiteralPath $installedModule)
        ChatPatch = $chatText.Contains($PatchMarker)
        Config = (Test-Path -LiteralPath $config)
        Bridge = $false
    }
    try {
        $response = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8787/v1/models" -TimeoutSec 2
        $checks.Bridge = $response.StatusCode -eq 200
    } catch {}
    $checks | ConvertTo-Json -Depth 5
    if (-not $checks.FastPathModule -or -not $checks.ChatPatch -or -not $checks.Config) {
        exit 2
    }
    exit 0
}

New-Item -ItemType Directory -Force -Path $configDir | Out-Null
$existingManifest = $null
if (Test-Path -LiteralPath $manifest) {
    try { $existingManifest = Read-Utf8 $manifest | ConvertFrom-Json } catch {}
}
$backupDir = $null
$firstInstall = $true
if ($existingManifest -and $existingManifest.backup_dir -and
    (Test-Path -LiteralPath $existingManifest.backup_dir)) {
    $backupDir = $existingManifest.backup_dir
    $firstInstall = $false
    Write-Step "Reusing the original rollback baseline at $backupDir"
}
if ($firstInstall) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupDir = Join-Path $configDir "CodexFreeCADBackups\$timestamp"
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    foreach ($path in @($chat, $installedModule, $config)) {
        if (Test-Path -LiteralPath $path) {
            Copy-Item -LiteralPath $path -Destination $backupDir -Force
        }
    }
}

Copy-Item -LiteralPath $PayloadModule -Destination $installedModule -Force
[void](Patch-ChatWidget $chat)
Update-FreeCADAIConfig $config

$manifestData = [ordered]@{
    integration_version = "1.0.0"
    installed_at = (Get-Date).ToString("o")
    repository = "Codex-FreeCAD local fast path"
    freecad = $freecad
    freecad_user_root = $versionRoot
    freecad_ai_plugin = $plugin
    backup_dir = $backupDir
    bridge_url = "http://127.0.0.1:8787/v1"
    patch_marker = $PatchMarker
}
Write-Utf8 $manifest (($manifestData | ConvertTo-Json -Depth 10) + [Environment]::NewLine)

Start-Bridge
Write-Step "Installed. FreeCAD: $freecad"
Write-Step "Plugin: $plugin"
Write-Step "Bridge: http://127.0.0.1:8787/v1"
if ($StartFreeCAD) {
    & (Join-Path $RepoRoot "start_freecad_with_codex_ai.ps1") -FreeCADPath $freecad
}
