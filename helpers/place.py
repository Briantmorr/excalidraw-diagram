#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Union

_HELPERS = Path(__file__).resolve().parent
_SKILL_ROOT = _HELPERS.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from helpers.core import (  # noqa: E402
    BORDER_COLOR, DEFAULT_FONT_FAMILY, PALETTE,
    ROLE_PRESETS, SHAPE_DEFAULTS, TEXT_BODY, TEXT_DEFAULTS,
    TEXT_SUBORDINATE, Bounds, appstate_defaults, detect_frames, frac_index,
    gen_nonce, gen_seed, get_element_bounds, next_index, now_ms,
    recenter_text, text_height,
)
from helpers._rubric_targets import DEFAULT_SIZES  # noqa: E402

SOURCE: str = "https://github.com/zsviczian/obsidian-excalidraw-plugin/releases/tag/2.22.3"


class Role(str, Enum):
    STAGE = "stage"
    BRANCH = "branch"
    HUB = "hub"
    SPOKE = "spoke"
    SINK = "sink"
    STEP = "step"
    BARRIER = "barrier"
    CONTAINER = "container"
    WEIGHT_HEAVY = "weight_heavy"
    WEIGHT_LIGHT = "weight_light"
    ANNOTATION = "annotation"
    TITLE = "title"
    HERO = "stage"
    SECONDARY = "step"


@dataclass(frozen=True)
class RightOf:
    id: str
    gap: float = 25.0

@dataclass(frozen=True)
class Below:
    id: str
    gap: float = 25.0

@dataclass(frozen=True)
class Row:
    y: float
    index: int
    total: int
    gap: float = 25.0
    width: float | None = None
    center_x: float | None = None
    x_start: float | None = None

@dataclass(frozen=True)
class Spine:
    x: float
    y_index: int
    gap: float = 100.0
    y_start: float = 0.0

@dataclass(frozen=True)
class Near:
    id: str
    direction: str = "right"
    gap: float = 30.0

@dataclass(frozen=True)
class Like:
    id: str

@dataclass(frozen=True)
class Explicit:
    x: float
    y: float


Anchor = Union[RightOf, Below, Row, Spine, Near, Like, Explicit]
_CLOCKWISE: tuple[str, ...] = ("right", "below", "left", "above")


def _anchor_from_dict(d: dict[str, Any]) -> Anchor:
    if "rel" not in d:
        return Explicit(x=float(d["x"]), y=float(d["y"]))
    rel = d["rel"]
    if rel == "right_of":
        return RightOf(id=d["id"], gap=float(d.get("gap", 25.0)))
    if rel == "below":
        return Below(id=d["id"], gap=float(d.get("gap", 25.0)))
    if rel == "row":
        return Row(y=float(d["y"]), index=int(d["index"]), total=int(d["total"]),
                   gap=float(d.get("gap", 25.0)),
                   width=float(d["width"]) if "width" in d else None,
                   center_x=float(d["center_x"]) if "center_x" in d else None,
                   x_start=float(d["x_start"]) if "x_start" in d else None)
    if rel == "spine":
        return Spine(x=float(d["x"]), y_index=int(d["y_index"]),
                     gap=float(d.get("gap", 100.0)), y_start=float(d.get("y_start", 0.0)))
    if rel == "near":
        return Near(id=d["id"], direction=d.get("direction", "right"), gap=float(d.get("gap", 30.0)))
    if rel == "like":
        return Like(id=d["id"])
    if rel == "explicit":
        return Explicit(x=float(d["x"]), y=float(d["y"]))
    raise ValueError(f"unknown anchor rel: {rel!r}")


@dataclass
class PlaceSpec:
    id: str
    type: str = "rectangle"
    text: str | None = None
    role: Role | None = None
    anchor: Anchor | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    bg: str | None = None
    stroke: str | None = None
    text_size: int | None = None
    font_size: int | None = None
    stroke_width: int | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PlaceSpec":
        role = Role(d["role"]) if d.get("role") else None
        anchor = _anchor_from_dict(d["anchor"]) if d.get("anchor") else None
        return cls(id=d["id"], type=d.get("type", "rectangle"), text=d.get("text"),
                   role=role, anchor=anchor,
                   x=d.get("x"), y=d.get("y"),
                   width=d.get("width"), height=d.get("height"),
                   bg=d.get("bg"), stroke=d.get("stroke"),
                   text_size=d.get("text_size"), font_size=d.get("font_size"),
                   stroke_width=d.get("stroke_width"))


@dataclass
class PlaceResult:
    ok: bool
    placed_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        head = f"OK: placed {len(self.placed_ids)} elements" if self.ok \
            else f"ERROR: {'; '.join(self.errors)}"
        if self.warnings:
            return head + "\nWARNINGS:\n" + "\n".join(f"  {w}" for w in self.warnings)
        return head


