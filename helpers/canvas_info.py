#!/usr/bin/env python3
"""Summarize an excalidraw canvas: element IDs, types, positions, sizes, text previews."""

import json
import os
import sys
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.excalidraw_core import get_frame_ids


def _element_center(e: dict) -> tuple[float, float]:
    return e["x"] + e.get("width", 0) / 2, e["y"] + e.get("height", 0) / 2


def _point_in_bounds(px: float, py: float, shape: dict) -> bool:
    sx, sy = shape["x"], shape["y"]
    sw, sh = shape.get("width", 0), shape.get("height", 0)
    return sx <= px <= sx + sw and sy <= py <= sy + sh


def summarize(filepath: str) -> str:
    data = json.loads(Path(filepath).read_text())
    elements = [e for e in data.get("elements", []) if not e.get("isDeleted")]

    if not elements:
        return "empty canvas"

    xs = [e["x"] for e in elements]
    ys = [e["y"] for e in elements]
    x2s = [e["x"] + e.get("width", 0) for e in elements]
    y2s = [e["y"] + e.get("height", 0) for e in elements]

    bounds = f"bounds: ({min(xs):.0f}, {min(ys):.0f}) to ({max(x2s):.0f}, {max(y2s):.0f})"
    canvas_size = f"canvas: {max(x2s)-min(xs):.0f}x{max(y2s)-min(ys):.0f}"

    lines = [f"{bounds}  {canvas_size}", f"elements: {len(elements)}", "---"]

    for e in elements:
        eid = e["id"]
        etype = e["type"]
        x, y = e["x"], e["y"]
        w = e.get("width", 0)
        h = e.get("height", 0)

        parts = [f"{eid:<25} {etype:<8} ({x:.0f}, {y:.0f})  {w:.0f}x{h:.0f}"]

        bg = e.get("backgroundColor", "transparent")
        if bg and bg != "transparent":
            parts.append(f"bg={bg}")

        if etype == "text":
            text = e.get("text", "")
            preview = text.replace("\n", "\\n")[:40]
            parts.append(f'"{preview}"')

        lines.append("  ".join(parts))

    return "\n".join(lines)


def summarize_compact(filepath: str) -> str:
    data = json.loads(Path(filepath).read_text())
    elements = [e for e in data.get("elements", []) if not e.get("isDeleted")]

    if not elements:
        return "empty canvas"

    xs = [e["x"] for e in elements]
    ys = [e["y"] for e in elements]
    x2s = [e["x"] + e.get("width", 0) for e in elements]
    y2s = [e["y"] + e.get("height", 0) for e in elements]

    bounds = f"bounds: ({min(xs):.0f}, {min(ys):.0f}) to ({max(x2s):.0f}, {max(y2s):.0f})"
    canvas_size = f"canvas: {max(x2s)-min(xs):.0f}x{max(y2s)-min(ys):.0f}"

    lines = [f"{bounds}  {canvas_size}", f"elements: {len(elements)}", "---"]

    shapes = [e for e in elements if e["type"] not in ("text",)]
    texts = [e for e in elements if e["type"] == "text"]

    # Map text -> shape it belongs to
    text_to_shape: dict[str, str] = {}  # text element id -> shape element id

    for t in texts:
        # Check containerId first
        container_id = t.get("containerId")
        if container_id:
            text_to_shape[t["id"]] = container_id
            continue
        # Check if text center is within a shape's bounds
        tcx, tcy = _element_center(t)
        for s in shapes:
            if _point_in_bounds(tcx, tcy, s):
                text_to_shape[t["id"]] = s["id"]
                break

    # Build shape -> list of associated text elements
    shape_texts: dict[str, list[dict]] = {}
    for t in texts:
        sid = text_to_shape.get(t["id"])
        if sid:
            shape_texts.setdefault(sid, []).append(t)

    grouped_text_ids = set(text_to_shape.keys())

    frame_ids = get_frame_ids(elements)

    for e in shapes:
        eid = e["id"]
        etype = e["type"]
        x, y = e["x"], e["y"]
        w = e.get("width", 0)
        h = e.get("height", 0)

        # Detect frames (canonical: canvas_utils / core.detect_frames)
        is_frame = eid in frame_ids

        if etype == "arrow" or etype == "line":
            # Arrow format: id  arrow (x1,y1) -> (x2,y2)
            points = e.get("points", [])
            if points and len(points) >= 2:
                x1, y1 = x + points[0][0], y + points[0][1]
                x2, y2 = x + points[-1][0], y + points[-1][1]
                line = f"{eid}  {etype} ({x1:.0f},{y1:.0f}) → ({x2:.0f},{y2:.0f})"
            else:
                line = f"{eid}  {etype} ({x:.0f},{y:.0f}) {w:.0f}x{h:.0f}"
            lines.append(line)
            continue

        prefix = "[frame] " if is_frame else ""
        bg = e.get("backgroundColor", "transparent")
        bg_str = f" bg={bg}" if bg and bg != "transparent" else ""

        # Gather associated text
        assoc_texts = shape_texts.get(eid, [])
        if assoc_texts:
            text_preview = " | ".join(
                '"' + t.get("text", "").replace("\n", "\\n")[:40] + '"'
                for t in assoc_texts
            )
            line = f"{prefix}{eid}  {etype} ({x:.0f},{y:.0f}) {w:.0f}x{h:.0f}{bg_str}  {text_preview}"
        else:
            line = f"{prefix}{eid}  {etype} ({x:.0f},{y:.0f}) {w:.0f}x{h:.0f}{bg_str}"

        lines.append(line)

    # Ungrouped text elements
    for t in texts:
        if t["id"] in grouped_text_ids:
            continue
        tid = t["id"]
        x, y = t["x"], t["y"]
        text = t.get("text", "").replace("\n", "\\n")[:40]
        lines.append(f'[text] {tid}  ({x:.0f},{y:.0f}) "{text}"')

    return "\n".join(lines)


def summarize_json(filepath: str) -> str:
    data = json.loads(Path(filepath).read_text())
    elements = [e for e in data.get("elements", []) if not e.get("isDeleted")]

    result = []
    for e in elements:
        entry: dict = {
            "id": e["id"],
            "type": e["type"],
            "x": e["x"],
            "y": e["y"],
            "width": e.get("width", 0),
            "height": e.get("height", 0),
        }
        bg = e.get("backgroundColor", "transparent")
        if bg and bg != "transparent":
            entry["backgroundColor"] = bg
        stroke = e.get("strokeColor")
        if stroke:
            entry["strokeColor"] = stroke
        if e["type"] == "text":
            entry["text"] = e.get("text", "")
            entry["fontSize"] = e.get("fontSize", 14)
            entry["containerId"] = e.get("containerId")
        if e["type"] in ("arrow", "line"):
            entry["points"] = e.get("points", [])
        result.append(entry)

    return json.dumps(result, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Summarize excalidraw canvas")
    parser.add_argument("file", help="Path to .excalidraw file")
    parser.add_argument("--compact", action="store_true",
                        help="Group text labels with their parent shapes")
    parser.add_argument("--json", action="store_true",
                        help="Output machine-readable JSON array")
    args = parser.parse_args()

    if args.json:
        print(summarize_json(args.file))
    elif args.compact:
        print(summarize_compact(args.file))
    else:
        print(summarize(args.file))
