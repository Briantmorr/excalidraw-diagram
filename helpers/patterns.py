"""High-level diagram patterns built on place + connect primitives.

Each function emits a complete .excalidraw file for a recognised visual rhetoric:
pipeline, cycle, fanout, decision_tree, comparison_grid, weight_map, timeline,
side_by_side, nested, hub_spoke, storyboard, paired_contrast. All use shared
design constants, black borders, tight gaps, and the 0.62 text bbox ratio.
"""

from __future__ import annotations

import argparse
import inspect
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, Union

_HELPERS = Path(__file__).resolve().parent
_SKILL_ROOT = _HELPERS.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from helpers.constants import (  # noqa: E402
    DEFAULT_SIZES, PER_PATTERN, RUBRIC_TARGETS, pattern_target,
)
from helpers.connect import ConnectResult, ConnectSpec, connect  # noqa: E402
from helpers.core import PALETTE, ROLE_PRESETS, emit_free_text, text_width  # noqa: E402
from helpers.place import Explicit, PlaceResult, PlaceSpec, Role, Row, place  # noqa: E402

TEXT_RATIO: float = RUBRIC_TARGETS["text_bbox_ratio"]


@dataclass(frozen=True)
class Spoke:
    id: str
    text: str
    bg: str | None = None


@dataclass(frozen=True)
class Branch:
    id: str
    label: str
    condition: str
    bg: str | None = None


@dataclass(frozen=True)
class GridRow:
    label: str
    values: list[str]


@dataclass(frozen=True)
class WeightedItem:
    id: str
    label: str
    weight: float


@dataclass(frozen=True)
class TimelineItem:
    id: str
    label: str
    annotation: str | None = None
    bg: str | None = None


@dataclass(frozen=True)
class Pair:
    left: str
    right: str
    color: str | None = None


@dataclass(frozen=True)
class ContrastRow:
    """One row of a paired_contrast: two cells held in tension by a label."""
    label: str
    left: str
    right: str
    bg_left: str | None = None
    bg_right: str | None = None


@dataclass(frozen=True)
class Panel:
    id: str
    caption: str
    subtitle: str | None = None
    bg: str | None = None


def _centered_title_x(title: str, center_x: float, font_size: int) -> float:
    return center_x - len(title) * font_size * TEXT_RATIO / 2


def pipeline(
    filepath: Path,
    *,
    title: str,
    stages: list[str],
    color: str = "blue",
    orientation: Literal["horizontal", "vertical"] = "horizontal",
) -> None:
    if len(stages) < 2:
        raise ValueError("pipeline requires >=2 stages")
    targets = PER_PATTERN["pipeline"]
    gap_h, gap_v = targets["gap_h"], targets["gap_v"]
    preset = ROLE_PRESETS["stage"]
    w, h = preset.width, preset.height
    bg = PALETTE.get(color, PALETTE["blue"])
    x_start = 60.0
    title_y = 30.0
    body_y = title_y + 70.0
    title_fs = RUBRIC_TARGETS["font_size_title"]
    n = len(stages)
    if orientation == "horizontal":
        row_w = n * w + (n - 1) * gap_h
        content_cx = x_start + row_w / 2
    else:
        content_cx = x_start + w / 2
    title_x = content_cx - len(title) * title_fs * TEXT_RATIO / 2
    specs: list[PlaceSpec] = [
        PlaceSpec(id="title", role=Role.TITLE, text=title, type="text",
                  anchor=Explicit(x=title_x, y=title_y), font_size=title_fs)
    ]
    for i, label in enumerate(stages):
        if orientation == "horizontal":
            x = x_start + i * (w + gap_h)
            y = body_y
        else:
            x = x_start
            y = body_y + i * (h + gap_v)
        specs.append(PlaceSpec(
            id=f"stage_{i}", role=Role.STAGE, text=label,
            anchor=Explicit(x=x, y=y), width=w, height=h, bg=bg,
        ))
    place(Path(filepath), specs)
    edges = [ConnectSpec(from_id=f"stage_{i}", to_id=f"stage_{i+1}")
             for i in range(len(stages) - 1)]
    connect(Path(filepath), edges)


def _spoke(s: Union[str, dict, Spoke], i: int) -> Spoke:
    if isinstance(s, Spoke):
        return s
    if isinstance(s, str):
        return Spoke(id=f"spoke_{i}", text=s)
    return Spoke(id=s.get("id", f"spoke_{i}"), text=s["text"], bg=s.get("bg"))


def fanout(
    filepath: Path,
    *,
    title: str,
    hub: str,
    spokes: list[Union[str, dict, Spoke]],
    hub_role: str = "hub",
) -> PlaceResult:
    targets = PER_PATTERN["fanout"]
    gap_h, gap_v = targets["gap_h"], targets["gap_v"]
    hub_w, hub_h = DEFAULT_SIZES["hub_rectangle"]
    spoke_w, spoke_h = DEFAULT_SIZES["spoke_rectangle"]
    norm = [_spoke(s, i) for i, s in enumerate(spokes)]
    n = len(norm)
    if n == 0:
        raise ValueError("fanout requires at least one spoke")
    row_w = n * spoke_w + (n - 1) * gap_h
    canvas_w = max(row_w, hub_w)
    margin_x = 40.0
    title_y = 20.0
    title_size = RUBRIC_TARGETS["font_size_title"]
    hub_y = title_y + title_size * 1.4 + 20.0
    spoke_y = hub_y + hub_h + gap_v
    hub_x = margin_x + (canvas_w - hub_w) / 2
    row_x_start = margin_x + (canvas_w - row_w) / 2
    title_w = text_width(title, title_size)
    title_x = margin_x + (canvas_w - title_w) / 2
    specs: list[PlaceSpec] = [
        PlaceSpec(id="title", type="text", text=title, role=Role.TITLE,
                  anchor=Explicit(x=title_x, y=title_y), font_size=title_size),
        PlaceSpec(id="hub", text=hub, role=Role(hub_role),
                  anchor=Explicit(x=hub_x, y=hub_y),
                  width=hub_w, height=hub_h),
    ]
    for i, sp in enumerate(norm):
        specs.append(PlaceSpec(
            id=sp.id, text=sp.text, role=Role.SPOKE,
            anchor=Row(y=spoke_y, index=i, total=n, gap=gap_h,
                       width=spoke_w, x_start=row_x_start),
            width=spoke_w, height=spoke_h,
            bg=sp.bg or PALETTE["blue"],
        ))
    pres = place(Path(filepath), specs)
    if not pres.ok:
        raise RuntimeError(f"place failed: {pres.errors}")
    cspecs = [ConnectSpec(from_id="hub", to_id=sp.id,
                          start_side="bottom", end_side="top")
              for sp in norm]
    connect(Path(filepath), cspecs)
    return pres


