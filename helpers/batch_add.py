#!/usr/bin/env python3
"""Add multiple elements to an excalidraw canvas in one read/write cycle with auto-spacing."""

import json
import argparse
import random
import sys
import os
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from canvas_utils import get_element_bounds, get_canvas_bounds


ELEMENT_DEFAULTS = {
    "fillStyle": "solid",
    "strokeWidth": 2,
    "strokeStyle": "solid",
    "roughness": 1,
    "opacity": 100,
    "angle": 0,
    "groupIds": [],
    "boundElements": [],
    "link": None,
    "locked": False,
    "isDeleted": False,
    "frameId": None,
    "roundness": None,
    "hasTextLink": False,
}


TYPE_DEFAULTS = {
    "rectangle": (120, 60),
    "ellipse": (140, 140),
    "diamond": (120, 80),
}


def gen_seed() -> int:
    return random.randint(100000, 9999999)


def gen_nonce() -> int:
    return random.randint(100000000, 2147483647)


def compute_positions(specs: list[dict], elements: list[dict],
                      below_id: str = None, row_at: float = None,
                      gap: float = 30, default_width: float = None,
                      default_height: float = None) -> list[dict]:
    """Compute x/y for each spec that doesn't have explicit coordinates."""
    for spec in specs:
        etype = spec.get("type", "rectangle")
        dw, dh = TYPE_DEFAULTS.get(etype, (120, 60))
        if default_width:
            dw = default_width
        if default_height:
            dh = default_height
        spec.setdefault("width", dw)
        spec.setdefault("height", dh)

    needs_auto = [s for s in specs if "x" not in s or "y" not in s]
    if not needs_auto:
        return specs

    if below_id:
        target = next((e for e in elements if e["id"] == below_id), None)
        if not target:
            print(f"ERROR: --below element '{below_id}' not found", file=sys.stderr)
            sys.exit(1)
        b = get_element_bounds(target)
        start_y = b["y2"] + gap
        total_width = sum(s["width"] for s in needs_auto) + gap * (len(needs_auto) - 1)
        start_x = b["x"] + (target.get("width", 0) / 2) - (total_width / 2)
        cx = start_x
        for s in needs_auto:
            if "x" not in s:
                s["x"] = cx
            if "y" not in s:
                s["y"] = start_y
            cx += s["width"] + gap

    elif row_at is not None:
        total_width = sum(s["width"] for s in needs_auto) + gap * (len(needs_auto) - 1)
        canvas = get_canvas_bounds(elements)
        canvas_width = (canvas["x2"] - canvas["x"]) if canvas else 800
        canvas_start_x = canvas["x"] if canvas else 0
        start_x = canvas_start_x + (canvas_width - total_width) / 2
        cx = start_x
        for s in needs_auto:
            if "x" not in s:
                s["x"] = cx
            if "y" not in s:
                s["y"] = row_at
            cx += s["width"] + gap

    else:
        # Default: horizontal row starting at (100, 100)
        cx = 100.0
        for s in needs_auto:
            if "x" not in s:
                s["x"] = cx
            if "y" not in s:
                s["y"] = 100.0
            cx += s["width"] + gap

    return specs


