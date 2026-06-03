#!/usr/bin/env python3
"""Generate a positioned excalidraw diagram from a declarative graph spec using graphviz layout."""

import json
import argparse
import os
import subprocess
import time
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.excalidraw_core import (
    ARROW_COLOR,
    DEFAULT_FONT_FAMILY,
    SHAPE_DEFAULTS,
    gen_nonce,
    gen_seed,
    text_height,
    text_width,
)


def element_defaults() -> dict:
    """Fresh defaults per element — avoids shared mutable list references."""
    d = dict(SHAPE_DEFAULTS)
    d["groupIds"] = []
    d["boundElements"] = []
    return d

TYPE_DEFAULTS = {
    "rectangle": (180, 80),
    "ellipse": (160, 80),
    "diamond": (160, 100),
}

PX_PER_INCH = 72


def compute_fixed_point(src_center: tuple, tgt_center: tuple) -> tuple[list[float], list[float]]:
    dx = tgt_center[0] - src_center[0]
    dy = tgt_center[1] - src_center[1]
    if abs(dx) > abs(dy):
        start_fp = [1.0, 0.5] if dx > 0 else [0.0, 0.5]
        end_fp = [0.0, 0.5] if dx > 0 else [1.0, 0.5]
    else:
        start_fp = [0.5, 1.0] if dy > 0 else [0.5, 0.0]
        end_fp = [0.5, 0.0] if dy > 0 else [0.5, 1.0]
    return start_fp, end_fp


def build_dot_source(node_map: dict, edges: list, engine: str, direction: str) -> str:
    """Build DOT language source from node/edge spec."""
    rankdir = {"DOWN": "TB", "RIGHT": "LR", "UP": "BT", "LEFT": "RL"}.get(direction, "TB")

    lines = [f"digraph {{", f"  rankdir={rankdir};", "  ranksep=0.5;", "  nodesep=0.4;"]

    # Force-directed engines need overlap removal
    if engine in ("neato", "fdp", "sfdp", "twopi", "circo"):
        lines.append("  overlap=false;")
        lines.append("  sep=\"+20\";")

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
    """Run graphviz engine and return JSON output with positions."""
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
    """Extract node positions from graphviz JSON, converting to excalidraw coordinates."""
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
        cy = float(pos_parts[1])
        # Flip Y axis (graphviz: 0 at bottom, excalidraw: 0 at top)
        cy = canvas_height - cy
        # Convert from center to top-left
        w = node_map[nid]["width"]
        h = node_map[nid]["height"]
        positions[nid] = (cx - w / 2, cy - h / 2)

    return positions


GRID = 20
HIERARCHY_SCALE = {"hero": 1.15, "primary": 1.0, "secondary": 0.9}


def snap(v: float) -> float:
    return round(v / GRID) * GRID


def compute_node_roles(node_ids: list[str], edges: list[dict]) -> dict[str, str]:
    """Assign hero/primary/secondary roles based on graph topology."""
    in_degree = {nid: 0 for nid in node_ids}
    out_degree = {nid: 0 for nid in node_ids}
    for e in edges:
        out_degree[e["from"]] = out_degree.get(e["from"], 0) + 1
        in_degree[e["to"]] = in_degree.get(e["to"], 0) + 1

    roles = {}
    for nid in node_ids:
        total = in_degree[nid] + out_degree[nid]
        if in_degree[nid] == 0 and out_degree[nid] > 0:
            roles[nid] = "hero"
        elif total >= 3:
            roles[nid] = "hero"
        elif out_degree[nid] == 0 and in_degree[nid] > 0:
            roles[nid] = "secondary"
        else:
            roles[nid] = "primary"
    return roles


def apply_aesthetics(positions: dict[str, tuple], node_map: dict,
                     edges: list[dict]) -> dict[str, tuple]:
    """Post-process positions: grid snap, enforce spacing, scale hierarchy."""
    node_ids = list(positions.keys())
    roles = compute_node_roles(node_ids, edges)

    # Apply size hierarchy
    for nid, role in roles.items():
        scale = HIERARCHY_SCALE[role]
        orig_w = node_map[nid]["width"]
        orig_h = node_map[nid]["height"]
        node_map[nid]["width"] = snap(orig_w * scale)
        node_map[nid]["height"] = snap(orig_h * scale)

    # Grid-snap positions
    snapped = {}
    for nid, (x, y) in positions.items():
        snapped[nid] = (snap(x), snap(y))

    # Enforce minimum spacing (resolve overlaps from snapping)
    min_gap = GRID
    sorted_ids = sorted(snapped.keys(), key=lambda k: (snapped[k][1], snapped[k][0]))
    for i, nid_a in enumerate(sorted_ids):
        ax, ay = snapped[nid_a]
        aw, ah = node_map[nid_a]["width"], node_map[nid_a]["height"]
        for nid_b in sorted_ids[i + 1:]:
            bx, by = snapped[nid_b]
            bw, bh = node_map[nid_b]["width"], node_map[nid_b]["height"]
            # Check horizontal overlap
            if ay < by + bh + min_gap and by < ay + ah + min_gap:
                # Same vertical band — check horizontal gap
                if ax < bx + bw + min_gap and bx < ax + aw + min_gap:
                    # Overlap — push b right
                    snapped[nid_b] = (snap(ax + aw + min_gap), by)

    return snapped


