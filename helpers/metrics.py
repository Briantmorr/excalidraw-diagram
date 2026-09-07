#!/usr/bin/env python3
"""Mechanical metrics for diagram output — tokens (proxy), time, structural accuracy.

Deliberately NOT a taste score. There is no composite number to game: each axis is
reported raw, and the only verdict is the boolean `clean` (0 FAIL + 0 WARN from the
validators). Aesthetic quality is a human judgement made in a live render-and-look
loop, not something this harness pretends to measure.

Axes per diagram:
  - render_ms      wall-clock to render the PNG (helpers.render)
  - fails/warns    validator findings (helpers.validate) — structural accuracy
  - infos          validator infos (non-blocking)
  - clean          fails == 0 and warns == 0
  - spec_bytes     size of a sibling `<name>.spec.json`, if present — the controllable
                   proxy for "how much JSON the model had to emit". Actual token counts
                   aren't recoverable from a finished file; spec size is what we own.
  - n_elements     element count (helpers.canvas_view)
  - canvas         w x h and area_ratio (shape area / canvas area)

`--baseline metrics.json` prints per-file deltas against a prior run — the actual
progress-assessment mechanism (cheaper? faster? cleaner?).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_SKILL_ROOT = _HERE.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from helpers import validate as _validate  # noqa: E402
from helpers.canvas_view import canvas_info  # noqa: E402

# render is imported lazily inside measure_file — it pulls in playwright via
# skeleton_bridge, which may be absent. A missing renderer degrades render_ms to
# None; the structural axes (validator findings, spec size) still work.

DEFAULT_CORPUS = _HERE / "tests" / "fixtures"


def measure_file(f: Path) -> dict[str, Any]:
    """Collect the mechanical axes for one .excalidraw file."""
    entry: dict[str, Any] = {"file": f.name}

    spec = f.with_suffix(".spec.json")
    entry["spec_bytes"] = spec.stat().st_size if spec.exists() else None

    try:
        from helpers import render as _render
        res = _render.render(f, f.with_suffix(".metrics.png"), format="png", scale=2.0)
        entry["render_ms"] = round(res.latency_ms, 1)
        entry["png_bytes"] = res.bytes_written
    except Exception as exc:  # rendering needs playwright; degrade, don't crash
        entry["render_ms"] = None
        entry["render_error"] = str(exc)

    try:
        rep = _validate.check_all(f)
        entry["fails"] = len(rep.fails)
        entry["warns"] = len(rep.warns)
        entry["infos"] = len(rep.infos)
        entry["clean"] = not rep.fails and not rep.warns
        entry["findings"] = [
            {"severity": fi.severity, "code": fi.code, "message": fi.message}
            for fi in rep.findings
        ]
    except Exception as exc:
        entry["check_error"] = str(exc)

    try:
        info = canvas_info(f)
        entry["n_elements"] = info.n_elements
        w, h = info.canvas_size
        entry["canvas_w"] = round(w)
        entry["canvas_h"] = round(h)
        entry["area_ratio"] = round(info.area_ratio, 3)
    except Exception as exc:
        entry["info_error"] = str(exc)

    return entry


def collect(root: Path) -> dict[str, Any]:
    files = sorted(root.glob("*.excalidraw"))
    return {"dir": str(root), "files": [measure_file(f) for f in files]}


def _fmt(v: Any) -> str:
    return "-" if v is None else str(v)


def _delta(cur: Any, base: Any) -> str:
    if cur is None or base is None:
        return ""
    d = round(cur - base, 1)
    if d == 0:
        return "  (=)"
    return f"  ({d:+g})"


def _print_table(report: dict[str, Any], baseline: dict[str, Any] | None) -> None:
    base_by_file = (
        {e["file"]: e for e in baseline.get("files", [])} if baseline else {}
    )
    print(f"{'file':<32} {'render_ms':>10} {'fails':>6} {'warns':>6} "
          f"{'spec_b':>7} {'elems':>6}  clean")
    print("-" * 84)
    for e in report["files"]:
        b = base_by_file.get(e["file"], {})
        rm = e.get("render_ms")
        clean = "✓" if e.get("clean") else "✗"
        print(
            f"{e['file']:<32} "
            f"{_fmt(rm):>10}{_delta(rm, b.get('render_ms'))} "
            f"{_fmt(e.get('fails')):>6}{_delta(e.get('fails'), b.get('fails'))} "
            f"{_fmt(e.get('warns')):>6}{_delta(e.get('warns'), b.get('warns'))} "
            f"{_fmt(e.get('spec_bytes')):>7} "
            f"{_fmt(e.get('n_elements')):>6}  {clean}"
        )
    n = len(report["files"])
    n_clean = sum(1 for e in report["files"] if e.get("clean"))
    print("-" * 84)
    print(f"{n_clean}/{n} clean (0 fail, 0 warn)")


def run_metrics(
    root: Path,
    *,
    baseline: Path | None = None,
    out: Path | None = None,
) -> int:
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return 1
    if not sorted(root.glob("*.excalidraw")):
        print(f"ERROR: no .excalidraw files in {root}", file=sys.stderr)
        return 1

    report = collect(root)
    base = json.loads(baseline.read_text()) if baseline and baseline.exists() else None
    _print_table(report, base)

    out_path = out or (root / "metrics.json")
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\nmetrics: {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="metrics.py", description=__doc__)
    p.add_argument("dir", nargs="?", default=None)
    p.add_argument("--baseline")
    p.add_argument("-o", "--output")
    args = p.parse_args(argv)
    root = Path(args.dir) if args.dir else DEFAULT_CORPUS
    return run_metrics(
        root,
        baseline=Path(args.baseline) if args.baseline else None,
        out=Path(args.output) if args.output else None,
    )


if __name__ == "__main__":
    sys.exit(main())
