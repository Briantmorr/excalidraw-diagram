#!/usr/bin/env python3
"""excd — single argparse dispatcher for the excalidraw-diagram skill.

All subcommands delegate to the matching helper module. No business logic here.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SKILL_ROOT = _HERE.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

import argparse  # noqa: E402
import json  # noqa: E402
from dataclasses import asdict  # noqa: E402
from typing import Any  # noqa: E402

from helpers import patterns as _patterns  # noqa: E402
from helpers import render as _render  # noqa: E402
from helpers import validate as _validate  # noqa: E402
from helpers.connect import ConnectSpec, connect, connect_batch  # noqa: E402
from helpers.core import appstate_defaults  # noqa: E402
from helpers.canvas_view import summarize  # noqa: E402
from helpers.layout import GraphSpec, layout_dag  # noqa: E402
from helpers.patch import PatchSpec, patch, remove  # noqa: E402
from helpers.place import PlaceSpec, place  # noqa: E402

SOURCE = "https://github.com/zsviczian/obsidian-excalidraw-plugin/releases/tag/2.22.3"


# ---------------------------------------------------------------------------
# new
# ---------------------------------------------------------------------------

def _cmd_new(args: argparse.Namespace) -> int:
    out = Path(args.file)
    if out.exists() and not args.force:
        print(f"ERROR: {out} already exists (use --force to overwrite)", file=sys.stderr)
        return 1
    payload: dict[str, Any] = {
        "type": "excalidraw",
        "version": 2,
        "source": SOURCE,
        "elements": [],
        "appState": appstate_defaults(),
        "files": {},
    }
    out.write_text(json.dumps(payload, indent="\t"))
    print(f"OK: created {out}")
    return 0


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------

def _cmd_info(args: argparse.Namespace) -> int:
    fmt = "full" if args.full else ("json" if args.json else "compact")
    print(summarize(Path(args.file), fmt))
    return 0


# ---------------------------------------------------------------------------
# place
# ---------------------------------------------------------------------------

def _cmd_place(args: argparse.Namespace) -> int:
    raw = json.loads(args.spec)
    if not isinstance(raw, list):
        print("ERROR: place spec must be a JSON array", file=sys.stderr)
        return 1
    specs = [PlaceSpec.from_dict(d) for d in raw]
    result = place(Path(args.file), specs)
    print(result)
    return 0 if result.ok else 1


# ---------------------------------------------------------------------------
# pattern
# ---------------------------------------------------------------------------

def _cmd_pattern(args: argparse.Namespace) -> int:
    fn = _patterns.PATTERNS.get(args.name)
    if fn is None:
        print(f"ERROR: unknown pattern {args.name!r}; choices: {sorted(_patterns.PATTERNS)}",
              file=sys.stderr)
        return 1
    spec = json.loads(args.spec)
    if not isinstance(spec, dict):
        print("ERROR: pattern spec must be a JSON object", file=sys.stderr)
        return 1
    kwargs = _patterns._coerce_kwargs(fn, spec)
    result = fn(Path(args.file), **kwargs)
    _patterns.recenter_titles(Path(args.file))
    if result is not None:
        print(result)
    return 0


# ---------------------------------------------------------------------------
# connect / connect-batch
# ---------------------------------------------------------------------------

def _connect_spec_from_dict(d: dict[str, Any]) -> ConnectSpec:
    return ConnectSpec(
        from_id=d.get("from_id") or d["from"],
        to_id=d.get("to_id") or d["to"],
        label=d.get("label"),
        style=d.get("style", "solid"),
        stroke_width=d.get("stroke_width", 2),
        start_side=d.get("start_side"),
        end_side=d.get("end_side"),
        force_elbow=d.get("force_elbow", False),
    )


def _print_connect_result(result: Any) -> None:
    for e in result.created:
        tag = " [elbow]" if e.elbowed else ""
        print(f"OK: {e.from_id} -> {e.to_id}{tag}")
    for s in result.skipped:
        print(f"SKIP: {s}")
    for w in result.warnings:
        print(f"WARN: {w}")


def _cmd_connect(args: argparse.Namespace) -> int:
    spec = ConnectSpec(
        from_id=args.from_id, to_id=args.to_id, label=args.label,
        style=args.style, stroke_width=args.stroke_width,
        start_side=args.start_side, end_side=args.end_side,
        force_elbow=args.force_elbow,
    )
    _print_connect_result(connect(Path(args.file), [spec]))
    return 0


def _cmd_connect_batch(args: argparse.Namespace) -> int:
    raw = json.loads(args.spec)
    if not isinstance(raw, list):
        print("ERROR: connect-batch spec must be a JSON array", file=sys.stderr)
        return 1
    specs = [_connect_spec_from_dict(d) for d in raw]
    _print_connect_result(connect_batch(Path(args.file), specs))
    return 0


# ---------------------------------------------------------------------------
# patch / remove
# ---------------------------------------------------------------------------

def _cmd_patch(args: argparse.Namespace) -> int:
    if args.spec:
        raw = json.loads(args.spec)
        if not isinstance(raw, list):
            print("ERROR: patch spec must be a JSON array", file=sys.stderr)
            return 1
        specs = [PatchSpec.from_dict(d) for d in raw]
    elif args.id:
        d: dict[str, Any] = {"id": args.id}
        for k in ("x", "y", "width", "height", "text", "bg", "stroke",
                 "stroke_width", "font_size"):
            v = getattr(args, k, None)
            if v is not None:
                d[k] = v
        specs = [PatchSpec.from_dict(d)]
    elif not sys.stdin.isatty():
        raw = json.loads(sys.stdin.read())
        specs = [PatchSpec.from_dict(d) for d in raw]
    else:
        print("ERROR: provide --spec, --id, or pipe JSON via stdin", file=sys.stderr)
        return 1
    result = patch(Path(args.file), specs)
    print(result.summary())
    return 0 if result.ok else 1


def _cmd_remove(args: argparse.Namespace) -> int:
    result = remove(Path(args.file), args.ids)
    print(result.summary())
    return 0 if not result.missing else 1


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------

def _cmd_check(args: argparse.Namespace) -> int:
    report = _validate.check_all(Path(args.file))
    for f in report.findings:
        ids = f",{','.join(f.element_ids)}" if f.element_ids else ""
        print(f"[{f.severity}] {f.code}: {f.message}{ids}")
    if not report.findings:
        print("OK: no findings")
    if args.strict and (report.fails or report.warns):
        return 1
    return 0 if report.ok() else 1


# ---------------------------------------------------------------------------
# tighten
# ---------------------------------------------------------------------------

def _cmd_tighten(args: argparse.Namespace) -> int:
    target_bbox: tuple[int, int] | None = None
    if args.target_bbox:
        try:
            w, h = (int(p) for p in args.target_bbox.lower().split("x"))
            target_bbox = (w, h)
        except ValueError:
            print(f"ERROR: --target-bbox must look like 800x600", file=sys.stderr)
            return 1
    rep = _validate.tighten(
        Path(args.file),
        target_bbox=target_bbox,
        snap=args.snap,
        dry_run=args.dry_run,
    )
    print(json.dumps(asdict(rep), indent=2))
    return 0


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------

def _cmd_render(args: argparse.Namespace) -> int:
    inp = Path(args.file)
    if not inp.exists():
        print(f"ERROR: input not found: {inp}", file=sys.stderr)
        return 1
    fmt = "svg" if args.svg else "png"
    out: Path = args.output or inp.with_suffix(f".{fmt}")
    result = _render.render(inp, out, format=fmt, scale=args.scale)
    print(json.dumps({
        "path": str(result.path),
        "format": result.format,
        "width": result.width,
        "height": result.height,
        "bytes": result.bytes_written,
        "latency_ms": round(result.latency_ms, 1),
    }, indent=2))
    return 0


# ---------------------------------------------------------------------------
# layout
# ---------------------------------------------------------------------------

def _cmd_layout(args: argparse.Namespace) -> int:
    spec_dict = json.loads(args.spec)
    spec = _patterns_layout_spec(spec_dict)
    elements = layout_dag(spec, engine=args.engine, direction=args.direction)
    out = Path(args.file)
    payload = {
        "type": "excalidraw",
        "version": 2,
        "source": SOURCE,
        "elements": elements,
        "files": {},
        "appState": appstate_defaults(),
    }
    out.write_text(json.dumps(payload, indent="\t"))
    print(f"OK: {len(spec.nodes)} nodes, {len(spec.edges)} edges -> {out}")
    return 0


def _patterns_layout_spec(d: dict[str, Any]) -> GraphSpec:
    from helpers.layout import EdgeSpec, NodeSpec
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


# ---------------------------------------------------------------------------
# sketch
# ---------------------------------------------------------------------------

def _cmd_sketch(args: argparse.Namespace) -> int:
    from helpers.chat2svg_sketch import (
        run_pipeline, strokes_to_excalidraw, svg_to_strokes,
    )
    out_path = Path(args.file)
    svg = run_pipeline(args.prompt, model=args.model, refine_iter=args.refine,
                       sketch_style=args.sketch_style, verbose=args.verbose)
    if args.save_svg:
        Path(args.save_svg).write_text(svg)
    strokes = svg_to_strokes(svg)

    if out_path.exists():
        existing = json.loads(out_path.read_text())
        idx_offset = len(existing.get("elements", []))
        scene = strokes_to_excalidraw(strokes, offset_x=args.x, offset_y=args.y,
                                      scale=args.scale, index_offset=idx_offset)
        existing.setdefault("elements", []).extend(scene["elements"])
        existing["source"] = SOURCE
        out_path.write_text(json.dumps(existing, indent=2))
    else:
        scene = strokes_to_excalidraw(strokes, offset_x=args.x, offset_y=args.y,
                                      scale=args.scale)
        out_path.write_text(json.dumps(scene, indent=2))
    print(f"OK: sketched {len(strokes)} strokes -> {out_path}")
    return 0


# ---------------------------------------------------------------------------
# compose
# ---------------------------------------------------------------------------

def _cmd_compose(args: argparse.Namespace) -> int:
    from helpers.patterns import ComposeStep, compose
    raw = json.loads(args.spec)
    if not isinstance(raw, list):
        print("ERROR: compose spec must be a JSON array", file=sys.stderr)
        return 1
    steps = [
        ComposeStep(pattern=item["pattern"], spec=item.get("spec", {}))
        for item in raw
    ]
    compose(Path(args.file), steps)
    print(f"OK: composed {len(steps)} patterns -> {args.file}")
    return 0


# ---------------------------------------------------------------------------
# bench
# ---------------------------------------------------------------------------

def _cmd_bench(args: argparse.Namespace) -> int:
    root = Path(args.dir)
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return 1
    files = sorted(root.glob("*.excalidraw"))
    if not files:
        print(f"ERROR: no .excalidraw files in {root}", file=sys.stderr)
        return 1
    report: dict[str, Any] = {"dir": str(root), "files": []}
    for f in files:
        entry: dict[str, Any] = {"file": f.name}
        try:
            png_out = f.with_suffix(".bench.png")
            res = _render.render(f, png_out, format="png", scale=2.0)
            entry["render_ms"] = round(res.latency_ms, 1)
            entry["render_path"] = str(res.path)
            entry["png_bytes"] = res.bytes_written
        except Exception as exc:
            entry["render_error"] = str(exc)
        try:
            rep = _validate.check_all(f)
            entry["fails"] = len(rep.fails)
            entry["warns"] = len(rep.warns)
            entry["infos"] = len(rep.infos)
            entry["score"] = max(0, 100 - 10 * len(rep.fails) - 2 * len(rep.warns))
            entry["findings"] = [
                {"severity": fi.severity, "code": fi.code, "message": fi.message,
                 "ids": list(fi.element_ids)}
                for fi in rep.findings
            ]
        except Exception as exc:
            entry["check_error"] = str(exc)
        report["files"].append(entry)
        print(f"{f.name}: render={entry.get('render_ms', 'ERR')}ms "
              f"score={entry.get('score', 'ERR')} "
              f"fails={entry.get('fails', '?')} warns={entry.get('warns', '?')}")

    out_json = Path(args.output) if args.output else root / "bench-report.json"
    out_json.write_text(json.dumps(report, indent=2))
    print(f"\nreport: {out_json}")
    return 0


# ---------------------------------------------------------------------------
# parser construction
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="excd", description="excalidraw-diagram CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("new", help="create empty .excalidraw")
    sp.add_argument("file")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=_cmd_new)

    sp = sub.add_parser("info", help="compact summary of canvas")
    sp.add_argument("file")
    sp.add_argument("--full", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=_cmd_info)

    sp = sub.add_parser("place", help="declarative role+anchor placement")
    sp.add_argument("file")
    sp.add_argument("spec", help="JSON array of placement specs")
    sp.set_defaults(func=_cmd_place)

    sp = sub.add_parser("pattern", help="one-shot pattern generation")
    sp.add_argument("name", choices=sorted(_patterns.PATTERNS))
    sp.add_argument("file")
    sp.add_argument("spec", help="JSON object of pattern kwargs")
    sp.set_defaults(func=_cmd_pattern)

    sp = sub.add_parser("connect", help="single arrow")
    sp.add_argument("file")
    sp.add_argument("--from", dest="from_id", required=True)
    sp.add_argument("--to", dest="to_id", required=True)
    sp.add_argument("--label")
    sp.add_argument("--style", default="solid", choices=["solid", "dashed"])
    sp.add_argument("--stroke-width", dest="stroke_width", type=int, default=2,
                    choices=[1, 2, 3])
    sp.add_argument("--start-side", dest="start_side",
                    choices=["top", "bottom", "left", "right"])
    sp.add_argument("--end-side", dest="end_side",
                    choices=["top", "bottom", "left", "right"])
    sp.add_argument("--force-elbow", dest="force_elbow", action="store_true")
    sp.set_defaults(func=_cmd_connect)

    sp = sub.add_parser("connect-batch", help="multiple arrows in one call")
    sp.add_argument("file")
    sp.add_argument("spec", help="JSON array of {from,to,label?,style?,stroke_width?,start_side?,end_side?}")
    sp.set_defaults(func=_cmd_connect_batch)

    sp = sub.add_parser("patch", help="mutate one element")
    sp.add_argument("file")
    sp.add_argument("--id")
    sp.add_argument("--spec", help="JSON array of patch specs (overrides --id)")
    sp.add_argument("--x", type=float)
    sp.add_argument("--y", type=float)
    sp.add_argument("--width", type=float)
    sp.add_argument("--height", type=float)
    sp.add_argument("--text")
    sp.add_argument("--bg")
    sp.add_argument("--stroke")
    sp.add_argument("--stroke-width", dest="stroke_width", type=int)
    sp.add_argument("--font-size", dest="font_size", type=int)
    sp.add_argument("--text-size", dest="font_size", type=int,
                    help="alias for --font-size")
    sp.set_defaults(func=_cmd_patch)

    sp = sub.add_parser("remove", help="delete element + dead bindings")
    sp.add_argument("file")
    sp.add_argument("--id", dest="ids", action="append", required=True)
    sp.set_defaults(func=_cmd_remove)

    sp = sub.add_parser("check", help="run all validators")
    sp.add_argument("file")
    sp.add_argument("--strict", action="store_true")
    sp.set_defaults(func=_cmd_check)

    sp = sub.add_parser("tighten", help="grid-snap, align, compress gaps")
    sp.add_argument("file")
    sp.add_argument("--target-bbox", dest="target_bbox", help="WxH e.g. 800x600")
    sp.add_argument("--snap", type=int, default=20)
    sp.add_argument("--beyond", action="store_true")
    sp.add_argument("--dry-run", dest="dry_run", action="store_true")
    sp.set_defaults(func=_cmd_tighten)

    sp = sub.add_parser("render", help="headless PNG/SVG")
    sp.add_argument("file")
    sp.add_argument("-o", "--output", type=Path)
    sp.add_argument("-s", "--scale", type=float, default=2.0)
    sp.add_argument("--svg", action="store_true")
    sp.set_defaults(func=_cmd_render)

    sp = sub.add_parser("layout", help="graphviz auto-layout for DAGs")
    sp.add_argument("file")
    sp.add_argument("--spec", required=True, help="JSON {nodes:[...],edges:[...]}")
    sp.add_argument("--engine", default="dot", choices=["dot", "neato", "fdp", "circo"])
    sp.add_argument("--direction", default="DOWN", choices=["DOWN", "RIGHT", "UP", "LEFT"])
    sp.set_defaults(func=_cmd_layout)

    sp = sub.add_parser("sketch", help="text -> SVG -> freedraw strokes")
    sp.add_argument("prompt")
    sp.add_argument("file")
    sp.add_argument("--x", type=float, default=50)
    sp.add_argument("--y", type=float, default=50)
    sp.add_argument("--scale", type=float, default=1.0)
    sp.add_argument("--save-svg", dest="save_svg")
    sp.add_argument("--model", default="claude-sonnet-latest")
    sp.add_argument("--refine", type=int, default=0)
    sp.add_argument("--sketch-style", dest="sketch_style", action="store_true")
    sp.add_argument("-v", "--verbose", action="store_true")
    sp.set_defaults(func=_cmd_sketch)

    sp = sub.add_parser("bench", help="render+check every .excalidraw in a dir")
    sp.add_argument("dir")
    sp.add_argument("-o", "--output", help="bench-report.json path")
    sp.set_defaults(func=_cmd_bench)

    sp = sub.add_parser("compose", help="stack multiple patterns vertically on one canvas")
    sp.add_argument("file")
    sp.add_argument("spec", help='JSON array of {"pattern":..,"spec":{..}}')
    sp.set_defaults(func=_cmd_compose)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
