#!/usr/bin/env python3
"""Graphviz-driven auto-layout for strict DAGs (v4 primitive).

Public API: GraphSpec, NodeSpec, EdgeSpec, layout_dag.
CLI: layout.py <file> '<json-spec>' [--engine dot|neato|fdp|circo] [--direction DOWN|RIGHT|UP|LEFT]
"""
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from ._rubric_targets import DEFAULT_SIZES, RUBRIC_TARGETS

Engine = Literal["dot", "neato", "fdp", "circo"]
Direction = Literal["DOWN", "RIGHT", "UP", "LEFT"]
NodeType = Literal["rectangle", "ellipse", "diamond"]
Role = Literal["hero", "primary", "secondary"]

GRID = 20
PX_PER_INCH = 72
RANKDIR = {"DOWN": "TB", "RIGHT": "LR", "UP": "BT", "LEFT": "RL"}


@dataclass
class NodeSpec:
    id: str
    text: str
    type: NodeType = "rectangle"
    bg: str | None = None
    role: Role | None = None


@dataclass
class EdgeSpec:
    from_id: str
    to_id: str
    label: str | None = None
    style: str | None = None


@dataclass
class GraphSpec:
    nodes: list[NodeSpec] = field(default_factory=list)
    edges: list[EdgeSpec] = field(default_factory=list)


@dataclass
class _PositionedNode:
    spec: NodeSpec
    x: float
    y: float
    width: int
    height: int
    role: Role


def _snap(v: float) -> int:
    return int(round(v / GRID) * GRID)


def _derive_roles(nodes: list[NodeSpec], edges: list[EdgeSpec]) -> dict[str, Role]:
    in_deg: dict[str, int] = {n.id: 0 for n in nodes}
    out_deg: dict[str, int] = {n.id: 0 for n in nodes}
    for e in edges:
        if e.from_id == e.to_id:
            continue
        if e.from_id in out_deg:
            out_deg[e.from_id] += 1
        if e.to_id in in_deg:
            in_deg[e.to_id] += 1

    roles: dict[str, Role] = {}
    for n in nodes:
        if n.role is not None:
            roles[n.id] = n.role
            continue
        total = in_deg[n.id] + out_deg[n.id]
        if in_deg[n.id] == 0 and out_deg[n.id] > 0:
            roles[n.id] = "hero"
        elif total >= 3:
            roles[n.id] = "hero"
        elif out_deg[n.id] == 0 and in_deg[n.id] > 0:
            roles[n.id] = "secondary"
        else:
            roles[n.id] = "primary"
    return roles


def _size_for(node: NodeSpec, role: Role) -> tuple[int, int]:
    key_role = f"hub_{node.type}" if role == "hero" else f"spoke_{node.type}" if role == "secondary" else node.type
    w, h = DEFAULT_SIZES.get(key_role, DEFAULT_SIZES[node.type])
    return _snap(w), _snap(h)


def _build_dot(nodes: list[NodeSpec], edges: list[EdgeSpec],
               sizes: dict[str, tuple[int, int]],
               engine: Engine, direction: Direction) -> str:
    rankdir = RANKDIR[direction]
    lines = [
        "digraph {",
        f"  rankdir={rankdir};",
        "  ranksep=0.5;",
        "  nodesep=0.4;",
    ]
    if engine in ("neato", "fdp", "circo"):
        lines += ["  overlap=false;", '  sep="+20";']
    lines.append("  node [shape=box];")
    shape_map = {"rectangle": "box", "ellipse": "ellipse", "diamond": "diamond"}
    for n in nodes:
        w, h = sizes[n.id]
        lines.append(
            f'  "{n.id}" [width={w / PX_PER_INCH:.3f} '
            f'height={h / PX_PER_INCH:.3f} shape={shape_map[n.type]} fixedsize=true];'
        )
    for e in edges:
        if e.from_id == e.to_id:
            continue
        lines.append(f'  "{e.from_id}" -> "{e.to_id}";')
    lines.append("}")
    return "\n".join(lines)


