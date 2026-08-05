#!/usr/bin/env python3
"""v4 primitive: connect — single + batch arrow creation with elbow + crossing detection."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from helpers.core import (  # noqa: E402
    ARROW_COLOR, DEFAULT_FONT_FAMILY, EDGE_GAP, SAFE_BINDING, TEXT_BBOX_RATIO,
    TEXT_BODY, appstate_defaults, frac_index, gen_nonce, gen_seed, next_index,
    now_ms, shape_edge_point,
)

LABEL_FONT_SIZE: int = 14
LABEL_PADDING: int = 50
BODY_TEXT_COLOR: str = TEXT_BODY
LABEL_MAX_CHARS: int = 8           # arrow labels must be one short token
LABEL_MAX_TOKENS: int = 1

Side = Literal["top", "bottom", "left", "right"]
Style = Literal["solid", "dashed"]


def normalize_label(raw: str | None) -> str | None:
    """Reduce an arrow label to ≤1 token, ≤LABEL_MAX_CHARS.

    Multi-segment labels like "Yes / Gold" become "Yes" — second axis
    belongs in a node, not on an arrow. This is the single gate every
    pattern flows labels through.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    for sep in ("/", "|", ",", ";", ":", " - ", "  "):
        if sep in s:
            s = s.split(sep, 1)[0].strip()
    s = s.split()[0] if s.split() else s
    return s[:LABEL_MAX_CHARS] if s else None


@dataclass
class ConnectSpec:
    from_id: str
    to_id: str
    label: str | None = None
    style: Style = "solid"
    stroke_width: int = 2
    start_side: Side | None = None
    end_side: Side | None = None
    force_elbow: bool = False

    def __post_init__(self) -> None:
        self.label = normalize_label(self.label)


@dataclass
class Edge:
    from_id: str
    to_id: str
    arrow_id: str
    label_id: str | None
    elbowed: bool
    start: tuple[float, float]
    end: tuple[float, float]


@dataclass
class ConnectResult:
    created: list[Edge] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _tw(s: str, fs: float = LABEL_FONT_SIZE) -> float:
    return len(s) * fs * TEXT_BBOX_RATIO


def _th(lines: int, fs: float = LABEL_FONT_SIZE) -> float:
    return lines * fs * 1.25


def _bounds(el: dict) -> tuple[float, float, float, float]:
    x, y = el["x"], el["y"]
    return x, y, x + el.get("width", 0), y + el.get("height", 0)


def _center(el: dict) -> tuple[float, float]:
    x1, y1, x2, y2 = _bounds(el)
    return (x1 + x2) / 2, (y1 + y2) / 2


def compute_edge_point(
    src: dict, tgt: dict, side: Side | None = None, *, is_source: bool = True,
) -> tuple[float, float, Side]:
    sx, sy = _center(src)
    tx, ty = _center(tgt)
    dx, dy = tx - sx, ty - sy
    el = src if is_source else tgt
    x1, y1, x2, y2 = _bounds(el)
    cx, cy = _center(el)
    if side is None:
        if abs(dy) > 2 * abs(dx):
            side = ("bottom" if dy > 0 else "top") if is_source else ("top" if dy > 0 else "bottom")
        else:
            side = ("right" if dx > 0 else "left") if is_source else ("left" if dx > 0 else "right")
        # Auto side: attach to the TRUE shape outline (ellipse curve / diamond
        # slant), inset by EDGE_GAP. Mirrors EA intersectElementWithLine.
        toward = (tx, ty) if is_source else (sx, sy)
        px, py = shape_edge_point(el, toward, gap=EDGE_GAP)
        return px, py, side
    # Explicit side: snap to that face midpoint (unchanged — needed for gates,
    # barriers, and uniform fan-out where the caller controls the face), inset
    # by EDGE_GAP so the arrowhead clears the border.
    if side == "top":
        return cx, y1 - EDGE_GAP, side
    if side == "bottom":
        return cx, y2 + EDGE_GAP, side
    if side == "left":
        return x1 - EDGE_GAP, cy, side
    return x2 + EDGE_GAP, cy, side