@dataclass
class _Resolved:
    id: str
    type: str
    text: str | None
    x: float
    y: float
    width: float
    height: float
    bg: str
    stroke: str
    stroke_width: int
    font_size: int
    text_color: str


_TYPE_DEFAULT_SIZE: dict[str, tuple[int, int]] = {
    "rectangle": DEFAULT_SIZES["rectangle"],
    "ellipse":   DEFAULT_SIZES["ellipse"],
    "diamond":   DEFAULT_SIZES["diamond"],
    "text":      (0, 0),
}


def _bounds_overlap(ax: float, ay: float, ax2: float, ay2: float,
                    bx: float, by: float, bx2: float, by2: float) -> bool:
    return ax < bx2 and ax2 > bx and ay < by2 and ay2 > by


def _is_occupied(elements: list[dict[str, Any]], x: float, y: float,
                 w: float, h: float, exclude: set[str]) -> bool:
    pad = 15.0
    for e in elements:
        if e.get("isDeleted") or e["id"] in exclude or e["type"] == "text":
            continue
        b = get_element_bounds(e)
        ex, ey, ex2, ey2 = b.x, b.y, b.x2, b.y2
        if e["type"] == "arrow":
            if ey2 - ey < 30: ey -= pad; ey2 += pad
            if ex2 - ex < 30: ex -= pad; ex2 += pad
        if _bounds_overlap(x, y, x + w, y + h, ex, ey, ex2, ey2):
            return True
    return False


def _candidate(b: Bounds, direction: str, gap: float, w: float, h: float) -> tuple[float, float]:
    if direction == "right": return b.x2 + gap, b.y
    if direction == "below": return b.x, b.y2 + gap
    if direction == "left":  return b.x - gap - w, b.y
    return b.x, b.y - gap - h


def _find_near(elements: list[dict[str, Any]], near_id: str, direction: str,
               gap: float, w: float, h: float) -> tuple[float, float]:
    target = next((e for e in elements if e["id"] == near_id), None)
    if target is None:
        raise ValueError(f"near anchor: id {near_id!r} not found")
    b = get_element_bounds(target)
    skip = {f["id"] for f in detect_frames(elements)} | {near_id}
    start = _CLOCKWISE.index(direction) if direction in _CLOCKWISE else 0
    for i in range(4):
        d = _CLOCKWISE[(start + i) % 4]
        cx, cy = _candidate(b, d, gap, w, h)
        if not _is_occupied(elements, cx, cy, w, h, skip):
            return cx, cy
    max_y2 = max((e.get("y", 0) + e.get("height", 0) for e in elements if not e.get("isDeleted")), default=0.0)
    return b.x, max_y2 + gap


def _resolve_like(elements: list[dict[str, Any]], placed: dict[str, dict[str, Any]],
                  like_id: str) -> dict[str, Any]:
    target = next((e for e in elements if e["id"] == like_id),
                  placed.get(like_id))
    if target is None:
        raise ValueError(f"like anchor: id {like_id!r} not found")
    out: dict[str, Any] = {}
    for k in ("width", "height", "backgroundColor", "strokeColor", "strokeWidth", "type", "fontSize"):
        if k in target:
            out[k] = target[k]
    bound = next((e for e in elements if e.get("containerId") == like_id and e["type"] == "text"), None)
    if bound and "fontSize" in bound:
        out["fontSize"] = bound["fontSize"]
    return out