def layout_graph(filepath: str, spec: dict, engine: str = "dot",
                 direction: str = "DOWN",
                 origin_x: float = 100, origin_y: float = 100) -> str:
    """Create a fully-positioned excalidraw diagram from a graph spec.

    spec format:
    {
      "nodes": [{"id": "x", "text": "Label", "type": "rectangle", "bg": "#color"}],
      "edges": [{"from": "x", "to": "y", "label": "optional"}]
    }
    """
    path = Path(filepath)
    if path.exists():
        data = json.loads(path.read_text())
    else:
        data = {"type": "excalidraw", "version": 2,
                "source": "https://github.com/zsviczian/obsidian-excalidraw-plugin/releases/tag/2.22.3",
                "elements": [], "files": {},
                "appState": {
                    "gridSize": None,
                    "viewBackgroundColor": "#ffffff",
                    "isBindingEnabled": True,
                }}

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

    # Shift to origin
    min_x = min(p[0] for p in positions.values())
    min_y = min(p[1] for p in positions.values())
    final_positions = {
        nid: (x - min_x + origin_x, y - min_y + origin_y)
        for nid, (x, y) in positions.items()
    }

    # Aesthetic post-processing
    final_positions = apply_aesthetics(final_positions, node_map, edges)

    # Generate excalidraw elements
    elements = data.get("elements", [])
    existing_ids = {e["id"] for e in elements}

    for nid in [n["id"] for n in nodes]:
        if nid in existing_ids:
            return f"ERROR: element ID '{nid}' already exists in file"

    now = int(time.time() * 1000)
    indices = [e.get("index", "") for e in elements if e.get("index")]
    base_idx = (sorted(indices)[-1] + "0") if indices else "a0"
    idx_counter = 0

    shape_elements = []

    for nid in [n["id"] for n in nodes]:
        info = node_map[nid]
        x, y = final_positions[nid]
        idx = base_idx + str(idx_counter).zfill(2)
        idx_counter += 1

        shape = {
            **element_defaults(),
            "type": info["type"],
            "id": nid,
            "x": x,
            "y": y,
            "width": info["width"],
            "height": info["height"],
            "strokeColor": info["stroke"],
            "backgroundColor": info["bg"],
            "seed": gen_seed(),
            "version": 1,
            "versionNonce": gen_nonce(),
            "index": idx,
            "updated": now,
        }

        if info["type"] in ("rectangle", "diamond"):
            shape["roundness"] = {"type": 3}

        text = info["text"]
        text_size = 16
        text_id = f"{nid}_text"
        tw = text_width(text, text_size)
        th = text_height(1, text_size)

        shape["boundElements"] = [{"id": text_id, "type": "text"}]
        shape_elements.append(shape)

        text_elem = {
            **element_defaults(),
            "type": "text",
            "id": text_id,
            "x": x + (info["width"] - tw) / 2,
            "y": y + (info["height"] - th) / 2,
            "width": tw,
            "height": th,
            "text": text,
            "originalText": text,
            "rawText": text,
            "fontSize": text_size,
            "fontFamily": DEFAULT_FONT_FAMILY,
            "textAlign": "center",
            "verticalAlign": "middle",
            "strokeColor": "#0a0a0a",
            "backgroundColor": "transparent",
            "strokeWidth": 1,
            "roughness": 0,
            "seed": gen_seed(),
            "version": 1,
            "versionNonce": gen_nonce(),
            "index": idx + "t",
            "updated": now,
            "containerId": nid,
            "lineHeight": 1.25,
            "autoResize": True,
        }
        shape_elements.append(text_elem)

    # Generate arrows (build separately, will be inserted BEFORE shapes for z-order)
    arrow_elements = []
    for e in edges:
        src_id, tgt_id = e["from"], e["to"]
        arrow_id = f"arrow_{src_id}_{tgt_id}"
        if arrow_id in existing_ids:
            continue

        sx, sy = final_positions[src_id]
        tx, ty = final_positions[tgt_id]
        src_w, src_h = node_map[src_id]["width"], node_map[src_id]["height"]
        tgt_w, tgt_h = node_map[tgt_id]["width"], node_map[tgt_id]["height"]
        src_cx = sx + src_w / 2
        src_cy = sy + src_h / 2
        tgt_cx = tx + tgt_w / 2
        tgt_cy = ty + tgt_h / 2

        start_fp, end_fp = compute_fixed_point((src_cx, src_cy), (tgt_cx, tgt_cy))

        # Compute arrow start/end at shape EDGE (not center)
        arrow_sx = sx + start_fp[0] * src_w
        arrow_sy = sy + start_fp[1] * src_h
        arrow_ex = tx + end_fp[0] * tgt_w
        arrow_ey = ty + end_fp[1] * tgt_h
        dx = arrow_ex - arrow_sx
        dy = arrow_ey - arrow_sy

        idx = base_idx + str(idx_counter).zfill(2)
        idx_counter += 1

        arrow = {
            **element_defaults(),
            "type": "arrow",
            "id": arrow_id,
            "x": arrow_sx,
            "y": arrow_sy,
            "width": abs(dx),
            "height": abs(dy),
            "strokeColor": ARROW_COLOR,
            "backgroundColor": "transparent",
            "strokeWidth": 2,
            "points": [[0, 0], [dx, dy]],
            "startBinding": {"mode": "orbit", "elementId": src_id, "fixedPoint": start_fp},
            "endBinding": {"mode": "orbit", "elementId": tgt_id, "fixedPoint": end_fp},
            "startArrowhead": None,
            "endArrowhead": "arrow",
            "elbowed": False,
            "hasTextLink": False,
            "seed": gen_seed(),
            "version": 2,
            "versionNonce": gen_nonce(),
            "index": idx,
            "updated": now,
            "roundness": {"type": 2},
        }
        arrow_elements.append(arrow)

        # Register arrow on shape endpoints
        for el in shape_elements:
            if el["id"] in (src_id, tgt_id):
                bound = el.get("boundElements", [])
                if not any(b.get("id") == arrow_id for b in bound):
                    bound.append({"id": arrow_id, "type": "arrow"})
                el["boundElements"] = bound

        # Arrow label
        label = e.get("label")
        if label:
            label_id = f"{arrow_id}_label"
            mid_x = arrow_sx + dx / 2
            mid_y = arrow_sy + dy / 2
            font_size = 14
            lw = text_width(label, font_size)
            lh = text_height(1, font_size)

            label_elem = {
                **element_defaults(),
                "type": "text",
                "id": label_id,
                "x": mid_x - lw / 2,
                "y": mid_y - lh / 2,
                "width": lw,
                "height": lh,
                "text": label,
                "originalText": label,
                "rawText": label,
                "fontSize": font_size,
                "fontFamily": DEFAULT_FONT_FAMILY,
                "textAlign": "center",
                "verticalAlign": "middle",
                "strokeColor": ARROW_COLOR,
                "backgroundColor": "transparent",
                "strokeWidth": 1,
                "roughness": 0,
                "seed": gen_seed(),
                "version": 1,
                "versionNonce": gen_nonce(),
                "index": idx + "l",
                "updated": now,
                "containerId": arrow_id,
                "lineHeight": 1.25,
                "autoResize": True,
            }
            arrow_elements.append(label_elem)
            arrow["boundElements"].append({"id": label_id, "type": "text"})

    # Element order: shapes MUST come before arrows (plugin hangs otherwise)
    data["elements"] = elements + shape_elements + arrow_elements
    if "files" not in data:
        data["files"] = {}
    if "appState" not in data:
        data["appState"] = {}
    data["appState"].setdefault("gridSize", None)
    data["appState"].setdefault("viewBackgroundColor", "#ffffff")
    data["appState"].setdefault("isBindingEnabled", True)
    data["source"] = "https://github.com/zsviczian/obsidian-excalidraw-plugin/releases/tag/2.22.3"
    path.write_text(json.dumps(data, indent="\t"))

    return f"OK: laid out {len(nodes)} nodes + {len(edges)} edges (engine={engine}, direction={direction})"


def main():
    parser = argparse.ArgumentParser(description="Generate positioned excalidraw diagram from graph spec")
    parser.add_argument("file", help="Output .excalidraw file path")
    parser.add_argument("--spec", required=True, help="JSON graph spec (nodes + edges)")
    parser.add_argument("--engine", default="dot",
                        choices=["dot", "neato", "fdp", "sfdp", "twopi", "circo"],
                        help="Graphviz layout engine (default: dot/Sugiyama)")
    parser.add_argument("--direction", default="DOWN", choices=["DOWN", "RIGHT", "UP", "LEFT"],
                        help="Layout direction for hierarchical engines (default: DOWN)")
    parser.add_argument("--origin-x", type=float, default=100, help="X offset for diagram origin")
    parser.add_argument("--origin-y", type=float, default=100, help="Y offset for diagram origin")

    args = parser.parse_args()

    try:
        spec = json.loads(args.spec)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    result = layout_graph(
        args.file, spec,
        engine=args.engine,
        direction=args.direction,
        origin_x=args.origin_x,
        origin_y=args.origin_y,
    )
    print(result)


if __name__ == "__main__":
    main()
