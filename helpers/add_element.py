#!/usr/bin/env python3
"""Add a new element to an existing excalidraw canvas."""

import json
import argparse
import random
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from canvas_utils import get_element_bounds, detect_frames, get_canvas_bounds


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
    "fontFamily": 1,
}


def gen_seed():
    return random.randint(100000, 9999999)


def gen_nonce():
    return random.randint(100000000, 2147483647)


def bounds_overlap(ax, ay, ax2, ay2, bx, by, bx2, by2):
    return ax < bx2 and ax2 > bx and ay < by2 and ay2 > by


def is_occupied(elements, x, y, width, height, exclude_id=None, exclude_ids=None):
    """Check if a region is occupied by existing elements.
    Arrows get a minimum 30px hitbox so placement avoids crossing them visually."""
    if exclude_ids is None:
        exclude_ids = set()
    arrow_padding = 15
    for e in elements:
        if e.get("isDeleted"):
            continue
        if exclude_id and e["id"] == exclude_id:
            continue
        if e["id"] in exclude_ids:
            continue
        if e["type"] == "text":
            continue
        eb = get_element_bounds(e)
        ex, ey, ex2, ey2 = eb["x"], eb["y"], eb["x2"], eb["y2"]
        # Expand arrow hitbox so they act as thin visual obstacles
        if e["type"] == "arrow":
            if ey2 - ey < 30:
                ey -= arrow_padding
                ey2 += arrow_padding
            if ex2 - ex < 30:
                ex -= arrow_padding
                ex2 += arrow_padding
        if bounds_overlap(x, y, x + width, y + height, ex, ey, ex2, ey2):
            return True
    return False


def compute_candidate(bounds, direction, gap, new_width, new_height):
    if direction == "right":
        return bounds["x2"] + gap, bounds["y"]
    elif direction == "below":
        return bounds["x"], bounds["y2"] + gap
    elif direction == "left":
        return bounds["x"] - gap - new_width, bounds["y"]
    elif direction == "above":
        return bounds["x"], bounds["y"] - gap - new_height
    return bounds["x2"] + gap, bounds["y"]


CLOCKWISE = ["right", "below", "left", "above"]


def fits_in_frame(x, y, width, height, frame_bounds):
    """Check if element at (x,y) with given size fits within frame."""
    if frame_bounds is None:
        return True
    return (x >= frame_bounds["x"] and y >= frame_bounds["y"]
            and x + width <= frame_bounds["x2"] and y + height <= frame_bounds["y2"])


def find_placement(elements, near_id, direction="right", gap=40, new_width=160, new_height=160):
    target = None
    for e in elements:
        if e["id"] == near_id:
            target = e
            break
    if not target:
        return None, None

    b = get_element_bounds(target)

    # Use shared frame detection
    frames = detect_frames(elements)
    frame = frames[0] if frames else None

    # Exclude only frames from occupancy checks (arrows have padded hitbox instead)
    frame_ids = {f["id"] for f in frames}
    skip_ids = frame_ids

    # Try requested direction first, then rotate clockwise
    start_idx = CLOCKWISE.index(direction) if direction in CLOCKWISE else 0
    for i in range(4):
        d = CLOCKWISE[(start_idx + i) % 4]
        cx, cy = compute_candidate(b, d, gap, new_width, new_height)
        if (fits_in_frame(cx, cy, new_width, new_height, frame)
                and not is_occupied(elements, cx, cy, new_width, new_height,
                                    exclude_id=near_id, exclude_ids=skip_ids)):
            return cx, cy

    # All directions either occupied or out of frame — try clamping to frame
    if frame:
        for i in range(4):
            d = CLOCKWISE[(start_idx + i) % 4]
            cx, cy = compute_candidate(b, d, gap, new_width, new_height)
            cx = max(frame["x"], min(cx, frame["x2"] - new_width))
            cy = max(frame["y"], min(cy, frame["y2"] - new_height))
            if not is_occupied(elements, cx, cy, new_width, new_height,
                               exclude_id=near_id, exclude_ids=skip_ids):
                return cx, cy

    # Last resort — find open space inside frame
    if frame:
        for try_y in range(int(frame["y"]), int(frame["y2"] - new_height), 50):
            for try_x in range(int(frame["x"]), int(frame["x2"] - new_width), 50):
                if not is_occupied(elements, try_x, try_y, new_width, new_height, exclude_ids=skip_ids):
                    return try_x, try_y

    # No frame or no space — place below lowest element
    max_y2 = 0
    for e in elements:
        if e.get("isDeleted"):
            continue
        ey2 = e["y"] + e.get("height", 0)
        if ey2 > max_y2:
            max_y2 = ey2
    return b["x"], max_y2 + gap


def resolve_like(elements: list, like_id: str) -> dict:
    """Read properties from a reference element to use as defaults."""
    target = next((e for e in elements if e["id"] == like_id), None)
    if not target:
        return {}
    props = {}
    for key in ("width", "height", "backgroundColor", "strokeColor",
                "strokeWidth", "roughness", "fillStyle"):
        if key in target:
            props[key] = target[key]
    # Look for associated text element to get fontSize
    text_el = next((e for e in elements if e["id"] == f"{like_id}_text"
                    or (e.get("containerId") == like_id and e["type"] == "text")), None)
    if text_el and "fontSize" in text_el:
        props["fontSize"] = text_el["fontSize"]
    return props