def _seg_hits_rect(
    p1: tuple[float, float], p2: tuple[float, float], rect: tuple[float, float, float, float],
) -> bool:
    x1, y1 = p1
    x2, y2 = p2
    rx1, ry1, rx2, ry2 = rect
    LEFT, RIGHT, BOTTOM, TOP = 1, 2, 4, 8

    def code(x: float, y: float) -> int:
        c = 0
        if x < rx1: c |= LEFT
        elif x > rx2: c |= RIGHT
        if y < ry1: c |= BOTTOM
        elif y > ry2: c |= TOP
        return c

    c1, c2 = code(x1, y1), code(x2, y2)
    while True:
        if not (c1 | c2):
            return True
        if c1 & c2:
            return False
        out = c1 or c2
        if out & TOP:
            x = x1 + (x2 - x1) * (ry2 - y1) / (y2 - y1) if y2 != y1 else x1
            y = ry2
        elif out & BOTTOM:
            x = x1 + (x2 - x1) * (ry1 - y1) / (y2 - y1) if y2 != y1 else x1
            y = ry1
        elif out & RIGHT:
            y = y1 + (y2 - y1) * (rx2 - x1) / (x2 - x1) if x2 != x1 else y1
            x = rx2
        else:
            y = y1 + (y2 - y1) * (rx1 - x1) / (x2 - x1) if x2 != x1 else y1
            x = rx1
        if out == c1:
            x1, y1, c1 = x, y, code(x, y)
        else:
            x2, y2, c2 = x, y, code(x, y)


def detect_crossing(
    p1: tuple[float, float], p2: tuple[float, float],
    obstacles: list[dict], exclude_ids: set[str],
) -> list[str]:
    hits: list[str] = []
    for el in obstacles:
        if el["id"] in exclude_ids or el.get("isDeleted"):
            continue
        if el.get("type") in ("arrow", "text", "freedraw", "line"):
            continue
        if el.get("width", 0) <= 0:
            continue
        if _seg_hits_rect(p1, p2, _bounds(el)):
            hits.append(el["id"])
    return hits


def _path_clear(pts: list[tuple[float, float]], obstacles: list[dict], exclude: set[str]) -> bool:
    return not any(detect_crossing(a, b, obstacles, exclude) for a, b in zip(pts, pts[1:]))


def _elbow_path(
    start: tuple[float, float], end: tuple[float, float],
    start_side: Side,
    obstacles: list[dict], exclude: set[str],
) -> list[tuple[float, float]] | None:
    sx, sy = start
    ex, ey = end
    h_first = [(sx, sy), (ex, sy), (ex, ey)]
    v_first = [(sx, sy), (sx, ey), (ex, ey)]
    candidates = [h_first, v_first] if start_side in ("left", "right") else [v_first, h_first]
    for p in candidates:
        if _path_clear(p, obstacles, exclude):
            return p
    return None


def _build_arrow(
    spec: ConnectSpec, arrow_id: str, start: tuple[float, float],
    points: list[tuple[float, float]], elbowed: bool, index: str,
) -> dict:
    sx, sy = start
    rel = [[p[0] - sx, p[1] - sy] for p in points]
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return {"type": "arrow", "id": arrow_id, "x": sx, "y": sy,
        "width": max(xs) - min(xs), "height": max(ys) - min(ys),
        "strokeColor": ARROW_COLOR, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": spec.stroke_width, "strokeStyle": spec.style,
        "roughness": 1, "opacity": 100, "angle": 0, "points": rel,
        "startBinding": SAFE_BINDING(spec.from_id), "endBinding": SAFE_BINDING(spec.to_id),
        "startArrowhead": None, "endArrowhead": "arrow",
        "elbowed": elbowed, "hasTextLink": False,
        "seed": gen_seed(), "version": 2, "versionNonce": gen_nonce(),
        "isDeleted": False, "groupIds": [], "boundElements": [],
        "link": None, "locked": False, "frameId": None,
        "roundness": {"type": 2} if not elbowed else None,
        "index": index, "updated": now_ms()}


