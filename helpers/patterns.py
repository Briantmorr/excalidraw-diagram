"""High-level diagram patterns built on place + connect primitives.

Each function emits a complete .excalidraw file for a recognised visual rhetoric:
pipeline, fanout, decision_tree, comparison_grid, weight_map, timeline,
side_by_side, nested, hub_spoke, storyboard. All use shared rubric targets,
black borders, gold-median gaps, and the v4 0.62 text bbox ratio.
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

from helpers._rubric_targets import (  # noqa: E402
    DEFAULT_SIZES, PER_PATTERN, RUBRIC_TARGETS, pattern_target,
)
from helpers.connect import ConnectResult, ConnectSpec, connect  # noqa: E402
from helpers.core import PALETTE, ROLE_PRESETS, text_width  # noqa: E402
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
    specs: list[PlaceSpec] = [
        PlaceSpec(id="title", role=Role.TITLE, text=title, type="text",
                  anchor=Explicit(x=x_start, y=title_y))
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
    canvas_w, _ = targets["canvas_max"]
    palette_cycle = (
        PALETTE["green"], PALETTE["blue"], PALETTE["cream"], PALETTE["red"],
    )
    diamond_w, diamond_h = DEFAULT_SIZES["diamond"]
    rect_w, rect_h = DEFAULT_SIZES["rectangle"]
    n = len(branches)
    title_h = RUBRIC_TARGETS["font_size_title"]
    row_y = 50 + title_h + 20 + diamond_h + gap_v
    row_total_w = n * rect_w + max(0, n - 1) * gap_h
    center_x = max(canvas_w, row_total_w + 80) / 2
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
    mid = (n - 1) / 2
    connect(Path(filepath), [
        ConnectSpec(from_id="root", to_id=br.id, label=br.condition,
                    start_side="bottom", end_side="top",
                    force_elbow=abs(i - mid) > 0.5)
        for i, br in enumerate(branches)
    ])


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
            if is_h:
                ay = (y + marker_h + 14) if i % 2 == 0 else (y - 14 - fs_anno * 1.25)
                ax = x + (marker_w - tw) / 2
            else:
                ax = (x + marker_w + 24) if i % 2 == 0 else (x - 24 - tw)
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
}

_DC_BY_FIELD: dict[str, type] = {
    "spokes": Spoke,
    "branches": Branch,
    "rows": GridRow,
    "items": WeightedItem,
    "panels": Panel,
    "pairs": Pair,
}


def _coerce_item(field_name: str, val: Any, fn_name: str) -> Any:
    if not isinstance(val, dict):
        return val
    if field_name == "items" and fn_name == "timeline":
        return TimelineItem(**val)
    if field_name == "items" and fn_name == "weight_map":
        return WeightedItem(**val)
    cls = _DC_BY_FIELD.get(field_name)
    if cls is None:
        return val
    return cls(**val)


def _coerce_kwargs(fn: Callable[..., Any], spec: dict[str, Any]) -> dict[str, Any]:
    sig = inspect.signature(fn)
    out: dict[str, Any] = {}
    for k, v in spec.items():
        if k not in sig.parameters:
            continue
        if isinstance(v, list):
            out[k] = [_coerce_item(k, item, fn.__name__) for item in v]
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
