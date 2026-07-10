#!/usr/bin/env python3
"""Command-line client for the local FreeCAD RPC server."""

from __future__ import annotations

import argparse
import json
import urllib.request


BASE_URL = "http://127.0.0.1:8765"


def request(method: str, path: str, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("health")
    sub.add_parser("document")

    box = sub.add_parser("box")
    box.add_argument("--length", type=float, required=True)
    box.add_argument("--width", type=float)
    box.add_argument("--height", type=float)
    box.add_argument("--name", default="Codex_Box")

    code = sub.add_parser("python")
    code.add_argument("code")

    args = parser.parse_args()
    if args.cmd == "health":
        result = request("GET", "/health")
    elif args.cmd == "document":
        result = request("GET", "/document")
    elif args.cmd == "box":
        length = args.length
        result = request(
            "POST",
            "/execute",
            {
                "action": "create_box",
                "args": {
                    "length": length,
                    "width": args.width if args.width is not None else length,
                    "height": args.height if args.height is not None else length,
                    "name": args.name,
                },
            },
        )
    else:
        result = request("POST", "/execute", {"action": "run_python", "args": {"code": args.code}})
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

