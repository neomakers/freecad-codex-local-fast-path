"""Deterministic local plans for common FreeCAD AI primitive requests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LocalToolPlan:
    """A tool call that can be safely planned without a model request."""

    name: str
    arguments: dict[str, Any]
    summary: str


_NUMBER = re.compile(
    r"(?<![A-Za-z])(-?\d+(?:\.\d+)?)\s*"
    r"(mm|cm|m|\u6beb\u7c73|\u5398\u7c73|\u7c73)?"
    r"(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
_QUESTION_WORDS = (
    "?", "\uff1f", "how", "what", "why", "explain", "example",
    "\u5982\u4f55", "\u600e\u4e48", "\u4ec0\u4e48", "\u4e3a\u4ec0\u4e48", "\u793a\u4f8b",
)


def _to_mm(value: str, unit: str) -> float:
    multiplier = {
        "": 1.0, "mm": 1.0, "cm": 10.0, "m": 1000.0,
        "\u6beb\u7c73": 1.0, "\u5398\u7c73": 10.0, "\u7c73": 1000.0,
    }
    return float(value) * multiplier[unit.lower()]


def _numbers(text: str) -> list[float]:
    return [_to_mm(value, unit or "") for value, unit in _NUMBER.findall(text)]


def _named_dimension(text: str, names: tuple[str, ...]) -> float | None:
    alternatives = "|".join(
        rf"\b{re.escape(name)}\b" if name.isascii() else re.escape(name)
        for name in names
    )
    match = re.search(
        rf"(?:{alternatives})\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*"
        rf"(mm|cm|m|\u6beb\u7c73|\u5398\u7c73|\u7c73)?"
        rf"(?![A-Za-z0-9_])",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    return _to_mm(match.group(1), match.group(2) or "")


def _is_direct_request(text: str) -> bool:
    lowered = text.casefold()
    return not any(word in lowered for word in _QUESTION_WORDS)


def _box(text: str) -> LocalToolPlan:
    values = _numbers(text)
    length = _named_dimension(text, ("length", "long", "\u957f"))
    width = _named_dimension(text, ("width", "wide", "\u5bbd"))
    height = _named_dimension(text, ("height", "high", "\u9ad8"))
    length = length if length is not None else (values[0] if values else 10.0)
    width = width if width is not None else (values[1] if len(values) > 1 else length)
    height = height if height is not None else (values[2] if len(values) > 2 else length)
    return LocalToolPlan(
        "create_primitive",
        {"shape_type": "box", "label": "Quick_Box", "length": length,
         "width": width, "height": height},
        "Local fast path: creating a parametric box.",
    )


def _cylinder(text: str) -> LocalToolPlan:
    values = _numbers(text)
    diameter = _named_dimension(text, ("diameter", "dia", "\u76f4\u5f84"))
    radius = _named_dimension(text, ("radius", "r", "\u534a\u5f84"))
    height = _named_dimension(text, ("height", "high", "h", "\u9ad8"))
    radius = radius if radius is not None else (diameter / 2 if diameter is not None else (values[0] if values else 5.0))
    height = height if height is not None else (values[1] if len(values) > 1 else 10.0)
    return LocalToolPlan(
        "create_primitive",
        {"shape_type": "cylinder", "label": "Quick_Cylinder", "radius": radius,
         "height": height},
        "Local fast path: creating a parametric cylinder.",
    )


def _sphere(text: str) -> LocalToolPlan:
    values = _numbers(text)
    diameter = _named_dimension(text, ("diameter", "dia", "\u76f4\u5f84"))
    radius = _named_dimension(text, ("radius", "r", "\u534a\u5f84"))
    radius = radius if radius is not None else (diameter / 2 if diameter is not None else (values[0] if values else 5.0))
    return LocalToolPlan(
        "create_primitive",
        {"shape_type": "sphere", "label": "Quick_Sphere", "radius": radius},
        "Local fast path: creating a parametric sphere.",
    )


def _cone(text: str) -> LocalToolPlan:
    values = _numbers(text)
    radius1 = _named_dimension(text, ("radius1", "r1", "\u5e95\u534a\u5f84"))
    radius2 = _named_dimension(text, ("radius2", "r2", "\u9876\u534a\u5f84"))
    height = _named_dimension(text, ("height", "high", "h", "\u9ad8"))
    radius1 = radius1 if radius1 is not None else (values[0] if values else 5.0)
    radius2 = radius2 if radius2 is not None else (values[1] if len(values) > 1 else 0.0)
    height = height if height is not None else (values[2] if len(values) > 2 else 10.0)
    return LocalToolPlan(
        "create_primitive",
        {"shape_type": "cone", "label": "Quick_Cone", "radius": radius1,
         "radius2": radius2, "height": height},
        "Local fast path: creating a parametric cone.",
    )


def plan_local_arguments(text: str) -> LocalToolPlan | None:
    """Parse only direct, unambiguous primitive creation requests."""
    if not text or not _is_direct_request(text):
        return None
    lowered = text.casefold()
    if any(word in lowered for word in ("box", "cube", "\u76d2\u5b50", "\u65b9\u5757", "\u7acb\u65b9\u4f53", "\u957f\u65b9\u4f53")):
        return _box(text)
    if any(word in lowered for word in ("cylinder", "\u5706\u67f1", "\u5706\u7b52")):
        return _cylinder(text)
    if any(word in lowered for word in ("sphere", "ball", "\u7403\u4f53")):
        return _sphere(text)
    if any(word in lowered for word in ("cone", "\u5706\u9525")):
        return _cone(text)
    return None


def plan_local_tool(messages: list[dict], registry) -> LocalToolPlan | None:
    """Plan a local tool call when the registry exposes create_primitive."""
    if registry is None or registry.get("create_primitive") is None:
        return None
    for message in reversed(messages):
        if message.get("role") == "user" and isinstance(message.get("content"), str):
            return plan_local_arguments(message["content"].strip())
    return None