def batch_add(filepath: str, specs: list[dict], below_id: str = None,
              row_at: float = None, gap: float = 30,
              default_width: float = None, default_height: float = None) -> str:
    path = Path(filepath)
    data = json.loads(path.read_text())
    elements = data.get("elements", [])

    existing_ids = {e["id"] for e in elements}

    # Validate IDs
    for spec in specs:
        if not spec.get("id"):
            return "ERROR: every element must have an 'id' field"
        if spec["id"] in existing_ids:
            return f"ERROR: element ID '{spec['id']}' already exists"

    # Apply defaults
    for spec in specs:
        spec.setdefault("type", "rectangle")
        spec.setdefault("bg", "transparent")
        spec.setdefault("stroke", "#000000")
        spec.setdefault("text_size", 14)

    # Compute positions
    specs = compute_positions(specs, elements, below_id, row_at, gap,
                              default_width, default_height)

    # Determine starting index
    indices = [e.get("index", "") for e in elements if e.get("index")]
    if indices:
        last = sorted(indices)[-1]
        base_idx = last + "0"
    else:
        base_idx = "a0"

    added_ids = []
    now = int(time.time() * 1000)

    for i, spec in enumerate(specs):
        etype = spec["type"]
        eid = spec["id"]
        x = spec.get("x", 0)
        y = spec.get("y", 0)
        w = spec["width"]
        h = spec["height"]
        idx = base_idx + str(i).zfill(2)

        if etype == "text":
            text = spec.get("text", "")
            text_size = spec.get("text_size", 16)
            estimated_width = len(text) * text_size * 0.55
            text_height = text_size * 1.25
            text_elem = {
                **ELEMENT_DEFAULTS,
                "type": "text",
                "id": eid,
                "x": x,
                "y": y,
                "width": estimated_width,
                "height": text_height,
                "text": text,
                "originalText": text,
                "rawText": text,
                "fontSize": text_size,
                "fontFamily": 1,
                "textAlign": "left",
                "verticalAlign": "top",
                "strokeColor": spec.get("stroke", "#0a0a0a"),
                "backgroundColor": "transparent",
                "strokeWidth": 1,
                "roughness": 0,
                "seed": gen_seed(),
                "version": 1,
                "versionNonce": gen_nonce(),
                "index": idx,
                "updated": now,
                "containerId": None,
                "lineHeight": 1.25,
                "autoResize": True,
            }
            elements.append(text_elem)
        else:
            shape = {
                **ELEMENT_DEFAULTS,
                "type": etype,
                "id": eid,
                "x": x,
                "y": y,
                "width": w,
                "height": h,
                "strokeColor": spec["stroke"],
                "backgroundColor": spec["bg"],
                "seed": gen_seed(),
                "version": 1,
                "versionNonce": gen_nonce(),
                "index": idx,
                "updated": now,
            }

            if etype in ("rectangle", "diamond"):
                shape["roundness"] = {"type": 3}

            elements.append(shape)

            text = spec.get("text")
            if text:
                text_size = spec.get("text_size", 14)
                estimated_width = len(text) * text_size * 0.55
                text_id = f"{eid}_text"
                text_elem = {
                    **ELEMENT_DEFAULTS,
                    "type": "text",
                    "id": text_id,
                    "x": x + (w - estimated_width) / 2,
                    "y": y + (h - text_size * 1.25) / 2,
                    "width": estimated_width,
                    "height": text_size * 1.25,
                    "text": text,
                    "originalText": text,
                    "rawText": text,
                    "fontSize": text_size,
                    "fontFamily": 1,
                    "textAlign": "center",
                    "verticalAlign": "middle",
                    "strokeColor": "#0a0a0a",
                    "backgroundColor": "transparent",
                    "strokeWidth": 1,
                    "roughness": 0,
                    "seed": gen_seed(),
                    "version": 1,
                    "versionNonce": gen_nonce(),
                    "index": idx + "t",
                    "updated": now,
                    "containerId": eid,
                    "lineHeight": 1.25,
                    "autoResize": True,
                }
                elements.append(text_elem)
                shape["boundElements"] = [{"id": text_id, "type": "text"}]

        added_ids.append(eid)

    data["elements"] = elements
    if "files" not in data:
        data["files"] = {}
    if "appState" not in data:
        data["appState"] = {}
    data["appState"].setdefault("gridSize", None)
    data["appState"].setdefault("viewBackgroundColor", "#ffffff")
    data["source"] = "https://github.com/zsviczian/obsidian-excalidraw-plugin/releases/tag/2.22.3"
    path.write_text(json.dumps(data, indent="\t"))

    # Post-placement collision check
    abs_filepath = str(path.resolve())
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    from check_collision import check_collisions

    warnings = []
    for eid in added_ids:
        result = check_collisions(abs_filepath, eid)
        if "OK" not in result:
            warnings.append(f"  {eid}: {result}")

    msg = f"OK: added {len(added_ids)}/{len(specs)} elements"
    if warnings:
        msg += "\n" + "\n".join(warnings)
    return msg


def main():
    parser = argparse.ArgumentParser(description="Batch add elements to excalidraw canvas")
    parser.add_argument("file", help="Path to .excalidraw file")
    parser.add_argument("json_spec", help="JSON array of element specs")
    parser.add_argument("--below", help="Place elements in a row below this element ID")
    parser.add_argument("--row-at", type=float, help="Place all at this y coordinate, evenly spaced")
    parser.add_argument("--gap", type=float, default=30, help="Gap between elements (default: 30)")
    parser.add_argument("--width", type=float, help="Default width for all elements")
    parser.add_argument("--height", type=float, help="Default height for all elements")

    args = parser.parse_args()

    try:
        specs = json.loads(args.json_spec)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(specs, list):
        print("ERROR: JSON must be an array of element specs", file=sys.stderr)
        sys.exit(1)

    result = batch_add(
        args.file, specs,
        below_id=args.below,
        row_at=args.row_at,
        gap=args.gap,
        default_width=args.width,
        default_height=args.height,
    )
    print(result)


if __name__ == "__main__":
    main()
