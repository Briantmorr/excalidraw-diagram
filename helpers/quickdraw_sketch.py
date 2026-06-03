#!/usr/bin/env python3
"""Fetch a human-drawn sketch from Google QuickDraw dataset and convert to Excalidraw freedraw.

Usage:
    python3 quickdraw_sketch.py <category> <output.excalidraw> [--scale 2.0] [--x 100] [--y 100] [--n 1]

Categories: cat, house, bridge, tree, bicycle, flower, sun, cloud, bird, fish, etc.
Full list: https://github.com/googlecreativelab/quickdraw-dataset/blob/master/categories.txt

The QuickDraw simplified format stores strokes as [[x_coords], [y_coords]] arrays.
Each stroke becomes one freedraw element in the output.
"""

import json
import argparse
import random
import time
import sys
import urllib.request
from pathlib import Path


CACHE_DIR = Path.home() / ".cache" / "quickdraw"
QUICKDRAW_URL = "https://storage.googleapis.com/quickdraw_dataset/full/simplified/{}.ndjson"


def fetch_category(category: str, max_samples: int = 100) -> list[dict]:
    """Download and cache QuickDraw samples for a category."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{category}.json"

    if cache_file.exists():
        return json.loads(cache_file.read_text())

    url = QUICKDRAW_URL.format(category.replace(" ", "%20"))
    print(f"Downloading {category} from QuickDraw...", file=sys.stderr)

    samples = []
    try:
        with urllib.request.urlopen(url) as resp:
            for i, line in enumerate(resp):
                if i >= max_samples:
                    break
                data = json.loads(line.decode("utf-8"))
                if data.get("recognized", False):
                    samples.append(data)
    except urllib.error.HTTPError as e:
        print(f"ERROR: category '{category}' not found (HTTP {e.code})", file=sys.stderr)
        sys.exit(1)

    cache_file.write_text(json.dumps(samples))
    print(f"Cached {len(samples)} samples for '{category}'", file=sys.stderr)
    return samples


def quickdraw_to_freedraw(
    drawing: list[list[list[int]]],
    offset_x: float = 0,
    offset_y: float = 0,
    scale: float = 1.0,
    stroke_color: str = "#1a1a1a",
) -> list[dict]:
    """Convert QuickDraw drawing format to freedraw element specs."""
    elements = []

    for i, stroke in enumerate(drawing):
        xs, ys = stroke[0], stroke[1]
        if len(xs) < 2:
            continue

        # Scale and offset
        scaled_xs = [x * scale for x in xs]
        scaled_ys = [y * scale for y in ys]

        # First point becomes the element origin
        origin_x = scaled_xs[0] + offset_x
        origin_y = scaled_ys[0] + offset_y

        # Points are relative to origin
        points = [[round(scaled_xs[j] - scaled_xs[0], 1),
                   round(scaled_ys[j] - scaled_ys[0], 1)]
                  for j in range(len(xs))]

        # Densify if needed (QuickDraw simplified data can be sparse)
        points = densify_points(points, min_density=5.0)

        elements.append({
            "id": f"qd_stroke_{i}",
            "points": points,
            "x": round(origin_x, 1),
            "y": round(origin_y, 1),
            "stroke": stroke_color,
            "width": 1,
        })

    return elements


def densify_points(points: list[list[float]], min_density: float = 5.0) -> list[list[float]]:
    """Add intermediate points so no gap exceeds min_density pixels."""
    import math
    if len(points) < 2:
        return points

    dense = [points[0]]
    for i in range(1, len(points)):
        dx = points[i][0] - points[i-1][0]
        dy = points[i][1] - points[i-1][1]
        dist = math.hypot(dx, dy)
        steps = max(1, int(dist / min_density))
        for s in range(1, steps + 1):
            t = s / steps
            x = points[i-1][0] + dx * t
            y = points[i-1][1] + dy * t
            dense.append([round(x, 1), round(y, 1)])

    return dense


def make_excalidraw(elements: list[dict]) -> dict:
    """Wrap freedraw elements in excalidraw file structure."""
    now = int(time.time() * 1000)
    exc_elements = []

    for i, spec in enumerate(elements):
        pts = spec["points"]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        w = max(xs) - min(xs) if xs else 0
        h = max(ys) - min(ys) if ys else 0

        exc_elements.append({
            "type": "freedraw",
            "id": spec["id"],
            "x": spec["x"],
            "y": spec["y"],
            "width": w,
            "height": h,
            "points": pts,
            "strokeColor": spec["stroke"],
            "backgroundColor": "transparent",
            "strokeWidth": spec["width"],
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
            "seed": random.randint(100000, 9999999),
            "version": 1,
            "versionNonce": random.randint(100000000, 2147483647),
            "index": f"a{i:03d}",
            "updated": now,
        })

    return {
        "type": "excalidraw",
        "version": 2,
        "source": "https://github.com/zsviczian/obsidian-excalidraw-plugin/releases/tag/2.22.3",
        "elements": exc_elements,
        "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
        "files": {},
    }


def main():
    parser = argparse.ArgumentParser(description="QuickDraw → Excalidraw freedraw")
    parser.add_argument("category", help="QuickDraw category (e.g. cat, house, bridge)")
    parser.add_argument("output", help="Output .excalidraw file path")
    parser.add_argument("--scale", type=float, default=2.0, help="Scale factor (default 2.0)")
    parser.add_argument("--x", type=float, default=50, help="X offset (default 50)")
    parser.add_argument("--y", type=float, default=50, help="Y offset (default 50)")
    parser.add_argument("--n", type=int, default=1, help="Number of sketches to place (default 1)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")

    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    samples = fetch_category(args.category)
    if not samples:
        print(f"ERROR: no samples found for '{args.category}'", file=sys.stderr)
        sys.exit(1)

    all_elements = []
    for i in range(args.n):
        sample = random.choice(samples)
        x_offset = args.x + i * 300  # space multiple sketches apart
        elements = quickdraw_to_freedraw(
            sample["drawing"],
            offset_x=x_offset,
            offset_y=args.y,
            scale=args.scale,
        )
        # Prefix IDs to avoid collision
        for el in elements:
            el["id"] = f"s{i}_{el['id']}"
        all_elements.extend(elements)

    data = make_excalidraw(all_elements)
    Path(args.output).write_text(json.dumps(data, indent="\t"))
    print(f"OK: wrote {len(all_elements)} strokes from '{args.category}' to {args.output}")


if __name__ == "__main__":
    main()
