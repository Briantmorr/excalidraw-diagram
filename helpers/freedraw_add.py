#!/usr/bin/env python3
"""Add freedraw (pencil sketch) elements to an excalidraw canvas.

Usage:
    python3 freedraw_add.py <file> '<json_array_of_strokes>'

Each stroke spec:
    {"id": "stroke1", "points": [[0,0],[5,3],[10,8],...], "x": 100, "y": 100,
     "stroke": "#000000", "width": 2}

Points are LOCAL coordinates relative to (x, y). The first point should be [0,0].
"""

import json
import argparse
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import gen_nonce, gen_seed


FREEDRAW_DEFAULTS = {
    "type": "freedraw",
    "fillStyle": "solid",
    "strokeStyle": "solid",
    "roughness": 0,
    "opacity": 100,
    "angle": 0,
    "groupIds": [],
    "boundElements": [],
    "link": None,
    "locked": False,
    "isDeleted": False,
    "frameId": None,
    "roundness": None,
    "simulatePressure": True,
    "pressures": [],
}


def compute_bounds(points: list[list[float]]) -> tuple[float, float]:
    """Compute width/height from points array."""
    if not points:
        return 0, 0
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return max(xs) - min(xs), max(ys) - min(ys)


def freedraw_add(filepath: str, strokes: list[dict]) -> str:
    path = Path(filepath)

    if path.exists():
        data = json.loads(path.read_text())
    else:
        data = {
            "type": "excalidraw",
            "version": 2,
            "source": "https://github.com/zsviczian/obsidian-excalidraw-plugin/releases/tag/2.22.3",
            "elements": [],
            "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
            "files": {},
        }

    elements = data.get("elements", [])
    existing_ids = {e["id"] for e in elements}

    # Determine starting index
    indices = [e.get("index", "") for e in elements if e.get("index")]
    if indices:
        base_idx = sorted(indices)[-1] + "0"
    else:
        base_idx = "a0"

    now = int(time.time() * 1000)
    added = []

    for i, spec in enumerate(strokes):
        eid = spec.get("id", f"freedraw_{i}")
        if eid in existing_ids:
            return f"ERROR: element ID '{eid}' already exists"

        points = spec.get("points", [[0, 0]])
        x = spec.get("x", 0)
        y = spec.get("y", 0)
        stroke_color = spec.get("stroke", "#000000")
        stroke_width = spec.get("width", 2)

        w, h = compute_bounds(points)
        idx = base_idx + str(i).zfill(2)

        element = {
            **FREEDRAW_DEFAULTS,
            "id": eid,
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "points": points,
            "strokeColor": stroke_color,
            "backgroundColor": "transparent",
            "strokeWidth": stroke_width,
            "seed": gen_seed(),
            "version": 1,
            "versionNonce": gen_nonce(),
            "index": idx,
            "updated": now,
        }

        elements.append(element)
        added.append(eid)

    data["elements"] = elements
    if "files" not in data:
        data["files"] = {}
    data["source"] = "https://github.com/zsviczian/obsidian-excalidraw-plugin/releases/tag/2.22.3"
    path.write_text(json.dumps(data, indent="\t"))

    return f"OK: added {len(added)} freedraw strokes"


def main():
    parser = argparse.ArgumentParser(description="Add freedraw strokes to excalidraw canvas")
    parser.add_argument("file", help="Path to .excalidraw file")
    parser.add_argument("json_spec", help="JSON array of stroke specs")

    args = parser.parse_args()

    try:
        strokes = json.loads(args.json_spec)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(strokes, list):
        print("ERROR: JSON must be an array of stroke specs", file=sys.stderr)
        sys.exit(1)

    result = freedraw_add(args.file, strokes)
    print(result)


if __name__ == "__main__":
    main()
