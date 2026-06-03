#!/usr/bin/env python3
"""Render an .excalidraw file to PNG/SVG via the shared skeleton_bridge Playwright instance."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from helpers.skeleton_bridge import export_to_canvas, export_to_svg

Format = Literal["png", "svg"]


@dataclass
class RenderResult:
    path: Path
    format: Format
    latency_ms: float
    width: int
    height: int
    bytes_written: int


def _read_excalidraw(path: Path) -> tuple[list[dict], dict, dict]:
    raw = json.loads(path.read_text())
    elements = raw.get("elements", [])
    appstate = raw.get("appState", {}) or {}
    files = raw.get("files", {}) or {}
    appstate.setdefault("viewBackgroundColor", "#ffffff")
    appstate.setdefault("isBindingEnabled", True)
    return elements, appstate, files


def render(
    input_path: Path,
    output_path: Path,
    *,
    format: Format = "png",
    scale: float = 2.0,
    padding: int = 16,
) -> RenderResult:
    return _render(input_path, output_path, format=format, scale=scale, padding=padding)


def _render(
    input_path: Path,
    output_path: Path,
    *,
    format: Format,
    scale: float,
    padding: int,
) -> RenderResult:
    t0 = time.perf_counter()
    elements, appstate, files = _read_excalidraw(input_path)

    if format == "png":
        canvas = export_to_canvas(elements, appstate, files, scale=scale, padding=padding)
        payload = canvas.png_bytes
        width, height = canvas.width, canvas.height
    else:
        svg = export_to_svg(elements, appstate, files, padding=padding)
        payload = svg.xml.encode("utf-8")
        width, height = int(svg.width), int(svg.height)

    output_path.write_bytes(payload)
    return RenderResult(
        path=output_path,
        format=format,
        latency_ms=(time.perf_counter() - t0) * 1000.0,
        width=width,
        height=height,
        bytes_written=len(payload),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render .excalidraw -> PNG/SVG")
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("-f", "--format", choices=["png", "svg"], default="png")
    parser.add_argument("-s", "--scale", type=float, default=2.0)
    parser.add_argument("--bench", action="store_true")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: input not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    out: Path = args.output or args.input.with_suffix(f".{args.format}")

    if args.bench:
        cold = render(args.input, out, format=args.format, scale=args.scale)
        warm = render(args.input, out, format=args.format, scale=args.scale)
        print(json.dumps({
            "cold_ms": round(cold.latency_ms, 1),
            "warm_ms": round(warm.latency_ms, 1),
            "path": str(out),
            "width": cold.width,
            "height": cold.height,
            "bytes": cold.bytes_written,
        }, indent=2))
        return

    result = render(args.input, out, format=args.format, scale=args.scale)
    print(json.dumps({
        **{k: (str(v) if isinstance(v, Path) else v) for k, v in asdict(result).items()},
        "latency_ms": round(result.latency_ms, 1),
    }, indent=2))


if __name__ == "__main__":
    main()
