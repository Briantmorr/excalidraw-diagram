#!/usr/bin/env python3
"""Batch arrow connector — emit N arrows in one process.

CLI: python batch_connect.py <file.excalidraw> '<json-array>'

Each spec: {from, to, label?, style?, stroke_width?, start_side?, end_side?}

Behavior:
- Skips self-loops silently (per rendering invariants).
- Runs the label-fit horizontal nudge ONCE globally before any arrow is built,
  so multiple arrows targeting the same shape do not oscillate.
- Appends all arrows after all existing shapes (shapes-before-arrows invariant).
- Updates boundElements bidirectionally per arrow.
- Indices stay monotonic (next_index + base36-style suffix per emitted element).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure parent helpers/ dir AND this dir are on sys.path so `core` resolves
# (used by _connect_internals) and the sibling internals module imports here.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE))

from _connect_internals import (  # noqa: E402
    ArrowSpec,
    apply_target_shifts,
    emit_arrows,
    ensure_app_state,
    plan_label_nudges,
)


def _coerce_spec(raw: dict) -> ArrowSpec:
    if "from" not in raw or "to" not in raw:
        raise ValueError(f"spec missing 'from' or 'to': {raw!r}")
    return ArrowSpec(
        from_id=str(raw["from"]),
        to_id=str(raw["to"]),
        label=raw.get("label"),
        style=raw.get("style", "solid"),
        stroke_width=int(raw.get("stroke_width", 2)),
        start_side=raw.get("start_side"),
        end_side=raw.get("end_side"),
    )


def batch_connect(filepath: str, specs_json: str) -> str:
    path = Path(filepath)
    data = json.loads(path.read_text())
    elements: list[dict] = data.get("elements", [])

    raw_specs = json.loads(specs_json)
    if not isinstance(raw_specs, list):
        raise ValueError("specs must be a JSON array")
    specs = [_coerce_spec(r) for r in raw_specs]

    by_id = {e["id"]: e for e in elements}
    shifts = plan_label_nudges(specs, by_id)
    apply_target_shifts(elements, shifts)

    created, messages = emit_arrows(elements, specs)

    data["elements"] = elements
    ensure_app_state(data)
    path.write_text(json.dumps(data, indent=2))

    summary = f"OK: created {created}/{len(specs)} arrows"
    if shifts:
        summary += f"; nudged {len(shifts)} target(s) for label fit"
    return summary + "\n" + "\n".join(messages)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add multiple arrows to an excalidraw canvas in one call"
    )
    parser.add_argument("file", help="Path to .excalidraw file")
    parser.add_argument(
        "specs",
        help="JSON array of arrow specs: "
        "[{\"from\":\"a\",\"to\":\"b\",\"label\":\"x\"}, ...]",
    )
    args = parser.parse_args()
    print(batch_connect(args.file, args.specs))


if __name__ == "__main__":
    main()