def _lookup(eid: str, elements: list[dict[str, Any]],
            placed: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if eid in placed:
        return placed[eid]
    for e in elements:
        if e["id"] == eid:
            return e
    raise ValueError(f"anchor target {eid!r} not found")


def resolve_anchor(spec: PlaceSpec, elements: list[dict[str, Any]],
                   placed: dict[str, dict[str, Any]]) -> None:
    a = spec.anchor
    if a is None:
        return
    if isinstance(a, Explicit):
        if spec.x is None: spec.x = a.x
        if spec.y is None: spec.y = a.y
        return
    if isinstance(a, RightOf):
        b = get_element_bounds(_lookup(a.id, elements, placed))
        if spec.x is None: spec.x = b.x2 + a.gap
        if spec.y is None: spec.y = b.y
        return
    if isinstance(a, Below):
        ref = _lookup(a.id, elements, placed)
        b = get_element_bounds(ref)
        if spec.y is None: spec.y = b.y2 + a.gap
        if spec.x is None:
            ref_cx = ref["x"] + ref.get("width", 0) / 2
            w = spec.width or _TYPE_DEFAULT_SIZE.get(spec.type, (160, 60))[0]
            spec.x = ref_cx - w / 2
        return
    if isinstance(a, Row):
        w = a.width or spec.width or _TYPE_DEFAULT_SIZE.get(spec.type, (160, 60))[0]
        if spec.width is None: spec.width = w
        if a.x_start is not None:
            x_start = a.x_start
        elif a.center_x is not None:
            x_start = a.center_x - (w * a.total + a.gap * (a.total - 1)) / 2
        else:
            x_start = 100.0
        if spec.x is None: spec.x = x_start + a.index * (w + a.gap)
        if spec.y is None: spec.y = a.y
        return
    if isinstance(a, Spine):
        w = spec.width or _TYPE_DEFAULT_SIZE.get(spec.type, (160, 60))[0]
        if spec.width is None: spec.width = w
        if spec.x is None: spec.x = a.x - w / 2
        if spec.y is None: spec.y = a.y_start + a.y_index * a.gap
        return
    if isinstance(a, Near):
        td = _TYPE_DEFAULT_SIZE.get(spec.type, (160, 60))
        w = spec.width or td[0]
        h = spec.height or td[1]
        direction = "right" if a.direction == "any" else a.direction
        existing_ids = {e["id"] for e in elements}
        merged = list(elements) + [pe for pid, pe in placed.items() if pid not in existing_ids]
        cx, cy = _find_near(merged, a.id, direction, a.gap, w, h)
        if spec.x is None: spec.x = cx
        if spec.y is None: spec.y = cy
        if spec.width is None: spec.width = w
        if spec.height is None: spec.height = h
        return
    if isinstance(a, Like):
        props = _resolve_like(elements, placed, a.id)
        if spec.width is None and "width" in props: spec.width = props["width"]
        if spec.height is None and "height" in props: spec.height = props["height"]
        if spec.bg is None and "backgroundColor" in props: spec.bg = props["backgroundColor"]
        if spec.stroke is None and "strokeColor" in props: spec.stroke = props["strokeColor"]
        if spec.stroke_width is None and "strokeWidth" in props: spec.stroke_width = props["strokeWidth"]
        if spec.font_size is None and "fontSize" in props: spec.font_size = props["fontSize"]


def _apply_role(spec: PlaceSpec) -> None:
    if spec.role is None:
        return
    p = ROLE_PRESETS[spec.role.value]
    if p.shape and spec.type == "rectangle":
        spec.type = p.shape
    if spec.width is None and p.width: spec.width = p.width
    if spec.height is None and p.height: spec.height = p.height
    if spec.font_size is None: spec.font_size = p.text_size
    if spec.text_size is None: spec.text_size = p.text_size
    if spec.stroke_width is None: spec.stroke_width = p.stroke_width
    if spec.bg is None and p.bg: spec.bg = p.bg


def _resolve_defaults(spec: PlaceSpec) -> _Resolved:
    text_color = TEXT_SUBORDINATE if spec.role == Role.ANNOTATION else TEXT_BODY
    fs = spec.font_size or spec.text_size or 16
    is_text = spec.type == "text"
    td = _TYPE_DEFAULT_SIZE.get(spec.type, (160, 60))
    bg = spec.bg or "transparent"
    if isinstance(bg, str) and bg in PALETTE:
        bg = PALETTE[bg]
    stroke = spec.stroke or BORDER_COLOR
    if isinstance(stroke, str) and stroke in PALETTE:
        stroke = PALETTE[stroke]
    return _Resolved(
        id=spec.id, type=spec.type, text=spec.text,
        x=float(spec.x or 0.0), y=float(spec.y or 0.0),
        width=float(spec.width if spec.width is not None else (0 if is_text else td[0])),
        height=float(spec.height if spec.height is not None else (0 if is_text else td[1])),
        bg=bg,
        stroke=stroke,
        stroke_width=int(spec.stroke_width if spec.stroke_width is not None else 2),
        font_size=int(fs), text_color=text_color,
    )


def _emit_text(r: _Resolved, idx: str, now: int, free_floating: bool) -> dict[str, Any]:
    text = (r.text or "").replace("\\n", "\n")
    lines = text.split("\n") if text else [""]
    longest = max(lines, key=len) if lines else ""
    tw = len(longest) * r.font_size * 0.62
    th = text_height(max(len(lines), 1), r.font_size)
    if free_floating:
        x, y = r.x, r.y
        align, valign, container_id, elem_id = "left", "top", None, r.id
    else:
        x = r.x + (r.width - tw) / 2
        y = r.y + (r.height - th) / 2
        align, valign, container_id, elem_id = "center", "middle", r.id, f"{r.id}_text"
    return {
        **TEXT_DEFAULTS,
        "type": "text", "id": elem_id,
        "x": x, "y": y, "width": tw, "height": th,
        "text": text, "originalText": text, "rawText": text,
        "fontSize": r.font_size, "fontFamily": DEFAULT_FONT_FAMILY,
        "textAlign": align, "verticalAlign": valign,
        "strokeColor": r.text_color,
        "seed": gen_seed(), "version": 1, "versionNonce": gen_nonce(),
        "index": idx, "updated": now,
        "containerId": container_id,
    }


def _emit_shape(r: _Resolved, idx: str, now: int) -> dict[str, Any]:
    s: dict[str, Any] = {
        **SHAPE_DEFAULTS,
        "type": r.type, "id": r.id,
        "x": r.x, "y": r.y, "width": r.width, "height": r.height,
        "strokeColor": r.stroke, "backgroundColor": r.bg,
        "strokeWidth": r.stroke_width,
        "seed": gen_seed(), "version": 1, "versionNonce": gen_nonce(),
        "index": idx, "updated": now,
    }
    if r.type in ("rectangle", "diamond"):
        s["roundness"] = {"type": 3}
    return s


def _load(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text())
    return {"type": "excalidraw", "version": 2, "source": SOURCE,
            "elements": [], "appState": appstate_defaults(), "files": {}}


def _save(path: Path, data: dict[str, Any]) -> None:
    app = data.setdefault("appState", appstate_defaults())
    for k, v in appstate_defaults().items():
        app.setdefault(k, v)
    data.setdefault("files", {})
    data["source"] = SOURCE
    path.write_text(json.dumps(data, indent="\t"))


def place(filepath: Path, specs: list[PlaceSpec]) -> PlaceResult:
    path = Path(filepath)
    data = _load(path)
    elements: list[dict[str, Any]] = data.setdefault("elements", [])
    existing_ids: set[str] = {e["id"] for e in elements}
    seen: set[str] = set()
    for s in specs:
        if not s.id:
            return PlaceResult(ok=False, errors=["spec missing 'id'"])
        if s.id in existing_ids or s.id in seen:
            return PlaceResult(ok=False, errors=[f"duplicate id {s.id!r}"])
        seen.add(s.id)
    placed: dict[str, dict[str, Any]] = {}
    resolved: list[_Resolved] = []
    for s in specs:
        _apply_role(s)
        try:
            resolve_anchor(s, elements, placed)
        except ValueError as exc:
            return PlaceResult(ok=False, errors=[str(exc)])
        r = _resolve_defaults(s)
        resolved.append(r)
        placed[r.id] = {"id": r.id, "type": r.type, "x": r.x, "y": r.y,
                        "width": r.width, "height": r.height,
                        "backgroundColor": r.bg, "strokeColor": r.stroke,
                        "strokeWidth": r.stroke_width, "fontSize": r.font_size,
                        "isDeleted": False}
    warnings: list[str] = []
    for r in resolved:
        if not r.text or r.type == "text":
            continue
        lines = r.text.split("\n")
        if len(lines) > 2:
            warnings.append(f"{r.id}: {len(lines)}-line label exceeds 2-line max")
        for line in lines:
            if len(line) > 25:
                warnings.append(f"{r.id}: label line {len(line)} chars > 25")
    base = next_index(elements).rstrip("0") or "a"
    if base == "a" and not any(e.get("index") for e in elements):
        base = "a"
    now = now_ms()
    placed_ids: list[str] = []
    counter = 0
    for r in resolved:
        idx_shape = frac_index(base, counter); counter += 1
        if r.type == "text":
            elements.append(_emit_text(r, idx_shape, now, free_floating=True))
        else:
            shape = _emit_shape(r, idx_shape, now)
            elements.append(shape)
            if r.text:
                idx_text = frac_index(base, counter); counter += 1
                t = _emit_text(r, idx_text, now, free_floating=False)
                elements.append(t)
                shape["boundElements"] = [{"id": t["id"], "type": "text"}]
        placed_ids.append(r.id)
    for r in resolved:
        target = next((e for e in elements if e["id"] == r.id and e["type"] != "text"), None)
        if target is None:
            continue
        recenter_text(elements, target, target["x"], target["y"],
                      target.get("width", 0), target.get("height", 0))
    data["elements"] = elements
    _save(path, data)
    return PlaceResult(ok=True, placed_ids=placed_ids, warnings=warnings)


def _cli() -> None:
    p = argparse.ArgumentParser(description="Declarative excalidraw placement")
    p.add_argument("file")
    p.add_argument("json_spec")
    args = p.parse_args()
    raw = json.loads(args.json_spec)
    if not isinstance(raw, list):
        print("ERROR: JSON must be an array", file=sys.stderr)
        sys.exit(1)
    specs = [PlaceSpec.from_dict(d) for d in raw]
    print(place(Path(args.file), specs))


if __name__ == "__main__":
    _cli()