def _label_midpoint(pts: list[list[float]]) -> tuple[float, float]:
    seg = [((pts[i+1][0]-pts[i][0])**2 + (pts[i+1][1]-pts[i][1])**2)**0.5 for i in range(len(pts)-1)]
    total = sum(seg) or 1.0
    target, acc = total / 2, 0.0
    for i, s in enumerate(seg):
        if acc + s >= target:
            t = (target - acc) / s if s else 0
            return pts[i][0] + (pts[i+1][0] - pts[i][0]) * t, pts[i][1] + (pts[i+1][1] - pts[i][1]) * t
        acc += s
    return pts[-1][0] / 2, pts[-1][1] / 2


def _build_label(arrow: dict, label: str, label_id: str, index: str) -> dict:
    mx, my = _label_midpoint(arrow["points"])
    ax, ay, w, h = arrow["x"], arrow["y"], _tw(label), _th(1)
    return {"type": "text", "id": label_id,
        "x": ax + mx - w / 2, "y": ay + my - h / 2, "width": w, "height": h,
        "text": label, "originalText": label, "rawText": label,
        "fontSize": LABEL_FONT_SIZE, "fontFamily": DEFAULT_FONT_FAMILY,
        "textAlign": "center", "verticalAlign": "middle",
        "strokeColor": BODY_TEXT_COLOR, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
        "roughness": 0, "opacity": 100, "angle": 0, "hasTextLink": False,
        "seed": gen_seed(), "version": 1, "versionNonce": gen_nonce(),
        "isDeleted": False, "groupIds": [], "boundElements": [],
        "link": None, "locked": False, "frameId": None, "roundness": None,
        "containerId": arrow["id"], "lineHeight": 1.25, "autoResize": True,
        "index": index, "updated": now_ms()}


def _plan_label_shifts(specs: list[ConnectSpec], by_id: dict[str, dict]) -> dict[str, float]:
    shifts: dict[str, float] = {}
    for spec in specs:
        if not spec.label or spec.from_id == spec.to_id:
            continue
        src, tgt = by_id.get(spec.from_id), by_id.get(spec.to_id)
        if not src or not tgt:
            continue
        sx, _sy, _ = compute_edge_point(src, tgt, spec.start_side, is_source=True)
        ex, _ey, _ = compute_edge_point(src, tgt, spec.end_side, is_source=False)
        # Direction from centers (stable); edge points can cross when shapes are
        # nearer than 2*EDGE_GAP, which would flip the sign of ex-sx.
        scx, _scy = _center(src)
        tcx, tcy = _center(tgt)
        cdx, cdy = tcx - scx, tcy - _scy
        dx = ex - sx
        if abs(cdx) <= abs(cdy):
            continue
        min_len = _tw(spec.label) + LABEL_PADDING
        if abs(dx) >= min_len:
            continue
        proposed = (1 if cdx >= 0 else -1) * (min_len - abs(dx))
        existing = shifts.get(spec.to_id)
        if existing is None or abs(proposed) > abs(existing):
            shifts[spec.to_id] = proposed
    return shifts


def _apply_shifts(elements: list[dict], shifts: dict[str, float]) -> None:
    if not shifts:
        return
    by_id = {e["id"]: e for e in elements}
    for tid, dx in shifts.items():
        tgt = by_id.get(tid)
        if not tgt:
            continue
        tgt["x"] += dx
        for el in elements:
            if el.get("containerId") == tid:
                el["x"] += dx


def _ensure_app_state(data: dict) -> None:
    data.setdefault("files", {})
    data.setdefault("appState", {})
    for k, v in appstate_defaults().items():
        data["appState"].setdefault(k, v)
    data.setdefault(
        "source",
        "https://github.com/zsviczian/obsidian-excalidraw-plugin/releases/tag/2.22.3",
    )


