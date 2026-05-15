#!/usr/bin/env python3
"""
Generate a positioned excalidraw diagram using graphviz for layout and
the official Excalidraw convertToExcalidrawElements API for element finalization.

Combines:
- Graphviz: positions nodes optimally (Sugiyama, force-directed, etc.)
- Excalidraw API: proper text sizing, arrow bindings, container auto-fit

Usage:
    python3 layout_graph_native.py output.excalidraw --spec '{
      "nodes": [{"id": "a", "text": "Service A", "type": "rectangle", "bg": "#d4e8ff"}],
      "edges": [{"from": "a", "to": "b", "label": "REST"}]
    }' --engine dot --direction DOWN
"""

import json
import argparse
import subprocess
import sys
from pathlib import Path

from skeleton_to_elements import convert_skeleton


PX_PER_INCH = 72
GRID = 20

TYPE_DEFAULTS = {
    "rectangle": (180, 80),
    "ellipse": (180, 80),
    "diamond": (180, 100),
}


def snap(v: float) -> float:
    return round(v / GRID) * GRID


def build_dot_source(node_map: dict, edges: list, engine: str, direction: str) -> str:
    rankdir = {"DOWN": "TB", "RIGHT": "LR", "UP": "BT", "LEFT": "RL"}.get(direction, "TB")
    lines = [f"digraph {{", f"  rankdir={rankdir};", "  ranksep=0.6;", "  nodesep=0.5;"]

    if engine in ("neato", "fdp", "sfdp", "twopi", "circo"):
        lines.append("  overlap=false;")
        lines.append('  sep="+25";')

    lines.append("  node [shape=box];")

    for nid, info in node_map.items():
        w_in = info["width"] / PX_PER_INCH
        h_in = info["height"] / PX_PER_INCH
        shape = {"rectangle": "box", "ellipse": "ellipse", "diamond": "diamond"}.get(info["type"], "box")
        lines.append(f'  "{nid}" [width={w_in:.3f} height={h_in:.3f} shape={shape} fixedsize=true];')

    for e in edges:
        lines.append(f'  "{e["from"]}" -> "{e["to"]}";')

    lines.append("}")
    return "\n".join(lines)


def run_graphviz(dot_source: str, engine: str) -> dict:
    result = subprocess.run(
        [engine, "-Tjson0"],
        input=dot_source,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"graphviz failed: {result.stderr}")
    return json.loads(result.stdout)


def extract_positions(gv_data: dict, node_map: dict) -> dict[str, tuple[float, float]]:
    bb = gv_data.get("bb", "0,0,100,100")
    bb_parts = [float(x) for x in bb.split(",")]
    canvas_height = bb_parts[3]

    positions = {}
    for obj in gv_data.get("objects", []):
        nid = obj.get("name")
        if nid not in node_map:
            continue
        pos_parts = obj["pos"].split(",")
        cx = float(pos_parts[0])
        cy = canvas_height - float(pos_parts[1])
        w = node_map[nid]["width"]
        h = node_map[nid]["height"]
        positions[nid] = (cx - w / 2, cy - h / 2)

    return positions


def build_skeleton(node_map: dict, positions: dict, edges: list, origin_x: float, origin_y: float) -> list[dict]:
    """Build ExcalidrawElementSkeleton array from positioned graph."""
    # Shift to origin
    min_x = min(p[0] for p in positions.values())
    min_y = min(p[1] for p in positions.values())

    final = {
        nid: (snap(x - min_x + origin_x), snap(y - min_y + origin_y))
        for nid, (x, y) in positions.items()
    }

    skeleton = []

    # Shapes
    for nid, info in node_map.items():
        x, y = final[nid]
        elem: dict = {
            "type": info["type"],
            "id": nid,
            "x": x,
            "y": y,
            "width": info["width"],
            "height": info["height"],
        }
        if info["bg"] != "transparent":
            elem["backgroundColor"] = info["bg"]
        if info.get("stroke") and info["stroke"] != "#000000":
            elem["strokeColor"] = info["stroke"]
        if info["text"]:
            elem["label"] = {"text": info["text"]}
        skeleton.append(elem)

    # Arrows — specify start/end binding + edge-to-edge geometry
    for e in edges:
        src_id, tgt_id = e["from"], e["to"]
        if src_id not in final or tgt_id not in final:
            continue

        sx, sy = final[src_id]
        tx, ty = final[tgt_id]
        src_w, src_h = node_map[src_id]["width"], node_map[src_id]["height"]
        tgt_w, tgt_h = node_map[tgt_id]["width"], node_map[tgt_id]["height"]

        src_cx, src_cy = sx + src_w / 2, sy + src_h / 2
        tgt_cx, tgt_cy = tx + tgt_w / 2, ty + tgt_h / 2
        dx, dy = tgt_cx - src_cx, tgt_cy - src_cy

        # Compute edge exit/entry points (not centers)
        if abs(dx) > abs(dy):
            # Horizontal dominant
            start_x = sx + src_w if dx > 0 else sx
            start_y = src_cy
            end_x = tx if dx > 0 else tx + tgt_w
            end_y = tgt_cy
        else:
            # Vertical dominant
            start_x = src_cx
            start_y = sy + src_h if dy > 0 else sy
            end_x = tgt_cx
            end_y = ty if dy > 0 else ty + tgt_h

        arrow: dict = {
            "type": "arrow",
            "id": f"arrow_{src_id}_{tgt_id}",
            "x": start_x,
            "y": start_y,
            "width": end_x - start_x,
            "height": end_y - start_y,
            "start": {"id": src_id},
            "end": {"id": tgt_id},
        }

        if e.get("label"):
            arrow["label"] = {"text": e["label"]}
        if e.get("style") == "dashed":
            arrow["strokeStyle"] = "dashed"

        skeleton.append(arrow)

    return skeleton


