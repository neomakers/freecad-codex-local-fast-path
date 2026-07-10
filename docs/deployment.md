# Codex + FreeCAD AI deployment

This repository packages the tested local integration between the FreeCAD AI
workbench and Codex CLI. The important design choice is to keep three paths
separate:

1. The FreeCAD AI chat worker handles the UI and executes FreeCAD tools on the
   Qt main thread.
2. The local fast path recognizes only unambiguous primitive commands and
   executes the existing `create_primitive` tool without a model request.
3. The localhost bridge is an OpenAI-compatible fallback for complex requests
   and runs Codex CLI using the user's existing ChatGPT login.

That separation is what keeps simple commands near the local 5-20 ms range
without pretending that remote model reasoning can be 20 ms.

## Install on another Windows computer

Prerequisites:

- FreeCAD 1.0 or newer.
- The FreeCAD AI workbench installed, or use `-InstallPlugin`.
- Codex Desktop/CLI already signed in with ChatGPT.
- PowerShell 5.1 or newer.

From a clone of this repository:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1 -InstallPlugin -StartFreeCAD
```

The installer discovers FreeCAD, discovers the versioned FreeCAD user folder,
finds or installs FreeCAD AI, checks the expected source anchors, creates a
timestamped backup, installs the payload, configures the localhost provider,
starts the bridge, and records a manifest for rollback. The installed
workbench also runs the same connection check when FreeCAD AI is activated, so
opening FreeCAD manually does not depend on a previously running bridge.

For a machine that already has FreeCAD AI:

```powershell
.\install.ps1 -StartFreeCAD
```

To preserve an existing provider while still enabling the local fast path:

```powershell
.\install.ps1 -KeepProvider
```

## Verify and rollback

```powershell
.\verify.ps1
.\uninstall.ps1
```

`verify.ps1` exits with code `0` only when the plugin payload, chat patch, and
configuration are present. The bridge status is included in the JSON report.
`uninstall.ps1` restores the newest backup and never deletes the backup itself.

The workbench activation hook is the normal runtime path. It repairs the
integration-owned custom provider settings in both the JSON file and the
in-memory FreeCAD AI config, then starts the bridge only when port 8787 is not
ready.

## Updating the integration

The patch is guarded by `CODEX_FREECAD_FAST_PATH_V1`. Re-running the installer
is idempotent: it updates the shared payload but does not insert a second chat
worker block. If the upstream FreeCAD AI chat file changes and the expected
anchor is gone, the installer stops with a readable error instead of applying a
blind text replacement. Update the patcher and test it against that upstream
version before publishing a new integration version.
