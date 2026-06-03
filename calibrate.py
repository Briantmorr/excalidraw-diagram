"""Calibrate rubric targets from the gold test_set_v13.

Reads gold .excalidraw files, computes per-pattern shape stats, gap medians,
area ratios, canvas compactness, font sizes, and color frequencies.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GOLD_DIR = Path(
    "/Users/I523193/Documents/obsidian/work/research/excalidraw/test_set_v13"
)

PATTERN_FROM_FILENAME: dict[str, str] = {
    "t1_architecture_flow": "fanout",
    "t2_decision_tree": "decision_tree",
    "t3_comparison_table": "comparison_grid",
    "t4_emotional_weight_map": "weight_map",
    "t5_conversation_timeline": "timeline",
    "t6_storyboard": "storyboard",
    "t7_sprint_lifecycle": "cycle",
    "t8_composite": "composite",
}


@dataclass
class ShapeRec:
    type: str
    x: float
    y: float
    w: float
    h: float
    fill: str
    stroke: str
    font_size: int | None = None


@dataclass
class FileStats:
    pattern: str
    file: str
    shapes: list[ShapeRec] = field(default_factory=list)
    arrows: list[dict[str, Any]] = field(default_factory=list)
    texts: list[ShapeRec] = field(default_factory=list)
    canvas_w: float = 0
    canvas_h: float = 0


def load(path: Path) -> FileStats:
    data = json.loads(path.read_text())
    pattern = PATTERN_FROM_FILENAME.get(path.stem, "unknown")
    fs = FileStats(pattern=pattern, file=path.stem)
    xs: list[float] = []
    ys: list[float] = []
    for el in data["elements"]:
        if el.get("isDeleted"):
            continue
        t = el["type"]
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        w, h = float(el.get("width", 0)), float(el.get("height", 0))
        rec = ShapeRec(
            type=t,
            x=x,
            y=y,
            w=w,
            h=h,
            fill=el.get("backgroundColor", "transparent"),
            stroke=el.get("strokeColor", "#000000"),
            font_size=el.get("fontSize"),
        )
        xs.extend([x, x + w])
        ys.extend([y, y + h])
        if t == "arrow":
            fs.arrows.append(el)
        elif t == "text":
            fs.texts.append(rec)
        else:
            fs.shapes.append(rec)
    if xs:
        fs.canvas_w = max(xs) - min(xs)
        fs.canvas_h = max(ys) - min(ys)
    return fs


def median(vals: list[float]) -> float:
    return statistics.median(vals) if vals else 0.0


def percentile(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def shape_type_stats(all_shapes: list[ShapeRec]) -> dict[str, dict[str, float]]:
    by_type: dict[str, list[ShapeRec]] = defaultdict(list)
    for s in all_shapes:
        by_type[s.type].append(s)
    out: dict[str, dict[str, float]] = {}
    for t, recs in by_type.items():
        ws = [r.w for r in recs]
        hs = [r.h for r in recs]
        out[t] = {
            "n": len(recs),
            "median_w": median(ws),
            "median_h": median(hs),
            "p25_w": percentile(ws, 0.25),
            "p75_w": percentile(ws, 0.75),
            "p25_h": percentile(hs, 0.25),
            "p75_h": percentile(hs, 0.75),
        }
    return out


def nearest_neighbor_gaps(shapes: list[ShapeRec]) -> tuple[list[float], list[float]]:
    """Return (h_gaps, v_gaps) — pairwise nearest-neighbor edge distances on each axis
    when shapes share approx row/column."""
    h_gaps: list[float] = []
    v_gaps: list[float] = []
    for i, a in enumerate(shapes):
        for b in shapes[i + 1 :]:
            # row-aligned (similar y)
            if abs((a.y + a.h / 2) - (b.y + b.h / 2)) < max(a.h, b.h) * 0.6:
                gap = max(a.x, b.x) - min(a.x + a.w, b.x + b.w)
                if 0 <= gap < 400:
                    h_gaps.append(gap)
            # col-aligned (similar x)
            if abs((a.x + a.w / 2) - (b.x + b.w / 2)) < max(a.w, b.w) * 0.6:
                gap = max(a.y, b.y) - min(a.y + a.h, b.y + b.h)
                if 0 <= gap < 400:
                    v_gaps.append(gap)
    return h_gaps, v_gaps


def area_ratio(shapes: list[ShapeRec]) -> tuple[float, float]:
    areas = [s.w * s.h for s in shapes if s.type not in {"text", "frame", "line"} and s.w * s.h > 0]
    if not areas:
        return 0.0, 0.0
    return max(areas) / min(areas), min(areas)


def title_fontsize(texts: list[ShapeRec], canvas_h: float) -> int:
    """Largest free-floating text in top 25% of canvas."""
    top_y = canvas_h * 0.25
    candidates = [t for t in texts if t.y < top_y and t.font_size]
    if not candidates:
        return 0
    return max(c.font_size or 0 for c in candidates)


def fontsize_distribution(texts: list[ShapeRec]) -> dict[int, int]:
    c: Counter[int] = Counter()
    for t in texts:
        if t.font_size:
            c[t.font_size] += 1
    return dict(c)


def color_freq(shapes: list[ShapeRec]) -> list[tuple[str, int]]:
    c: Counter[str] = Counter()
    for s in shapes:
        if s.fill and s.fill != "transparent":
            c[s.fill] += 1
    return c.most_common(5)


def segments_intersect(
    p1: tuple[float, float], p2: tuple[float, float], rect: tuple[float, float, float, float]
) -> bool:
    """Cohen-Sutherland: does segment p1->p2 cross axis-aligned rect (x,y,w,h)?"""
    x, y, w, h = rect
    INSIDE, LEFT, RIGHT, BOTTOM, TOP = 0, 1, 2, 4, 8

    def code(px: float, py: float) -> int:
        c = INSIDE
        if px < x:
            c |= LEFT
        elif px > x + w:
            c |= RIGHT
        if py < y:
            c |= BOTTOM
        elif py > y + h:
            c |= TOP
        return c

    x1, y1 = p1
    x2, y2 = p2
    c1, c2 = code(x1, y1), code(x2, y2)
    while True:
        if not (c1 | c2):
            return True
        if c1 & c2:
            return False
        co = c1 or c2
        if co & TOP:
            xi = x1 + (x2 - x1) * (y + h - y1) / (y2 - y1) if y2 != y1 else x1
            yi = y + h
        elif co & BOTTOM:
            xi = x1 + (x2 - x1) * (y - y1) / (y2 - y1) if y2 != y1 else x1
            yi = y
        elif co & RIGHT:
            yi = y1 + (y2 - y1) * (x + w - x1) / (x2 - x1) if x2 != x1 else y1
            xi = x + w
        elif co & LEFT:
            yi = y1 + (y2 - y1) * (x - x1) / (x2 - x1) if x2 != x1 else y1
            xi = x
        else:
            return False
        if co == c1:
            x1, y1 = xi, yi
            c1 = code(x1, y1)
        else:
            x2, y2 = xi, yi
            c2 = code(x2, y2)


def arrow_stats(arrows: list[dict[str, Any]], shapes: list[ShapeRec]) -> dict[str, float]:
    if not arrows:
        return {"n": 0, "median_len": 0.0, "frac_labeled": 0.0, "frac_crossing": 0.0}
    lengths: list[float] = []
    labeled = 0
    crossing = 0
    for a in arrows:
        pts = a.get("points") or []
        if len(pts) < 2:
            continue
        x0, y0 = a.get("x", 0), a.get("y", 0)
        sx, sy = x0 + pts[0][0], y0 + pts[0][1]
        ex, ey = x0 + pts[-1][0], y0 + pts[-1][1]
        lengths.append(((ex - sx) ** 2 + (ey - sy) ** 2) ** 0.5)
        if a.get("boundElements"):
            labeled += 1
        for s in shapes:
            if s.type == "text":
                continue
            if segments_intersect((sx, sy), (ex, ey), (s.x + 2, s.y + 2, s.w - 4, s.h - 4)):
                crossing += 1
                break
    n = len(arrows)
    return {
        "n": n,
        "median_len": median(lengths),
        "frac_labeled": labeled / n if n else 0.0,
        "frac_crossing": crossing / n if n else 0.0,
    }


def main() -> None:
    files = sorted(GOLD_DIR.glob("*.excalidraw"))
    all_stats: list[FileStats] = [load(p) for p in files]
    all_shapes: list[ShapeRec] = []
    for fs in all_stats:
        all_shapes.extend(fs.shapes)

    print("=" * 80)
    print("PER-SHAPE-TYPE STATS (across full gold set)")
    print("=" * 80)
    for t, st in shape_type_stats(all_shapes).items():
        print(
            f"  {t:12s} n={int(st['n']):3d}  w_med={st['median_w']:6.1f} "
            f"[{st['p25_w']:.0f}-{st['p75_w']:.0f}]  "
            f"h_med={st['median_h']:6.1f} [{st['p25_h']:.0f}-{st['p75_h']:.0f}]"
        )

    print()
    print("=" * 80)
    print("PER-FILE / PER-PATTERN STATS")
    print("=" * 80)
    for fs in all_stats:
        h_gaps, v_gaps = nearest_neighbor_gaps(fs.shapes)
        ar_max, _ = area_ratio(fs.shapes)
        total_shape_area = sum(s.w * s.h for s in fs.shapes)
        canvas_area = fs.canvas_w * fs.canvas_h or 1
        compactness = total_shape_area / canvas_area
        title_fs = title_fontsize(fs.texts, fs.canvas_h)
        font_dist = fontsize_distribution(fs.texts)
        colors = color_freq(fs.shapes)
        astats = arrow_stats(fs.arrows, fs.shapes)
        print(f"\n[{fs.file}] pattern={fs.pattern}")
        print(f"  canvas: {fs.canvas_w:.0f} x {fs.canvas_h:.0f}  compactness={compactness:.3f}")
        print(f"  shapes={len(fs.shapes)}  arrows={len(fs.arrows)}  texts={len(fs.texts)}")
        print(
            f"  h_gap median={median(h_gaps):.0f}  v_gap median={median(v_gaps):.0f}  "
            f"area_ratio_max={ar_max:.2f}"
        )
        print(f"  title_fs={title_fs}  font_dist={font_dist}")
        print(f"  top_colors={colors}")
        print(
            f"  arrows: n={int(astats['n'])} median_len={astats['median_len']:.0f} "
            f"frac_labeled={astats['frac_labeled']:.2f} frac_crossing={astats['frac_crossing']:.2f}"
        )

    print()
    print("=" * 80)
    print("AGGREGATE COLOR USAGE (full gold)")
    print("=" * 80)
    cc: Counter[str] = Counter()
    for s in all_shapes:
        if s.fill and s.fill != "transparent":
            cc[s.fill] += 1
    for color, n in cc.most_common(15):
        print(f"  {color}: {n}")


if __name__ == "__main__":
    main()
