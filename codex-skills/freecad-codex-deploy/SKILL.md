---
name: freecad-codex-deploy
description: Deploy and troubleshoot the local Codex CLI integration for FreeCAD_AI_Mod on Windows. Use when a user wants FreeCAD_AI_Mod to call Codex without an API key, wants the 20 ms local fast path for routine CAD commands, needs installation on another computer, or wants to verify, update, or roll back this integration.
---

# FreeCAD Codex Deploy

Use this skill to reproduce the tested `FreeCAD_AI_Mod` route on another Windows
computer. Keep the two execution paths explicit:

- Deterministic primitive commands run inside the FreeCAD AI worker and reuse
  its existing `create_primitive` tool. This is the low-latency path.
- Complex requests go through the localhost OpenAI-compatible bridge to Codex
  CLI. This path is model- and network-dependent; never promise 20 ms for it.

## Deploy

1. Locate the repository root containing `install.ps1`.
2. Run PowerShell with a process-scoped execution-policy bypass.
3. Run `install.ps1 -InstallPlugin -StartFreeCAD` when the upstream FreeCAD AI package is missing. The installer displays it as `FreeCAD_AI_Mod`.
   Omit `-InstallPlugin` when it is already installed.
4. Use `-KeepProvider` when the user wants to preserve an existing provider;
   otherwise configure the custom provider at `http://127.0.0.1:8787/v1`.
5. Run `verify.ps1` and report its JSON plus the bridge health result.

After installation, loading, activating, or opening the `FreeCAD_AI_Mod` chat
repairs the integration-owned provider settings and starts the bridge if it is
down. The user does not need to launch a separate bridge window.

The installer must discover paths. Never copy the local `D:` drive path or the
local `E:` workspace path into a user's configuration. It creates a timestamped
backup and refuses to patch `chat_widget.py` if the expected upstream anchor is
missing.

## Diagnose

Check these in order:

1. FreeCAD AI plugin path ends in `Mod\freecad-ai`.
2. `freecad_ai\core\local_fast_path.py` exists.
3. `chat_widget.py` contains `CODEX_FREECAD_FAST_PATH_V1` exactly once.
4. `FreeCADAI\config.json` has `mode=act`, `enable_tools=true`, and
   `tools_detected=true`. For the Codex route, provider base URL must be
   `http://127.0.0.1:8787/v1`.
5. `http://127.0.0.1:8787/v1/models` returns HTTP 200.

If the bridge is unavailable, run `start_codex_freecad_bridge.ps1` and inspect
`%LOCALAPPDATA%\CodexFreeCADBridge\bridge.log`. Codex CLI must already be
installed or exposed by Codex Desktop and authenticated through ChatGPT.

If the installer reports an unsupported upstream plugin, stop and inspect the
new plugin version. Update the patch anchor and test it before using `-Force`
or making any manual edit. For rollback, run `uninstall.ps1`; never delete the
timestamped backup as part of diagnosis.

## Extend

Add new deterministic routes only when their input grammar is unambiguous and
their execution can reuse an existing FreeCAD tool. Put the parser in
`payload/freecad_ai/core/local_fast_path.py`, add a regression test, copy the
payload through the installer, and keep ambiguous or visual requests on the
normal model path. Share the parser between the plugin and bridge so behavior
does not drift.

## User-facing verification

After deployment, test these in the FreeCAD AI chat dock while in Act mode:

```text
create a box 40 x 30 x 20 mm
create a cylinder diameter 20 mm height 35 mm
```

Confirm a parametric object appears in the FreeCAD model tree and the chat
shows a local fast-path timing. Then test one complex request and confirm it
falls back to Codex instead of being incorrectly handled by the parser.
