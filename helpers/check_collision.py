#!/usr/bin/env python3
"""Check for element collisions/overlaps in an excalidraw canvas. Reports pairs that overlap."""

import json
import os
import sys
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from canvas_utils import get_element_bounds, get_frame_ids


def get_bounds_tuple(e: dict) -> tuple:
    b = get_element_bounds(e)
    return (b["x"], b["y"], b["x2"], b["y2"])


def overlap_area(a: tuple, b: tuple) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    dx = min(ax2, bx2) - max(ax1, bx1)
    dy = min(ay2, by2) - max(ay1, by1)
    if dx <= 0 or dy <= 0:
        return 0
    return dx * dy


def check_collisions(filepath: str, target_id: str = None, threshold: float = 100,
                     ignore_ids: list = None) -> str:
    """Check for collisions. If target_id specified, only check that element against others.
    threshold: minimum overlap area (px²) to report (filters tiny edge touches).
    ignore_ids: element IDs to exclude from checks (e.g., border frames)."""
    if ignore_ids is None:
        ignore_ids = []

    data = json.loads(Path(filepath).read_text())
    all_elements = data.get("elements", [])
    elements = [e for e in all_elements
                if not e.get("isDeleted") and e.get("width", 0) > 0 and e.get("height", 0) > 0]

    # Use shared frame detection
    frame_ids = get_frame_ids(elements) | set(ignore_ids)

    elements = [e for e in elements if e["id"] not in frame_ids]

    # Skip text elements that are inside shapes (they're supposed to overlap)
    shape_ids = {e["id"] for e in elements if e["type"] != "text"}
    text_inside = set()
    for e in elements:
        if e["type"] == "text":
            container = e.get("containerId")
            if container and container in shape_ids:
                text_inside.add(e["id"])

    # Filter to meaningful elements (shapes + free text only)
    candidates = [e for e in elements if e["id"] not in text_inside]

    # Pair text with its visual parent (skip collision between shape and its label)
    visual_pairs_to_skip = set()
    for e in elements:
        if e["type"] == "text" and e["id"] not in text_inside:
            eb = get_bounds_tuple(e)
            for s in elements:
                if s["type"] != "text" and s["id"] != e["id"]:
                    sb = get_bounds_tuple(s)
                    tcx = (eb[0] + eb[2]) / 2
                    tcy = (eb[1] + eb[3]) / 2
                    if sb[0] <= tcx <= sb[2] and sb[1] <= tcy <= sb[3]:
                        visual_pairs_to_skip.add((min(e["id"], s["id"]), max(e["id"], s["id"])))

    collisions = []

    if target_id:
        target = next((e for e in candidates if e["id"] == target_id), None)
        if not target:
            return f"ERROR: element '{target_id}' not found"
        tb = get_bounds_tuple(target)
        for other in candidates:
            if other["id"] == target_id:
                continue
            pair_key = (min(target_id, other["id"]), max(target_id, other["id"]))
            if pair_key in visual_pairs_to_skip:
                continue
            ob = get_bounds_tuple(other)
            area = overlap_area(tb, ob)
            if area >= threshold:
                collisions.append((target_id, other["id"], area))
    else:
        seen = set()
        for i, a in enumerate(candidates):
            for j, b in enumerate(candidates):
                if j <= i:
                    continue
                pair_key = (min(a["id"], b["id"]), max(a["id"], b["id"]))
                if pair_key in seen or pair_key in visual_pairs_to_skip:
                    continue
                seen.add(pair_key)
                ab = get_bounds_tuple(a)
                bb = get_bounds_tuple(b)
                area = overlap_area(ab, bb)
                if area >= threshold:
                    collisions.append((a["id"], b["id"], area))

    # Bounds check: does target exceed any detected frame?
    boundary_warnings = []
    if target_id and frame_ids:
        target_el = next((e for e in all_elements if e["id"] == target_id), None)
        if target_el:
            tb = get_bounds_tuple(target_el)
            for fid in frame_ids:
                frame_el = next((e for e in all_elements if e["id"] == fid), None)
                if frame_el:
                    fb = get_bounds_tuple(frame_el)
                    if tb[0] < fb[0] or tb[1] < fb[1] or tb[2] > fb[2] or tb[3] > fb[3]:
                        boundary_warnings.append(
                            f"  ⚠ {target_id} exceeds frame {fid} bounds "
                            f"(frame: {fb[0]:.0f},{fb[1]:.0f} to {fb[2]:.0f},{fb[3]:.0f})")

    if not collisions and not boundary_warnings:
        return "OK: no collisions detected"

    lines = []
    if collisions:
        lines.append(f"COLLISIONS: {len(collisions)} found")
        for a_id, b_id, area in sorted(collisions, key=lambda x: -x[2]):
            lines.append(f"  {a_id} ↔ {b_id}  overlap={area:.0f}px²")
    if boundary_warnings:
        lines.append(f"BOUNDARY: {len(boundary_warnings)} warnings")
        lines.extend(boundary_warnings)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Check element collisions in excalidraw file")
    parser.add_argument("file", help="Path to .excalidraw file")
    parser.add_argument("--id", help="Only check this element against others")
    parser.add_argument("--threshold", type=float, default=100,
                        help="Min overlap area (px²) to report (default: 100)")
    parser.add_argument("--ignore", nargs="*", default=[],
                        help="Element IDs to exclude (e.g., border frames)")
    args = parser.parse_args()
    print(check_collisions(args.file, args.id, args.threshold, args.ignore))


if __name__ == "__main__":
    main()
