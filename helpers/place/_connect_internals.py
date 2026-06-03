"""Shared arrow-creation internals used by connect_elements.py (single)
and batch_connect.py (batch).

Design:
- `compute_fixed_points` — auto/forced side selection for arrow endpoints
- `plan_label_nudges` — given a list of arrow specs and the current elements,
  return a per-target {dx} dict (only horizontal nudges, matching legacy
  behavior). Compute once from initial source positions, then apply once.
- `apply_target_shifts` — apply nudges to target shapes AND any bound text
- `build_arrow_and_label` — produce arrow dict and optional label dict for a
  single spec, but do NOT mutate the elements list (caller does).

Invariants preserved (per memory feedback_excalidraw_rendering_invariants):
- monotonic indices via core.next_index/frac_index
- shape-before-arrow ordering: caller appends shapes first, arrows after
- reference integrity: boundElements updated bidirectionally
- arrow color: ARROW_COLOR (#3a3428); fontFamily: 1
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.excalidraw_core import (
    ARROW_COLOR,
    DEFAULT_FONT_FAMILY,
    gen_nonce,
    gen_seed,
    next_index,
    text_height,
    text_width,
)


SIDE_TO_FP: dict[str, list[float]] = {
    "top": [0.5, 0.0],
    "bottom": [0.5, 1.0],
    "left": [0.0, 0.5],
    "right": [1.0, 0.5],
}


@dataclass
class ArrowSpec:
    from_id: str
    to_id: str
    label: str | None = None
    style: str = "solid"
    stroke_width: int = 2
    start_side: str | None = None
    end_side: str | None = None


@dataclass
class _PlannedArrow:
    spec: ArrowSpec
    start_fp: list[float]
    end_fp: list[float]
    arrow_id: str
    label_id: str | None = None


def _center(el: dict) -> tuple[float, float]:
    return el["x"] + el.get("width", 0) / 2, el["y"] + el.get("height", 0) / 2


def compute_fixed_points(
    src: dict,
    tgt: dict,
    start_side: str | None = None,
    end_side: str | None = None,
) -> tuple[list[float], list[float]]:
    if start_side and end_side:
        return SIDE_TO_FP[start_side], SIDE_TO_FP[end_side]

    sx, sy = _center(src)
    tx, ty = _center(tgt)
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


def _arrow_endpoints(
    src: dict, tgt: dict, start_fp: list[float], end_fp: list[float]
) -> tuple[float, float, float, float]:
    sw = src.get("width", 0)
    sh = src.get("height", 0)
    tw = tgt.get("width", 0)
    th = tgt.get("height", 0)
    return (
        src["x"] + start_fp[0] * sw,
        src["y"] + start_fp[1] * sh,
        tgt["x"] + end_fp[0] * tw,
        tgt["y"] + end_fp[1] * th,
    )


def plan_label_nudges(
    specs: list[ArrowSpec],
    by_id: dict[str, dict],
    font_size: int = 14,
) -> dict[str, float]:
    """Compute per-target horizontal shifts so labels fit.

    Returns {target_id: dx}. Only horizontal arrows whose label exceeds the
    current arrow length contribute. Multiple specs targeting the same shape
    aggregate to the maximum-magnitude shift in a consistent direction; if
    they conflict, we take the larger absolute value (later passes use the
    final position so all arrows still resolve correctly).
    """
    shifts: dict[str, float] = {}
    for spec in specs:
        if not spec.label:
            continue
        if spec.from_id == spec.to_id:
            continue
        src = by_id.get(spec.from_id)
        tgt = by_id.get(spec.to_id)
        if src is None or tgt is None:
            continue

        start_fp, end_fp = compute_fixed_points(
            src, tgt, spec.start_side, spec.end_side
        )
        sx, sy, ex, ey = _arrow_endpoints(src, tgt, start_fp, end_fp)
        dx, dy = ex - sx, ey - sy
        if abs(dx) <= abs(dy):
            continue  # only nudge horizontal arrows (matches legacy behavior)

        label_w = text_width(spec.label, font_size)
        min_length = label_w + 50
        if abs(dx) >= min_length:
            continue

        shortfall = min_length - abs(dx)
        sign = 1 if dx >= 0 else -1
        proposed = sign * shortfall

        existing = shifts.get(spec.to_id)
        if existing is None or abs(proposed) > abs(existing):
            shifts[spec.to_id] = proposed
    return shifts


def apply_target_shifts(elements: list[dict], shifts: dict[str, float]) -> None:
    if not shifts:
        return
    by_id = {e["id"]: e for e in elements}
    for tgt_id, dx in shifts.items():
        tgt = by_id.get(tgt_id)
        if tgt is None:
            continue
        tgt["x"] += dx
        for el in elements:
            if el.get("containerId") == tgt_id:
                el["x"] += dx


def _build_arrow_dict(
    spec: ArrowSpec,
    src: dict,
    tgt: dict,
    start_fp: list[float],
    end_fp: list[float],
    arrow_id: str,
    index: str,
    now: int,
) -> dict:
    sx, sy, ex, ey = _arrow_endpoints(src, tgt, start_fp, end_fp)
    dx, dy = ex - sx, ey - sy
    return {
        "type": "arrow",
        "id": arrow_id,
        "x": sx,
        "y": sy,
        "width": abs(dx),
        "height": abs(dy),
        "strokeColor": ARROW_COLOR,
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": spec.stroke_width,
        "strokeStyle": spec.style,
        "roughness": 1,
        "opacity": 100,
        "angle": 0,
        "points": [[0, 0], [dx, dy]],
        "startBinding": {
            "mode": "orbit",
            "elementId": spec.from_id,
            "fixedPoint": start_fp,
        },
        "endBinding": {
            "mode": "orbit",
            "elementId": spec.to_id,
            "fixedPoint": end_fp,
        },
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
        "index": index,
        "updated": now,
    }


def _build_label_dict(
    label: str,
    arrow_id: str,
    arrow_dict: dict,
    index: str,
    now: int,
    font_size: int = 14,
) -> dict:
    sx = arrow_dict["x"]
    sy = arrow_dict["y"]
    pts = arrow_dict["points"]
    dx = pts[1][0] - pts[0][0]
    dy = pts[1][1] - pts[0][1]
    mid_x = sx + dx / 2
    mid_y = sy + dy / 2
    estimated_w = text_width(label, font_size)
    label_h = text_height(1, font_size)
    return {
        "type": "text",
        "id": f"{arrow_id}_label",
        "x": mid_x - estimated_w / 2,
        "y": mid_y - label_h / 2,
        "width": estimated_w,
        "height": label_h,
        "text": label,
        "originalText": label,
        "rawText": label,
        "fontSize": font_size,
        "fontFamily": DEFAULT_FONT_FAMILY,
        "textAlign": "center",
        "verticalAlign": "middle",
        "strokeColor": ARROW_COLOR,
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
        "index": index,
        "updated": now,
    }


def emit_arrows(
    elements: list[dict],
    specs: list[ArrowSpec],
) -> tuple[int, list[str]]:
    """Append arrows (and labels) for `specs` onto `elements` in-place.

    Returns (created_count, messages). Skips self-loops silently. Skips
    arrows whose endpoints are missing or whose arrow id already exists,
    recording a message in either case.

    Caller is responsible for:
    - having already run plan_label_nudges + apply_target_shifts when batch
    - persisting elements back to disk
    """
    by_id = {e["id"]: e for e in elements}
    created = 0
    messages: list[str] = []
    now = int(time.time() * 1000)
    base_idx = next_index(elements)

    for i, spec in enumerate(specs):
        if spec.from_id == spec.to_id:
            messages.append(f"SKIP self-loop: {spec.from_id}")
            continue
        src = by_id.get(spec.from_id)
        tgt = by_id.get(spec.to_id)
        if src is None:
            messages.append(f"ERROR: source '{spec.from_id}' not found")
            continue
        if tgt is None:
            messages.append(f"ERROR: target '{spec.to_id}' not found")
            continue

        arrow_id = f"arrow_{spec.from_id}_{spec.to_id}"
        if arrow_id in by_id:
            messages.append(f"ERROR: arrow '{arrow_id}' already exists")
            continue

        start_fp, end_fp = compute_fixed_points(
            src, tgt, spec.start_side, spec.end_side
        )

        # Two suffix chars per emitted element keep indices monotonic across
        # both arrow and (optional) label. Use 2*i and 2*i+1.
        arrow_idx = f"{base_idx}{2 * i:02d}"
        arrow = _build_arrow_dict(
            spec, src, tgt, start_fp, end_fp, arrow_id, arrow_idx, now
        )
        elements.append(arrow)
        by_id[arrow_id] = arrow

        for el_id in (spec.from_id, spec.to_id):
            el = by_id[el_id]
            bound = el.get("boundElements") or []
            if not any(b.get("id") == arrow_id for b in bound):
                bound.append({"id": arrow_id, "type": "arrow"})
            el["boundElements"] = bound

        if spec.label:
            label_idx = f"{base_idx}{2 * i + 1:02d}"
            label_elem = _build_label_dict(
                spec.label, arrow_id, arrow, label_idx, now
            )
            elements.append(label_elem)
            by_id[label_elem["id"]] = label_elem
            arrow["boundElements"].append(
                {"id": label_elem["id"], "type": "text"}
            )

        created += 1
        messages.append(f"OK: connected {spec.from_id} -> {spec.to_id}")

    return created, messages


def ensure_app_state(data: dict) -> None:
    if "files" not in data:
        data["files"] = {}
    if "appState" not in data:
        data["appState"] = {}
    data["appState"].setdefault("gridSize", None)
    data["appState"].setdefault("viewBackgroundColor", "#ffffff")
    data["appState"].setdefault("isBindingEnabled", True)
    data["source"] = (
        "https://github.com/zsviczian/obsidian-excalidraw-plugin/releases/tag/2.22.3"
    )
