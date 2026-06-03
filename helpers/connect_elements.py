#!/usr/bin/env python3
"""Add an arrow connecting two existing elements in an excalidraw canvas."""

import json
import argparse
import random
import time
from pathlib import Path


def gen_seed() -> int:
    return random.randint(100000, 9999999)


def gen_nonce() -> int:
    return random.randint(100000000, 2147483647)


def center(el: dict) -> tuple[float, float]:
    return el["x"] + el.get("width", 0) / 2, el["y"] + el.get("height", 0) / 2


def next_index(elements: list[dict]) -> str:
    indices = [e.get("index", "") for e in elements if e.get("index")]
    if indices:
        return sorted(indices)[-1] + "0"
    return "a0"


SIDE_TO_FP = {
    "top": [0.5, 0.0],
    "bottom": [0.5, 1.0],
    "left": [0.0, 0.5],
    "right": [1.0, 0.5],
}


def compute_fixed_points(src: dict, tgt: dict,
                         start_side: str | None = None,
                         end_side: str | None = None) -> tuple[list[float], list[float]]:
    """Compute fixedPoint [0-1, 0-1] for arrow start/end based on relative positions.
    If start_side/end_side provided, use those instead of auto-computing."""
    if start_side and end_side:
        return SIDE_TO_FP[start_side], SIDE_TO_FP[end_side]

    sx, sy = center(src)
    tx, ty = center(tgt)
    dx, dy = tx - sx, ty - sy

    if start_side:
        start_fp = SIDE_TO_FP[start_side]
    elif abs(dx) > abs(dy):
        start_fp = [1.0, 0.5] if dx > 0 else [0.0, 0.5]
    else:
        start_fp = [0.5, 1.0] if dy > 0 else [0.5, 0.0]

    if end_side:
        end_fp = SIDE_TO_FP[end_side]
    elif abs(dx) > abs(dy):
        end_fp = [0.0, 0.5] if dx > 0 else [1.0, 0.5]
    else:
        end_fp = [0.5, 0.0] if dy > 0 else [0.5, 1.0]

    return start_fp, end_fp


