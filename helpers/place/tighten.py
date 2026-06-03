#!/usr/bin/env python3
"""Post-generation layout-tightening pass.

Closes the documented "canvas ~10% larger than gold" gap by:
  1. Snapping every shape's (x, y) to the nearest grid (default 20px).
  2. Detecting spines (clusters of >=3 shapes sharing an x- or y-center within
     a tolerance) and re-aligning each cluster to its median center.
  3. Optionally scaling INTER-SHAPE GAPS (not shape sizes) to fit a target
     bounding box. Without `--target-bbox`, derives a "tight" target from the
     gold-set heuristic: max_shape_area * 1.4 * num_shapes.
  4. Re-centering all bound text and visually-centered free-floating text
     after every shape mutation (delegates to core.recenter).
  5. Running check_collision after the pass — if tightening introduced an
     overlap that was not present before, the entire pass is REVERTED.

Rendering invariants preserved:
  - shape z-order untouched (no element re-ordering)
  - arrow ordering preserved (shapes still come before arrows)
  - bindings untouched (no isBindingEnabled flip; bindings remain
    {elementId, focus, gap})
  - no phantom containers, no self-loops introduced
  - all shape borders remain #000000, arrow color #3a3428, fontFamily 1,
    viewBackgroundColor #ffffff (read-only — we never touch these fields)

CLI:
  python tighten.py <file.excalidraw> [--target-bbox WxH] [--snap 20] [--dry-run]

Summary line emitted:
  TIGHTEN: snapped N, aligned to spine M, bbox shrunk X% (W0xH0 -> W1xH1)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Iterable

# Helpers live one directory up; add that to sys.path so we can import siblings.
_HERE = Path(__file__).resolve().parent
_HELPERS = _HERE.parent
sys.path.insert(0, str(_HELPERS))

from core.excalidraw_core import (  # noqa: E402
    get_canvas_bounds,
    get_frame_ids,
    recenter,
)
from check_collision import check_collisions  # noqa: E402


SHAPE_TYPES: frozenset[str] = frozenset({"rectangle", "ellipse", "diamond"})
DEFAULT_SNAP: int = 20
SPINE_TOLERANCE: int = 30
SPINE_MIN_MEMBERS: int = 3

# Heuristic coefficients derived from v13 gold-set measurements.
# ratio = bbox_area / (max_shape_area * num_shapes); gold median ~1.3.
GOLD_TIGHT_COEFF: float = 1.4   # target shrink-to area when input is loose
GOLD_LOOSE_COEFF: float = 2.0   # do not shrink at all unless input exceeds this


@dataclass
class TightenSummary:
    snapped: int = 0
    aligned: int = 0
    bbox_before: tuple[float, float] = (0.0, 0.0)
    bbox_after: tuple[float, float] = (0.0, 0.0)
    reverted: bool = False
    reason: str = ""

    def shrink_pct(self) -> float:
        bw, bh = self.bbox_before
        aw, ah = self.bbox_after
        before_area = bw * bh
        after_area = aw * ah
        if before_area <= 0:
            return 0.0
        return (1.0 - after_area / before_area) * 100.0

    def format_line(self) -> str:
        bw, bh = self.bbox_before
        aw, ah = self.bbox_after
        if self.reverted:
            return (
                f"TIGHTEN: REVERTED ({self.reason}) — snapped 0, aligned 0, "
                f"bbox unchanged ({bw:.0f}x{bh:.0f})"
            )
        return (
            f"TIGHTEN: snapped {self.snapped}, aligned to spine "
            f"{self.aligned}, bbox shrunk {self.shrink_pct():.1f}% "
            f"({bw:.0f}x{bh:.0f} -> {aw:.0f}x{ah:.0f})"
        )


def _movable_shapes(elements: list[dict], frame_ids: set[str]) -> list[dict]:
    """Shapes eligible for tightening: not deleted, not a frame, has positive size."""
    return [
        e
        for e in elements
        if e.get("type") in SHAPE_TYPES
        and not e.get("isDeleted")
        and e.get("width", 0) > 0
        and e.get("height", 0) > 0
        and e["id"] not in frame_ids
    ]


def _move_shape(
    elements: list[dict], shape: dict, new_x: float, new_y: float
) -> bool:
    """Move a shape and re-center its bound + visually-centered free text.

    Returns True if the shape actually moved.
    """
    old_x = shape["x"]
    old_y = shape["y"]
    if new_x == old_x and new_y == old_y:
        return False
    shape["x"] = new_x
    shape["y"] = new_y
    shape["version"] = shape.get("version", 1) + 1
    recenter(
        elements,
        shape,
        old_x=old_x,
        old_y=old_y,
        old_width=shape.get("width", 0),
        old_height=shape.get("height", 0),
    )
    return True


def _snap_pass(
    elements: list[dict], shapes: list[dict], grid: int
) -> int:
    """Snap every shape's (x, y) to the nearest multiple of `grid`.

    Returns the number of shapes that actually moved.
    """
    if grid <= 0:
        return 0
    moved = 0
    for shape in shapes:
        nx = round(shape["x"] / grid) * grid
        ny = round(shape["y"] / grid) * grid
        if _move_shape(elements, shape, nx, ny):
            moved += 1
    return moved


def _cluster_by_center(
    shapes: list[dict], axis: str, tol: int
) -> list[list[dict]]:
    """Cluster shapes whose center along `axis` ('x' or 'y') is within `tol`.

    Greedy 1-D agglomerative clustering on sorted centers.
    Returns clusters in input order (only clusters with >=SPINE_MIN_MEMBERS are
    returned to the caller; small clusters are dropped here too for clarity).
    """
    if not shapes:
        return []
    if axis == "x":
        keyed = [(s["x"] + s.get("width", 0) / 2, s) for s in shapes]
    else:
        keyed = [(s["y"] + s.get("height", 0) / 2, s) for s in shapes]
    keyed.sort(key=lambda kv: kv[0])

    clusters: list[list[tuple[float, dict]]] = []
    for center, shape in keyed:
        if clusters and abs(center - clusters[-1][-1][0]) <= tol:
            clusters[-1].append((center, shape))
        else:
            clusters.append([(center, shape)])

    return [
        [s for _, s in cl]
        for cl in clusters
        if len(cl) >= SPINE_MIN_MEMBERS
    ]


def _align_to_median(
    elements: list[dict], cluster: list[dict], axis: str
) -> int:
    """Re-align cluster members so their `axis`-center sits on the cluster median.

    Shape sizes are preserved; only x or y is updated. Returns number of shapes
    actually moved.
    """
    if axis == "x":
        centers = [s["x"] + s.get("width", 0) / 2 for s in cluster]
    else:
        centers = [s["y"] + s.get("height", 0) / 2 for s in cluster]
    target_center = median(centers)

    moved = 0
    for shape in cluster:
        if axis == "x":
            new_x = target_center - shape.get("width", 0) / 2
            new_y = shape["y"]
        else:
            new_x = shape["x"]
            new_y = target_center - shape.get("height", 0) / 2
        if _move_shape(elements, shape, new_x, new_y):
            moved += 1
    return moved


def _spine_pass(
    elements: list[dict], shapes: list[dict], tol: int
) -> int:
    """Detect x- and y-spines (>=3 shapes) and snap each spine to its median.

    Returns number of shapes moved.
    """
    moved = 0
    for axis in ("x", "y"):
        for cluster in _cluster_by_center(shapes, axis, tol):
            moved += _align_to_median(elements, cluster, axis)
    return moved


def _bbox_of_shapes(shapes: Iterable[dict]) -> tuple[float, float, float, float]:
    shapes = list(shapes)
    if not shapes:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [s["x"] for s in shapes]
    ys = [s["y"] for s in shapes]
    xs2 = [s["x"] + s.get("width", 0) for s in shapes]
    ys2 = [s["y"] + s.get("height", 0) for s in shapes]
    return (min(xs), min(ys), max(xs2), max(ys2))


def _gap_scale_pass(
    elements: list[dict],
    shapes: list[dict],
    target_w: float | None,
    target_h: float | None,
    snap: int,
) -> int:
    """Scale inter-shape gaps (preserving sizes) so the bbox fits target W x H.

    Each shape's distance from the bbox top-left is multiplied by sx, sy where
    sx, sy <= 1 (we only ever shrink — never grow). After scaling, positions
    are re-snapped to the grid to preserve invariants.

    Returns number of shapes moved.
    """
    if not shapes:
        return 0
    x1, y1, x2, y2 = _bbox_of_shapes(shapes)
    cur_w = x2 - x1
    cur_h = y2 - y1
    if cur_w <= 0 or cur_h <= 0:
        return 0

    sx = 1.0 if target_w is None else min(1.0, target_w / cur_w)
    sy = 1.0 if target_h is None else min(1.0, target_h / cur_h)
    if sx >= 1.0 and sy >= 1.0:
        return 0

    moved = 0
    for shape in shapes:
        # Distance of shape's top-left from bbox top-left, scaled.
        dx = shape["x"] - x1
        dy = shape["y"] - y1
        new_x = x1 + dx * sx
        new_y = y1 + dy * sy
        if snap > 0:
            new_x = round(new_x / snap) * snap
            new_y = round(new_y / snap) * snap
        if _move_shape(elements, shape, new_x, new_y):
            moved += 1
    return moved


def _derive_tight_target(shapes: list[dict]) -> tuple[float, float]:
    """Aspect-preserving target derived from a gold-set heuristic.

    Empirical gold-set ratio (current_bbox_area / (max_shape_area * num_shapes))
    has median ~1.3 across the v13 gold set, so we use 1.4 as the "tight"
    coefficient. We DO NOT shrink unless the current canvas exceeds a higher
    "loose" threshold (default 2.0x the gold-median area) — otherwise tighten
    would penalise legitimately-sparse layouts (timelines, hub-and-spoke,
    lifecycle wheels) whose ratios naturally fall above the median.

    Returns the tight target with the canvas's current aspect ratio preserved.
    On already-tight inputs, returns the current size (so the gap-scale pass
    becomes a no-op).
    """
    if not shapes:
        return (0.0, 0.0)
    max_area = max(s.get("width", 0) * s.get("height", 0) for s in shapes)
    n = len(shapes)
    base_area = max_area * n
    target_area = base_area * GOLD_TIGHT_COEFF
    loose_area = base_area * GOLD_LOOSE_COEFF

    x1, y1, x2, y2 = _bbox_of_shapes(shapes)
    cur_w = x2 - x1
    cur_h = y2 - y1
    cur_area = cur_w * cur_h
    if cur_area <= 0 or cur_area <= loose_area:
        return (cur_w, cur_h)

    scale = (target_area / cur_area) ** 0.5
    return (cur_w * scale, cur_h * scale)


def _categorize_collisions(report: str) -> set[str]:
    """Extract pair keys (sorted tuple of ids) from a check_collision report.

    Pairs are reported as "  id_a ↔ id_b  overlap=…px²".
    Used for revert semantics: tightening only reverts if it INTRODUCES new
    overlaps (existing overlaps in the input are tolerated).
    """
    pairs: set[str] = set()
    for line in report.splitlines():
        line = line.strip()
        if "↔" not in line:
            continue
        head = line.split("overlap=")[0]
        try:
            a, b = [s.strip() for s in head.split("↔")]
        except ValueError:
            continue
        pairs.add(" ".join(sorted([a, b])))
    return pairs


def _shape_only_pairs(pairs: set[str], shape_ids: set[str]) -> set[str]:
    """Filter a pair-set down to pairs where BOTH ids are shapes.

    Arrows are excluded because their stored geometry is stale immediately
    after a shape moves — Excalidraw re-routes bound arrows at render time.
    Including arrow geometry in the revert decision would yield false
    positives: every snap of a shape would appear to "collide" with the
    arrow whose endpoint it carries.
    """
    out: set[str] = set()
    for p in pairs:
        a, b = p.split(" ", 1)
        if a in shape_ids and b in shape_ids:
            out.add(p)
    return out


def tighten(
    filepath: str,
    target_bbox: tuple[int, int] | None = None,
    snap: int = DEFAULT_SNAP,
    dry_run: bool = False,
) -> TightenSummary:
    """Run the full tighten pass on `filepath`. See module docstring."""
    path = Path(filepath)
    raw = path.read_text()
    data = json.loads(raw)
    elements = data.get("elements", [])

    frame_ids = get_frame_ids(elements)
    shapes = _movable_shapes(elements, frame_ids)

    summary = TightenSummary()
    if not shapes:
        b = get_canvas_bounds(elements)
        if b:
            wh = (b["x2"] - b["x"], b["y2"] - b["y"])
            summary.bbox_before = wh
            summary.bbox_after = wh
        return summary

    bx1, by1, bx2, by2 = _bbox_of_shapes(shapes)
    summary.bbox_before = (bx2 - bx1, by2 - by1)

    # Snapshot baseline collisions BEFORE any mutation, so we only revert on
    # NEW overlaps introduced by tightening. Track shape ids so we can filter
    # out arrow-vs-X pairs (arrow geometry is stale after a shape move; the
    # renderer re-routes bound arrows so those reports are false positives).
    shape_ids = {s["id"] for s in shapes}
    baseline_pairs = _shape_only_pairs(
        _categorize_collisions(check_collisions(filepath)), shape_ids
    )

    # Take a deep snapshot for revert. json round-trip is the safest deep copy
    # since elements may carry arbitrary Excalidraw fields.
    pre_snapshot = json.loads(raw)

    # 1) Grid snap
    summary.snapped = _snap_pass(elements, shapes, snap)

    # 2) Spine alignment
    summary.aligned = _spine_pass(elements, shapes, SPINE_TOLERANCE)

    # 3) Optional gap scaling toward target bbox
    if target_bbox is not None:
        tw, th = target_bbox
    else:
        tw, th = _derive_tight_target(shapes)
    _gap_scale_pass(
        elements,
        shapes,
        target_w=tw if tw > 0 else None,
        target_h=th if th > 0 else None,
        snap=snap,
    )

    nx1, ny1, nx2, ny2 = _bbox_of_shapes(shapes)
    summary.bbox_after = (nx2 - nx1, ny2 - ny1)

    # Persist a tentative version so check_collisions can read it on disk.
    if not dry_run:
        path.write_text(json.dumps(data, indent=2))

    # 4) Revert if tightening INTRODUCED shape-vs-shape overlaps not present at baseline.
    post_pairs = _shape_only_pairs(
        _categorize_collisions(
            check_collisions(filepath if not dry_run else _write_temp(data))
        ),
        shape_ids,
    )
    new_overlaps = post_pairs - baseline_pairs
    if new_overlaps:
        summary.reverted = True
        summary.reason = f"introduced {len(new_overlaps)} new overlap(s)"
        if not dry_run:
            path.write_text(raw)
        # Recompute bbox_after to reflect the reverted state.
        summary.bbox_after = summary.bbox_before
        summary.snapped = 0
        summary.aligned = 0

    return summary


def _write_temp(data: dict) -> str:
    """Write a temp file for dry-run collision checks without touching the input."""
    import tempfile

    fd, name = tempfile.mkstemp(suffix=".excalidraw")
    os.close(fd)
    Path(name).write_text(json.dumps(data, indent=2))
    return name


def _parse_bbox(spec: str | None) -> tuple[int, int] | None:
    if spec is None:
        return None
    if "x" not in spec.lower():
        raise argparse.ArgumentTypeError(
            f"--target-bbox must look like WxH, got: {spec!r}"
        )
    w_s, h_s = spec.lower().split("x", 1)
    return (int(w_s), int(h_s))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Post-generation layout tightening for .excalidraw files."
    )
    parser.add_argument("file", help="Path to .excalidraw file")
    parser.add_argument(
        "--target-bbox",
        type=str,
        default=None,
        help='Target bounding box as "WxH" (e.g. "620x440"). '
        "When omitted, a tight target is derived from the shape inventory.",
    )
    parser.add_argument(
        "--snap",
        type=int,
        default=DEFAULT_SNAP,
        help=f"Grid size for position snapping (default: {DEFAULT_SNAP})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute the tighten plan without writing back to disk.",
    )
    args = parser.parse_args()

    target_bbox = _parse_bbox(args.target_bbox)
    summary = tighten(
        args.file,
        target_bbox=target_bbox,
        snap=args.snap,
        dry_run=args.dry_run,
    )
    print(summary.format_line())
    return 0


if __name__ == "__main__":
    sys.exit(main())