def connect(filepath: Path, specs: list[ConnectSpec]) -> ConnectResult:
    path = Path(filepath)
    data = json.loads(path.read_text())
    elements: list[dict] = data.get("elements", [])
    by_id = {e["id"]: e for e in elements}
    result = ConnectResult()

    _apply_shifts(elements, _plan_label_shifts(specs, by_id))
    base = next_index(elements)
    counter = 0

    for spec in specs:
        if spec.from_id == spec.to_id:
            result.skipped.append(f"self-loop: {spec.from_id}")
            continue
        src, tgt = by_id.get(spec.from_id), by_id.get(spec.to_id)
        if not src:
            result.skipped.append(f"missing source: {spec.from_id}")
            continue
        if not tgt:
            result.skipped.append(f"missing target: {spec.to_id}")
            continue
        arrow_id = f"arrow_{spec.from_id}_{spec.to_id}"
        if arrow_id in by_id:
            result.skipped.append(f"exists: {arrow_id}")
            continue

        sx, sy, sside = compute_edge_point(src, tgt, spec.start_side, is_source=True)
        ex, ey, _ = compute_edge_point(src, tgt, spec.end_side, is_source=False)
        start, end = (sx, sy), (ex, ey)
        exclude = {spec.from_id, spec.to_id}

        elbowed = False
        points: list[tuple[float, float]] = [start, end]
        needs_elbow = spec.force_elbow or bool(detect_crossing(start, end, elements, exclude))
        if needs_elbow:
            path_pts = _elbow_path(start, end, sside, elements, exclude)
            if path_pts:
                points = path_pts
                elbowed = True
            else:
                result.warnings.append(
                    f"no clear elbow for {spec.from_id}->{spec.to_id}; using straight"
                )

        arrow_idx = frac_index(base, counter)
        counter += 1
        arrow = _build_arrow(spec, arrow_id, start, points, elbowed, arrow_idx)
        elements.append(arrow)
        by_id[arrow_id] = arrow

        for eid in (spec.from_id, spec.to_id):
            el = by_id[eid]
            bound = el.get("boundElements") or []
            if not any(b.get("id") == arrow_id for b in bound):
                bound.append({"id": arrow_id, "type": "arrow"})
            el["boundElements"] = bound

        label_id: str | None = None
        if spec.label:
            label_id = f"{arrow_id}_label"
            label_idx = frac_index(base, counter)
            counter += 1
            label_elem = _build_label(arrow, spec.label, label_id, label_idx)
            elements.append(label_elem)
            by_id[label_id] = label_elem
            arrow["boundElements"].append({"id": label_id, "type": "text"})

        result.created.append(Edge(
            from_id=spec.from_id, to_id=spec.to_id, arrow_id=arrow_id,
            label_id=label_id, elbowed=elbowed, start=start, end=end,
        ))

    data["elements"] = elements
    _ensure_app_state(data)
    path.write_text(json.dumps(data, indent=2))
    return result


def connect_batch(filepath: Path, specs: list[ConnectSpec]) -> ConnectResult:
    return connect(filepath, specs)


def _spec_from_dict(d: dict) -> ConnectSpec:
    return ConnectSpec(
        from_id=d.get("from_id") or d["from"], to_id=d.get("to_id") or d["to"],
        label=d.get("label"), style=d.get("style", "solid"),
        stroke_width=d.get("stroke_width", 2),
        start_side=d.get("start_side"), end_side=d.get("end_side"),
        force_elbow=d.get("force_elbow", False),
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Connect excalidraw elements")
    p.add_argument("file")
    p.add_argument("specs", nargs="?", help="JSON array of ConnectSpec dicts")
    p.add_argument("--from", dest="from_id")
    p.add_argument("--to", dest="to_id")
    p.add_argument("--label")
    p.add_argument("--style", default="solid", choices=["solid", "dashed"])
    p.add_argument("--stroke-width", type=int, default=2, choices=[1, 2, 3])
    p.add_argument("--start-side", choices=["top", "bottom", "left", "right"])
    p.add_argument("--end-side", choices=["top", "bottom", "left", "right"])
    p.add_argument("--force-elbow", action="store_true")
    a = p.parse_args()
    if a.specs:
        specs = [_spec_from_dict(d) for d in json.loads(a.specs)]
    elif a.from_id and a.to_id:
        specs = [ConnectSpec(
            from_id=a.from_id, to_id=a.to_id, label=a.label, style=a.style,
            stroke_width=a.stroke_width, start_side=a.start_side, end_side=a.end_side,
            force_elbow=a.force_elbow,
        )]
    else:
        p.error("provide JSON specs or --from/--to")
    r = connect(Path(a.file), specs)
    for e in r.created:
        print(f"OK: {e.from_id} -> {e.to_id}{' [elbow]' if e.elbowed else ''}")
    for s in r.skipped:
        print(f"SKIP: {s}")
    for w in r.warnings:
        print(f"WARN: {w}")


if __name__ == "__main__":
    main()
