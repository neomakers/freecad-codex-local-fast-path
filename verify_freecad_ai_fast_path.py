import os
import sys
from pathlib import Path

import FreeCAD as App

repo_root = Path(__file__).resolve().parent
plugin_path = os.environ.get("FREECAD_AI_PLUGIN_PATH", "")
if not plugin_path:
    freecad_root = Path(os.environ.get("APPDATA", "")) / "FreeCAD"
    matches = list(freecad_root.glob("v*-*/Mod/freecad-ai"))
    if matches:
        plugin_path = str(sorted(matches, key=lambda p: p.stat().st_mtime, reverse=True)[0])
if not plugin_path or not Path(plugin_path).is_dir():
    raise RuntimeError("FreeCAD AI plugin was not found. Run install.ps1 first.")
sys.path.insert(0, plugin_path)

from freecad_ai.core.local_fast_path import plan_local_tool
from freecad_ai.core.codex_autostart import ensure_codex_connection
from freecad_ai.tools.freecad_tools import _handle_create_primitive


class _Registry:
    def get(self, name):
        return object() if name == "create_primitive" else None


prompt = "\u521b\u5efa\u4e00\u4e2a 40 x 30 x 20 mm \u7684\u76d2\u5b50"
plan = plan_local_tool([{"role": "user", "content": prompt}], _Registry())
assert plan is not None, "The local parser did not recognize the command"
assert plan.arguments["length"] == 40.0
assert plan.arguments["width"] == 30.0
assert plan.arguments["height"] == 20.0

doc = App.newDocument("FastPathVerification")
result = _handle_create_primitive(**plan.arguments)
assert result.success, result.error

connection = ensure_codex_connection()
assert connection["ok"], connection

box = doc.getObject(result.data["name"])
assert box is not None
assert (box.Length, box.Width, box.Height) == (40.0, 30.0, 20.0)
print("PASS: local fast path created a 40 x 30 x 20 mm PartDesign box")
print("PASS: FreeCAD AI auto-connect is ready")
