"""v4 validate — all structural / aesthetic / argument checks in one module."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Iterable, Literal

from helpers.constants import RUBRIC_TARGETS

Severity = Literal["FAIL", "WARN", "INFO"]

SHAPE_TYPES: frozenset[str] = frozenset({"rectangle", "ellipse", "diamond"})
DEFAULT_SNAP = 20
SPINE_TOLERANCE = 30
SPINE_MIN_MEMBERS = 3
COLLISION_THRESHOLD = 100.0
TITLE_FS_MIN = 22
TITLE_TOP_BAND_RATIO = 0.25
SHAPE_EDGE_GAP = 30.0
HIERARCHY_RATIO_FLOOR = 1.8
DIVIDER_THICKNESS = 8
MONOCULTURE_RATIO = 0.80
ARROW_PROXIMITY_PX = 24.0
SIZE_TOLERANCE = 0.10
_BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz"


@dataclass(frozen=True)
class Finding:
    severity: Severity
    code: str
    message: str
    element_ids: tuple[str, ...] = ()


@dataclass
class ValidationReport:
    findings: list[Finding] = field(default_factory=list)

    @property
    def fails(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "FAIL"]

    @property
    def warns(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "WARN"]

    @property
    def infos(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "INFO"]

    def ok(self) -> bool:
        return not self.fails


@dataclass
class TightenReport:
    snapped: int = 0
    aligned: int = 0
    bbox_before: tuple[float, float] = (0.0, 0.0)
    bbox_after: tuple[float, float] = (0.0, 0.0)
    reverted: bool = False
    reason: str = ""

    def shrink_pct(self) -> float:
        bw, bh = self.bbox_before
        aw, ah = self.bbox_after
        before = bw * bh
        return 0.0 if before <= 0 else (1.0 - (aw * ah) / before) * 100.0


def _bounds(e: dict) -> tuple[float, float, float, float]:
    x, y = float(e.get("x", 0)), float(e.get("y", 0))
    return (x, y, x + float(e.get("width", 0)), y + float(e.get("height", 0)))


def _overlap(a: tuple[float, float, float, float],
             b: tuple[float, float, float, float]) -> float:
    dx = min(a[2], b[2]) - max(a[0], b[0])
    dy = min(a[3], b[3]) - max(a[1], b[1])
    return 0.0 if dx <= 0 or dy <= 0 else dx * dy


def _live(elements: list[dict]) -> list[dict]:
    return [e for e in elements if not e.get("isDeleted")]


def _canvas_bounds(elements: list[dict]) -> tuple[float, float, float, float] | None:
    active = [e for e in _live(elements)
              if e.get("type") != "text" and float(e.get("width", 0)) > 0]
    if not active:
        return None
    bs = [_bounds(e) for e in active]
    return (min(b[0] for b in bs), min(b[1] for b in bs),
            max(b[2] for b in bs), max(b[3] for b in bs))


def _detect_frames(elements: list[dict]) -> set[str]:
    non_text = [e for e in _live(elements)
                if e.get("type") != "text" and float(e.get("width", 0)) > 0]
    if not non_text:
        return set()
    cb = _canvas_bounds(elements)
    canvas_area = ((cb[2] - cb[0]) * (cb[3] - cb[1])) if cb else 1.0
    frames: set[str] = set()
    for e in _live(elements):
        if e.get("type") != "rectangle":
            continue
        if e.get("backgroundColor") not in (None, "transparent"):
            continue
        eb = _bounds(e)
        e_area = (eb[2] - eb[0]) * (eb[3] - eb[1])
        others = [o for o in non_text if o["id"] != e["id"]]
        if not others:
            continue
        contained = sum(1 for o in others
                        if eb[0] <= float(o.get("x", 0))
                        and eb[1] <= float(o.get("y", 0))
                        and eb[2] >= float(o.get("x", 0)) + float(o.get("width", 0))
                        and eb[3] >= float(o.get("y", 0)) + float(o.get("height", 0)))
        if contained > len(others) * 0.5 or e_area > canvas_area * 0.6:
            frames.add(e["id"])
    return frames


def check_collisions(elements: list[dict], *, target_id: str | None = None,
                     threshold: float = COLLISION_THRESHOLD,
                     ignore_ids: Iterable[str] | None = None) -> list[Finding]:
    skip = _detect_frames(elements) | set(ignore_ids or [])
    # Arrows are excluded: their axis-aligned bounding boxes overlap by construction
    # (siblings fanning from one hub share a tail region; an arrow's bbox always
    # covers its own endpoint shapes). Arrow geometry is checked precisely by
    # check_aesthetics via segment intersection, so bbox collision here only mis-fires.
    pool = [e for e in _live(elements)
            if e.get("type") not in ("arrow", "line")
            and float(e.get("width", 0)) > 0 and float(e.get("height", 0)) > 0
            and e["id"] not in skip]
    shape_ids = {e["id"] for e in pool if e.get("type") != "text"}
    bound_text = {e["id"] for e in pool
                  if e.get("type") == "text" and e.get("containerId") in shape_ids}
    cands = [e for e in pool if e["id"] not in bound_text]

    visual_skip: set[tuple[str, str]] = set()
    for t in cands:
        if t.get("type") != "text":
            continue
        tb = _bounds(t)
        tcx, tcy = (tb[0] + tb[2]) / 2, (tb[1] + tb[3]) / 2
        for s in cands:
            if s["id"] == t["id"] or s.get("type") not in SHAPE_TYPES:
                continue
            sb = _bounds(s)
            sw, sh = sb[2] - sb[0], sb[3] - sb[1]
            if sw <= 0 or sh <= 0 or not (sb[0] <= tcx <= sb[2] and sb[1] <= tcy <= sb[3]):
                continue
            scx, scy = (sb[0] + sb[2]) / 2, (sb[1] + sb[3]) / 2
            if abs(tcx - scx) / sw < 0.3 and abs(tcy - scy) / sh < 0.3:
                visual_skip.add(tuple(sorted((t["id"], s["id"]))))  # type: ignore[arg-type]

    findings: list[Finding] = []

    def report(a_id: str, b_id: str, area: float) -> Finding:
        return Finding("WARN", "COLLISION",
                       f"{a_id} overlaps {b_id} ({area:.0f}px2)", (a_id, b_id))

    if target_id is not None:
        target = next((e for e in cands if e["id"] == target_id), None)
        if target is None:
            return [Finding("FAIL", "TARGET_NOT_FOUND",
                            f"element {target_id!r} not found", (target_id,))]
        tb = _bounds(target)
        for o in cands:
            if o["id"] == target_id:
                continue
            key = tuple(sorted((target_id, o["id"])))
            if key in visual_skip:
                continue
            area = _overlap(tb, _bounds(o))
            if area >= threshold:
                findings.append(report(target_id, o["id"], area))
        return findings

    seen: set[tuple[str, str]] = set()
    for i, a in enumerate(cands):
        ab = _bounds(a)
        for b in cands[i + 1:]:
            key = tuple(sorted((a["id"], b["id"])))
            if key in seen or key in visual_skip:
                continue
            seen.add(key)  # type: ignore[arg-type]
            area = _overlap(ab, _bounds(b))
            if area >= threshold:
                findings.append(report(a["id"], b["id"], area))
    return findings


@dataclass
class _Shape:
    id: str
    type: str
    x: float
    y: float
    width: float
    height: float

    @property
    def area(self) -> float:
        return self.width * self.height


def _meaningful(elements: list[dict]) -> list[_Shape]:
    frames = _detect_frames(elements)
    out: list[_Shape] = []
    for e in _live(elements):
        if e.get("type") not in SHAPE_TYPES or e["id"] in frames:
            continue
        w, h = float(e.get("width", 0)), float(e.get("height", 0))
        if w < DIVIDER_THICKNESS or h < DIVIDER_THICKNESS:
            continue
        out.append(_Shape(e["id"], e["type"], float(e.get("x", 0)),
                          float(e.get("y", 0)), w, h))
    return out


def _is_uniform_row(shapes: list[_Shape]) -> bool:
    if len(shapes) < 3 or len({s.type for s in shapes}) != 1:
        return False
    ys, xs = [s.y for s in shapes], [s.x for s in shapes]
    if not (max(ys) - min(ys) <= 30 or max(xs) - min(xs) <= 30):
        return False
    ws, hs = [s.width for s in shapes], [s.height for s in shapes]
    return max(ws) - min(ws) <= 25 and max(hs) - min(hs) <= 25


def _is_grid(shapes: list[_Shape]) -> bool:
    if len(shapes) < 4:
        return False
    w0, h0 = shapes[0].width, shapes[0].height
    if not all(abs(s.width - w0) < 1 and abs(s.height - h0) < 1 for s in shapes):
        return False
    xs = [round(s.x) for s in shapes]
    ys = [round(s.y) for s in shapes]
    if len(set(xs)) < 2 or len(set(ys)) < 2:
        return False
    rc, cc = Counter(ys), Counter(xs)
    if min(rc.values()) < 2 or min(cc.values()) < 2:
        return False
    return len(shapes) >= 0.6 * len(set(ys)) * len(set(xs))


def check_hierarchy(elements: list[dict]) -> list[Finding]:
    shapes = _meaningful(elements)
    if len(shapes) < 2 or _is_grid(shapes) or _is_uniform_row(shapes):
        return []
    # A closed arrow loop (cycle diagram) argues through the loop, not size —
    # uniform nodes are correct there.
    if _cycle_shapes(elements):
        return []
    areas = [s.area for s in shapes]
    ratio = max(areas) / min(areas)
    if ratio >= HIERARCHY_RATIO_FLOOR:
        return []
    return [Finding("WARN", "HIERARCHY_FLAT",
                    f"area ratio {ratio:.2f}x below floor {HIERARCHY_RATIO_FLOOR}x",
                    tuple(s.id for s in shapes))]


def _arrow_endpoint(arrow: dict, which: str) -> tuple[float, float] | None:
    pts = arrow.get("points") or []
    if not pts:
        return None
    pt = pts[0] if which == "start" else pts[-1]
    if not isinstance(pt, (list, tuple)) or len(pt) < 2:
        return None
    return (float(arrow.get("x", 0)) + float(pt[0]),
            float(arrow.get("y", 0)) + float(pt[1]))


def _nearest_shape(xy: tuple[float, float], shapes: list[dict],
                   max_dist: float) -> str | None:
    best_id, best_d = None, max_dist
    px, py = xy
    for s in shapes:
        b = _bounds(s)
        dx = max(b[0] - px, 0.0, px - b[2])
        dy = max(b[1] - py, 0.0, py - b[3])
        d = math.hypot(dx, dy)
        if d <= best_d:
            best_d, best_id = d, s["id"]
    return best_id


def _arrow_edges(arrows: list[dict], shapes: list[dict]) -> list[tuple[str, str]]:
    sids = {s["id"] for s in shapes}
    edges: list[tuple[str, str]] = []
    for a in arrows:
        sb = a.get("startBinding") or {}
        eb = a.get("endBinding") or {}
        sid = sb.get("elementId") if isinstance(sb, dict) else None
        eid = eb.get("elementId") if isinstance(eb, dict) else None
        if sid not in sids:
            xy = _arrow_endpoint(a, "start")
            sid = _nearest_shape(xy, shapes, ARROW_PROXIMITY_PX) if xy else None
        if eid not in sids:
            xy = _arrow_endpoint(a, "end")
            eid = _nearest_shape(xy, shapes, ARROW_PROXIMITY_PX) if xy else None
        if sid and eid and sid != eid and sid in sids and eid in sids:
            edges.append((sid, eid))
    return edges


def _has_directed_cycle(edges: list[tuple[str, str]]) -> bool:
    """True if the directed arrow graph contains a cycle (a closed loop).

    A closed loop is the whole argument of a `cycle` diagram — uniform nodes and
    flat size hierarchy are intentional there, so the hierarchy/monoculture warns
    must stand down when this is present."""
    adj: dict[str, list[str]] = defaultdict(list)
    for a, b in edges:
        adj[a].append(b)
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {}

    def visit(u: str) -> bool:
        color[u] = GREY
        for v in adj[u]:
            c = color.get(v, WHITE)
            if c == GREY:
                return True
            if c == WHITE and visit(v):
                return True
        color[u] = BLACK
        return False

    return any(color.get(nid, WHITE) == WHITE and visit(nid)
               for nid in list(adj))


def _cycle_shapes(elements: list[dict]) -> bool:
    """Do the meaningful shapes form a closed directed arrow loop?"""
    frames = _detect_frames(elements)
    shapes = [e for e in _live(elements)
              if e.get("type") in SHAPE_TYPES
              and float(e.get("width", 0)) > 0
              and e["id"] not in frames]
    arrows = [e for e in _live(elements) if e.get("type") == "arrow"]
    return _has_directed_cycle(_arrow_edges(arrows, shapes))


def _largest_component(node_ids: set[str], edges: list[tuple[str, str]]) -> int:
    if not node_ids:
        return 0
    adj: dict[str, set[str]] = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    seen: set[str] = set()
    largest = 0
    for n in node_ids:
        if n in seen:
            continue
        stack, size = [n], 0
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            size += 1
            stack.extend(y for y in adj[x] if y not in seen)
        largest = max(largest, size)
    return largest


def check_argument(elements: list[dict]) -> list[Finding]:
    frames = _detect_frames(elements)
    shapes_d = [e for e in _live(elements)
                if e.get("type") in SHAPE_TYPES
                and float(e.get("width", 0)) > 0
                and float(e.get("height", 0)) > 0
                and e["id"] not in frames]
    if len(shapes_d) < 2:
        return []
    arrows = [e for e in _live(elements) if e.get("type") == "arrow"]
    findings: list[Finding] = []

    # A diagram can argue without shape variety or arrow flow when it argues through
    # (a) a true grid — ≥2 rows × ≥2 cols (comparison_grid, paired_contrast),
    # (b) strong size hierarchy — size itself encodes the point (weight_map,
    #     mirrored side_by_side), or
    # (c) containment — uniform boxes inside a container/frame argue "these belong
    #     inside that" (nested).
    # A bare uniform row/column with none of these is the bag-of-rectangles defect
    # and still warns.
    meaningful = _meaningful(elements)
    edges = _arrow_edges(arrows, shapes_d)
    areas = [float(s.get("width", 0)) * float(s.get("height", 0)) for s in shapes_d]
    size_argues = (min(areas) > 0
                   and max(areas) / min(areas) >= HIERARCHY_RATIO_FLOOR)
    has_container = bool(frames)
    # A closed arrow loop is a cycle — the loop is the argument, uniform nodes fine.
    is_cycle = _has_directed_cycle(edges)
    argues_without_variety = (_is_grid(meaningful) or size_argues
                              or has_container or is_cycle)

    counts = Counter(s["type"] for s in shapes_d)
    dom_type, dom_n = counts.most_common(1)[0]
    dom_ratio = dom_n / len(shapes_d)
    span = _largest_component({s["id"] for s in shapes_d}, edges)
    no_flow = len(arrows) < 2 or (span / len(shapes_d)) <= 0.5

    if dom_ratio > MONOCULTURE_RATIO and no_flow and not argues_without_variety:
        findings.append(Finding(
            "WARN", "WEAK_ARGUMENT",
            f"{dom_n}/{len(shapes_d)} are {dom_type} ({dom_ratio:.0%}); "
            f"flow span {span}/{len(shapes_d)}",
            tuple(s["id"] for s in shapes_d)))

    ws = [float(s.get("width", 0)) for s in shapes_d]
    hs = [float(s.get("height", 0)) for s in shapes_d]
    w0, h0 = ws[0], hs[0]
    # Uniform sizes are intentional for pipelines/cycles/timelines (one-shape-per-sequence).
    # Only flag when there's no arrow flow AND no size variation — that's the bag-of-rectangles case.
    if (not arrows and not argues_without_variety
            and w0 > 0 and h0 > 0
            and all(abs(w - w0) / w0 <= SIZE_TOLERANCE and abs(h - h0) / h0 <= SIZE_TOLERANCE
                    for w, h in zip(ws, hs))):
        findings.append(Finding(
            "WARN", "NO_SHAPE_VARIETY",
            f"all {len(shapes_d)} shapes within {int(SIZE_TOLERANCE*100)}% of {w0:.0f}x{h0:.0f} and no arrows",
            tuple(s["id"] for s in shapes_d)))
    return findings


_VERB_RE = re.compile(
    r"\b(is|are|was|were|be|been|has|have|had|do|does|did|can|will|should|would|"
    r"could|may|might|must|makes?|made|runs?|ran|shows?|showed|works?|worked|"
    r"goes|went|flows?|flowed|loops?|looped|branches|branched|becomes?|became|"
    r"deepens?|delivers?|routes?|processes|teaches|argues?|compares?|connects?|"
    r"separates?|transforms?|converts?|sends?|sent|receives?|calls?|triggers?|"
    r"falls?|fell|rises?|rose|grows?|grew|drops?|dropped|means?|meant|"
    r"creates?|created|breaks?|broke|saves?|saved|costs?|cost|needs?|"
    r"requires?|leads?|led|keeps?|kept|holds?|held)\b",
    re.IGNORECASE)


def _free_text(elements: list[dict]) -> list[dict]:
    return [e for e in _live(elements)
            if e.get("type") == "text" and not e.get("containerId")]


def _looks_like_takeaway(text: str) -> bool:
    flat = text.replace("\n", " ").strip()
    if not flat:
        return False
    if len(flat.split()) > 4 and _VERB_RE.search(flat):
        return True
    if ":" in flat and len(flat.split(":", 1)[1].strip().split()) >= 2:
        return True
    if flat.endswith((".", "!", "?")):
        return True
    if re.search(r"\b\d+\s*(x|%|ms|s|min|hrs?|days?|records?|users?|requests?)\b",
                 flat, re.IGNORECASE):
        return True
    return bool(re.search(r"\bfrom\s+\w+\s+to\s+\w+", flat, re.IGNORECASE))


def _is_shape_anchored(text_el: dict, shapes: list[dict]) -> bool:
    tb = _bounds(text_el)
    for s in shapes:
        sb = _bounds(s)
        if min(tb[3], sb[3]) - max(tb[1], sb[1]) <= 0:
            continue
        if max(sb[0] - tb[2], tb[0] - sb[2], 0.0) < SHAPE_EDGE_GAP:
            return True
    return False


def check_title(elements: list[dict]) -> list[Finding]:
    shapes = [e for e in _live(elements)
              if e.get("type") in SHAPE_TYPES and float(e.get("width", 0)) > 0]
    free = _free_text(elements)
    if shapes:
        bs = [_bounds(e) for e in shapes]
        cb = (min(b[0] for b in bs), min(b[1] for b in bs),
              max(b[2] for b in bs), max(b[3] for b in bs))
    elif free:
        bs = [_bounds(e) for e in free]
        cb = (min(b[0] for b in bs), min(b[1] for b in bs),
              max(b[2] for b in bs), max(b[3] for b in bs))
    else:
        return [Finding("FAIL", "NO_TITLE", "empty diagram", ())]
    height = cb[3] - cb[1] or 1.0
    band_y = cb[1] + TITLE_TOP_BAND_RATIO * height
    cands = [t for t in free
             if float(t.get("fontSize", 0) or 0) >= TITLE_FS_MIN
             and float(t.get("y", 0)) <= band_y
             and not _is_shape_anchored(t, shapes)]
    if not cands:
        return [Finding("FAIL", "NO_TITLE",
                        f"no free text fs>={TITLE_FS_MIN} in top "
                        f"{int(TITLE_TOP_BAND_RATIO*100)}% of canvas", ())]
    title = min(cands, key=lambda e: (float(e.get("y", 0)),
                                      -float(e.get("fontSize", 0))))
    text = (title.get("text") or "").strip()
    if not _looks_like_takeaway(text):
        return [Finding("INFO", "TITLE_PATTERN",
                        f"title looks like a topic, not a takeaway: {text!r}",
                        (title["id"],))]
    return []


def check_invariants(elements: list[dict],
                     app_state: dict | None = None) -> list[Finding]:
    findings: list[Finding] = []
    live = _live(elements)
    ids = {e["id"] for e in live}

    indices = [e["index"] for e in live if e.get("index")]
    if indices and any(indices[i] >= indices[i + 1] for i in range(len(indices) - 1)):
        findings.append(Finding("FAIL", "INDEX_NOT_MONOTONIC",
                                "element indices not monotonically increasing", ()))
    for e in live:
        idx = e.get("index")
        if idx is None:
            continue
        if (not isinstance(idx, str) or len(idx) < 3 or not idx[0].isalpha()
                or not all(c in _BASE36 for c in idx[1:])):
            findings.append(Finding("WARN", "INDEX_FORMAT",
                                    f"{e['id']} index {idx!r} not 'a' + base36",
                                    (e["id"],)))

    first_arrow = next((i for i, e in enumerate(live)
                        if e.get("type") == "arrow"), None)
    if first_arrow is not None:
        for e in live[first_arrow + 1:]:
            if e.get("type") in SHAPE_TYPES:
                findings.append(Finding("FAIL", "SHAPE_AFTER_ARROW",
                                        f"{e['id']} ({e.get('type')}) after arrow",
                                        (e["id"],)))
                break

    for a in (e for e in live if e.get("type") == "arrow"):
        sb, eb = a.get("startBinding") or {}, a.get("endBinding") or {}
        sid = sb.get("elementId") if isinstance(sb, dict) else None
        eid = eb.get("elementId") if isinstance(eb, dict) else None
        if sid and eid and sid == eid:
            findings.append(Finding("FAIL", "SELF_LOOP",
                                    f"arrow {a['id']} self-loop on {sid}",
                                    (a["id"], sid)))

    for e in live:
        for be in e.get("boundElements") or []:
            bid = be.get("id") if isinstance(be, dict) else None
            if bid and bid not in ids:
                findings.append(Finding("FAIL", "DANGLING_REF",
                                        f"{e['id']} boundElements -> missing {bid}",
                                        (e["id"], bid)))
        for key in ("startBinding", "endBinding"):
            b = e.get(key)
            if not isinstance(b, dict):
                continue
            tid = b.get("elementId")
            if tid and tid not in ids:
                findings.append(Finding("FAIL", "DANGLING_BINDING",
                                        f"{e['id']}.{key} -> missing {tid}",
                                        (e["id"], tid)))
            if "fixedPoint" in b and b.get("mode") != "orbit":
                findings.append(Finding("FAIL", "FIXEDPOINT_WITHOUT_ORBIT",
                                        f"{e['id']}.{key} fixedPoint without mode=orbit",
                                        (e["id"],)))

    for e in live:
        if e.get("type") != "text":
            continue
        cid = e.get("containerId")
        if cid is not None:
            if cid not in ids:
                findings.append(Finding("FAIL", "PHANTOM_CONTAINER",
                                        f"text {e['id']} containerId {cid!r} missing",
                                        (e["id"],)))
            continue
        for req in ("originalText", "rawText", "autoResize", "lineHeight"):
            if req not in e:
                findings.append(Finding(
                    "WARN", "STANDALONE_TEXT_FIELDS",
                    f"text {e['id']} missing {req} (required for containerId=None)",
                    (e["id"],)))

    border = RUBRIC_TARGETS["border_color"]
    arrow_color = RUBRIC_TARGETS["arrow_color"]
    body_color = RUBRIC_TARGETS["text_color_body"]
    sub_color = RUBRIC_TARGETS["text_color_subordinate"]
    font_family = RUBRIC_TARGETS["font_family"]

    for e in live:
        t = e.get("type")
        sc = e.get("strokeColor")
        if t in SHAPE_TYPES:
            if sc and sc != border:
                findings.append(Finding("WARN", "BORDER_COLOR",
                                        f"{e['id']} strokeColor {sc!r} != {border}",
                                        (e["id"],)))
            if "fontFamily" in e:
                findings.append(Finding("WARN", "SHAPE_HAS_FONTFAMILY",
                                        f"{e['id']} ({t}) carries fontFamily",
                                        (e["id"],)))
        elif t == "arrow":
            if sc and sc != arrow_color:
                findings.append(Finding("WARN", "ARROW_COLOR",
                                        f"{e['id']} strokeColor {sc!r} != {arrow_color}",
                                        (e["id"],)))
        elif t == "text":
            ff = e.get("fontFamily")
            if ff is not None and ff != font_family:
                findings.append(Finding("WARN", "FONT_FAMILY",
                                        f"text {e['id']} fontFamily {ff!r} != {font_family}",
                                        (e["id"],)))
            if sc and sc not in (body_color, sub_color):
                findings.append(Finding("INFO", "TEXT_COLOR",
                                        f"text {e['id']} strokeColor {sc!r} not in hierarchy",
                                        (e["id"],)))

    if app_state is not None:
        if app_state.get("isBindingEnabled") is not True:
            findings.append(Finding("WARN", "BINDING_DISABLED",
                                    "appState.isBindingEnabled not True", ()))
        bg = app_state.get("viewBackgroundColor")
        if bg and bg.lower() != RUBRIC_TARGETS["background_color"]:
            findings.append(Finding("WARN", "BACKGROUND_COLOR",
                                    f"viewBackgroundColor {bg!r} != "
                                    f"{RUBRIC_TARGETS['background_color']}", ()))

    arrow_label_ids = {
        be["id"]
        for e in live if e.get("type") == "arrow"
        for be in (e.get("boundElements") or [])
        if isinstance(be, dict) and be.get("type") == "text"
    }
    for e in live:
        if e.get("type") != "text" or e["id"] not in arrow_label_ids:
            continue
        text = (e.get("text") or "").strip()
        if not text:
            continue
        tokens = text.split()
        if len(tokens) > 1 or len(text) > 8 or any(sep in text for sep in "/|,;:"):
            findings.append(Finding(
                "FAIL", "LABEL_TOO_LONG",
                f"arrow label {text!r} must be ≤1 token, ≤8 chars (no separators)",
                (e["id"],),
            ))
    return findings


def _seg_intersect(p1: tuple[float, float], p2: tuple[float, float],
                   p3: tuple[float, float], p4: tuple[float, float]) -> bool:
    """True if segment p1-p2 crosses segment p3-p4 (proper intersection)."""
    def cross(o: tuple[float, float], a: tuple[float, float],
              b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    d1 = cross(p3, p4, p1)
    d2 = cross(p3, p4, p2)
    d3 = cross(p1, p2, p3)
    d4 = cross(p1, p2, p4)
    return ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
           ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0))


def _arrow_segments(arrow: dict) -> list[tuple[tuple[float, float],
                                                tuple[float, float]]]:
    pts = arrow.get("points") or []
    if len(pts) < 2:
        return []
    ax, ay = float(arrow.get("x", 0)), float(arrow.get("y", 0))
    abs_pts = [(ax + float(p[0]), ay + float(p[1])) for p in pts]
    return list(zip(abs_pts, abs_pts[1:]))


def _seg_hits_rect_strict(p1: tuple[float, float], p2: tuple[float, float],
                           bbox: tuple[float, float, float, float]) -> bool:
    """True if segment crosses any of the 4 rect edges. Endpoints inside count."""
    x1, y1, x2, y2 = bbox
    edges = [((x1, y1), (x2, y1)), ((x2, y1), (x2, y2)),
             ((x2, y2), (x1, y2)), ((x1, y2), (x1, y1))]
    for e1, e2 in edges:
        if _seg_intersect(p1, p2, e1, e2):
            return True
    return False


def _arrow_endpoints_ids(arrow: dict) -> set[str]:
    out: set[str] = set()
    for key in ("startBinding", "endBinding"):
        b = arrow.get(key)
        if isinstance(b, dict) and b.get("elementId"):
            out.add(b["elementId"])
    return out


def check_aesthetics(elements: list[dict]) -> list[Finding]:
    """Geometric / numeric checks that used to require eyes-on review.

    - ARROW_CROSSES_NON_ENDPOINT: arrow segment passes through a shape that
      isn't its source or target.
    - ARROW_CROSSES_ARROW: two arrows visually cross.
    - TEXT_OVERFLOWS_NEIGHBOR: free-text bbox overlaps a non-parent shape.
    - TEXT_EXCEEDS_CONTAINER: bound text wider/taller than its container.
    - TITLE_FONT_TOO_SMALL: title font-size not at least body+8.
    - PALETTE_OVERUSED: more than 5 distinct fill colors in use.
    """
    findings: list[Finding] = []
    live = _live(elements)
    shapes = [e for e in live
              if e.get("type") in SHAPE_TYPES
              and float(e.get("width", 0) or 0) > 0]
    arrows = [e for e in live if e.get("type") == "arrow"]
    free_text = [e for e in live
                 if e.get("type") == "text"
                 and e.get("containerId") is None]
    bound_text = [e for e in live
                  if e.get("type") == "text"
                  and e.get("containerId") is not None]
    by_id = {e["id"]: e for e in live}

    # ARROW_CROSSES_NON_ENDPOINT
    frame_ids_arrow = _detect_frames(elements)
    for a in arrows:
        endpoints = _arrow_endpoints_ids(a)
        for seg_p1, seg_p2 in _arrow_segments(a):
            for s in shapes:
                if s["id"] in endpoints:
                    continue
                if s["id"] in frame_ids_arrow:
                    continue  # arrows naturally cross frame boundaries
                if _seg_hits_rect_strict(seg_p1, seg_p2, _bounds(s)):
                    findings.append(Finding(
                        "FAIL", "ARROW_CROSSES_NON_ENDPOINT",
                        f"arrow {a['id']} crosses non-endpoint shape {s['id']}",
                        (a["id"], s["id"]),
                    ))
                    break  # one report per arrow per offending shape

    # ARROW_CROSSES_TEXT — an arrow shaft slicing through a free-text annotation
    # (not its own label) is unreadable. Shrink the text bbox slightly so an arrow
    # merely grazing the edge doesn't trip it; a real crossing cuts the interior.
    for a in arrows:
        own_labels = {be["id"] for be in (a.get("boundElements") or [])
                      if isinstance(be, dict) and be.get("type") == "text"}
        segs = _arrow_segments(a)
        for t in free_text:
            if t["id"] in own_labels:
                continue
            tb = _bounds(t)
            pad_x = (tb[2] - tb[0]) * 0.15
            pad_y = (tb[3] - tb[1]) * 0.15
            inner = (tb[0] + pad_x, tb[1] + pad_y, tb[2] - pad_x, tb[3] - pad_y)
            if any(_seg_hits_rect_strict(p1, p2, inner) for p1, p2 in segs):
                findings.append(Finding(
                    "FAIL", "ARROW_CROSSES_TEXT",
                    f"arrow {a['id']} crosses free-text {t['id']}",
                    (a["id"], t["id"]),
                ))
                break

    # ARROW_CROSSES_ARROW
    seen_pairs: set[tuple[str, str]] = set()
    for i, a1 in enumerate(arrows):
        for a2 in arrows[i + 1:]:
            key = tuple(sorted((a1["id"], a2["id"])))
            if key in seen_pairs:
                continue
            crossed = False
            for s1, s2 in _arrow_segments(a1):
                for t1, t2 in _arrow_segments(a2):
                    if _seg_intersect(s1, s2, t1, t2):
                        crossed = True
                        break
                if crossed:
                    break
            if crossed:
                seen_pairs.add(key)
                findings.append(Finding(
                    "WARN", "ARROW_CROSSES_ARROW",
                    f"arrows {a1['id']} and {a2['id']} cross",
                    (a1["id"], a2["id"]),
                ))

    # TEXT_OVERFLOWS_NEIGHBOR
    frame_ids = _detect_frames(elements)
    for t in free_text:
        tb = _bounds(t)
        for s in shapes:
            if s["id"] == t.get("containerId"):
                continue
            if s["id"] in frame_ids:
                continue  # frames intentionally enclose other elements
            sb = _bounds(s)
            if _overlap(tb, sb) > 100.0:
                findings.append(Finding(
                    "WARN", "TEXT_OVERFLOWS_NEIGHBOR",
                    f"free-text {t['id']} overlaps shape {s['id']}",
                    (t["id"], s["id"]),
                ))
                break

    # TEXT_EXCEEDS_CONTAINER
    for t in bound_text:
        cid = t.get("containerId")
        parent = by_id.get(cid) if cid else None
        if not parent:
            continue
        tw, th = float(t.get("width", 0)), float(t.get("height", 0))
        pw, ph = float(parent.get("width", 0)), float(parent.get("height", 0))
        if tw > pw + 1 or th > ph + 1:
            findings.append(Finding(
                "WARN", "TEXT_EXCEEDS_CONTAINER",
                f"text {t['id']} ({tw:.0f}x{th:.0f}) larger than "
                f"container {cid} ({pw:.0f}x{ph:.0f})",
                (t["id"], cid or ""),
            ))

    # TITLE_FONT_TOO_SMALL
    title_cands = [t for t in free_text
                   if float(t.get("fontSize", 0) or 0) >= TITLE_FS_MIN]
    body_cands = [t for t in bound_text
                  if float(t.get("fontSize", 0) or 0) > 0]
    if title_cands and body_cands:
        title_fs = max(float(t.get("fontSize", 0)) for t in title_cands)
        body_fs = median([float(t.get("fontSize", 0)) for t in body_cands])
        if title_fs < body_fs + 8:
            findings.append(Finding(
                "WARN", "TITLE_FONT_TOO_SMALL",
                f"title font {title_fs:.0f} not >= body {body_fs:.0f}+8",
                (),
            ))

    # PALETTE_OVERUSED
    fills = [e.get("backgroundColor") for e in shapes
             if e.get("backgroundColor")
             and e.get("backgroundColor") not in ("transparent", "")]
    distinct = {f.lower() for f in fills if f}
    cap = RUBRIC_TARGETS["max_distinct_fills"]
    if len(distinct) > cap:
        findings.append(Finding(
            "INFO", "PALETTE_OVERUSED",
            f"{len(distinct)} distinct fills (cap {cap}): "
            f"{sorted(distinct)}",
            (),
        ))

    # ANNOTATION_TOO_SMALL — free-text annotations under 11pt are illegible
    # at the typical render scale. 12 is the rubric default; 11 leaves room.
    for t in free_text:
        fs = float(t.get("fontSize", 0) or 0)
        if 0 < fs < 11:
            findings.append(Finding(
                "WARN", "ANNOTATION_TOO_SMALL",
                f"text {t['id']} font {fs:.0f}pt < 11pt floor",
                (t["id"],),
            ))

    # TITLE_OVERHANGS — a title wider than the diagram body reads as off-center
    # even when perfectly centered, because it juts past both content edges. The
    # fix is a shorter title or a wider diagram, not re-centering.
    body_shapes = [e for e in shapes]
    if body_shapes and title_cands:
        bx0 = min(_bounds(s)[0] for s in body_shapes)
        bx2 = max(_bounds(s)[2] for s in body_shapes)
        body_w = bx2 - bx0
        title = max(title_cands, key=lambda t: float(t.get("width", 0) or 0))
        tw = float(title.get("width", 0) or 0)
        # A centered title jutting well past both body edges reads as unbalanced.
        # Require both a large ratio AND a large absolute overhang per side, so a
        # normal title over a naturally-narrow body (a weight_map, a decision root)
        # doesn't trip — only a genuinely runaway title does.
        overhang_per_side = (tw - body_w) / 2
        if body_w > 0 and tw > body_w * 1.6 and overhang_per_side > 200:
            findings.append(Finding(
                "WARN", "TITLE_OVERHANGS",
                f"title {title['id']} ({tw:.0f}px) juts {overhang_per_side:.0f}px "
                f"past each edge of the diagram body ({body_w:.0f}px) — "
                f"shorten it or widen the diagram",
                (title["id"],),
            ))

    # COLOR_WORD_IN_SHAPE — a shape whose label names its own fill color
    # ("RED: ..." in a red box) is redundant: the fill already carries the color,
    # so the word is wasted ink. Encode the distinction in the fill, not the text.
    color_texts = {
        "#ffd4d0": {"red"},
        "#e0f4e8": {"green"},
        "#d3f9d8": {"green"},   # mint reads as green
        "#e7f5ff": {"blue"},
        "#fff9db": {"yellow"},
    }
    text_by_container: dict[str, str] = {}
    for t in bound_text:
        cid = t.get("containerId")
        if cid:
            text_by_container[cid] = (t.get("text") or "")
    for s in shapes:
        fill = (s.get("backgroundColor") or "").lower()
        names = color_texts.get(fill)
        if not names:
            continue
        label = text_by_container.get(s["id"], "").lower()
        words = set(re.findall(r"[a-z]+", label))
        if names & words:
            hit = next(iter(names & words))
            findings.append(Finding(
                "WARN", "COLOR_WORD_IN_SHAPE",
                f"shape {s['id']} label names its own fill color ({hit!r}); "
                f"redundant — the fill already carries it",
                (s["id"],),
            ))

    return findings


def check_all(filepath: Path) -> ValidationReport:
    data = json.loads(Path(filepath).read_text())
    elements = data.get("elements", [])
    app_state = data.get("appState")
    rep = ValidationReport()
    rep.findings.extend(check_invariants(elements, app_state))
    rep.findings.extend(check_collisions(elements))
    rep.findings.extend(check_hierarchy(elements))
    rep.findings.extend(check_argument(elements))
    rep.findings.extend(check_title(elements))
    rep.findings.extend(check_aesthetics(elements))
    if data.get("source") is None:
        rep.findings.append(Finding("WARN", "SOURCE_MISSING",
                                    "top-level `source` field absent", ()))
    return rep


def _movable(elements: list[dict]) -> list[dict]:
    frames = _detect_frames(elements)
    return [e for e in _live(elements)
            if e.get("type") in SHAPE_TYPES
            and float(e.get("width", 0)) > 0
            and float(e.get("height", 0)) > 0
            and e["id"] not in frames]


def _shape_pairs(shapes: list[dict]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for i in range(len(shapes)):
        ab = _bounds(shapes[i])
        for j in range(i + 1, len(shapes)):
            bb = _bounds(shapes[j])
            if ab[0] < bb[2] and ab[2] > bb[0] and ab[1] < bb[3] and ab[3] > bb[1]:
                pairs.add(tuple(sorted((shapes[i]["id"], shapes[j]["id"]))))  # type: ignore[arg-type]
    return pairs


def _recenter(elements: list[dict], target: dict, ox: float, oy: float,
              ow: float, oh: float) -> None:
    nx, ny = float(target.get("x", ox)), float(target.get("y", oy))
    nw, nh = float(target.get("width", ow)), float(target.get("height", oh))
    if nx == ox and ny == oy and nw == ow and nh == oh:
        return
    tid = target["id"]
    for e in elements:
        if e.get("type") != "text":
            continue
        if e.get("containerId") == tid:
            tw, th = float(e.get("width", 0)), float(e.get("height", 0))
            if (nw, nh) != (ow, oh):
                e["x"], e["y"] = nx + (nw - tw) / 2, ny + (nh - th) / 2
            else:
                e["x"] = float(e.get("x", 0)) + (nx - ox)
                e["y"] = float(e.get("y", 0)) + (ny - oy)
            e["version"] = e.get("version", 1) + 1
        elif e.get("containerId") is None:
            ex, ey = float(e.get("x", 0)), float(e.get("y", 0))
            ew, eh = float(e.get("width", 0)), float(e.get("height", 0))
            tcx, tcy = ex + ew / 2, ey + eh / 2
            ocx, ocy = ox + ow / 2, oy + oh / 2
            if abs(tcx - ocx) < 30 and abs(tcy - ocy) < 30:
                e["x"], e["y"] = nx + (nw - ew) / 2, ny + (nh - eh) / 2
                e["version"] = e.get("version", 1) + 1


def _try_move(elements: list[dict], shapes: list[dict], shape: dict,
              nx: float, ny: float,
              baseline: set[tuple[str, str]]) -> bool:
    ox, oy = float(shape["x"]), float(shape["y"])
    if nx == ox and ny == oy:
        return False
    ow, oh = float(shape.get("width", 0)), float(shape.get("height", 0))
    shape["x"], shape["y"] = nx, ny
    shape["version"] = shape.get("version", 1) + 1
    _recenter(elements, shape, ox, oy, ow, oh)
    if _shape_pairs(shapes) - baseline:
        shape["x"], shape["y"] = ox, oy
        _recenter(elements, shape, nx, ny, ow, oh)
        return False
    return True


def _bbox_wh(shapes: list[dict]) -> tuple[float, float]:
    if not shapes:
        return (0.0, 0.0)
    bs = [_bounds(s) for s in shapes]
    return (max(b[2] for b in bs) - min(b[0] for b in bs),
            max(b[3] for b in bs) - min(b[1] for b in bs))


def tighten(filepath: Path, *, target_bbox: tuple[int, int] | None = None,
            snap: int = DEFAULT_SNAP, dry_run: bool = False) -> TightenReport:
    path = Path(filepath)
    raw = path.read_text()
    data = json.loads(raw)
    elements = data.get("elements", [])
    shapes = _movable(elements)
    rep = TightenReport()
    if not shapes:
        cb = _canvas_bounds(elements)
        if cb:
            rep.bbox_before = (cb[2] - cb[0], cb[3] - cb[1])
            rep.bbox_after = rep.bbox_before
        return rep

    initial_pairs = _shape_pairs(shapes)
    baseline = set(initial_pairs)
    rep.bbox_before = _bbox_wh(shapes)

    if snap > 0:
        for s in shapes:
            nx = round(float(s["x"]) / snap) * snap
            ny = round(float(s["y"]) / snap) * snap
            if _try_move(elements, shapes, s, nx, ny, baseline):
                rep.snapped += 1
                baseline = _shape_pairs(shapes)

    for axis in ("x", "y"):
        keyed = sorted(
            ((float(s["x"]) + float(s.get("width", 0)) / 2 if axis == "x"
              else float(s["y"]) + float(s.get("height", 0)) / 2, s)
             for s in shapes),
            key=lambda kv: kv[0])
        clusters: list[list[tuple[float, dict]]] = []
        for c, s in keyed:
            if clusters and abs(c - clusters[-1][-1][0]) <= SPINE_TOLERANCE:
                clusters[-1].append((c, s))
            else:
                clusters.append([(c, s)])
        for cl in clusters:
            if len(cl) < SPINE_MIN_MEMBERS:
                continue
            target_c = median(c for c, _ in cl)
            for _, s in cl:
                if axis == "x":
                    nx, ny = target_c - float(s.get("width", 0)) / 2, float(s["y"])
                else:
                    nx, ny = float(s["x"]), target_c - float(s.get("height", 0)) / 2
                if _try_move(elements, shapes, s, nx, ny, baseline):
                    rep.aligned += 1
                    baseline = _shape_pairs(shapes)

    if target_bbox is not None:
        cw, ch = _bbox_wh(shapes)
        if cw > 0 and ch > 0:
            sx, sy = min(1.0, target_bbox[0] / cw), min(1.0, target_bbox[1] / ch)
            if sx < 1.0 or sy < 1.0:
                x1 = min(float(s["x"]) for s in shapes)
                y1 = min(float(s["y"]) for s in shapes)
                for s in shapes:
                    nx = x1 + (float(s["x"]) - x1) * sx
                    ny = y1 + (float(s["y"]) - y1) * sy
                    if snap > 0:
                        nx, ny = round(nx / snap) * snap, round(ny / snap) * snap
                    if _try_move(elements, shapes, s, nx, ny, baseline):
                        baseline = _shape_pairs(shapes)

    rep.bbox_after = _bbox_wh(shapes)
    new_overlaps = _shape_pairs(shapes) - initial_pairs
    if new_overlaps:
        rep.reverted = True
        rep.reason = f"introduced {len(new_overlaps)} new overlap(s)"
        rep.snapped = 0
        rep.aligned = 0
        rep.bbox_after = rep.bbox_before
        if not dry_run:
            path.write_text(raw)
        return rep
    if not dry_run:
        path.write_text(json.dumps(data, indent=2))
    return rep


def _format_finding(f: Finding) -> str:
    ids = f" [{','.join(f.element_ids)}]" if f.element_ids else ""
    return f"{f.severity}:{f.code} — {f.message}{ids}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="validate.py")
    p.add_argument("file", type=Path)
    p.add_argument("--check",
                   choices=["collisions", "hierarchy", "argument", "title",
                            "invariants", "all"],
                   default="all")
    p.add_argument("--tighten", action="store_true")
    p.add_argument("--target-bbox", type=str, default=None)
    p.add_argument("--snap", type=int, default=DEFAULT_SNAP)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    if args.tighten:
        tb: tuple[int, int] | None = None
        if args.target_bbox:
            w_s, h_s = args.target_bbox.lower().split("x", 1)
            tb = (int(w_s), int(h_s))
        rep = tighten(args.file, target_bbox=tb, snap=args.snap, dry_run=args.dry_run)
        if rep.reverted:
            print(f"TIGHTEN: REVERTED ({rep.reason})")
        else:
            bw, bh = rep.bbox_before
            aw, ah = rep.bbox_after
            print(f"TIGHTEN: snapped {rep.snapped}, aligned {rep.aligned}, "
                  f"bbox {bw:.0f}x{bh:.0f} -> {aw:.0f}x{ah:.0f} "
                  f"(shrink {rep.shrink_pct():.1f}%)")
        return 0

    data = json.loads(args.file.read_text())
    elements = data.get("elements", [])
    app_state = data.get("appState")
    findings: list[Finding] = []
    if args.check in ("invariants", "all"):
        findings += check_invariants(elements, app_state)
    if args.check in ("collisions", "all"):
        findings += check_collisions(elements)
    if args.check in ("hierarchy", "all"):
        findings += check_hierarchy(elements)
    if args.check in ("argument", "all"):
        findings += check_argument(elements)
    if args.check in ("title", "all"):
        findings += check_title(elements)
    if not findings:
        print("OK: no findings")
        return 0
    for f in findings:
        print(_format_finding(f))
    return 1 if any(f.severity == "FAIL" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
