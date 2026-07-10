# Codex FreeCAD local fast path

This project connects the FreeCAD AI workbench to Codex CLI through a local,
OpenAI-compatible bridge while adding a deterministic local path for routine
geometry commands.

The result is a practical split:

- `create a box 40 x 30 x 20 mm` is parsed inside FreeCAD AI and immediately
  calls the existing parametric FreeCAD tool.
- A complex modeling request falls back to Codex CLI through
  `http://127.0.0.1:8787/v1`.
- Activating the FreeCAD AI workbench repairs the local provider configuration
  and starts the bridge automatically.
- No API key is added by this project. The bridge uses the Codex login already
  present on the computer.

## Quick install

On Windows, clone this repository and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1 -InstallPlugin -StartFreeCAD
```

If FreeCAD AI is already installed, omit `-InstallPlugin`. The installer is
safe to rerun and creates a timestamped rollback backup before changing the
plugin. Full deployment notes are in [docs/deployment.md](docs/deployment.md).

To give another Codex the same deployment knowledge, install the bundled Skill
from `codex-skills/freecad-codex-deploy` into its skills directory, or ask Codex
to install that folder from this GitHub repository. The Skill tells it to use
the installer, verify the patch marker, preserve backups, and keep complex
requests on the model path.

## Repository layout

- `install.ps1`: discovers the local installation, applies the guarded patch,
  configures the provider, and starts the bridge.
- `verify.ps1`: reports whether the integration is complete.
- `uninstall.ps1`: restores the newest backup.
- `codex_freecad_bridge.py`: localhost fallback server.
- `payload/freecad_ai/core/local_fast_path.py`: shared deterministic parser
  copied into FreeCAD AI and reused by the bridge.
- `codex-skills/freecad-codex-deploy`: reusable instructions for another Codex
  instance to deploy and troubleshoot the route.
- `.github/workflows/validate.yml`: dependency-light regression checks for the
  parser, bridge, and PowerShell entry points.

## What this does not promise

Remote model reasoning cannot be made 20 ms by changing the transport. The
20 ms target applies to deterministic local commands. Complex requests still
depend on Codex authentication, network reachability, and model response time.
