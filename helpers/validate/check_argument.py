#!/usr/bin/env python3
"""Isomorphism Test: when text is stripped, do the remaining shapes still argue?

Emits two structural warnings:

  WARN:WEAK_ARGUMENT
      >80% of meaningful shapes share a single type (e.g. all rectangles)
      AND no visible directional flow exists. "No flow" =
        (a) <2 arrows total, OR
        (b) arrows form no connected component spanning >50% of shapes.

  WARN:NO_SHAPE_VARIETY
      Every meaningful shape has identical width AND height (within 10%).

Meaningful shapes = rectangles, ellipses, diamonds. Text, arrows, lines, and
detected frame/border elements are excluded. Self-loops (arrows whose start and
end bind to the same shape) do not contribute edges.

CLI: `python check_argument.py <file.excalidraw>` — exits 0 always (warnings
are advisory, mirroring check_collision.py); prints WARN:/FAIL:/OK lines.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from canvas_utils import get_element_bounds, get_frame_ids  # noqa: E402

SHAPE_TYPES = {"rectangle", "ellipse", "diamond"}
MONOCULTURE_RATIO = 0.80
SPAN_RATIO = 0.50
SIZE_TOLERANCE = 0.10  # 10%
PROXIMITY_PX = 24  # arrow endpoint snap radius for unbound arrows


def _live_elements(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Live (non-deleted) elements. Arrows/lines may have one zero dimension
    (perfectly horizontal/vertical) so we don't filter on width*height."""
    out: list[dict[str, Any]] = []
    for e in data.get("elements", []):
        if e.get("isDeleted"):
            continue
        if e["type"] in SHAPE_TYPES:
            if e.get("width", 0) > 0 and e.get("height", 0) > 0:
                out.append(e)
        else:
            out.append(e)
    return out


def _meaningful_shapes(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    frame_ids = get_frame_ids(elements)
    return [
        e for e in elements
        if e["type"] in SHAPE_TYPES and e["id"] not in frame_ids
    ]


def _arrow_endpoint_xy(arrow: dict[str, Any], which: str) -> tuple[float, float] | None:
    """Return absolute (x, y) of an arrow's start (which='start') or end ('end') point."""
    points = arrow.get("points") or []
    if not points:
        return None
    pt = points[0] if which == "start" else points[-1]
    if not isinstance(pt, (list, tuple)) or len(pt) < 2:
        return None
    return (arrow.get("x", 0) + pt[0], arrow.get("y", 0) + pt[1])


def _nearest_shape(xy: tuple[float, float], shapes: list[dict[str, Any]],
                   max_dist: float) -> str | None:
    best_id, best_d = None, max_dist
    px, py = xy
    for s in shapes:
        b = get_element_bounds(s)
        # Distance to bounding box (0 if inside)
        dx = max(b["x"] - px, 0, px - b["x2"])
        dy = max(b["y"] - py, 0, py - b["y2"])
        d = math.hypot(dx, dy)
        if d <= best_d:
            best_d = d
            best_id = s["id"]
    return best_id


def _arrow_edges(arrows: list[dict[str, Any]],
                 shapes: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Build (src_shape_id, dst_shape_id) edges from arrows.

    Uses startBinding/endBinding when present; otherwise snaps free endpoints
    to nearest shape within PROXIMITY_PX. Self-loops (src == dst) are dropped.
    """
    shape_ids = {s["id"] for s in shapes}
    edges: list[tuple[str, str]] = []
    for a in arrows:
        sb = a.get("startBinding") or {}
        eb = a.get("endBinding") or {}
        sid = sb.get("elementId") if isinstance(sb, dict) else None
        eid = eb.get("elementId") if isinstance(eb, dict) else None
        if sid not in shape_ids:
            xy = _arrow_endpoint_xy(a, "start")
            sid = _nearest_shape(xy, shapes, PROXIMITY_PX) if xy else None
        if eid not in shape_ids:
            xy = _arrow_endpoint_xy(a, "end")
            eid = _nearest_shape(xy, shapes, PROXIMITY_PX) if xy else None
        if sid and eid and sid != eid and sid in shape_ids and eid in shape_ids:
            edges.append((sid, eid))
    return edges


def _largest_connected_component(node_ids: set[str],
                                 edges: list[tuple[str, str]]) -> int:
    if not node_ids:
        return 0
    adj: dict[str, set[str]] = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    visited: set[str] = set()
    largest = 0
    for nid in node_ids:
        if nid in visited:
            continue
        stack = [nid]
        size = 0
        while stack:
            x = stack.pop()
            if x in visited:
                continue
            visited.add(x)
            size += 1
            for y in adj[x]:
                if y not in visited:
                    stack.append(y)
        if size > largest:
            largest = size
    return largest


def _identical_size(shapes: list[dict[str, Any]], tol: float = SIZE_TOLERANCE) -> bool:
    if len(shapes) < 2:
        return False
    ws = [s["width"] for s in shapes]
    hs = [s["height"] for s in shapes]
    w_ref, h_ref = ws[0], hs[0]
    if w_ref <= 0 or h_ref <= 0:
        return False
    for w, h in zip(ws, hs):
        if abs(w - w_ref) / w_ref > tol or abs(h - h_ref) / h_ref > tol:
            return False
    return True


def check_argument(filepath: str) -> tuple[int, list[str]]:
    """Run the Isomorphism Test on filepath. Returns (exit_code, lines)."""
    try:
        data = json.loads(Path(filepath).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return 0, [f"FAIL:READ_ERROR {exc}"]

    elements = _live_elements(data)
    shapes = _meaningful_shapes(elements)
    arrows = [e for e in elements if e["type"] == "arrow"]

    lines: list[str] = []

    if len(shapes) < 2:
        lines.append(f"OK: not enough shapes to evaluate (n={len(shapes)})")
        return 0, lines

    # --- WEAK_ARGUMENT --------------------------------------------------------
    type_counts = Counter(s["type"] for s in shapes)
    dominant_type, dominant_n = type_counts.most_common(1)[0]
    dominant_ratio = dominant_n / len(shapes)
    monoculture = dominant_ratio > MONOCULTURE_RATIO

    edges = _arrow_edges(arrows, shapes)
    span = _largest_connected_component({s["id"] for s in shapes}, edges)
    span_ratio = span / len(shapes)
    no_flow = len(arrows) < 2 or span_ratio <= SPAN_RATIO

    if monoculture and no_flow:
        reason_parts = [
            f"{dominant_n}/{len(shapes)} shapes are {dominant_type} ({dominant_ratio:.0%})",
        ]
        if len(arrows) < 2:
            reason_parts.append(f"{len(arrows)} arrow(s)")
        else:
            reason_parts.append(
                f"largest arrow component spans {span}/{len(shapes)} shapes ({span_ratio:.0%})"
            )
        lines.append(
            "WARN:WEAK_ARGUMENT — strip-text test fails: "
            + "; ".join(reason_parts)
        )

    # --- NO_SHAPE_VARIETY -----------------------------------------------------
    if _identical_size(shapes):
        w0, h0 = shapes[0]["width"], shapes[0]["height"]
        lines.append(
            f"WARN:NO_SHAPE_VARIETY — all {len(shapes)} shapes within 10% of "
            f"{w0:.0f}x{h0:.0f} (size encodes no hierarchy)"
        )

    if not lines:
        lines.append("OK: argument structure passes isomorphism test")

    return 0, lines


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Isomorphism Test: detect weak structural arguments in an excalidraw file.",
    )
    parser.add_argument("file", help="Path to .excalidraw file")
    args = parser.parse_args()
    code, lines = check_argument(args.file)
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