def add_element(filepath: str, element_type: str, element_id: str,
                x: float, y: float, width: float, height: float,
                bg: str = "transparent", stroke: str = "#000000",
                text: str = None, text_size: int = 14,
                near_id: str = None, direction: str = "right", gap: float = 40,
                like_id: str = None) -> str:
    path = Path(filepath)
    data = json.loads(path.read_text())
    elements = data.get("elements", [])

    # Apply --like defaults (explicit args override)
    like_overrides = {}
    if like_id:
        like_props = resolve_like(elements, like_id)
        if not like_props:
            return f"ERROR: --like element '{like_id}' not found"
        if bg == "transparent" and "backgroundColor" in like_props:
            bg = like_props["backgroundColor"]
        if stroke == "#000000" and "strokeColor" in like_props:
            stroke = like_props["strokeColor"]
        if width == 160 and "width" in like_props:
            width = like_props["width"]
        if height == 160 and "height" in like_props:
            height = like_props["height"]
        if text_size == 14 and "fontSize" in like_props:
            text_size = like_props["fontSize"]
        for k in ("strokeWidth", "roughness", "fillStyle"):
            if k in like_props:
                like_overrides[k] = like_props[k]

    # Check ID uniqueness
    existing_ids = {e["id"] for e in elements}
    if element_id in existing_ids:
        return f"ERROR: element ID '{element_id}' already exists"

    # Compute placement if --near specified
    if near_id:
        computed_x, computed_y = find_placement(elements, near_id, direction, gap, width, height)
        if computed_x is None:
            return f"ERROR: near element '{near_id}' not found"
        x = computed_x
        y = computed_y

    # Determine next index
    indices = [e.get("index", "") for e in elements if e.get("index")]
    if indices:
        last = sorted(indices)[-1]
        # Simple increment: aZ -> aa, aI -> aJ
        next_idx = last + "0"
    else:
        next_idx = "a0"

    shape = {
        **ELEMENT_DEFAULTS,
        "type": element_type,
        "id": element_id,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "strokeColor": stroke,
        "backgroundColor": bg,
        "seed": gen_seed(),
        "version": 1,
        "versionNonce": gen_nonce(),
        "index": next_idx,
        "updated": int(__import__("time").time() * 1000),
        **like_overrides,
    }

    if element_type in ("rectangle", "diamond"):
        shape["roundness"] = {"type": 3}

    elements.append(shape)

    # Add text label if specified
    if text:
        text = text.replace("\\n", "\n")
        num_lines = text.count("\n") + 1
        longest_line = max(text.split("\n"), key=len)
        text_width = len(longest_line) * text_size * 0.55
        text_height = num_lines * text_size * 1.25
        text_id = f"{element_id}_text"

        text_elem = {
            **ELEMENT_DEFAULTS,
            "type": "text",
            "id": text_id,
            "x": x + (width - text_width) / 2,
            "y": y + (height - text_height) / 2,
            "width": text_width,
            "height": text_height,
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
            "index": next_idx + "1",
            "updated": int(__import__("time").time() * 1000),
            "containerId": element_id,
            "lineHeight": 1.25,
            "autoResize": True,
        }
        elements.append(text_elem)

        # Bind text to shape (bidirectional link)
        shape["boundElements"] = [{"id": text_id, "type": "text"}]

    data["elements"] = elements
    path.write_text(json.dumps(data, indent=2))

    # Post-placement collision/boundary check
    from check_collision import check_collisions
    import os
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    collision_result = check_collisions(filepath, element_id)

    msg = f"OK: added {element_type} '{element_id}' at ({x:.0f}, {y:.0f}) {width}x{height}"
    if "OK" not in collision_result:
        msg += f"\n⚠ {collision_result}"
    return msg


def main():
    parser = argparse.ArgumentParser(description="Add element to excalidraw canvas")
    parser.add_argument("file", help="Path to .excalidraw file")
    parser.add_argument("--type", required=True, choices=["ellipse", "rectangle", "diamond", "text", "line"])
    parser.add_argument("--id", required=True, help="Unique element ID")
    parser.add_argument("--x", type=float, default=0)
    parser.add_argument("--y", type=float, default=0)
    parser.add_argument("--width", type=float, default=160)
    parser.add_argument("--height", type=float, default=160)
    parser.add_argument("--bg", default="transparent", help="Background color")
    parser.add_argument("--stroke", default="#000000", help="Stroke color")
    parser.add_argument("--text", help="Text label inside shape")
    parser.add_argument("--text-size", type=int, default=14)
    parser.add_argument("--near", help="Place near this element ID")
    parser.add_argument("--direction", default="right", choices=["right", "left", "above", "below"])
    parser.add_argument("--gap", type=float, default=40)
    parser.add_argument("--like", help="Copy style from this element ID")

    args = parser.parse_args()
    result = add_element(
        args.file, args.type, args.id,
        args.x, args.y, args.width, args.height,
        args.bg, args.stroke, args.text, args.text_size,
        args.near, args.direction, args.gap,
        like_id=getattr(args, "like", None)
    )
    print(result)


if __name__ == "__main__":
    main()
