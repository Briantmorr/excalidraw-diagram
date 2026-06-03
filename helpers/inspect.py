#!/usr/bin/env python3
"""Read-only canvas summary for `excd info` and the LLM design loop."""

from __future__ import annotations

import sys
from pathlib import Path

# When run as a script, our directory is sys.path[0] and shadows stdlib `inspect`
# (this file is named inspect.py). Swap in the parent so stdlib resolves and
# `from helpers...` imports still work.
_here = Path(__file__).resolve().parent
if sys.path and sys.path[0] in (str(_here), ""):
    sys.path[0] = str(_here.parent)

import argparse  # noqa: E402
import json  # noqa: E402
import statistics  # noqa: E402
from dataclasses import asdict, dataclass, field  # noqa: E402
from typing import Any, Literal  # noqa: E402

from helpers.core import get_canvas_bounds, get_frame_ids  # noqa: E402

Format = Literal["compact", "json", "full"]


@dataclass
class ElementRecord:
    id: str
    type: str
    x: float
    y: float
    width: float
    height: float
    background: str | None = None
    text: str | None = None
    font_size: int | None = None
    container_id: str | None = None
    points: list[list[float]] | None = None
    bound_elements: list[str] = field(default_factory=list)
    start_id: str | None = None
    end_id: str | None = None
    is_frame: bool = False


@dataclass
class CanvasInfo:
    bounds: tuple[float, float, float, float] | None
    canvas_size: tuple[float, float]
    n_elements: int
    n_shapes: int
    n_arrows: int
    n_texts: int
    area_ratio: float
    gap_h_median: float | None
    gap_v_median: float | None
    hierarchy_verdict: str
    elements: list[ElementRecord]


def _bg(e: dict[str, Any]) -> str | None:
    bg = e.get("backgroundColor")
    return bg if bg and bg != "transparent" else None


def _bind_id(b: Any) -> str | None:
    return b.get("elementId") if isinstance(b, dict) else None


def _to_record(e: dict[str, Any], frame_ids: set[str]) -> ElementRecord:
    bound = [_bind_id(be) or (be if isinstance(be, str) else None)
             for be in (e.get("boundElements") or [])]
    is_text = e["type"] == "text"
    is_arrow = e["type"] == "arrow"
    return ElementRecord(
        id=e["id"], type=e["type"],
        x=e["x"], y=e["y"],
        width=e.get("width", 0), height=e.get("height", 0),
        background=_bg(e),
        text=e.get("text") if is_text else None,
        font_size=e.get("fontSize") if is_text else None,
        container_id=e.get("containerId") if is_text else None,
        points=e.get("points") if e["type"] in ("arrow", "line") else None,
        bound_elements=[b for b in bound if b],
        start_id=_bind_id(e.get("startBinding")) if is_arrow else None,
        end_id=_bind_id(e.get("endBinding")) if is_arrow else None,
        is_frame=e["id"] in frame_ids,
    )


