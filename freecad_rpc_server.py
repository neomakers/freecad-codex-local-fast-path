"""Small local RPC server that runs inside FreeCAD.

This is an alternate integration route: Codex talks to FreeCAD over localhost
instead of making FreeCAD AI call Codex as an LLM provider.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import FreeCAD as App

try:
    import FreeCADGui as Gui
except Exception:
    Gui = None

try:
    from PySide6 import QtCore
except Exception:
    try:
        from PySide2 import QtCore
    except Exception:
        QtCore = None


HOST = "127.0.0.1"
PORT = 8765


def _doc():
    doc = App.ActiveDocument
    if doc is None:
        doc = App.newDocument("Codex_FreeCAD")
    return doc


def _fit_view():
    if Gui is None:
        return
    try:
        if Gui.ActiveDocument and Gui.ActiveDocument.ActiveView:
            Gui.ActiveDocument.ActiveView.fitAll()
    except Exception:
        pass


def _create_box(args):
    import Part

    t0 = time.perf_counter()
    length = float(args.get("length", args.get("x", 10)))
    width = float(args.get("width", args.get("y", length)))
    height = float(args.get("height", args.get("z", length)))
    name = str(args.get("name") or "Codex_Box")
    fit_view = bool(args.get("fit_view", False))

    doc = _doc()
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = Part.makeBox(length, width, height)
    obj.Label = name
    doc.recompute()
    if fit_view:
        _fit_view()

    return {
        "ok": True,
        "object": obj.Name,
        "label": obj.Label,
        "shape": "box",
        "length": length,
        "width": width,
        "height": height,
        "document": doc.Name,
        "server_elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
    }


def _document_info(_args):
    doc = App.ActiveDocument
    if doc is None:
        return {"ok": True, "document": None, "objects": []}
    return {
        "ok": True,
        "document": doc.Name,
        "file": doc.FileName,
        "objects": [
            {
                "name": obj.Name,
                "label": obj.Label,
                "type": obj.TypeId,
            }
            for obj in doc.Objects
        ],
    }


def _run_python(args):
    code = str(args.get("code") or "")
    if not code.strip():
        return {"ok": False, "error": "No code supplied."}
    namespace = {"App": App, "Gui": Gui}
    exec(code, namespace, namespace)
    doc = App.ActiveDocument
    if doc:
        doc.recompute()
    _fit_view()
    return {"ok": True, "result": namespace.get("result")}


def _warmup():
    try:
        import Part

        doc = _doc()
        obj = doc.addObject("Part::Feature", "__CodexRPCWarmup")
        obj.Shape = Part.makeBox(0.1, 0.1, 0.1)
        doc.recompute()
        doc.removeObject(obj.Name)
        doc.recompute()
        App.Console.PrintMessage("Codex FreeCAD RPC warmup complete.\n")
    except Exception as exc:
        App.Console.PrintWarning(f"Codex FreeCAD RPC warmup failed: {exc}\n")


ACTIONS = {
    "create_box": _create_box,
    "document_info": _document_info,
    "run_python": _run_python,
}


_TASKS = queue.Queue()


def _run_on_main_thread(func, *args, **kwargs):
    if QtCore is None:
        return func(*args, **kwargs)
    done = threading.Event()
    item = {"func": func, "args": args, "kwargs": kwargs, "result": None, "error": None}
    _TASKS.put((item, done))
    if not done.wait(timeout=30):
        raise TimeoutError("Timed out waiting for FreeCAD main thread.")
    if item["error"] is not None:
        raise item["error"]
    return item["result"]


def _process_tasks():
    while True:
        try:
            item, done = _TASKS.get_nowait()
        except queue.Empty:
            break
        try:
            item["result"] = item["func"](*item["args"], **item["kwargs"])
        except Exception as exc:
            item["error"] = exc
        finally:
            done.set()


class Handler(BaseHTTPRequestHandler):
    server_version = "CodexFreeCADRPC/0.1"

    def log_message(self, fmt, *args):
        App.Console.PrintMessage("[Codex RPC] " + (fmt % args) + "\n")

    def _json(self, code, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.rstrip("/") == "/health":
            self._json(
                200,
                {
                    "ok": True,
                    "service": "codex-freecad-rpc",
                    "freecad_version": ".".join(App.Version()[:3]),
                    "time": time.time(),
                },
            )
            return
        if self.path.rstrip("/") == "/document":
            self._json(200, _run_on_main_thread(_document_info, {}))
            return
        self._json(404, {"ok": False, "error": "Unknown path"})

    def do_POST(self):
        if self.path.rstrip("/") != "/execute":
            self._json(404, {"ok": False, "error": "Unknown path"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length).decode("utf-8"))
            action = str(request.get("action") or "")
            args = request.get("args") or {}
            if action not in ACTIONS:
                self._json(400, {"ok": False, "error": "Unknown action", "action": action})
                return
            result = _run_on_main_thread(ACTIONS[action], args)
            self._json(200, result)
        except Exception as exc:
            self._json(
                500,
                {
                    "ok": False,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                },
            )


def start_server():
    _warmup()
    if QtCore is not None:
        timer = QtCore.QTimer()
        timer.timeout.connect(_process_tasks)
        timer.start(10)
        globals()["_CODEX_RPC_TIMER"] = timer
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    App.Console.PrintMessage(f"Codex FreeCAD RPC listening on http://{HOST}:{PORT}\n")
    return server


try:
    _CODEX_RPC_SERVER
except NameError:
    _CODEX_RPC_SERVER = start_server()
else:
    App.Console.PrintMessage("Codex FreeCAD RPC is already running.\n")