def _run_graphviz(dot_src: str, engine: Engine) -> dict[str, Any]:
    proc = subprocess.run(
        [engine, "-Tjson0"], input=dot_src, capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise RuntimeError(f"graphviz {engine} failed: {proc.stderr}")
    return json.loads(proc.stdout)


def _extract_positions(gv: dict[str, Any], sizes: dict[str, tuple[int, int]]
                       ) -> dict[str, tuple[float, float]]:
    bb = [float(x) for x in gv.get("bb", "0,0,100,100").split(",")]
    canvas_h = bb[3]
    out: dict[str, tuple[float, float]] = {}
    for obj in gv.get("objects", []):
        nid = obj.get("name")
        if nid not in sizes:
            continue
        cx_s, cy_s = obj["pos"].split(",")
        cx, cy = float(cx_s), canvas_h - float(cy_s)
        w, h = sizes[nid]
        out[nid] = (cx - w / 2, cy - h / 2)
    return out


def _resolve_overlaps(placed: list[_PositionedNode]) -> None:
    placed.sort(key=lambda p: (p.y, p.x))
    for i, a in enumerate(placed):
        for b in placed[i + 1:]:
            if a.y < b.y + b.height + GRID and b.y < a.y + a.height + GRID:
                if a.x < b.x + b.width + GRID and b.x < a.x + a.width + GRID:
                    b.x = _snap(a.x + a.width + GRID)


def _build_skeleton(placed: list[_PositionedNode], edges: list[EdgeSpec]
                    ) -> list[dict[str, Any]]:
    body_size = RUBRIC_TARGETS["font_size_body"]
    border = RUBRIC_TARGETS["border_color"]
    arrow_color = RUBRIC_TARGETS["arrow_color"]
    skel: list[dict[str, Any]] = []
    valid_ids = {p.spec.id for p in placed}
    for p in placed:
        node_dict: dict[str, Any] = {
            "type": p.spec.type,
            "id": p.spec.id,
            "x": p.x,
            "y": p.y,
            "width": p.width,
            "height": p.height,
            "strokeColor": border,
            "backgroundColor": p.spec.bg or "transparent",
            "label": {"text": p.spec.text, "fontSize": body_size},
        }
        skel.append(node_dict)
    for e in edges:
        if e.from_id == e.to_id:
            continue
        if e.from_id not in valid_ids or e.to_id not in valid_ids:
            continue
        arrow: dict[str, Any] = {
            "type": "arrow",
            "strokeColor": arrow_color,
            "start": {"id": e.from_id},
            "end": {"id": e.to_id},
        }
        if e.label:
            arrow["label"] = {"text": e.label, "fontSize": RUBRIC_TARGETS["font_size_subordinate"]}
        if e.style:
            arrow["strokeStyle"] = e.style
        skel.append(arrow)
    return skel


def _normalize_origin(placed: list[_PositionedNode], origin: tuple[int, int] = (100, 100)) -> None:
    if not placed:
        return
    min_x = min(p.x for p in placed)
    min_y = min(p.y for p in placed)
    ox, oy = origin
    for p in placed:
        p.x = _snap(p.x - min_x + ox)
        p.y = _snap(p.y - min_y + oy)


def layout_dag(spec: GraphSpec, *, engine: Engine = "dot",
               direction: Direction = "DOWN") -> list[dict[str, Any]]:
    if not spec.nodes:
        return []
    roles = _derive_roles(spec.nodes, spec.edges)
    sizes = {n.id: _size_for(n, roles[n.id]) for n in spec.nodes}
    dot_src = _build_dot(spec.nodes, spec.edges, sizes, engine, direction)
    gv = _run_graphviz(dot_src, engine)
    raw = _extract_positions(gv, sizes)
    placed = [
        _PositionedNode(spec=n, x=raw[n.id][0], y=raw[n.id][1],
                        width=sizes[n.id][0], height=sizes[n.id][1], role=roles[n.id])
        for n in spec.nodes if n.id in raw
    ]
    _normalize_origin(placed)
    _resolve_overlaps(placed)
    skeleton = _build_skeleton(placed, spec.edges)
    from . import skeleton_bridge  # local import: keeps tests stub-friendly
    return skeleton_bridge.convert_skeleton(skeleton)


def _spec_from_dict(d: dict[str, Any]) -> GraphSpec:
    nodes = [NodeSpec(
        id=n["id"], text=n.get("text", n["id"]),
        type=n.get("type", "rectangle"), bg=n.get("bg"), role=n.get("role"),
    ) for n in d.get("nodes", [])]
    edges = [EdgeSpec(
        from_id=e.get("from_id", e.get("from")),
        to_id=e.get("to_id", e.get("to")),
        label=e.get("label"), style=e.get("style"),
    ) for e in d.get("edges", [])]
    return GraphSpec(nodes=nodes, edges=edges)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("spec")
    ap.add_argument("--engine", default="dot", choices=["dot", "neato", "fdp", "circo"])
    ap.add_argument("--direction", default="DOWN", choices=["DOWN", "RIGHT", "UP", "LEFT"])
    args = ap.parse_args()
    spec = _spec_from_dict(json.loads(args.spec))
    elements = layout_dag(spec, engine=args.engine, direction=args.direction)
    out = Path(args.file)
    payload = {
        "type": "excalidraw",
        "version": 2,
        "source": "https://github.com/zsviczian/obsidian-excalidraw-plugin/releases/tag/2.22.3",
        "elements": elements,
        "files": {},
        "appState": {
            "gridSize": None,
            "viewBackgroundColor": RUBRIC_TARGETS["background_color"],
            "isBindingEnabled": True,
        },
    }
    out.write_text(json.dumps(payload, indent="\t"))
    print(f"OK: {len(spec.nodes)} nodes, {len(spec.edges)} edges -> {out}")


if __name__ == "__main__":
    main()