def layout_graph_native(
    filepath: str,
    spec: dict,
    engine: str = "dot",
    direction: str = "DOWN",
    origin_x: float = 100,
    origin_y: float = 100,
) -> str:
    path = Path(filepath)
    nodes = spec.get("nodes", [])
    edges = spec.get("edges", [])

    if not nodes:
        return "ERROR: no nodes in spec"

    # Build node info map
    node_map = {}
    for n in nodes:
        nid = n["id"]
        ntype = n.get("type", "rectangle")
        dw, dh = TYPE_DEFAULTS.get(ntype, (180, 80))
        node_map[nid] = {
            "id": nid,
            "type": ntype,
            "text": n.get("text", nid),
            "width": n.get("width", dw),
            "height": n.get("height", dh),
            "bg": n.get("bg", "transparent"),
            "stroke": n.get("stroke", "#000000"),
        }

    # Run graphviz layout
    dot_source = build_dot_source(node_map, edges, engine, direction)
    try:
        gv_data = run_graphviz(dot_source, engine)
    except FileNotFoundError:
        return f"ERROR: '{engine}' not found. Install graphviz: brew install graphviz"
    except RuntimeError as e:
        return f"ERROR: {e}"

    positions = extract_positions(gv_data, node_map)
    if not positions:
        return "ERROR: graphviz produced no positions"

    # Build skeleton and convert via official API
    skeleton = build_skeleton(node_map, positions, edges, origin_x, origin_y)
    elements = convert_skeleton(skeleton, regenerate_ids=False)

    # Write to file
    if path.exists():
        data = json.loads(path.read_text())
        existing_ids = {e["id"] for e in data.get("elements", [])}
        for e in elements:
            if e["id"] in existing_ids:
                return f"ERROR: element ID '{e['id']}' already exists in file"
        data["elements"].extend(elements)
    else:
        data = {
            "type": "excalidraw",
            "version": 2,
            "source": "layout_graph_native",
            "elements": elements,
            "appState": {"gridSize": None},
        }

    path.write_text(json.dumps(data, indent="\t"))
    return f"OK: laid out {len(nodes)} nodes + {len(edges)} edges (engine={engine}, direction={direction})"


def main():
    parser = argparse.ArgumentParser(description="Generate excalidraw diagram with native element finalization")
    parser.add_argument("file", help="Output .excalidraw file path")
    parser.add_argument("--spec", required=True, help="JSON graph spec (nodes + edges)")
    parser.add_argument("--engine", default="dot", choices=["dot", "neato", "fdp", "sfdp", "twopi", "circo"])
    parser.add_argument("--direction", default="DOWN", choices=["DOWN", "RIGHT", "UP", "LEFT"])
    parser.add_argument("--origin-x", type=float, default=100)
    parser.add_argument("--origin-y", type=float, default=100)
    args = parser.parse_args()

    try:
        spec = json.loads(args.spec)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    result = layout_graph_native(
        args.file, spec,
        engine=args.engine,
        direction=args.direction,
        origin_x=args.origin_x,
        origin_y=args.origin_y,
    )
    print(result)


if __name__ == "__main__":
    main()