def _gap_medians(shapes: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    rows: dict[int, list[dict[str, Any]]] = {}
    cols: dict[int, list[dict[str, Any]]] = {}
    for s in shapes:
        cx = s["x"] + s.get("width", 0) / 2
        cy = s["y"] + s.get("height", 0) / 2
        rows.setdefault(round(cy / 30), []).append(s)
        cols.setdefault(round(cx / 30), []).append(s)
    h_gaps = [b["x"] - (a["x"] + a.get("width", 0))
              for row in rows.values() if len(row) >= 2
              for a, b in zip(sorted(row, key=lambda s: s["x"]),
                              sorted(row, key=lambda s: s["x"])[1:])]
    v_gaps = [b["y"] - (a["y"] + a.get("height", 0))
              for col in cols.values() if len(col) >= 2
              for a, b in zip(sorted(col, key=lambda s: s["y"]),
                              sorted(col, key=lambda s: s["y"])[1:])]
    return (statistics.median(h_gaps) if h_gaps else None,
            statistics.median(v_gaps) if v_gaps else None)


def _hierarchy(shapes: list[dict[str, Any]]) -> str:
    sized = [s for s in shapes if s.get("width", 0) > 0 and s.get("height", 0) > 0]
    if len(sized) < 2:
        return "n/a"
    areas = sorted((s["width"] * s["height"] for s in sized), reverse=True)
    ratio = areas[0] / areas[-1] if areas[-1] else 1.0
    label = "flat" if ratio < 1.10 else "subtle" if ratio < 2.00 else "strong"
    return f"{label} ({ratio:.2f}x)"


def canvas_info(filepath: Path) -> CanvasInfo:
    data = json.loads(Path(filepath).read_text())
    elements = [e for e in data.get("elements", []) if not e.get("isDeleted")]
    frame_ids = get_frame_ids(elements)
    shapes = [e for e in elements
              if e["type"] not in ("text", "arrow", "line") and e["id"] not in frame_ids]
    arrows = [e for e in elements if e["type"] in ("arrow", "line")]
    texts = [e for e in elements if e["type"] == "text"]

    bd = get_canvas_bounds(elements)
    bounds = (bd.x, bd.y, bd.x2, bd.y2) if bd else None
    size = (bd.x2 - bd.x, bd.y2 - bd.y) if bd else (0.0, 0.0)
    canvas_area = size[0] * size[1] or 1.0
    shape_area = sum(s.get("width", 0) * s.get("height", 0) for s in shapes)
    gh, gv = _gap_medians(shapes)

    return CanvasInfo(
        bounds=bounds, canvas_size=size,
        n_elements=len(elements), n_shapes=len(shapes),
        n_arrows=len(arrows), n_texts=len(texts),
        area_ratio=shape_area / canvas_area,
        gap_h_median=gh, gap_v_median=gv,
        hierarchy_verdict=_hierarchy(shapes),
        elements=[_to_record(e, frame_ids) for e in elements],
    )


def _header(info: CanvasInfo) -> list[str]:
    if info.bounds is None:
        return ["empty canvas"]
    x, y, x2, y2 = info.bounds
    w, h = info.canvas_size
    gh = f"{info.gap_h_median:.0f}" if info.gap_h_median is not None else "-"
    gv = f"{info.gap_v_median:.0f}" if info.gap_v_median is not None else "-"
    return [
        f"bounds: ({x:.0f},{y:.0f}) to ({x2:.0f},{y2:.0f})  canvas: {w:.0f}x{h:.0f}",
        f"elements: {info.n_elements} (shapes={info.n_shapes} arrows={info.n_arrows} texts={info.n_texts})",
        f"area_ratio: {info.area_ratio:.2f}  gap_h: {gh}  gap_v: {gv}  hierarchy: {info.hierarchy_verdict}",
        "---",
    ]


def format_compact(info: CanvasInfo) -> str:
    lines = _header(info)
    if info.bounds is None:
        return "\n".join(lines)

    by_id = {r.id: r for r in info.elements}
    shapes = [r for r in info.elements if r.type not in ("text", "arrow", "line")]
    arrows = [r for r in info.elements if r.type in ("arrow", "line")]
    texts = [r for r in info.elements if r.type == "text"]

    text_to_shape: dict[str, str] = {}
    for t in texts:
        if t.container_id and t.container_id in by_id:
            text_to_shape[t.id] = t.container_id
            continue
        tcx, tcy = t.x + t.width / 2, t.y + t.height / 2
        for s in shapes:
            if s.x <= tcx <= s.x + s.width and s.y <= tcy <= s.y + s.height:
                text_to_shape[t.id] = s.id
                break

    grouped: dict[str, list[ElementRecord]] = {}
    for t in texts:
        sid = text_to_shape.get(t.id)
        if sid:
            grouped.setdefault(sid, []).append(t)

    for s in shapes:
        prefix = "[frame] " if s.is_frame else ""
        bg = f" bg={s.background}" if s.background else ""
        labels = grouped.get(s.id, [])
        preview = ""
        if labels:
            preview = "  " + " | ".join(
                '"' + (t.text or "").replace("\n", "\\n")[:40] + '"' for t in labels)
        lines.append(f"{prefix}{s.id}  {s.type} ({s.x:.0f},{s.y:.0f}) {s.width:.0f}x{s.height:.0f}{bg}{preview}")

    for a in arrows:
        ep = ""
        if a.points and len(a.points) >= 2:
            x1, y1 = a.x + a.points[0][0], a.y + a.points[0][1]
            x2, y2 = a.x + a.points[-1][0], a.y + a.points[-1][1]
            ep = f" ({x1:.0f},{y1:.0f})→({x2:.0f},{y2:.0f})"
        bind = f"  [{a.start_id or '?'}→{a.end_id or '?'}]" if (a.start_id or a.end_id) else ""
        lines.append(f"{a.id}  {a.type}{ep}{bind}")

    for t in texts:
        if t.id in text_to_shape:
            continue
        preview = (t.text or "").replace("\n", "\\n")[:40]
        lines.append(f'[text] {t.id}  ({t.x:.0f},{t.y:.0f}) "{preview}"')

    return "\n".join(lines)


def format_full(info: CanvasInfo) -> str:
    lines = _header(info)
    if info.bounds is None:
        return "\n".join(lines)
    for r in info.elements:
        parts = [f"{r.id:<25} {r.type:<10} ({r.x:.0f},{r.y:.0f})  {r.width:.0f}x{r.height:.0f}"]
        if r.background:
            parts.append(f"bg={r.background}")
        if r.type == "text":
            preview = (r.text or "").replace("\n", "\\n")[:40]
            parts.append(f'fs={r.font_size} "{preview}"')
            if r.container_id:
                parts.append(f"container={r.container_id}")
        if r.type == "arrow":
            parts.append(f"start={r.start_id} end={r.end_id}")
        if r.bound_elements:
            parts.append(f"bound={','.join(r.bound_elements)}")
        if r.is_frame:
            parts.append("[frame]")
        lines.append("  ".join(parts))
    return "\n".join(lines)


def summarize(filepath: Path, format: Format = "compact") -> str:
    info = canvas_info(Path(filepath))
    if format == "json":
        return json.dumps(asdict(info), indent=2, default=str)
    if format == "full":
        return format_full(info)
    return format_compact(info)


def _main() -> int:
    p = argparse.ArgumentParser(description="Inspect an excalidraw canvas.")
    p.add_argument("file", type=Path)
    p.add_argument("--format", choices=("compact", "json", "full"), default="compact")
    args = p.parse_args()
    print(summarize(args.file, args.format))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
