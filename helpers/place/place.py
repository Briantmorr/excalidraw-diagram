#!/usr/bin/env python3
"""Single declarative placement tool.

Unifies the layout primitives that batch_add (``--row-at``, ``--below``) and
add_element (``--near``, ``--like``) expose today into a single per-spec
``anchor`` field, plus role-based defaults for size and style.

CLI
---

    python place.py <file.excalidraw> '<json-array>'

Each spec
    {
        "id":     str,                 # required, unique
        "type":   str,                 # default "rectangle"; "text" emits free-floating text
        "text":   str | None,
        "role":   str | None,          # "stage" | "branch" | "hub" | "spoke" |
                                       # "annotation" | "title" — drives size + style defaults
        "anchor": dict | None,         # see below
        # explicit overrides — any of these win over role/anchor:
        "x", "y", "width", "height", "bg", "stroke", "text_size",
        "stroke_width", "font_size",
    }

Anchor variants
    {"rel": "right_of",  "id": "X", "gap": 25}
    {"rel": "below",     "id": "X", "gap": 25}
    {"rel": "row",       "y": 200, "index": 0, "total": 5,
                         "gap": 25, "width": 200,
                         "x_start": ..., "center_x": ...}        (auto x)
    {"rel": "spine",     "x": 400, "y_index": 0, "gap": 100, "y_start": ...}
    {"rel": "near",      "id": "X", "direction": "right"|"below"|"left"|"above"|"any",
                         "gap": 30}                              (clockwise free-space search)
    {"rel": "like",      "id": "X"}                              (copy size+style of X)
    {"x": ..., "y": ...}                                          (explicit; alias for no anchor)

Output invariants
    - shape-before-arrow ordering preserved
    - monotonic indices (continues from existing max index)
    - recenter pass applied after all placements
    - post-place check_collision invoked
    - all shape borders #000000; arrow color #3a3428; fontFamily 1;
      viewBackgroundColor #ffffff (untouched)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_HELPERS = _HERE.parent
sys.path.insert(0, str(_HELPERS))

from core.excalidraw_core import (  # noqa: E402
    DEFAULT_FONT_FAMILY,
    SHAPE_DEFAULTS,
    TEXT_DEFAULTS,
    detect_frames,
    frac_index,
    gen_nonce,
    gen_seed,
    get_element_bounds,
    next_index,
    now_ms,
    recenter,
    text_height,
    text_width,
)


# ---------------------------------------------------------------------------
# Role-based defaults: size + (sometimes) bg + stroke_width + text_size
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RoleSpec:
    width: float
    height: float
    text_size: int = 14
    stroke_width: int = 2
    bg: str | None = None
    type: str | None = None  # may force a shape type (e.g. title -> text)


ROLE_DEFAULTS: dict[str, RoleSpec] = {
    # Hero / orchestrator-ish: the diagram's anchor.
    "stage":      RoleSpec(width=210, height=80, text_size=18, stroke_width=3,
                           bg="#eae8e4"),
    # Branch / decision node: yellow diamond by convention; bg only.
    "branch":     RoleSpec(width=220, height=120, text_size=16, bg="#fff9db"),
    # Hub at center of a hub-and-spoke; large primary container.
    "hub":        RoleSpec(width=200, height=120, text_size=18, stroke_width=3,
                           bg="#e7f5ff"),
    # Spoke / leaf in a row of siblings.
    "spoke":      RoleSpec(width=160, height=70, text_size=16, bg="#e7f5ff"),
    # Free-floating annotation text (subdued grey).
    "annotation": RoleSpec(width=0, height=0, text_size=12, type="text"),
    # Title text (free-floating, top of canvas).
    "title":      RoleSpec(width=0, height=0, text_size=28, type="text"),
}


# ---------------------------------------------------------------------------
# Anchor resolution
# ---------------------------------------------------------------------------

CLOCKWISE = ["right", "below", "left", "above"]


def _bounds_overlap(ax: float, ay: float, ax2: float, ay2: float,
                    bx: float, by: float, bx2: float, by2: float) -> bool:
    return ax < bx2 and ax2 > bx and ay < by2 and ay2 > by


def _is_occupied(elements: list[dict], x: float, y: float,
                 width: float, height: float,
                 exclude_id: str | None = None,
                 exclude_ids: set[str] | None = None) -> bool:
    """Same hit-test as add_element.is_occupied: arrows expanded to a 30px hitbox."""
    if exclude_ids is None:
        exclude_ids = set()
    pad = 15
    for e in elements:
        if e.get("isDeleted"):
            continue
        if exclude_id and e["id"] == exclude_id:
            continue
        if e["id"] in exclude_ids:
            continue
        if e["type"] == "text":
            continue
        eb = get_element_bounds(e)
        ex, ey, ex2, ey2 = eb["x"], eb["y"], eb["x2"], eb["y2"]
        if e["type"] == "arrow":
            if ey2 - ey < 30:
                ey -= pad
                ey2 += pad
            if ex2 - ex < 30:
                ex -= pad
                ex2 += pad
        if _bounds_overlap(x, y, x + width, y + height, ex, ey, ex2, ey2):
            return True
    return False


def _candidate(bounds: dict, direction: str, gap: float,
               new_w: float, new_h: float) -> tuple[float, float]:
    if direction == "right":
        return bounds["x2"] + gap, bounds["y"]
    if direction == "below":
        return bounds["x"], bounds["y2"] + gap
    if direction == "left":
        return bounds["x"] - gap - new_w, bounds["y"]
    if direction == "above":
        return bounds["x"], bounds["y"] - gap - new_h
    return bounds["x2"] + gap, bounds["y"]


def _find_near(elements: list[dict], near_id: str, direction: str,
               gap: float, new_w: float, new_h: float) -> tuple[float, float]:
    """Clockwise free-space search starting at `direction`. Falls back to
    placing below the lowest element when nothing fits."""
    target = next((e for e in elements if e["id"] == near_id), None)
    if target is None:
        raise ValueError(f"anchor near '{near_id}' not found")
    b = get_element_bounds(target)
    frames = detect_frames(elements)
    skip_ids = {f["id"] for f in frames}

    start_idx = CLOCKWISE.index(direction) if direction in CLOCKWISE else 0
    for i in range(4):
        d = CLOCKWISE[(start_idx + i) % 4]
        cx, cy = _candidate(b, d, gap, new_w, new_h)
        if not _is_occupied(elements, cx, cy, new_w, new_h,
                            exclude_id=near_id, exclude_ids=skip_ids):
            return cx, cy

    # Fallback: below the lowest element.
    max_y2 = 0.0
    for e in elements:
        if e.get("isDeleted"):
            continue
        max_y2 = max(max_y2, e.get("y", 0) + e.get("height", 0))
    return b["x"], max_y2 + gap


def _resolve_like(elements: list[dict], like_id: str) -> dict[str, Any]:
    target = next((e for e in elements if e["id"] == like_id), None)
    if target is None:
        raise ValueError(f"anchor like '{like_id}' not found")
    props: dict[str, Any] = {}
    for k in ("width", "height", "backgroundColor", "strokeColor",
              "strokeWidth", "roughness", "fillStyle"):
        if k in target:
            props[k] = target[k]
    text_el = next((e for e in elements
                    if (e["id"] == f"{like_id}_text"
                        or (e.get("containerId") == like_id and e["type"] == "text"))),
                   None)
    if text_el and "fontSize" in text_el:
        props["fontSize"] = text_el["fontSize"]
    return props


# ---------------------------------------------------------------------------
# Spec normalization
# ---------------------------------------------------------------------------

@dataclass
class ResolvedSpec:
    id: str
    type: str
    text: str | None = None
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    bg: str = "transparent"
    stroke: str = "#000000"
    stroke_width: int = 2
    text_size: int = 14
    extra: dict[str, Any] = field(default_factory=dict)


_TYPE_DEFAULT_SIZE: dict[str, tuple[float, float]] = {
    "rectangle": (160, 70),
    "ellipse":   (140, 80),
    "diamond":   (160, 90),
    "text":      (0, 0),
}


def _apply_role(spec: dict[str, Any]) -> dict[str, Any]:
    role = spec.get("role")
    if not role:
        return spec
    rs = ROLE_DEFAULTS.get(role)
    if rs is None:
        raise ValueError(f"unknown role '{role}' on '{spec.get('id')}'")
    out = dict(spec)
    if rs.type and "type" not in out:
        out["type"] = rs.type
    if rs.width and "width" not in out:
        out["width"] = rs.width
    if rs.height and "height" not in out:
        out["height"] = rs.height
    if "text_size" not in out:
        out["text_size"] = rs.text_size
    if "stroke_width" not in out:
        out["stroke_width"] = rs.stroke_width
    if rs.bg and "bg" not in out:
        out["bg"] = rs.bg
    return out


def _resolve_anchor(spec: dict[str, Any], elements: list[dict],
                    placed_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Mutates spec to set x/y (and width/height for `like`) based on anchor.
    `placed_by_id` lets later specs anchor against earlier ones in the same call."""
    anchor = spec.get("anchor")
    if anchor is None:
        return spec

    # Explicit {x,y} anchor variant.
    if "rel" not in anchor and ("x" in anchor or "y" in anchor):
        if "x" in anchor and "x" not in spec:
            spec["x"] = anchor["x"]
        if "y" in anchor and "y" not in spec:
            spec["y"] = anchor["y"]
        return spec

    rel = anchor.get("rel")

    def _lookup(eid: str) -> dict[str, Any]:
        if eid in placed_by_id:
            return placed_by_id[eid]
        for e in elements:
            if e["id"] == eid:
                return e
        raise ValueError(f"anchor target '{eid}' not found for spec '{spec.get('id')}'")

    if rel == "right_of":
        ref = _lookup(anchor["id"])
        gap = anchor.get("gap", 25)
        b = get_element_bounds(ref)
        spec.setdefault("x", b["x2"] + gap)
        spec.setdefault("y", b["y"])
    elif rel == "below":
        ref = _lookup(anchor["id"])
        gap = anchor.get("gap", 25)
        b = get_element_bounds(ref)
        spec.setdefault("y", b["y2"] + gap)
        # x: caller can supply, else align center with reference if ref has width
        if "x" not in spec:
            ref_cx = ref["x"] + ref.get("width", 0) / 2
            w = spec.get("width") or _TYPE_DEFAULT_SIZE.get(spec.get("type", "rectangle"),
                                                           (160, 70))[0]
            spec["x"] = ref_cx - w / 2
    elif rel == "row":
        # All siblings at the same y, evenly spaced. Uses `index`/`total` so
        # every spec in the row knows its own slot.
        idx = anchor["index"]
        total = anchor["total"]
        gap = anchor.get("gap", 25)
        w = anchor.get("width") or spec.get("width") \
            or _TYPE_DEFAULT_SIZE.get(spec.get("type", "rectangle"), (160, 70))[0]
        if "width" not in spec:
            spec["width"] = w
        # Resolve start_x: explicit x_start, or center_x, or default 100.
        if "x_start" in anchor:
            x_start = anchor["x_start"]
        elif "center_x" in anchor:
            row_w = w * total + gap * (total - 1)
            x_start = anchor["center_x"] - row_w / 2
        else:
            x_start = 100.0
        spec.setdefault("x", x_start + idx * (w + gap))
        spec.setdefault("y", anchor["y"])
    elif rel == "spine":
        # Vertical spine at x=anchor["x"]. y_index counts from top; gap is the
        # vertical gap between consecutive spine slots. y_start anchors slot 0.
        y_start = anchor.get("y_start", 0.0)
        gap = anchor.get("gap", 100)
        y_index = anchor["y_index"]
        y = y_start + y_index * gap
        x_center = anchor["x"]
        w = spec.get("width") or _TYPE_DEFAULT_SIZE.get(spec.get("type", "rectangle"),
                                                       (160, 70))[0]
        if "width" not in spec:
            spec["width"] = w
        spec.setdefault("x", x_center - w / 2)
        spec.setdefault("y", y)
    elif rel == "near":
        ref_id = anchor["id"]
        direction = anchor.get("direction", "right")
        if direction == "any":
            direction = "right"
        gap = anchor.get("gap", 30)
        # Need width/height to search.
        type_default = _TYPE_DEFAULT_SIZE.get(spec.get("type", "rectangle"), (160, 70))
        w = spec.get("width") or type_default[0]
        h = spec.get("height") or type_default[1]
        # Search uses both already-on-canvas elements AND specs placed earlier
        # in this call (so two consecutive `near` calls don't collide).
        search_elements = elements + [e for e in placed_by_id.values()
                                      if e.get("id") not in {x["id"] for x in elements}]
        cx, cy = _find_near(search_elements, ref_id, direction, gap, w, h)
        spec.setdefault("x", cx)
        spec.setdefault("y", cy)
        if "width" not in spec:
            spec["width"] = w
        if "height" not in spec:
            spec["height"] = h
    elif rel == "like":
        props = _resolve_like(elements, anchor["id"])
        # like copies size+style; position must come from elsewhere (explicit x/y
        # or another anchor field — caller's choice).
        if "width" not in spec and "width" in props:
            spec["width"] = props["width"]
        if "height" not in spec and "height" in props:
            spec["height"] = props["height"]
        if "bg" not in spec and "backgroundColor" in props:
            spec["bg"] = props["backgroundColor"]
        if "stroke" not in spec and "strokeColor" in props:
            spec["stroke"] = props["strokeColor"]
        if "stroke_width" not in spec and "strokeWidth" in props:
            spec["stroke_width"] = props["strokeWidth"]
        if "text_size" not in spec and "fontSize" in props:
            spec["text_size"] = props["fontSize"]
    else:
        raise ValueError(f"unknown anchor rel '{rel}' on spec '{spec.get('id')}'")
    return spec