def decision_tree(
    filepath: Path, *, title: str, root: str, branches: list[Branch],
) -> None:
    targets = PER_PATTERN["decision_tree"]
    gap_h, gap_v = targets["gap_h"], targets["gap_v"]
    palette_cycle = (
        PALETTE["green"], PALETTE["blue"], PALETTE["cream"], PALETTE["red"],
    )
    diamond_w, diamond_h = DEFAULT_SIZES["diamond"]
    rect_w, rect_h = DEFAULT_SIZES["rectangle"]
    n = len(branches)
    # Widen gaps for >2 branches so outer arrows clear sibling shapes.
    if n > 2:
        gap_h = max(gap_h, rect_w // 2 + 30)
        gap_v = max(gap_v, 110)
    title_h = RUBRIC_TARGETS["font_size_title"]
    row_y = 50 + title_h + 20 + diamond_h + gap_v
    row_total_w = n * rect_w + max(0, n - 1) * gap_h
    canvas_w = max(targets["canvas_max"][0], row_total_w + 80)
    center_x = canvas_w / 2
    diamond_x = center_x - diamond_w / 2
    title_x = _centered_title_x(title, center_x, title_h)

    specs: list[PlaceSpec] = [
        PlaceSpec(id="title", type="text", text=title, role=Role.TITLE,
                  anchor=Explicit(x=title_x, y=20)),
        PlaceSpec(id="root", type="diamond", text=root, role=Role.BRANCH,
                  anchor=Explicit(x=diamond_x, y=70),
                  width=diamond_w, height=diamond_h, bg=PALETTE["yellow"]),
    ]
    for i, br in enumerate(branches):
        bg = br.bg or palette_cycle[i % len(palette_cycle)]
        specs.append(PlaceSpec(
            id=br.id, type="rectangle", text=br.label, role=Role.STEP,
            anchor=Row(y=row_y, index=i, total=n, gap=gap_h,
                       width=rect_w, center_x=center_x),
            width=rect_w, height=rect_h, bg=bg,
        ))
    place(Path(filepath), specs)
    # Straight diagonals from diamond bottom to each branch top.
    # With widened gap_h above, straight arrows clear siblings cleanly;
    # forced elbows would stack in a single horizontal corridor and collide.
    # Dedupe duplicate labels — three "Yes" labels read as noise; the
    # branch nodes carry the disambiguating info (30%/20%/10%).
    from helpers.connect import normalize_label
    seen_labels: set[str] = set()
    arrow_specs: list[ConnectSpec] = []
    for br in branches:
        norm = normalize_label(br.condition) or ""
        keep = norm and norm not in seen_labels
        if keep:
            seen_labels.add(norm)
        arrow_specs.append(ConnectSpec(
            from_id="root", to_id=br.id,
            label=br.condition if keep else None,
            start_side="bottom", end_side="top",
            force_elbow=False,
        ))
    connect(Path(filepath), arrow_specs)


def comparison_grid(
    filepath: Path, *, title: str, columns: list[str], rows: list[GridRow],
) -> PlaceResult:
    targets = pattern_target("comparison_grid")
    canvas_max = targets["canvas_max"]
    n_cols = 1 + len(columns)
    cell_w = min(DEFAULT_SIZES["rectangle"][0], (canvas_max[0] - 60) // n_cols)
    cell_h = DEFAULT_SIZES["rectangle"][1]
    grid_w = cell_w * n_cols
    x0 = 60.0
    title_y = 30.0
    grid_y = title_y + 36.0 + 24.0
    title_x = x0 + (grid_w - text_width(title, RUBRIC_TARGETS["font_size_title"])) / 2
    header_bg = PALETTE["grey"]
    label_bg = PALETTE["silver"]
    body_fs = RUBRIC_TARGETS["font_size_body"]
    sub_fs = RUBRIC_TARGETS["font_size_subordinate"]
    specs: list[PlaceSpec] = [
        PlaceSpec(id="cg_title", type="text", text=title, role=Role.TITLE,
                  anchor=Explicit(x=title_x, y=title_y),
                  font_size=RUBRIC_TARGETS["font_size_title"]),
        PlaceSpec(id="cg_h_0_0", type="rectangle", text="",
                  anchor=Explicit(x=x0, y=grid_y),
                  width=cell_w, height=cell_h, bg=header_bg, stroke_width=2),
    ]
    for ci, col in enumerate(columns):
        specs.append(PlaceSpec(
            id=f"cg_h_0_{ci+1}", type="rectangle", text=col,
            anchor=Explicit(x=x0 + (ci + 1) * cell_w, y=grid_y),
            width=cell_w, height=cell_h, bg=header_bg,
            font_size=sub_fs, stroke_width=2,
        ))
    for ri, row in enumerate(rows):
        ry = grid_y + (ri + 1) * cell_h
        specs.append(PlaceSpec(
            id=f"cg_r_{ri+1}_0", type="rectangle", text=row.label,
            anchor=Explicit(x=x0, y=ry),
            width=cell_w, height=cell_h, bg=label_bg,
            font_size=body_fs, stroke_width=2,
        ))
        for ci in range(len(columns)):
            val = row.values[ci] if ci < len(row.values) else ""
            specs.append(PlaceSpec(
                id=f"cg_r_{ri+1}_{ci+1}", type="rectangle", text=val,
                anchor=Explicit(x=x0 + (ci + 1) * cell_w, y=ry),
                width=cell_w, height=cell_h, bg="transparent",
                font_size=body_fs, stroke_width=2,
            ))
    return place(Path(filepath), specs)


def weight_map(
    filepath: Path, *, title: str, items: list[WeightedItem],
) -> PlaceResult:
    if not items:
        return PlaceResult(ok=False, errors=["weight_map needs at least one item"])
    targets = PER_PATTERN["weight_map"]
    canvas_w, _ = targets["canvas_max"]
    gap_h, gap_v = targets["gap_h"], targets["gap_v"]
    ranked = sorted(items, key=lambda it: it.weight, reverse=True)
    n = len(ranked)
    if n <= 3:
        bands: list[list[WeightedItem]] = [[r] for r in ranked] + [[]] * (3 - n)
    else:
        h_cnt = (n + 2) // 3
        l_cnt = n // 3
        m_cnt = n - h_cnt - l_cnt
        bands = [ranked[:h_cnt], ranked[h_cnt:h_cnt + m_cnt], ranked[h_cnt + m_cnt:]]
    band_specs: list[tuple[str, tuple[int, int], int, str, int]] = [
        ("Heavy", DEFAULT_SIZES["weight_heavy"], 3, PALETTE["grey"], 18),
        ("Medium", (180, 100), 2, PALETTE["blue"], 16),
        ("Light", DEFAULT_SIZES["weight_light"], 1, PALETTE["cream"], 14),
    ]
    label_margin = 90.0
    title_y = 30.0
    cy = title_y + 40.0 + 20.0
    title_x = canvas_w / 2 - len(title) * 28 * TEXT_RATIO / 2
    specs: list[PlaceSpec] = [
        PlaceSpec(id="title", type="text", text=title, role=Role.TITLE,
                  anchor=Explicit(x=title_x, y=title_y), font_size=28),
    ]
    for (label, (w, h), sw, bg, fs), band in zip(band_specs, bands):
        if not band:
            cy += h + gap_v
            continue
        row_w = w * len(band) + gap_h * (len(band) - 1)
        x_start = max(label_margin, (canvas_w + label_margin) / 2 - row_w / 2)
        specs.append(PlaceSpec(
            id=f"label_{label.lower()}", type="text", text=label,
            role=Role.ANNOTATION,
            anchor=Explicit(x=20.0, y=cy + h / 2 - 9),
            font_size=14,
        ))
        for i, it in enumerate(band):
            specs.append(PlaceSpec(
                id=it.id, type="ellipse", text=it.label,
                anchor=Explicit(x=x_start + i * (w + gap_h), y=cy),
                width=w, height=h, bg=bg, stroke_width=sw, font_size=fs,
            ))
        cy += h + gap_v
    return place(Path(filepath), specs)


def timeline(
    filepath: Path,
    *,
    title: str,
    items: list[TimelineItem],
    orientation: Literal["horizontal", "vertical"] = "horizontal",
) -> None:
    if len(items) < 2:
        raise ValueError("timeline needs >=2 items")
    p = PER_PATTERN["timeline"]
    cmax_w, _ = p["canvas_max"]
    palette_seq = (PALETTE["green"], PALETTE["grey"], PALETTE["blue"],
                   PALETTE["yellow"], PALETTE["cream"])
    fs_title = RUBRIC_TARGETS["font_size_title"]
    fs_anno = RUBRIC_TARGETS["font_size_annotation"]
    n = len(items)
    is_h = orientation == "horizontal"
    marker_w, marker_h = (160, 70) if is_h else (180, 60)
    gap_pref = p["gap_h"] if is_h else max(p["gap_v"], 60)
    if is_h:
        gap = min(gap_pref, max(60, (cmax_w - 200 - n * marker_w) // max(n - 1, 1)))
    else:
        gap = gap_pref
    x0, y0 = (100.0, 140.0) if is_h else (200.0, 120.0)
    tw_title = len(title) * fs_title * TEXT_RATIO
    title_x = (x0 + (n * marker_w + (n - 1) * gap - tw_title) / 2) if is_h else (x0 - 80)
    specs: list[PlaceSpec] = [PlaceSpec(
        id="title", type="text", text=title, role=Role.TITLE,
        anchor=Explicit(x=max(20.0, title_x), y=40.0), font_size=fs_title)]
    for i, it in enumerate(items):
        x = x0 + i * (marker_w + gap) if is_h else x0
        y = y0 if is_h else y0 + i * (marker_h + gap)
        specs.append(PlaceSpec(
            id=it.id, type="ellipse", text=it.label,
            anchor=Explicit(x=x, y=y),
            width=marker_w, height=marker_h,
            bg=it.bg or palette_seq[i % len(palette_seq)], font_size=14,
        ))
        if it.annotation:
            tw = len(it.annotation) * fs_anno * TEXT_RATIO
            # Annotations always above (horizontal) or to the right (vertical).
            # Alternating sides reads as zigzag; the eye loses the spine.
            if is_h:
                ay = y - 14 - fs_anno * 1.25
                ax = x + (marker_w - tw) / 2
            else:
                ax = x + marker_w + 24
                ay = y + (marker_h - fs_anno * 1.25) / 2
            specs.append(PlaceSpec(
                id=f"{it.id}_anno", type="text", text=it.annotation,
                role=Role.ANNOTATION,
                anchor=Explicit(x=ax, y=ay), font_size=fs_anno,
            ))
    place(Path(filepath), specs)
    side_a, side_b = ("right", "left") if is_h else ("bottom", "top")
    connect(Path(filepath), [
        ConnectSpec(from_id=items[i].id, to_id=items[i + 1].id,
                    start_side=side_a, end_side=side_b)
        for i in range(n - 1)
    ])


def side_by_side(
    filepath: Path,
    *,
    title: str,
    left_label: str,
    right_label: str,
    pairs: list[Pair],
    dashed_right: bool = False,
) -> None:
    t = PER_PATTERN["side_by_side"]
    gap_h, gap_v = t["gap_h"], t["gap_v"]
    fills = (PALETTE["blue"], PALETTE["green"], PALETTE["yellow"],
             PALETTE["cream"], PALETTE["red"])
    cap = RUBRIC_TARGETS["max_distinct_fills"]
    body_fs = RUBRIC_TARGETS["font_size_body"]
    sub_fs = RUBRIC_TARGETS["font_size_subordinate"]
    title_fs = RUBRIC_TARGETS["font_size_title"]
    hero, sec = (220, 90), (150, 60)
    cx = 450.0
    title_y = 30.0
    header_y = title_y + 50
    rows_y0 = header_y + 50
    specs: list[PlaceSpec] = [
        PlaceSpec(id="title", role=Role.TITLE, text=title,
                  anchor=Explicit(x=_centered_title_x(title, cx, title_fs),
                                  y=title_y),
                  font_size=title_fs),
        PlaceSpec(id="hdr_l", type="text", text=left_label,
                  anchor=Explicit(x=cx - gap_h / 2 - hero[0], y=header_y),
                  font_size=sub_fs),
        PlaceSpec(id="hdr_r", type="text", text=right_label,
                  anchor=Explicit(x=cx + gap_h / 2, y=header_y),
                  font_size=sub_fs),
    ]
    y = rows_y0
    for i, p in enumerate(pairs):
        (w_l, h_l), (w_r, h_r) = ((hero, sec) if i == 0 else (sec, hero))
        row_h = max(h_l, h_r)
        bg = p.color or fills[i % min(len(fills), cap)]
        lx = cx - gap_h / 2 - w_l
        rx = cx + gap_h / 2
        ly = y + (row_h - h_l) / 2
        ry = y + (row_h - h_r) / 2
        specs.append(PlaceSpec(id=f"L{i}", text=p.left,
                               anchor=Explicit(x=lx, y=ly),
                               width=w_l, height=h_l, bg=bg,
                               font_size=body_fs))
        specs.append(PlaceSpec(id=f"R{i}", text=p.right,
                               anchor=Explicit(x=rx, y=ry),
                               width=w_r, height=h_r, bg=bg,
                               font_size=body_fs))
        y += row_h + gap_v
    place(Path(filepath), specs)
    if dashed_right:
        data = json.loads(Path(filepath).read_text())
        ids = {f"R{i}" for i in range(len(pairs))}
        for e in data["elements"]:
            if e.get("id") in ids and e.get("type") != "text":
                e["strokeStyle"] = "dashed"
        Path(filepath).write_text(json.dumps(data, indent=2))


def nested(
    filepath: Path | str,
    *,
    title: str,
    outer: str,
    inner: list[str],
    inner_inner: list[str] | None = None,
) -> None:
    targets = PER_PATTERN.get("nested_container", PER_PATTERN["pipeline"])
    gap_h, gap_v = targets["gap_h"], targets["gap_v"]
    pad, label_band = 40, 44
    inner_w, inner_h = 160, 60
    ii_w, ii_h = 100, 40
    n, nn = len(inner), len(inner_inner or [])
    inner_row_w = n * inner_w + max(n - 1, 0) * gap_h
    ii_row_w = nn * ii_w + max(nn - 1, 0) * gap_h if nn else 0
    cont_w = max(inner_row_w, ii_row_w) + 2 * pad
    cont_h = label_band + inner_h + (gap_v + ii_h if nn else 0) + pad
    ox, oy = 80.0, 120.0
    body_fs = RUBRIC_TARGETS["font_size_body"]
    sub_fs = RUBRIC_TARGETS["font_size_subordinate"]
    specs: list[PlaceSpec] = [
        PlaceSpec(id="nested_title", type="text", text=title, role=Role.TITLE,
                  anchor=Explicit(x=ox, y=oy - 70),
                  font_size=RUBRIC_TARGETS["font_size_title"]),
        PlaceSpec(id="nested_outer", type="rectangle", text=None,
                  anchor=Explicit(x=ox, y=oy), width=cont_w, height=cont_h,
                  bg=None, stroke_width=3),
        PlaceSpec(id="nested_outer_label", type="text", text=outer,
                  anchor=Explicit(x=ox + 16, y=oy + 12),
                  font_size=body_fs + 2),
    ]
    inner_y = oy + label_band
    irx = ox + (cont_w - inner_row_w) / 2
    for i, t in enumerate(inner):
        specs.append(PlaceSpec(
            id=f"nested_inner_{i}", type="rectangle", text=t,
            anchor=Explicit(x=irx + i * (inner_w + gap_h), y=inner_y),
            width=inner_w, height=inner_h, bg=PALETTE["blue"],
            font_size=body_fs))
    if nn:
        iiy = inner_y + inner_h + gap_v
        iix = ox + (cont_w - ii_row_w) / 2
        for j, t in enumerate(inner_inner or []):
            specs.append(PlaceSpec(
                id=f"nested_ii_{j}", type="rectangle", text=t,
                anchor=Explicit(x=iix + j * (ii_w + gap_h), y=iiy),
                width=ii_w, height=ii_h, bg=PALETTE["mint"],
                font_size=sub_fs))
    place(Path(filepath), specs)


def _hs_slug(s: str, i: int) -> str:
    out = "".join(ch for ch in s.lower() if ch.isalnum() or ch == "_")[:24]
    return out or f"n{i}"


def hub_spoke(
    filepath: Path | str,
    *,
    title: str,
    hub: str,
    spokes: list[str],
    with_descriptions: bool = False,
) -> tuple[PlaceResult, ConnectResult]:
    p = Path(filepath)
    if p.exists():
        p.unlink()
    t = PER_PATTERN["hub_spoke"]
    cw, ch = t["canvas_max"]
    hub_w, hub_h = DEFAULT_SIZES["hub_rectangle"]
    sp_w, sp_h = DEFAULT_SIZES["spoke_rectangle"]
    cx = cw / 2
    cy = ch / 2 + 30
    n = max(1, len(spokes))
    rx = max(hub_w / 2 + sp_w / 2 + 100, cw * 0.34)
    ry = max(hub_h / 2 + sp_h / 2 + 80, ch * 0.32)
    hub_id = f"hub_{_hs_slug(hub, 0)}"
    title_w = len(title) * RUBRIC_TARGETS["font_size_title"] * TEXT_RATIO
    specs: list[PlaceSpec] = [
        PlaceSpec(id="title", role=Role.TITLE, text=title,
                  anchor=Explicit(x=cw / 2 - title_w / 2, y=20)),
        PlaceSpec(id=hub_id, role=Role.HUB, text=hub,
                  anchor=Explicit(x=cx - hub_w / 2, y=cy - hub_h / 2)),
    ]
    radials: list[tuple[str, float, float, float]] = []
    for i, label in enumerate(spokes):
        angle = -math.pi / 2 + 2 * math.pi * i / n
        sx = cx + rx * math.cos(angle) - sp_w / 2
        sy = cy + ry * math.sin(angle) - sp_h / 2
        sid = f"spoke_{i}_{_hs_slug(label, i)}"
        radials.append((sid, angle, sx, sy))
        specs.append(PlaceSpec(id=sid, role=Role.SPOKE, text=label,
                               anchor=Explicit(x=sx, y=sy)))
    if with_descriptions:
        ann_fs = RUBRIC_TARGETS["font_size_annotation"]
        for i, (_, angle, x, y) in enumerate(radials):
            text = f"detail {i + 1}"
            ax = x + sp_w / 2 + (sp_w * 0.7) * math.cos(angle) - len(text) * ann_fs * TEXT_RATIO / 2
            ay = y + sp_h / 2 + (sp_h * 0.9) * math.sin(angle) - ann_fs / 2
            specs.append(PlaceSpec(id=f"ann_{i}", role=Role.ANNOTATION, text=text,
                                   anchor=Explicit(x=ax, y=ay)))
    pr = place(p, specs)
    if not pr.ok:
        raise RuntimeError(f"hub_spoke place failed: {pr.errors}")
    cr = connect(p, [ConnectSpec(from_id=hub_id, to_id=sid) for sid, *_ in radials])
    return pr, cr


def paired_contrast(
    filepath: Path,
    *,
    title: str,
    left_label: str,
    right_label: str,
    rows: list[ContrastRow],
    bracket: bool = True,
) -> None:
    """Two columns held in tension by row labels. Each row is one paired
    contrast — left and right cells about the same thing, named by the row
    label. Optional dashed bracket between cells emphasises the tension.

    Use when the prompt is "two truths about X" or "before/after pairs that
    belong together" — comparison_grid is for tabular data, paired_contrast
    is for held tensions.
    """
    if len(rows) < 1:
        raise ValueError("paired_contrast requires >=1 row")
    body_fs = RUBRIC_TARGETS["font_size_body"]
    sub_fs = RUBRIC_TARGETS["font_size_subordinate"]
    title_fs = RUBRIC_TARGETS["font_size_title"]
    cell_w, cell_h = 220, 70
    gap_x = 140  # wide gap so the bracket has room to breathe
    row_label_h = sub_fs * 1.4
    gap_y = 40
    canvas_w = cell_w * 2 + gap_x
    cx = canvas_w / 2
    title_y = 30.0
    header_y = title_y + 50
    rows_y0 = header_y + 50
    fills = (PALETTE["blue"], PALETTE["yellow"], PALETTE["green"], PALETTE["cream"])
    title_w = len(title) * title_fs * TEXT_RATIO
    left_x = cx - gap_x / 2 - cell_w
    right_x = cx + gap_x / 2
    specs: list[PlaceSpec] = [
        PlaceSpec(id="pc_title", role=Role.TITLE, text=title,
                  anchor=Explicit(x=cx - title_w / 2, y=title_y),
                  font_size=title_fs),
        PlaceSpec(id="pc_hdr_l", type="text", text=left_label, role=Role.ANNOTATION,
                  anchor=Explicit(x=left_x + cell_w / 2 - len(left_label) * sub_fs * TEXT_RATIO / 2,
                                  y=header_y),
                  font_size=sub_fs),
        PlaceSpec(id="pc_hdr_r", type="text", text=right_label, role=Role.ANNOTATION,
                  anchor=Explicit(x=right_x + cell_w / 2 - len(right_label) * sub_fs * TEXT_RATIO / 2,
                                  y=header_y),
                  font_size=sub_fs),
    ]
    y = rows_y0
    for i, row in enumerate(rows):
        bg_l = row.bg_left or fills[i % len(fills)]
        bg_r = row.bg_right or bg_l
        # Row label above its row, centered between the two cells.
        label_w = len(row.label) * sub_fs * TEXT_RATIO
        specs.append(PlaceSpec(
            id=f"pc_row_{i}_label", type="text", text=row.label,
            role=Role.ANNOTATION,
            anchor=Explicit(x=cx - label_w / 2, y=y),
            font_size=sub_fs,
        ))
        cell_y = y + row_label_h + 4
        specs.append(PlaceSpec(
            id=f"pc_row_{i}_l", type="rectangle", text=row.left,
            anchor=Explicit(x=left_x, y=cell_y),
            width=cell_w, height=cell_h, bg=bg_l, font_size=body_fs,
        ))
        specs.append(PlaceSpec(
            id=f"pc_row_{i}_r", type="rectangle", text=row.right,
            anchor=Explicit(x=right_x, y=cell_y),
            width=cell_w, height=cell_h, bg=bg_r, font_size=body_fs,
        ))
        y = cell_y + cell_h + gap_y
    place(Path(filepath), specs)
    if bracket:
        edges = [
            ConnectSpec(from_id=f"pc_row_{i}_l", to_id=f"pc_row_{i}_r",
                        start_side="right", end_side="left",
                        style="dashed", stroke_width=1)
            for i in range(len(rows))
        ]
        connect(Path(filepath), edges)


def storyboard(filepath: Path, *, title: str, panels: list[Panel]) -> None:
    if len(panels) < 2:
        raise ValueError("storyboard requires at least 2 panels")
    targets = PER_PATTERN["storyboard"]
    gap_h = targets["gap_h"]
    canvas_w, _ = targets["canvas_max"]
    panel_w, panel_h = 220, 140
    title_y = 30.0
    panel_y = title_y + 70.0
    fills = (PALETTE["green"], PALETTE["cream"], PALETTE["red"],
             PALETTE["blue"], PALETTE["yellow"])
    center_x = canvas_w / 2
    title_fs = RUBRIC_TARGETS["font_size_title"]
    title_w = len(title) * title_fs * TEXT_RATIO
    specs: list[PlaceSpec] = [
        PlaceSpec(id="title", type="text", role=Role.TITLE, text=title,
                  anchor=Explicit(x=center_x - title_w / 2, y=title_y)),
    ]
    for i, p in enumerate(panels):
        text = p.caption if not p.subtitle else f"{p.caption}\n{p.subtitle}"
        specs.append(PlaceSpec(
            id=p.id, type="rectangle", text=text,
            anchor=Row(y=panel_y, index=i, total=len(panels), gap=float(gap_h),
                       width=float(panel_w), center_x=center_x),
            width=float(panel_w), height=float(panel_h),
            bg=p.bg or fills[i % len(fills)],
            font_size=RUBRIC_TARGETS["font_size_body"],
            stroke_width=2,
        ))
    r = place(Path(filepath), specs)
    if not r.ok:
        raise RuntimeError(f"place failed: {r.errors}")
    edges = [
        ConnectSpec(from_id=panels[i].id, to_id=panels[i + 1].id,
                    start_side="right", end_side="left", stroke_width=2)
        for i in range(len(panels) - 1)
    ]
    if edges:
        connect(Path(filepath), edges)


def _cycle_node(n: Union[str, dict, Spoke], i: int) -> Spoke:
    if isinstance(n, Spoke):
        return n
    if isinstance(n, str):
        return Spoke(id=f"node_{i}", text=n)
    return Spoke(id=n.get("id", f"node_{i}"), text=n["text"], bg=n.get("bg"))


def cycle(
    filepath: Path,
    *,
    title: str,
    nodes: list[Union[str, dict, Spoke]],
    center_label: str | None = None,
    color: str = "blue",
    clockwise: bool = True,
) -> PlaceResult:
    """N nodes on a ring, arrows closing the loop — argues 'this repeats'.

    Nodes sit on a circle (uniform ellipses); consecutive arrows flow around the
    ring and the last node closes back to the first. Use for cycles, feedback
    loops, lifecycles — anything where the argument is that the process returns to
    its start. A `pipeline` cannot make this argument; it reads as terminating.
    """
    norm = [_cycle_node(n, i) for i, n in enumerate(nodes)]
    n = len(norm)
    if n < 3:
        raise ValueError("cycle requires >=3 nodes (a loop needs a triangle "
                         "minimum; for 2 items use pipeline or side_by_side)")
    body_fs = RUBRIC_TARGETS["font_size_body"]
    base_w, node_h = DEFAULT_SIZES["ellipse"]
    # Ellipses give ~75% of their width to text (corners are unusable). Size every
    # node to the longest label so nothing spills — uniform across the ring.
    longest = max(text_width(nd.text, body_fs) for nd in norm)
    node_w = max(base_w, longest / 0.72 + 24)
    default_bg = PALETTE.get(color, PALETTE["blue"])
    title_fs = RUBRIC_TARGETS["font_size_title"]
    title_y = 20.0

    # Ring radius: adjacent nodes must not touch. The chord between neighbours is
    # 2*r*sin(pi/n); require it to exceed node_w + gap so boxes clear each other.
    gap = 50.0
    sep = node_w + gap
    radius = max(180.0, sep / (2 * math.sin(math.pi / n)))
    ring_top = title_y + title_fs * 1.4 + 40.0
    cx = radius + node_w / 2 + 40.0
    cy = ring_top + radius + node_h / 2

    # Place nodes clockwise starting at 12 o'clock (-90°).
    specs: list[PlaceSpec] = []
    title_w = text_width(title, title_fs)
    specs.append(PlaceSpec(
        id="title", type="text", role=Role.TITLE, text=title,
        anchor=Explicit(x=cx - title_w / 2, y=title_y), font_size=title_fs))

    direction = 1 if clockwise else -1
    for i, node in enumerate(norm):
        ang = -math.pi / 2 + direction * (2 * math.pi * i / n)
        node_cx = cx + radius * math.cos(ang)
        node_cy = cy + radius * math.sin(ang)
        specs.append(PlaceSpec(
            id=node.id, type="ellipse", text=node.text, role=Role.STEP,
            anchor=Explicit(x=node_cx - node_w / 2, y=node_cy - node_h / 2),
            width=node_w, height=node_h,
            bg=node.bg or default_bg,
            font_size=body_fs))

    if center_label:
        # Center of the ring is only clear when the loop is wide enough that arrows
        # skirt the interior. On a tight triangle (n<=4) the chords cross the middle,
        # so drop the label below the ring as a subtitle instead of over the arrows.
        cl_fs = body_fs
        cl_w = text_width(center_label, cl_fs)
        if n >= 5:
            cl_x, cl_y = cx - cl_w / 2, cy - cl_fs / 2
        else:
            cl_x, cl_y = cx - cl_w / 2, cy + radius + node_h / 2 + 24
        specs.append(PlaceSpec(
            id="center", type="text", role=Role.ANNOTATION, text=center_label,
            anchor=Explicit(x=cl_x, y=cl_y), font_size=cl_fs))

    pres = place(Path(filepath), specs)
    if not pres.ok:
        raise RuntimeError(f"place failed: {pres.errors}")

    # Arrows around the ring, last closing back to first. Let auto-routing pick
    # sides from center-to-center geometry — on a circle each arrow naturally
    # exits toward its neighbor, tracing the ring rather than crossing it.
    edges = [ConnectSpec(from_id=norm[i].id, to_id=norm[(i + 1) % n].id)
             for i in range(n)]
    connect(Path(filepath), edges)
    return pres


PATTERNS: dict[str, Callable[..., Any]] = {
    "pipeline": pipeline,
    "fanout": fanout,
    "decision_tree": decision_tree,
    "comparison_grid": comparison_grid,
    "weight_map": weight_map,
    "timeline": timeline,
    "side_by_side": side_by_side,
    "nested": nested,
    "hub_spoke": hub_spoke,
    "storyboard": storyboard,
    "paired_contrast": paired_contrast,
    "cycle": cycle,
}


# --------------------------------------------------------------------------
# compose — stack multiple patterns vertically on one canvas
# --------------------------------------------------------------------------

COMPOSE_BAND_GAP: int = 80


@dataclass(frozen=True)
class ComposeStep:
    pattern: str
    spec: dict[str, Any]


def _canvas_bottom(filepath: Path) -> float:
    if not filepath.exists():
        return 0.0
    data = json.loads(filepath.read_text())
    bottoms = [
        float(e.get("y", 0)) + float(e.get("height", 0))
        for e in data.get("elements", [])
        if not e.get("isDeleted")
    ]
    return max(bottoms) if bottoms else 0.0


def _shift_new_elements(filepath: Path, baseline_count: int,
                         dy: float, dx: float = 0.0) -> None:
    if dy == 0 and dx == 0:
        return
    data = json.loads(filepath.read_text())
    elements = data.get("elements", [])
    for e in elements[baseline_count:]:
        if "y" in e and dy:
            e["y"] = float(e["y"]) + dy
        if "x" in e and dx:
            e["x"] = float(e["x"]) + dx
        for pt in e.get("points") or []:
            if isinstance(pt, list) and len(pt) >= 2:
                pass  # arrow points are relative to e["x"]/e["y"]; shifting suffices
    filepath.write_text(json.dumps(data, indent="\t"))


def _prefix_new_ids(filepath: Path, baseline_count: int, prefix: str) -> None:
    """Rewrite ids of elements appended after baseline_count to avoid clashes
    when stacking multiple patterns. Updates every reference (containerId,
    boundElements, startBinding/endBinding) consistently."""
    data = json.loads(filepath.read_text())
    elements: list[dict] = data.get("elements", [])
    new_slice = elements[baseline_count:]
    if not new_slice:
        return
    id_map: dict[str, str] = {}
    for e in new_slice:
        old = e.get("id")
        if not old:
            continue
        new_id = f"{prefix}_{old}"
        id_map[old] = new_id
        e["id"] = new_id
    for e in new_slice:
        cid = e.get("containerId")
        if cid in id_map:
            e["containerId"] = id_map[cid]
        for be in e.get("boundElements") or []:
            bid = be.get("id") if isinstance(be, dict) else None
            if bid in id_map:
                be["id"] = id_map[bid]
        for key in ("startBinding", "endBinding"):
            b = e.get(key)
            if isinstance(b, dict):
                tid = b.get("elementId")
                if tid in id_map:
                    b["elementId"] = id_map[tid]
    filepath.write_text(json.dumps(data, indent="\t"))


def _reorder_shapes_before_arrows(filepath: Path) -> None:
    """Enforce skill invariant: every shape appears before any arrow that
    binds to it. compose() appends band-by-band, which interleaves shapes
    with prior bands' arrows — this final pass restabilises the order."""
    data = json.loads(filepath.read_text())
    elements: list[dict] = data.get("elements", [])
    non_arrows = [e for e in elements if e.get("type") != "arrow"]
    arrows = [e for e in elements if e.get("type") == "arrow"]
    data["elements"] = non_arrows + arrows
    # Reassign monotonic indices.
    for i, e in enumerate(data["elements"]):
        hi, lo = divmod(i, 36)
        e["index"] = f"a{_BASE36[hi]}{_BASE36[lo]}" if hi < 36 else f"b{_BASE36[hi - 36]}{_BASE36[lo]}"
    filepath.write_text(json.dumps(data, indent="\t"))


_BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def _band_bbox(elements: list[dict]) -> tuple[float, float, float, float] | None:
    """Bbox of a slice of elements (min_x, min_y, max_x, max_y), or None if empty."""
    live = [e for e in elements if not e.get("isDeleted")
            and e.get("type") not in ("arrow", "text")
            and float(e.get("width", 0) or 0) > 0]
    if not live:
        # fall back to any live element so titles still get a bbox
        live = [e for e in elements if not e.get("isDeleted")]
    if not live:
        return None
    xs = [float(e.get("x", 0)) for e in live]
    ys = [float(e.get("y", 0)) for e in live]
    x2 = [float(e.get("x", 0)) + float(e.get("width", 0) or 0) for e in live]
    y2 = [float(e.get("y", 0)) + float(e.get("height", 0) or 0) for e in live]
    return (min(xs), min(ys), max(x2), max(y2))


def _is_title_text(e: dict) -> bool:
    """Heuristic: free text large enough to be a title (>=22pt) and unanchored."""
    return (e.get("type") == "text"
            and e.get("containerId") is None
            and float(e.get("fontSize", 0) or 0) >= 22)


def _recenter_titles_in_range(elements: list[dict], start: int, end: int) -> None:
    """Center any title-grade free text against the band's body bbox."""
    body = elements[start:end]
    body_shapes = [e for e in body if not e.get("isDeleted")
                   and e.get("type") not in ("arrow", "text")
                   and float(e.get("width", 0) or 0) > 0]
    if not body_shapes:
        return
    cx_body = (min(float(e["x"]) for e in body_shapes)
               + max(float(e["x"]) + float(e["width"]) for e in body_shapes)) / 2
    for e in body:
        if _is_title_text(e):
            tw = float(e.get("width", 0) or 0)
            e["x"] = cx_body - tw / 2


def recenter_titles(filepath: Path) -> None:
    """Public hook: center titles against their content bbox post-layout."""
    data = json.loads(Path(filepath).read_text())
    elements = data.get("elements", [])
    _recenter_titles_in_range(elements, 0, len(elements))
    Path(filepath).write_text(json.dumps(data, indent="\t"))


def _center_compose_bands(filepath: Path, band_ranges: list[tuple[int, int]]) -> None:
    """Shift each band horizontally so all bands share a common content axis.

    band_ranges is a list of (start_idx, end_idx_exclusive) into the elements
    array, one per compose step.
    """
    data = json.loads(filepath.read_text())
    elements: list[dict] = data.get("elements", [])
    bboxes: list[tuple[float, float, float, float] | None] = []
    for start, end in band_ranges:
        bboxes.append(_band_bbox(elements[start:end]))
    valid = [b for b in bboxes if b is not None]
    if not valid:
        return
    # Shared axis = average of band content centers (less sensitive to a
    # single wide band than min-of-min or max-of-max).
    axis = sum((b[0] + b[2]) / 2 for b in valid) / len(valid)
    for (start, end), bbox in zip(band_ranges, bboxes):
        if bbox is None:
            continue
        band_center = (bbox[0] + bbox[2]) / 2
        dx = axis - band_center
        if abs(dx) < 0.5:
            continue
        for e in elements[start:end]:
            if "x" in e:
                e["x"] = float(e["x"]) + dx
    filepath.write_text(json.dumps(data, indent="\t"))


def compose(filepath: Path, steps: list[ComposeStep],
            overall_title: str | None = None) -> None:
    """Stack patterns vertically. Each step appends below the previous bottom.

    Patterns place themselves at their own preferred top-Y; we measure the
    canvas before/after each call, namespace the new ids, shift them down
    to sit below the previous band, then run a final pass to center every
    band on a shared vertical axis.

    `overall_title` (recommended for synthesis jobs) adds a large canvas-level
    heading above all panes stating what the whole explanation argues — distinct
    from, and larger than, each pane's own title.
    """
    path = Path(filepath)
    if path.exists():
        path.unlink()
    band_ranges: list[tuple[int, int]] = []
    for i, step in enumerate(steps):
        fn = PATTERNS.get(step.pattern)
        if fn is None:
            raise ValueError(f"unknown pattern: {step.pattern}")
        prev_bottom = _canvas_bottom(path)
        prev_count = (
            len(json.loads(path.read_text()).get("elements", []))
            if path.exists() else 0
        )
        kwargs = _coerce_kwargs(fn, step.spec)
        fn(path, **kwargs)
        _prefix_new_ids(path, prev_count, f"b{i}")
        new_data = json.loads(path.read_text())
        new_elements = new_data.get("elements", [])[prev_count:]
        if not new_elements:
            continue
        new_top = min(
            (float(e.get("y", 0)) for e in new_elements
             if not e.get("isDeleted")),
            default=0.0,
        )
        target_top = prev_bottom + (COMPOSE_BAND_GAP if prev_bottom > 0 else 0)
        dy = target_top - new_top
        _shift_new_elements(path, prev_count, dy)
        new_count = len(json.loads(path.read_text()).get("elements", []))
        band_ranges.append((prev_count, new_count))
    _center_compose_bands(path, band_ranges)
    # After horizontal centering, recenter each band's title against its
    # own body. Titles tracked the band's old x-axis; the band may have
    # shifted, and the title may have been pattern-laid at a fixed margin.
    data = json.loads(path.read_text())
    elements = data.get("elements", [])
    for start, end in band_ranges:
        _recenter_titles_in_range(elements, start, end)
    path.write_text(json.dumps(data, indent="\t"))

    if overall_title:
        _add_overall_title(path, overall_title)
    _reorder_shapes_before_arrows(path)


def _add_overall_title(filepath: Path, title: str) -> None:
    """Place a large canvas-level heading above all bands, centered on the
    shared content axis, and push every existing element down to make room."""
    data = json.loads(filepath.read_text())
    elements: list[dict] = data.get("elements", [])
    live = [e for e in elements if not e.get("isDeleted")]
    if not live:
        return
    fs = RUBRIC_TARGETS["font_size_title"] + 8  # larger than any pane title
    xs = [float(e.get("x", 0)) for e in live]
    x2 = [float(e.get("x", 0)) + float(e.get("width", 0) or 0) for e in live]
    axis = (min(xs) + max(x2)) / 2
    top = min(float(e.get("y", 0)) for e in live)
    band_gap = 60.0
    title_h = fs * 1.25
    # Push everything down so the heading sits above with a clear gap.
    shift = band_gap + title_h
    for e in elements:
        if "y" in e:
            e["y"] = float(e["y"]) + shift
    tw = text_width(title, fs)
    heading = emit_free_text(
        title, x=axis - tw / 2, y=top, font_size=fs,
        color=RUBRIC_TARGETS["text_color_body"], align="center",
        text_id="overall_title",
    )
    heading["index"] = "a00"
    elements.insert(0, heading)
    filepath.write_text(json.dumps(data, indent="\t"))

_DC_BY_FIELD: dict[str, type] = {
    "spokes": Spoke,
    "branches": Branch,
    "rows": GridRow,
    "items": WeightedItem,
    "panels": Panel,
    "pairs": Pair,
}


def _coerce_item(field_name: str, val: Any, fn_name: str, index: int = 0) -> Any:
    """Coerce a spec dict into its dataclass, tolerating the ergonomic key
    names used in the docs (aliases) and auto-assigning `id` when omitted, so
    the documented one-line examples work verbatim.
    """
    if not isinstance(val, dict):
        return val
    d = dict(val)

    if field_name == "branches":
        # {label(edge), outcome(node)} -> Branch{condition, label}.
        if "outcome" in d:
            d["condition"] = d.get("condition", d.get("label", ""))
            d["label"] = d.pop("outcome")
        d.setdefault("condition", "")
        d.setdefault("id", f"branch_{index}")
        return Branch(**d)

    if field_name == "items" and fn_name == "timeline":
        # `when` is the event marker; the dataclass carries it as `annotation`.
        if "when" in d and "annotation" not in d:
            d["annotation"] = d.pop("when")
        d.setdefault("id", f"t_{index}")
        return TimelineItem(**d)

    if field_name == "items" and fn_name == "weight_map":
        d.setdefault("id", f"w_{index}")
        return WeightedItem(**d)

    if field_name == "rows" and fn_name == "paired_contrast":
        return ContrastRow(**d)

    if field_name == "rows":  # comparison_grid
        if "cells" in d and "values" not in d:
            d["values"] = d.pop("cells")
        return GridRow(**d)

    if field_name == "panels":
        # `sketch`/`caption`/`subtitle` -> Panel{caption, subtitle}.
        if "sketch" in d:
            d.pop("sketch")  # sketch hint is not a rendered field
        d.setdefault("id", f"panel_{index}")
        return Panel(**d)

    if field_name == "spokes":
        d.setdefault("id", f"spoke_{index}")
        return Spoke(**d)

    cls = _DC_BY_FIELD.get(field_name)
    if cls is None:
        return val
    return cls(**d)


def _coerce_kwargs(fn: Callable[..., Any], spec: dict[str, Any]) -> dict[str, Any]:
    sig = inspect.signature(fn)
    out: dict[str, Any] = {}
    for k, v in spec.items():
        if k not in sig.parameters:
            continue
        if isinstance(v, list):
            out[k] = [_coerce_item(k, item, fn.__name__, i) for i, item in enumerate(v)]
        else:
            out[k] = v
    return out


def _cli() -> None:
    p = argparse.ArgumentParser(description="Render a diagram pattern")
    p.add_argument("pattern", choices=sorted(PATTERNS))
    p.add_argument("file")
    p.add_argument("json_spec")
    args = p.parse_args()
    fn = PATTERNS[args.pattern]
    spec = json.loads(args.json_spec)
    if not isinstance(spec, dict):
        print("ERROR: json_spec must be an object", file=sys.stderr)
        sys.exit(1)
    kwargs = _coerce_kwargs(fn, spec)
    result = fn(Path(args.file), **kwargs)
    if result is not None:
        print(result)


if __name__ == "__main__":
    _cli()