def connect_elements(
    filepath: str,
    from_id: str,
    to_id: str,
    label: str | None = None,
    style: str = "solid",
    stroke_width: int = 2,
    start_side: str | None = None,
    end_side: str | None = None,
) -> str:
    path = Path(filepath)
    data = json.loads(path.read_text())
    elements: list[dict] = data.get("elements", [])

    by_id = {e["id"]: e for e in elements}

    if from_id not in by_id:
        return f"ERROR: source element '{from_id}' not found"
    if to_id not in by_id:
        return f"ERROR: target element '{to_id}' not found"

    src = by_id[from_id]
    tgt = by_id[to_id]

    start_fp, end_fp = compute_fixed_points(src, tgt, start_side, end_side)

    src_w = src.get("width", 0)
    src_h = src.get("height", 0)
    tgt_w = tgt.get("width", 0)
    tgt_h = tgt.get("height", 0)

    arrow_sx = src["x"] + start_fp[0] * src_w
    arrow_sy = src["y"] + start_fp[1] * src_h
    arrow_ex = tgt["x"] + end_fp[0] * tgt_w
    arrow_ey = tgt["y"] + end_fp[1] * tgt_h
    dx = arrow_ex - arrow_sx
    dy = arrow_ey - arrow_sy

    # Enforce minimum arrow length for labeled arrows (otherwise label hides the arrow)
    if label:
        font_size = 14
        label_w = len(label) * font_size * 0.55
        min_length = label_w + 50
        is_horizontal = abs(dx) > abs(dy)
        if is_horizontal and abs(dx) < min_length:
            shortfall = min_length - abs(dx)
            sign = 1 if dx >= 0 else -1
            tgt["x"] += sign * shortfall
            # Move target's bound text too
            for el in elements:
                if el.get("containerId") == to_id:
                    el["x"] += sign * shortfall
            arrow_ex = tgt["x"] + end_fp[0] * tgt_w
            dx = arrow_ex - arrow_sx

    arrow_id = f"arrow_{from_id}_{to_id}"
    if arrow_id in by_id:
        return f"ERROR: arrow '{arrow_id}' already exists"

    now = int(time.time() * 1000)
    idx = next_index(elements)

    arrow: dict = {
        "type": "arrow",
        "id": arrow_id,
        "x": arrow_sx,
        "y": arrow_sy,
        "width": abs(dx),
        "height": abs(dy),
        "strokeColor": "#3a3428",
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": stroke_width,
        "strokeStyle": style,
        "roughness": 1,
        "opacity": 100,
        "angle": 0,
        "points": [[0, 0], [dx, dy]],
        "startBinding": {"mode": "orbit", "elementId": from_id, "fixedPoint": start_fp},
        "endBinding": {"mode": "orbit", "elementId": to_id, "fixedPoint": end_fp},
        "startArrowhead": None,
        "endArrowhead": "arrow",
        "elbowed": False,
        "hasTextLink": False,
        "seed": gen_seed(),
        "version": 2,
        "versionNonce": gen_nonce(),
        "isDeleted": False,
        "groupIds": [],
        "boundElements": [],
        "link": None,
        "locked": False,
        "frameId": None,
        "roundness": {"type": 2},
        "index": idx,
        "updated": now,
    }

    elements.append(arrow)

    # Update boundElements on source and target
    for el_id in [from_id, to_id]:
        el = by_id[el_id]
        bound = el.get("boundElements") or []
        if not any(b.get("id") == arrow_id for b in bound):
            bound.append({"id": arrow_id, "type": "arrow"})
        el["boundElements"] = bound

    # Optional label text bound to the arrow
    if label:
        mid_x = arrow_sx + dx / 2
        mid_y = arrow_sy + dy / 2
        font_size = 14
        estimated_w = len(label) * font_size * 0.55
        label_h = font_size * 1.25
        label_id = f"{arrow_id}_label"
        label_idx = idx + "1"

        label_elem: dict = {
            "type": "text",
            "id": label_id,
            "x": mid_x - estimated_w / 2,
            "y": mid_y - label_h / 2,
            "width": estimated_w,
            "height": label_h,
            "text": label,
            "originalText": label,
            "rawText": label,
            "fontSize": font_size,
            "fontFamily": 1,
            "textAlign": "center",
            "verticalAlign": "middle",
            "strokeColor": "#3a3428",
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 1,
            "strokeStyle": "solid",
            "roughness": 0,
            "opacity": 100,
            "angle": 0,
            "hasTextLink": False,
            "seed": gen_seed(),
            "version": 1,
            "versionNonce": gen_nonce(),
            "isDeleted": False,
            "groupIds": [],
            "boundElements": [],
            "link": None,
            "locked": False,
            "frameId": None,
            "roundness": None,
            "containerId": arrow_id,
            "lineHeight": 1.25,
            "autoResize": True,
            "index": label_idx,
            "updated": now,
        }
        elements.append(label_elem)

        arrow["boundElements"].append({"id": label_id, "type": "text"})

    data["elements"] = elements
    if "files" not in data:
        data["files"] = {}
    if "appState" not in data:
        data["appState"] = {}
    data["appState"].setdefault("gridSize", None)
    data["appState"].setdefault("viewBackgroundColor", "#ffffff")
    data["appState"].setdefault("isBindingEnabled", True)
    data["source"] = "https://github.com/zsviczian/obsidian-excalidraw-plugin/releases/tag/2.22.3"
    path.write_text(json.dumps(data, indent=2))
    return f"OK: connected {from_id} -> {to_id}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Connect two excalidraw elements with an arrow")
    parser.add_argument("file", help="Path to .excalidraw file")
    parser.add_argument("--from", dest="from_id", required=True, help="Source element ID")
    parser.add_argument("--to", dest="to_id", required=True, help="Target element ID")
    parser.add_argument("--label", default=None, help="Text label on the arrow")
    parser.add_argument("--style", default="solid", choices=["solid", "dashed"], help="Stroke style")
    parser.add_argument("--stroke-width", type=int, default=2, choices=[1, 2, 3], help="Stroke width")
    parser.add_argument("--start-side", default=None, choices=["top", "bottom", "left", "right"],
                        help="Force arrow to start from this side of source element")
    parser.add_argument("--end-side", default=None, choices=["top", "bottom", "left", "right"],
                        help="Force arrow to end at this side of target element")

    args = parser.parse_args()
    result = connect_elements(
        args.file,
        args.from_id,
        args.to_id,
        label=args.label,
        style=args.style,
        stroke_width=args.stroke_width,
        start_side=args.start_side,
        end_side=args.end_side,
    )
    print(result)


if __name__ == "__main__":
    main()
