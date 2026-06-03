#!/usr/bin/env python3
"""Add an arrow connecting two existing elements in an excalidraw canvas.

CLI is unchanged; internals delegate to place._connect_internals so batch and
single share the same arrow-construction code path.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.excalidraw_core import next_index, text_width
from place._connect_internals import (  # noqa: E402
    SIDE_TO_FP,
    ArrowSpec,
    _build_arrow_dict,
    _build_label_dict,
    compute_fixed_points,
    ensure_app_state,
)


def connect_elements(
    filepath: str,
    from_id: str,
    to_id: str,
    label: str | None = None,
    style: str = "solid",
    stroke_width: int = 2,
    start_side: str | None = None,
    end_side: str | None = None,
) -> str:
    path = Path(filepath)
    data = json.loads(path.read_text())
    elements: list[dict] = data.get("elements", [])

    by_id = {e["id"]: e for e in elements}

    if from_id == to_id:
        return f"SKIP: self-loop ignored ({from_id})"
    if from_id not in by_id:
        return f"ERROR: source element '{from_id}' not found"
    if to_id not in by_id:
        return f"ERROR: target element '{to_id}' not found"

    src = by_id[from_id]
    tgt = by_id[to_id]
    spec = ArrowSpec(
        from_id=from_id,
        to_id=to_id,
        label=label,
        style=style,
        stroke_width=stroke_width,
        start_side=start_side,
        end_side=end_side,
    )

    start_fp, end_fp = compute_fixed_points(src, tgt, start_side, end_side)

    # Legacy per-arrow horizontal label-fit nudge (preserved verbatim for
    # the single-arrow CLI path; batch_connect uses a global pass instead).
    if label:
        sw = src.get("width", 0)
        sh = src.get("height", 0)
        tw = tgt.get("width", 0)
        th = tgt.get("height", 0)
        arrow_sx = src["x"] + start_fp[0] * sw
        arrow_ex = tgt["x"] + end_fp[0] * tw
        arrow_sy = src["y"] + start_fp[1] * sh
        arrow_ey = tgt["y"] + end_fp[1] * th
        dx = arrow_ex - arrow_sx
        dy = arrow_ey - arrow_sy
        font_size = 14
        label_w = text_width(label, font_size)
        min_length = label_w + 50
        is_horizontal = abs(dx) > abs(dy)
        if is_horizontal and abs(dx) < min_length:
            shortfall = min_length - abs(dx)
            sign = 1 if dx >= 0 else -1
            tgt["x"] += sign * shortfall
            for el in elements:
                if el.get("containerId") == to_id:
                    el["x"] += sign * shortfall

    arrow_id = f"arrow_{from_id}_{to_id}"
    if arrow_id in by_id:
        return f"ERROR: arrow '{arrow_id}' already exists"

    now = int(time.time() * 1000)
    idx = next_index(elements)
    arrow = _build_arrow_dict(spec, src, tgt, start_fp, end_fp, arrow_id, idx, now)
    elements.append(arrow)

    for el_id in (from_id, to_id):
        el = by_id[el_id]
        bound = el.get("boundElements") or []
        if not any(b.get("id") == arrow_id for b in bound):
            bound.append({"id": arrow_id, "type": "arrow"})
        el["boundElements"] = bound

    if label:
        label_idx = idx + "1"
        label_elem = _build_label_dict(label, arrow_id, arrow, label_idx, now)
        elements.append(label_elem)
        arrow["boundElements"].append({"id": label_elem["id"], "type": "text"})

    data["elements"] = elements
    ensure_app_state(data)
    path.write_text(json.dumps(data, indent=2))
    return f"OK: connected {from_id} -> {to_id}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Connect two excalidraw elements with an arrow"
    )
    parser.add_argument("file", help="Path to .excalidraw file")
    parser.add_argument("--from", dest="from_id", required=True, help="Source element ID")
    parser.add_argument("--to", dest="to_id", required=True, help="Target element ID")
    parser.add_argument("--label", default=None, help="Text label on the arrow")
    parser.add_argument(
        "--style", default="solid", choices=["solid", "dashed"], help="Stroke style"
    )
    parser.add_argument(
        "--stroke-width", type=int, default=2, choices=[1, 2, 3], help="Stroke width"
    )
    parser.add_argument(
        "--start-side",
        default=None,
        choices=["top", "bottom", "left", "right"],
        help="Force arrow to start from this side of source element",
    )
    parser.add_argument(
        "--end-side",
        default=None,
        choices=["top", "bottom", "left", "right"],
        help="Force arrow to end at this side of target element",
    )

    args = parser.parse_args()
    result = connect_elements(
        args.file,
        args.from_id,
        args.to_id,
        label=args.label,
        style=args.style,
        stroke_width=args.stroke_width,
        start_side=args.start_side,
        end_side=args.end_side,
    )
    print(result)


# Re-export for callers that imported from connect_elements module.
__all__ = ["connect_elements", "compute_fixed_points", "SIDE_TO_FP"]


if __name__ == "__main__":
    main()
