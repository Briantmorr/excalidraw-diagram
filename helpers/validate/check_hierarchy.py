#!/usr/bin/env python3
"""Detect flat size hierarchy in an excalidraw diagram.

Rubric: meaningful shapes should span a 1.75-3x area ratio between largest
and smallest. Below 1.75x the diagram looks flat — size variation is the
visual argument, so a uniform canvas fails the Isomorphism Test.

Skip patterns where flatness is INTENTIONAL:
- Uniform row (>=3 shapes of the same type, collinear, near-identical
  size) — this covers timelines, storyboards, comparison rows, and
  side-by-side panels where peer-equality is the point.
- Grid (>=4 identical shapes arranged on a 2D Cartesian product of
  rows x cols, with each row and each col holding multiple shapes) —
  comparison tables.
- Composite: when the canvas is large and contains multiple stacked
  sub-diagrams, the global max/min ratio is meaningless; we segment
  by vertical gaps and only complain about a band that is itself flat
  AND not an intentional-flat pattern.
- Dividers (very thin shapes), frames, explicit container rectangles,
  and zero-size elements are dropped before any of the above.

Usage: python check_hierarchy.py <file.excalidraw>
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

# Allow running both as module and as script.
_HERE = Path(__file__).resolve().parent
_HELPERS = _HERE.parent
if str(_HELPERS) not in sys.path:
    sys.path.insert(0, str(_HELPERS))

from core.excalidraw_core import get_frame_ids  # noqa: E402

# Threshold below which we warn. Rubric calls for 2-3x; we use 1.75 as the
# floor so a diagram that hits ~1.8x naturally is not penalized.
HIERARCHY_RATIO_FLOOR = 1.75

SHAPE_TYPES = {"rectangle", "ellipse", "diamond"}

# Thin-divider heuristic: any shape with either dimension under this is
# treated as a rule/divider, not a meaningful element.
DIVIDER_THICKNESS = 8

# Composite detection: stacked sub-diagrams typically span a large vertical
# extent. Below this we treat the canvas as a single section.
COMPOSITE_VERTICAL_EXTENT = 1500.0

# Gap (in px of empty vertical space) that splits one band from the next.
COMPOSITE_BAND_GAP = 200.0


@dataclass
class Shape:
    id: str
    type: str
    x: float
    y: float
    width: float
    height: float
    text_len: int
    degree: int  # number of arrow bindings touching this shape

    @property
    def area(self) -> float:
        return self.width * self.height


def _arrow_degree(elements: list[dict]) -> dict[str, int]:
    """Count how many arrow endpoints touch each shape (binding-graph degree)."""
    degree: dict[str, int] = {}
    for e in elements:
        if e.get("type") != "arrow" or e.get("isDeleted"):
            continue
        for key in ("startBinding", "endBinding"):
            b = e.get(key)
            if not b:
                continue
            tid = b.get("elementId")
            if tid:
                degree[tid] = degree.get(tid, 0) + 1
    return degree


def _bound_text_len(elements: list[dict]) -> dict[str, int]:
    """Map shape id -> length of its bound text label (proxy for importance)."""
    lengths: dict[str, int] = {}
    for e in elements:
        if e.get("type") != "text" or e.get("isDeleted"):
            continue
        cid = e.get("containerId")
        if cid:
            lengths[cid] = lengths.get(cid, 0) + len(e.get("text", ""))
    return lengths


def _collect_shapes(elements: list[dict]) -> list[Shape]:
    """Filter to meaningful shapes — drop deleted, frames, dividers,
    explicit containers, and zero-size elements."""
    frame_ids = get_frame_ids(elements)
    degree = _arrow_degree(elements)
    text_len = _bound_text_len(elements)

    shapes: list[Shape] = []
    for e in elements:
        if e.get("isDeleted"):
            continue
        if e.get("type") not in SHAPE_TYPES:
            continue
        if e.get("container") is True:
            continue
        if e["id"] in frame_ids:
            continue
        w = float(e.get("width", 0) or 0)
        h = float(e.get("height", 0) or 0)
        if w <= 0 or h <= 0:
            continue
        if w < DIVIDER_THICKNESS or h < DIVIDER_THICKNESS:
            continue
        shapes.append(
            Shape(
                id=e["id"],
                type=e["type"],
                x=float(e.get("x", 0)),
                y=float(e.get("y", 0)),
                width=w,
                height=h,
                text_len=text_len.get(e["id"], 0),
                degree=degree.get(e["id"], 0),
            )
        )
    return shapes


def _is_uniform_row(shapes: list[Shape], pos_tol: float = 30.0,
                    size_tol: float = 25.0) -> bool:
    """Detect a uniform row/column of peer shapes — covers timelines,
    storyboards, comparison rows, side-by-side panels.

    Requires:
    - >=3 shapes
    - All same type
    - Collinear in one axis (all share the same y, or all share the same x)
      within pos_tol
    - At most 2 distinct widths AND at most 2 distinct heights, and the
      width spread and height spread are both within size_tol
    """
    if len(shapes) < 3:
        return False
    types = {s.type for s in shapes}
    if len(types) != 1:
        return False
    ys = [s.y for s in shapes]
    xs = [s.x for s in shapes]
    horizontal = (max(ys) - min(ys)) <= pos_tol
    vertical = (max(xs) - min(xs)) <= pos_tol
    if not (horizontal or vertical):
        return False
    widths = [s.width for s in shapes]
    heights = [s.height for s in shapes]
    if (max(widths) - min(widths)) > size_tol:
        return False
    if (max(heights) - min(heights)) > size_tol:
        return False
    return True


def _is_grid(shapes: list[Shape], tol: float = 1.0) -> bool:
    """Detect a 2D grid: >=4 identical shapes whose (x, y) positions form
    a near-Cartesian product of multiple distinct columns AND multiple
    distinct rows, with each row and each column holding multiple shapes."""
    if len(shapes) < 4:
        return False
    w0, h0 = shapes[0].width, shapes[0].height
    if not all(abs(s.width - w0) < tol and abs(s.height - h0) < tol for s in shapes):
        return False
    xs = [round(s.x) for s in shapes]
    ys = [round(s.y) for s in shapes]
    cols, rows = set(xs), set(ys)
    if len(cols) < 2 or len(rows) < 2:
        return False
    # Each row must hold >=2 shapes, and each column must hold >=2 shapes.
    from collections import Counter
    row_counts = Counter(ys)
    col_counts = Counter(xs)
    if min(row_counts.values()) < 2 or min(col_counts.values()) < 2:
        return False
    # Cartesian-product test: total shapes should be at least 60% of
    # rows*cols (allows for a few empty cells but rejects scatter layouts).
    if len(shapes) < 0.6 * len(rows) * len(cols):
        return False
    return True


def _classify_intentional_flat(shapes: list[Shape]) -> str | None:
    """Return the name of an intentional-flat pattern, or None."""
    if _is_grid(shapes):
        return "grid"
    if _is_uniform_row(shapes):
        return "uniform-row"
    return None


def _segment_by_gaps(shapes: list[Shape],
                     gap: float = COMPOSITE_BAND_GAP) -> list[list[Shape]]:
    """Split shapes into vertical bands separated by `gap` px of empty space."""
    if not shapes:
        return []
    by_y = sorted(shapes, key=lambda s: s.y)
    segments: list[list[Shape]] = [[by_y[0]]]
    cur_bottom = by_y[0].y + by_y[0].height
    for s in by_y[1:]:
        if s.y - cur_bottom > gap:
            segments.append([s])
            cur_bottom = s.y + s.height
        else:
            segments[-1].append(s)
            cur_bottom = max(cur_bottom, s.y + s.height)
    return segments


def _candidate_upsizers(shapes: list[Shape], k: int = 3) -> list[Shape]:
    """Pick the most central shapes — those that most deserve to be larger.
    Rank by binding-graph degree; tiebreak by text length, then id."""
    ranked = sorted(shapes, key=lambda s: (-s.degree, -s.text_len, s.id))
    return ranked[:k]


def _is_composite(shapes: list[Shape]) -> bool:
    if not shapes:
        return False
    extent = max(s.y + s.height for s in shapes) - min(s.y for s in shapes)
    return extent > COMPOSITE_VERTICAL_EXTENT


def check_hierarchy(filepath: str) -> tuple[str, int]:
    """Return (output, exit_code). Exit code 0 if the diagram passes."""
    try:
        data = json.loads(Path(filepath).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return f"FAIL:READ_ERROR {exc}", 2

    elements = data.get("elements", [])
    shapes = _collect_shapes(elements)

    if len(shapes) < 2:
        return "OK: hierarchy not applicable (fewer than 2 meaningful shapes)", 0

    # Composite canvas: check each band independently. Skip bands that are
    # themselves intentional-flat patterns.
    if _is_composite(shapes):
        segments = _segment_by_gaps(shapes)
        bad: list[list[Shape]] = []
        for seg in segments:
            if len(seg) < 2:
                continue
            if _classify_intentional_flat(seg):
                continue
            areas = [s.area for s in seg]
            if max(areas) / min(areas) < HIERARCHY_RATIO_FLOOR:
                bad.append(seg)
        if not bad:
            return "OK: composite hierarchy healthy across sections", 0
        lines = []
        for seg in bad:
            areas = [s.area for s in seg]
            ratio = max(areas) / min(areas)
            cands = _candidate_upsizers(seg)
            cand_str = ", ".join(c.id for c in cands) if cands else "(no clear hub)"
            seg_y = min(s.y for s in seg)
            lines.append(
                f"  band y={seg_y:.0f} ({len(seg)} shapes) ratio={ratio:.2f}; "
                f"upsize: {cand_str}"
            )
        header = (f"WARN:HIERARCHY_FLAT {len(bad)} section(s) below "
                  f"{HIERARCHY_RATIO_FLOOR}x")
        return header + "\n" + "\n".join(lines), 0

    # Single-section: intentional-flat patterns pass.
    pattern = _classify_intentional_flat(shapes)
    if pattern:
        return f"OK: intentional flat hierarchy ({pattern})", 0

    areas = [s.area for s in shapes]
    ratio = max(areas) / min(areas)
    if ratio >= HIERARCHY_RATIO_FLOOR:
        return f"OK: hierarchy ratio {ratio:.2f}x (>= {HIERARCHY_RATIO_FLOOR}x)", 0

    cands = _candidate_upsizers(shapes)
    cand_str = ", ".join(c.id for c in cands) if cands else "(no clear hub)"
    msg = (f"WARN:HIERARCHY_FLAT ratio={ratio:.2f}x "
           f"(need >= {HIERARCHY_RATIO_FLOOR}x); upsize candidates: {cand_str}")
    return msg, 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check size-hierarchy spread in an excalidraw diagram."
    )
    parser.add_argument("file", help="Path to .excalidraw file")
    args = parser.parse_args()
    output, code = check_hierarchy(args.file)
    print(output)
    return code


if __name__ == "__main__":
    sys.exit(main())
