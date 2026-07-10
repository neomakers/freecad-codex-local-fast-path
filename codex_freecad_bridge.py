#!/usr/bin/env python3
"""OpenAI-compatible bridge from FreeCAD AI to the local Codex CLI.

FreeCAD AI can talk to any OpenAI-compatible /chat/completions endpoint.
This tiny stdlib-only server exposes that endpoint locally, calls Codex CLI
using the user's existing ChatGPT auth, then wraps the result back into the
OpenAI chat-completions shape FreeCAD AI expects.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
DEFAULT_WORKDIR = str(Path(__file__).resolve().parent)
DEFAULT_CODEX_MODEL = "gpt-5.5"


OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["content", "tool_calls"],
    "properties": {
        "content": {"type": "string"},
        "tool_calls": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "arguments_json"],
                "properties": {
                    "name": {"type": "string"},
                    "arguments_json": {"type": "string"},
                },
            },
        },
    },
}


def _local_appdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")


def _bridge_dir() -> Path:
    path = _local_appdata() / "CodexFreeCADBridge"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _find_packaged_codex() -> Path | None:
    patterns = [
        r"C:\Program Files\WindowsApps\OpenAI.Codex_*\app\resources\codex.exe",
        r"C:\Program Files\WindowsApps\OpenAI.Codex_*\app\resources\codex",
    ]
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(Path(p) for p in glob.glob(pattern))
    candidates = [p for p in candidates if p.exists()]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def resolve_codex_exe() -> Path:
    env_path = os.environ.get("CODEX_BRIDGE_CODEX_EXE")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    stable = _bridge_dir() / "codex.exe"
    source = _find_packaged_codex()
    if source and (not stable.exists() or source.stat().st_mtime > stable.stat().st_mtime):
        shutil.copy2(source, stable)
    if stable.exists():
        return stable

    found = shutil.which("codex")
    if found:
        return Path(found)
    raise FileNotFoundError("Could not find Codex CLI. Install or open Codex desktop first.")


def resolve_codex_model() -> str:
    """Choose a model supported by the bundled Codex CLI, with an override."""
    return os.environ.get("CODEX_BRIDGE_MODEL", "").strip() or DEFAULT_CODEX_MODEL


def content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                parts.append(str(item))
                continue
            if item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            elif item.get("type") in {"image_url", "image"}:
                parts.append("[Attached image omitted by Codex bridge]")
            else:
                parts.append(json.dumps(item, ensure_ascii=False))
        return "\n".join(p for p in parts if p)
    if content is None:
        return ""
    return json.dumps(content, ensure_ascii=False)


def compact_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tool in tools:
        fn = tool.get("function", {}) if isinstance(tool, dict) else {}
        if not isinstance(fn, dict):
            continue
        out.append(
            {
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {}),
            }
        )
    return out


def last_user_text(body: dict[str, Any]) -> str:
    for msg in reversed(body.get("messages") or []):
        if isinstance(msg, dict) and msg.get("role") == "user":
            return content_to_text(msg.get("content"))
    return ""


def available_tool_names(body: dict[str, Any]) -> set[str]:
    names = set()
    for tool in body.get("tools") or []:
        if isinstance(tool, dict):
            fn = tool.get("function") or {}
            if isinstance(fn, dict) and fn.get("name"):
                names.add(str(fn["name"]))
    return names


def try_fast_local_plan(body: dict[str, Any]) -> dict[str, Any] | None:
    """Return a local tool plan for very common CAD requests.

    This keeps the FreeCAD AI panel responsive for simple primitives and avoids
    using Codex CLI as a slow LLM endpoint for tasks a tiny parser can handle.
    """
    text = last_user_text(body).lower()
    if not text:
        return None
    tools = available_tool_names(body)
    wants_box = any(word in text for word in ["box", "cube", "盒子", "方块", "立方体", "长方体"])
    if not wants_box:
        return None

    numbers = [float(m.group(1)) for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:mm|毫米|cm|厘米)?", text)]
    if not numbers:
        length = width = height = 10.0
    elif len(numbers) == 1:
        length = width = height = numbers[0]
    else:
        length = numbers[0]
        width = numbers[1] if len(numbers) > 1 else numbers[0]
        height = numbers[2] if len(numbers) > 2 else numbers[0]

    if "create_primitive" in tools:
        return {
            "content": "",
            "tool_calls": [
                {
                    "name": "create_primitive",
                    "arguments": {
                        "shape_type": "box",
                        "label": "Codex_Box",
                        "length": length,
                        "width": width,
                        "height": height,
                    },
                }
            ],
        }
    if "create_box" in tools:
        return {
            "content": "",
            "tool_calls": [
                {
                    "name": "create_box",
                    "arguments": {"length": length, "width": width, "height": height},
                }
            ],
        }
    return None


def try_fast_local_plan(body: dict[str, Any]) -> dict[str, Any] | None:
    """Use the same parser shipped into the FreeCAD AI plugin."""
    text = last_user_text(body)
    if not text:
        return None
    payload_root = Path(__file__).resolve().parent / "payload"
    if not payload_root.is_dir():
        return None
    if str(payload_root) not in sys.path:
        sys.path.insert(0, str(payload_root))
    try:
        from freecad_ai.core.local_fast_path import plan_local_arguments
        plan = plan_local_arguments(text)
    except Exception:
        return None
    if plan is None or plan.name not in available_tool_names(body):
        return None
    return {
        "content": "",
        "tool_calls": [{"name": plan.name, "arguments": plan.arguments}],
    }


def build_codex_prompt(body: dict[str, Any]) -> str:
    messages = body.get("messages") or []
    tools = compact_tools(body.get("tools") or [])
    lines: list[str] = [
        "You are the reasoning backend for the FreeCAD AI workbench.",
        "FreeCAD AI will execute tool calls; you must not run shell commands or edit files yourself.",
        "Return only the JSON object required by the output schema.",
        "",
        "Output rules:",
        "- If the user asks for modeling/CAD actions and a relevant tool exists, return exactly one tool call.",
        "- If you need another step after seeing a tool result, return exactly one next tool call.",
        "- If no tool is needed, return content as a concise assistant reply and tool_calls as an empty array.",
        "- Tool names must exactly match one of the provided tool names.",
        "- Put tool arguments in arguments_json as a JSON object encoded as a string.",
        "- The decoded arguments_json object should match the tool schema as closely as possible.",
        "",
    ]
    if tools:
        lines.append("Available tools:")
        lines.append(json.dumps(tools, ensure_ascii=False, indent=2))
        lines.append("")
    else:
        lines.append("No tools are available for this turn.")
        lines.append("")

    lines.append("Conversation:")
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "unknown")
        lines.append(f"[{role}]")
        text = content_to_text(msg.get("content"))
        if text:
            lines.append(text)
        if msg.get("tool_calls"):
            lines.append("assistant_tool_calls=" + json.dumps(msg["tool_calls"], ensure_ascii=False))
        if msg.get("tool_call_id"):
            lines.append(f"tool_call_id={msg.get('tool_call_id')}")
        lines.append("")

    return "\n".join(lines)


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if "\n" in stripped:
            stripped = stripped.split("\n", 1)[1]
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            return json.loads(stripped[start : end + 1])
        raise


def encode_codex_stdin(prompt: str) -> bytes:
    """Encode prompts explicitly as UTF-8 for the Codex CLI stdin pipe.

    ``subprocess`` text mode uses the Windows locale by default. On a Chinese
    Windows installation that can be CP936, which produces bytes Codex rejects
    as invalid UTF-8. Replacing only malformed surrogate code points keeps the
    pipe valid UTF-8 without changing normal Unicode text.
    """
    return prompt.encode("utf-8", errors="replace")


def normalize_codex_result(raw: str) -> dict[str, Any]:
    data = extract_json_object(raw)
    content = data.get("content") or ""
    tool_calls = data.get("tool_calls") or []
    if not isinstance(content, str):
        content = str(content)
    if not isinstance(tool_calls, list):
        tool_calls = []
    normalized_calls: list[dict[str, Any]] = []
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        name = str(call.get("name", "")).strip()
        if not name:
            continue
        args = call.get("arguments")
        if args is None:
            args = call.get("arguments_json", "{}")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if not isinstance(args, dict):
            args = {}
        normalized_calls.append({"name": name, "arguments": args})
    return {"content": content, "tool_calls": normalized_calls}


def run_codex(body: dict[str, Any], keepalive=None, timeout: int = 240) -> dict[str, Any]:
    fast = try_fast_local_plan(body)
    if fast is not None:
        return fast

    codex_exe = resolve_codex_exe()
    workdir = os.environ.get("CODEX_BRIDGE_WORKDIR", DEFAULT_WORKDIR)
    if not Path(workdir).is_dir():
        workdir = DEFAULT_WORKDIR
    bridge_dir = _bridge_dir()
    schema_path = bridge_dir / "freecad-bridge-output.schema.json"
    schema_path.write_text(json.dumps(OUTPUT_SCHEMA, ensure_ascii=False, indent=2), encoding="utf-8")

    call_id = uuid.uuid4().hex
    result_path = bridge_dir / f"codex-result-{call_id}.json"
    log_path = bridge_dir / f"codex-run-{call_id}.log"
    prompt = build_codex_prompt(body)

    cmd = [
        str(codex_exe),
        "exec",
        "--ephemeral",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--color",
        "never",
        "-C",
        workdir,
        "--output-schema",
        str(schema_path),
        "-o",
        str(result_path),
        "-",
    ]
    cmd[2:2] = ["--model", resolve_codex_model()]

    env = os.environ.copy()
    env.setdefault("NO_COLOR", "1")
    env.setdefault("TERM", "xterm-256color")

    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        proc = subprocess.Popen(
            cmd,
            cwd=workdir,
            stdin=subprocess.PIPE,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
        )
        assert proc.stdin is not None
        proc.stdin.write(encode_codex_stdin(prompt))
        proc.stdin.close()

        deadline = time.time() + timeout
        while proc.poll() is None:
            if keepalive:
                keepalive()
            if time.time() > deadline:
                proc.kill()
                raise TimeoutError(f"Codex CLI timed out after {timeout}s. Log: {log_path}")
            time.sleep(5)

        if proc.returncode != 0:
            tail = ""
            try:
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
            except OSError:
                pass
            raise RuntimeError(f"Codex CLI exited with {proc.returncode}. Log: {log_path}\n{tail}")

    if not result_path.exists():
        raise RuntimeError(f"Codex CLI did not create result file. Log: {log_path}")
    raw = result_path.read_text(encoding="utf-8", errors="replace")
    return normalize_codex_result(raw)


def chat_completion_payload(result: dict[str, Any], model: str) -> dict[str, Any]:
    tool_calls = []
    for index, call in enumerate(result["tool_calls"]):
        tool_calls.append(
            {
                "id": f"call_{uuid.uuid4().hex[:16]}",
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                },
            }
        )
    message: dict[str, Any] = {
        "role": "assistant",
        "content": result["content"] if not tool_calls else (result["content"] or None),
    }
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "id": f"chatcmpl_codex_{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls" if tool_calls else "stop",
            }
        ],
    }


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "CodexFreeCADBridge/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _send_json(self, code: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_sse(self, payload: dict[str, Any]) -> None:
        self.wfile.write(("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode("utf-8"))
        self.wfile.flush()

    def _send_keepalive(self) -> None:
        try:
            self.wfile.write(b": codex working\n\n")
            self.wfile.flush()
        except OSError:
            pass

    def do_GET(self) -> None:
        if self.path.rstrip("/") in {"/health", "/v1/health"}:
            self._send_json(200, {"ok": True, "service": "codex-freecad-bridge"})
        elif self.path.rstrip("/") in {"/v1/models", "/models"}:
            self._send_json(
                200,
                {"object": "list", "data": [{"id": "codex-cli", "object": "model", "owned_by": "local"}]},
            )
        else:
            self._send_json(404, {"error": f"Unknown path: {self.path}"})

    def do_POST(self) -> None:
        if self.path.rstrip("/") not in {"/v1/chat/completions", "/chat/completions"}:
            self._send_json(404, {"error": f"Unknown path: {self.path}"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            model = body.get("model") or "codex-cli"
            stream = bool(body.get("stream"))
            if stream:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                self._streaming_started = True
                self._send_keepalive()
                result = run_codex(body, keepalive=self._send_keepalive)
                self._stream_result(result, model)
            else:
                result = run_codex(body)
                self._send_json(200, chat_completion_payload(result, model))
        except Exception as exc:
            self.log_message("error: %s", exc)
            if not getattr(self, "_streaming_started", False):
                self._send_json(500, {"error": str(exc)})
            else:
                try:
                    self._send_sse(
                        {
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": f"\n[Codex bridge error] {exc}"},
                                    "finish_reason": "stop",
                                }
                            ]
                        }
                    )
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                except OSError:
                    pass

    def _stream_result(self, result: dict[str, Any], model: str) -> None:
        if result["tool_calls"]:
            for index, call in enumerate(result["tool_calls"]):
                self._send_sse(
                    {
                        "id": f"chatcmpl_codex_{uuid.uuid4().hex}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": index,
                                            "id": f"call_{uuid.uuid4().hex[:16]}",
                                            "type": "function",
                                            "function": {
                                                "name": call["name"],
                                                "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                                            },
                                        }
                                    ]
                                },
                                "finish_reason": None,
                            }
                        ],
                    }
                )
            self._send_sse({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]})
        else:
            content = result["content"] or ""
            if content:
                self._send_sse(
                    {
                        "id": f"chatcmpl_codex_{uuid.uuid4().hex}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
                    }
                )
            self._send_sse({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        self.close_connection = True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    codex = resolve_codex_exe()
    print(f"Codex FreeCAD bridge listening on http://{args.host}:{args.port}/v1")
    print(f"Using Codex CLI: {codex}")
    server = ThreadingHTTPServer((args.host, args.port), BridgeHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