# ---------------------------------------------------------------------------
# Element emission (mirrors batch_add but factored out)
# ---------------------------------------------------------------------------

def _emit_text_elem(spec: ResolvedSpec, idx: str, now: int,
                    free_floating: bool) -> dict[str, Any]:
    text = (spec.text or "").replace("\\n", "\n")
    lines = text.split("\n") if text else [""]
    longest = max(lines, key=len) if lines else ""
    tw = text_width(longest, spec.text_size)
    th = text_height(max(len(lines), 1), spec.text_size)
    if free_floating:
        x = spec.x
        y = spec.y
        align = "left"
        valign = "top"
        stroke = spec.stroke if spec.stroke != "#000000" else "#0a0a0a"
        container_id = None
    else:
        x = spec.x + (spec.width - tw) / 2
        y = spec.y + (spec.height - th) / 2
        align = "center"
        valign = "middle"
        stroke = "#0a0a0a"
        container_id = spec.id
    return {
        **TEXT_DEFAULTS,
        "type": "text",
        "id": f"{spec.id}_text" if not free_floating else spec.id,
        "x": x,
        "y": y,
        "width": tw,
        "height": th,
        "text": text,
        "originalText": text,
        "rawText": text,
        "fontSize": spec.text_size,
        "fontFamily": DEFAULT_FONT_FAMILY,
        "textAlign": align,
        "verticalAlign": valign,
        "strokeColor": stroke,
        "backgroundColor": "transparent",
        "strokeWidth": 1,
        "roughness": 0,
        "seed": gen_seed(),
        "version": 1,
        "versionNonce": gen_nonce(),
        "index": idx,
        "updated": now,
        "containerId": container_id,
        "lineHeight": 1.25,
        "autoResize": True,
    }


