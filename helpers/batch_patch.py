#!/usr/bin/env python3
"""Apply multiple patches to an Excalidraw file in a single read/write cycle."""

import json
import sys
from pathlib import Path


PROP_ALIASES = {
    "bg": "backgroundColor",
    "stroke": "strokeColor",
}

FLOAT_KEYS = {"x", "y", "width", "height", "fontSize"}
INT_KEYS = {"strokeWidth"}


def normalize_patch(raw: dict) -> dict:
    """Expand shorthand aliases and coerce numeric types."""
    out = {}
    for k, v in raw.items():
        if k == "id":
            continue
        canonical = PROP_ALIASES.get(k, k)
        if canonical in FLOAT_KEYS:
            out[canonical] = float(v)
        elif canonical in INT_KEYS:
            out[canonical] = int(v)
        else:
            out[canonical] = v
    return out


def apply_recenter(elements: list, target: dict, old_x: float, old_y: float, old_width: float, old_height: float) -> None:
    element_id = target["id"]
    new_x = target.get("x", old_x)
    new_y = target.get("y", old_y)
    new_width = target.get("width", old_width)
    new_height = target.get("height", old_height)

    shape_moved = new_x != old_x or new_y != old_y
    shape_resized = new_width != old_width or new_height != old_height

    if not (shape_moved or shape_resized):
        return

    for e in elements:
        if e["type"] != "text":
            continue

        if e.get("containerId") == element_id:
            if shape_resized:
                text_w = e.get("width", 0)
                text_h = e.get("height", 0)
                e["x"] = new_x + (new_width - text_w) / 2
                e["y"] = new_y + (new_height - text_h) / 2
            elif shape_moved:
                e["x"] += new_x - old_x
                e["y"] += new_y - old_y
            e["version"] = e.get("version", 1) + 1

        elif e.get("containerId") is None:
            ex, ey = e["x"], e["y"]
            ew = e.get("width", 0)
            eh = e.get("height", 0)
            text_cx = ex + ew / 2
            text_cy = ey + eh / 2
            old_cx = old_x + old_width / 2
            old_cy = old_y + old_height / 2

            if abs(text_cx - old_cx) < 30 and abs(text_cy - old_cy) < 30:
                e["x"] = new_x + (new_width - ew) / 2
                e["y"] = new_y + (new_height - eh) / 2
                e["version"] = e.get("version", 1) + 1


def batch_patch(filepath: str, patch_list: list[dict]) -> str:
    path = Path(filepath)
    data = json.loads(path.read_text())
    elements = data.get("elements", [])

    index: dict[str, dict] = {e["id"]: e for e in elements}

    patched = []
    missing = []

    for raw in patch_list:
        element_id = raw.get("id")
        if not element_id:
            missing.append("<no-id>")
            continue

        target = index.get(element_id)
        if target is None:
            missing.append(element_id)
            continue

        props = normalize_patch(raw)

        old_x = target.get("x", 0.0)
        old_y = target.get("y", 0.0)
        old_width = target.get("width", 0.0)
        old_height = target.get("height", 0.0)

        for key, val in props.items():
            if key == "text":
                if isinstance(val, str):
                    val = val.replace("\\n", "\n")
                target["text"] = val
                target["originalText"] = val
                if "rawText" in target:
                    target["rawText"] = val
            else:
                target[key] = val

        target["version"] = target.get("version", 1) + 1

        if target["type"] != "text":
            apply_recenter(elements, target, old_x, old_y, old_width, old_height)

        patched.append(element_id)

    data["elements"] = elements
    path.write_text(json.dumps(data, indent=2))

    total = len(patch_list)
    n_ok = len(patched)

    if missing:
        return f"PARTIAL: patched {n_ok}/{total} (missing: {', '.join(missing)})"
    return f"OK: patched {n_ok}/{total} elements"


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: batch_patch.py <file.excalidraw> '<json>' | --stdin")
        sys.exit(1)

    filepath = sys.argv[1]

    if len(sys.argv) >= 3 and sys.argv[2] == "--stdin":
        raw_json = sys.stdin.read()
    elif len(sys.argv) >= 3:
        raw_json = sys.argv[2]
    else:
        raw_json = sys.stdin.read()

    try:
        patch_list = json.loads(raw_json)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON — {e}")
        sys.exit(1)

    if not isinstance(patch_list, list):
        print("ERROR: patches must be a JSON array")
        sys.exit(1)

    result = batch_patch(filepath, patch_list)
    print(result)
    if result.startswith("PARTIAL") or result.startswith("ERROR"):
        sys.exit(1)


if __name__ == "__main__":
    main()
