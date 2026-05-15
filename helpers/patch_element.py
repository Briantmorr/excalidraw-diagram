#!/usr/bin/env python3
"""Patch a single element in an excalidraw file by ID. Supports: x, y, width, height, text, backgroundColor, strokeColor, fontSize."""

import json
import sys
import argparse
from pathlib import Path


def patch(filepath: str, element_id: str, patches: dict) -> str:
    path = Path(filepath)
    data = json.loads(path.read_text())
    elements = data.get("elements", [])

    target = None
    for e in elements:
        if e["id"] == element_id:
            target = e
            break

    if target is None:
        return f"ERROR: element '{element_id}' not found"

    old_width = target.get("width")
    old_height = target.get("height")
    old_x = target.get("x")
    old_y = target.get("y")

    for key, val in patches.items():
        if key == "text":
            val = val.replace("\\n", "\n")
            target["text"] = val
            target["originalText"] = val
            if "rawText" in target:
                target["rawText"] = val
            # Recalculate height/width for multi-line text
            if target["type"] == "text":
                font_size = target.get("fontSize", 14)
                line_height = target.get("lineHeight", 1.25)
                num_lines = val.count("\n") + 1
                target["height"] = num_lines * font_size * line_height
                longest_line = max(val.split("\n"), key=len)
                target["width"] = len(longest_line) * font_size * 0.55
        elif key in ("x", "y", "width", "height", "fontSize"):
            target[key] = float(val)
        elif key in ("backgroundColor", "strokeColor", "strokeWidth"):
            target[key] = val

    target["version"] = target.get("version", 1) + 1

    # Auto-recenter contained text when shape resizes or moves
    new_width = target.get("width", old_width)
    new_height = target.get("height", old_height)
    new_x = target.get("x", old_x)
    new_y = target.get("y", old_y)

    if target["type"] != "text":
        shape_moved = (new_x != old_x or new_y != old_y)
        shape_resized = (new_width != old_width or new_height != old_height)

        if shape_moved or shape_resized:
            # Find text elements that are visually inside this shape
            for e in elements:
                if e["type"] == "text" and e.get("containerId") == element_id:
                    # Contained text — auto-adjust
                    if shape_resized:
                        text_w = e.get("width", 0)
                        text_h = e.get("height", 0)
                        e["x"] = new_x + (new_width - text_w) / 2
                        e["y"] = new_y + (new_height - text_h) / 2
                    elif shape_moved:
                        dx = new_x - old_x
                        dy = new_y - old_y
                        e["x"] += dx
                        e["y"] += dy
                    e["version"] = e.get("version", 1) + 1

            # Also handle free-floating text that was visually centered in the old shape
            if shape_resized or shape_moved:
                for e in elements:
                    if e["type"] == "text" and e.get("containerId") is None:
                        # Check if text was roughly centered in old shape bounds
                        ex, ey = e["x"], e["y"]
                        ew = e.get("width", 0)
                        eh = e.get("height", 0)
                        text_cx = ex + ew / 2
                        text_cy = ey + eh / 2
                        old_cx = old_x + old_width / 2
                        old_cy = old_y + old_height / 2

                        # If text center is within 30px of shape center, re-center it
                        if abs(text_cx - old_cx) < 30 and abs(text_cy - old_cy) < 30:
                            e["x"] = new_x + (new_width - ew) / 2
                            e["y"] = new_y + (new_height - eh) / 2
                            e["version"] = e.get("version", 1) + 1

    data["elements"] = elements
    path.write_text(json.dumps(data, indent=2))

    msg = f"OK: patched {element_id} with {patches}"

    # Post-patch collision check for moves/resizes
    if any(k in patches for k in ("x", "y", "width", "height")):
        import os
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        from check_collision import check_collisions
        collision_result = check_collisions(filepath, element_id)
        if "OK" not in collision_result:
            msg += f"\n⚠ {collision_result}"

    return msg


def main():
    parser = argparse.ArgumentParser(description="Patch excalidraw element by ID")
    parser.add_argument("file", help="Path to .excalidraw file")
    parser.add_argument("--id", required=True, help="Element ID to patch")
    parser.add_argument("--x", type=float)
    parser.add_argument("--y", type=float)
    parser.add_argument("--width", type=float)
    parser.add_argument("--height", type=float)
    parser.add_argument("--text")
    parser.add_argument("--bg", dest="backgroundColor")
    parser.add_argument("--stroke", dest="strokeColor")
    parser.add_argument("--stroke-width", dest="strokeWidth", type=int)
    parser.add_argument("--font-size", dest="fontSize", type=int)

    args = parser.parse_args()
    patches = {}
    for key in ("x", "y", "width", "height", "text", "backgroundColor", "strokeColor", "strokeWidth", "fontSize"):
        val = getattr(args, key, None)
        if val is not None:
            patches[key] = val

    if not patches:
        print("ERROR: no patches specified")
        sys.exit(1)

    result = patch(args.file, args.id, patches)
    print(result)


if __name__ == "__main__":
    main()