def _emit_shape(spec: ResolvedSpec, idx: str, now: int) -> dict[str, Any]:
    shape: dict[str, Any] = {
        **SHAPE_DEFAULTS,
        "type": spec.type,
        "id": spec.id,
        "x": spec.x,
        "y": spec.y,
        "width": spec.width,
        "height": spec.height,
        "strokeColor": spec.stroke,
        "backgroundColor": spec.bg,
        "strokeWidth": spec.stroke_width,
        "seed": gen_seed(),
        "version": 1,
        "versionNonce": gen_nonce(),
        "index": idx,
        "updated": now,
    }
    if spec.type in ("rectangle", "diamond"):
        shape["roundness"] = {"type": 3}
    return shape


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------

def place(filepath: str, specs: list[dict[str, Any]]) -> str:
    """Add elements to <filepath> driven by the declarative spec list."""
    path = Path(filepath)
    if path.exists():
        data = json.loads(path.read_text())
    else:
        data = {
            "type": "excalidraw",
            "version": 2,
            "source": "https://github.com/zsviczian/obsidian-excalidraw-plugin/releases/tag/2.22.3",
            "elements": [],
            "appState": {"viewBackgroundColor": "#ffffff"},
            "files": {},
        }
    elements: list[dict[str, Any]] = data.get("elements", [])
    existing_ids = {e["id"] for e in elements}

    # ---- Validation -------------------------------------------------------
    seen: set[str] = set()
    for s in specs:
        sid = s.get("id")
        if not sid:
            return "ERROR: every spec must have an 'id' field"
        if sid in existing_ids or sid in seen:
            return f"ERROR: element ID '{sid}' already exists"
        seen.add(sid)

    # ---- Resolve role + anchor in order ----------------------------------
    placed_by_id: dict[str, dict[str, Any]] = {}
    resolved: list[ResolvedSpec] = []

    for raw in specs:
        s = _apply_role(dict(raw))
        s.setdefault("type", "rectangle")
        # `like` may set width/height; resolve anchor first so we know geometry.
        s = _resolve_anchor(s, elements, placed_by_id)

        etype = s["type"]
        default_w, default_h = _TYPE_DEFAULT_SIZE.get(etype, (160, 70))
        if etype != "text":
            s.setdefault("width", default_w)
            s.setdefault("height", default_h)
        else:
            s.setdefault("width", 0)
            s.setdefault("height", 0)

        s.setdefault("x", 0.0)
        s.setdefault("y", 0.0)
        s.setdefault("bg", "transparent")
        s.setdefault("stroke", "#000000")
        s.setdefault("stroke_width", 2)
        s.setdefault("text_size", 14 if etype != "text" else 16)

        rspec = ResolvedSpec(
            id=s["id"],
            type=etype,
            text=s.get("text"),
            x=float(s["x"]),
            y=float(s["y"]),
            width=float(s["width"]),
            height=float(s["height"]),
            bg=s["bg"],
            stroke=s["stroke"],
            stroke_width=int(s["stroke_width"]),
            text_size=int(s["text_size"]),
        )
        resolved.append(rspec)
        # Stash a synthetic element so subsequent specs in this batch can
        # anchor against this one (covers `near`/`right_of`/`below` chains).
        placed_by_id[rspec.id] = {
            "id": rspec.id,
            "type": rspec.type,
            "x": rspec.x,
            "y": rspec.y,
            "width": rspec.width,
            "height": rspec.height,
            "isDeleted": False,
        }

    # ---- Label hygiene warnings (mirror batch_add) ------------------------
    warnings: list[str] = []
    for r in resolved:
        if not r.text or r.type == "text":
            continue
        lines = r.text.split("\n")
        if len(lines) > 2:
            warnings.append(f"  WARN: '{r.id}' has {len(lines)}-line label — max 2 lines per shape")
        for line in lines:
            if len(line) > 25:
                warnings.append(f"  WARN: '{r.id}' label line too long ({len(line)} chars)")

    # ---- Emit elements (shapes/text first; arrows are not produced here) -
    # Continue monotonic indices from existing canvas.
    base_idx = next_index(elements)[:-1] or "a"  # strip the trailing 0 from next_index
    # next_index returns last_idx + "0"; we want to use frac_index(last_idx, i)
    # where i increments per added element. Compute the prefix:
    indices = [e.get("index", "") for e in elements if e.get("index")]
    if indices:
        last = sorted(indices)[-1]
    else:
        last = "a"

    now = now_ms()
    added_ids: list[str] = []
    for i, r in enumerate(resolved):
        idx_shape = frac_index(last, i * 2)
        idx_text = frac_index(last, i * 2 + 1)
        if r.type == "text":
            elem = _emit_text_elem(r, idx_shape, now, free_floating=True)
            elements.append(elem)
        else:
            shape = _emit_shape(r, idx_shape, now)
            elements.append(shape)
            if r.text:
                t = _emit_text_elem(r, idx_text, now, free_floating=False)
                elements.append(t)
                shape["boundElements"] = [{"id": t["id"], "type": "text"}]
        added_ids.append(r.id)

    # ---- Recenter pass for any anchor-relocated existing element ---------
    # We didn't move existing elements, so recenter is a no-op here. We still
    # call it in case future variants do (e.g. minimum-arrow-length nudges).
    for r in resolved:
        target = next((e for e in elements if e["id"] == r.id and e["type"] != "text"),
                      None)
        if target is None:
            continue
        recenter(elements, target, target["x"], target["y"],
                 target.get("width", 0), target.get("height", 0))

    # ---- Persist ---------------------------------------------------------
    data["elements"] = elements
    data.setdefault("files", {})
    app = data.setdefault("appState", {})
    app.setdefault("gridSize", None)
    app.setdefault("viewBackgroundColor", "#ffffff")
    app.setdefault("isBindingEnabled", True)
    data["source"] = "https://github.com/zsviczian/obsidian-excalidraw-plugin/releases/tag/2.22.3"
    path.write_text(json.dumps(data, indent="\t"))

    # ---- Post-place collision check -------------------------------------
    abs_path = str(path.resolve())
    cwd_save = os.getcwd()
    os.chdir(str(_HELPERS))
    try:
        from check_collision import check_collisions
        coll_lines: list[str] = []
        for eid in added_ids:
            res = check_collisions(abs_path, eid)
            if "OK" not in res:
                coll_lines.append(f"  {eid}: {res}")
    finally:
        os.chdir(cwd_save)

    msg = f"OK: placed {len(added_ids)}/{len(specs)} elements"
    if warnings:
        msg += "\nLABEL WARNINGS:\n" + "\n".join(warnings)
    if coll_lines:
        msg += "\n" + "\n".join(coll_lines)
    return msg


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Declarative placement of excalidraw elements")
    parser.add_argument("file", help="Path to .excalidraw file (created if missing)")
    parser.add_argument("json_spec", help="JSON array of element specs")
    args = parser.parse_args()

    try:
        specs = json.loads(args.json_spec)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(specs, list):
        print("ERROR: JSON must be an array of element specs", file=sys.stderr)
        sys.exit(1)

    print(place(args.file, specs))


if __name__ == "__main__":
    main()
