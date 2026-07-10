"""Keep the FreeCAD AI workbench connected to the local Codex bridge."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path


BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8787
BRIDGE_URL = f"http://{BRIDGE_HOST}:{BRIDGE_PORT}/v1"


def _freecad_config_root() -> Path | None:
    try:
        import FreeCAD as App

        getter = getattr(App, "getUserConfigDir", None)
        if getter:
            path = getter()
            if path:
                return Path(path)
        version = App.Version()
        if version and len(version) >= 2:
            return Path(os.environ.get("APPDATA", Path.home())) / "FreeCAD" / f"v{version[0]}-{version[1]}"
    except Exception:
        pass
    return None


def _integration_dir() -> Path | None:
    root = _freecad_config_root()
    return root / "FreeCADAI" if root else None


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _repair_config(integration_dir: Path, manifest: dict) -> bool:
    """Make the installed workbench use the configured local bridge."""
    if manifest.get("keep_provider"):
        return False
    path = integration_dir / "config.json"
    config = _read_json(path)
    provider = config.setdefault("provider", {})
    changed = (
        provider.get("name") != "custom"
        or provider.get("base_url") != BRIDGE_URL
        or provider.get("model") != "codex-cli"
        or config.get("mode") != "act"
        or config.get("enable_tools") is not True
        or config.get("tools_detected") is not True
    )
    provider["name"] = "custom"
    provider["base_url"] = BRIDGE_URL
    provider["model"] = "codex-cli"
    provider.setdefault("api_key", "")
    config["mode"] = "act"
    config["enable_tools"] = True
    config["tools_detected"] = True
    if changed:
        _write_json(path, config)
        # The settings module may already have a singleton in this FreeCAD
        # session. Keep it aligned with the file we just repaired.
        try:
            from ..config import get_config

            current = get_config()
            current.provider.name = "custom"
            current.provider.base_url = BRIDGE_URL
            current.provider.model = "codex-cli"
            current.mode = "act"
            current.enable_tools = True
            current.tools_detected = True
        except Exception:
            pass
    return changed


def _bridge_ready() -> bool:
    try:
        with socket.create_connection((BRIDGE_HOST, BRIDGE_PORT), timeout=0.15):
            return True
    except OSError:
        return False


def _start_bridge(manifest: dict) -> bool:
    script = manifest.get("bridge_start_script")
    if not script or not Path(script).is_file():
        return False
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script],
            cwd=str(Path(script).parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=flags,
        )
    except OSError:
        return False

    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if _bridge_ready():
            return True
        time.sleep(0.1)
    return _bridge_ready()


def ensure_codex_connection() -> dict:
    """Repair config and start the bridge when the AI workbench activates."""
    integration_dir = _integration_dir()
    if integration_dir is None:
        return {"ok": False, "reason": "FreeCAD config directory unavailable"}
    manifest = _read_json(integration_dir / "codex-freecad-integration.json")
    config_changed = _repair_config(integration_dir, manifest)
    ready_before = _bridge_ready()
    ready_after = ready_before or _start_bridge(manifest)
    return {
        "ok": ready_after,
        "bridge_ready": ready_after,
        "config_repaired": config_changed,
        "bridge_url": BRIDGE_URL,
    }
