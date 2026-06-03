#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
import base64
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright


EXCALIDRAW_VERSION = "0.18.0"
ESM_URL = (
    f"https://esm.sh/@excalidraw/excalidraw@{EXCALIDRAW_VERSION}"
    "?bundle&deps=react@18,react-dom@18"
)
UTILS_URL = (
    f"https://esm.sh/@excalidraw/excalidraw@{EXCALIDRAW_VERSION}/utils"
    "?bundle&deps=react@18,react-dom@18"
)

HTML_TEMPLATE = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>
<div id="status">loading</div>
<script type="module">
try {{
    const mod = await import("{ESM_URL}");
    const utils = await import("{UTILS_URL}");
    window.__convertToExcalidrawElements = mod.convertToExcalidrawElements;
    window.__exportToCanvas = mod.exportToCanvas || utils.exportToCanvas;
    window.__exportToSvg = mod.exportToSvg || utils.exportToSvg;
    window.__ready = true;
    document.getElementById("status").textContent = "ready";
}} catch (e) {{
    window.__error = e.message;
    document.getElementById("status").textContent = "error: " + e.message;
}}
</script>
</body>
</html>"""


@dataclass
class CanvasResult:
    png_bytes: bytes
    width: int
    height: int


@dataclass
class SvgResult:
    xml: str
    width: float
    height: float


class Bridge:
    def __init__(self) -> None:
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._page: Page = self._browser.new_page()
        self._page.set_content(HTML_TEMPLATE)
        self._page.wait_for_function(
            "window.__ready === true || window.__error", timeout=30000
        )
        err = self._page.evaluate("window.__error")
        if err:
            self.close()
            raise RuntimeError(f"Failed to load Excalidraw: {err}")

    @property
    def page(self) -> Page:
        return self._page

    def convert(self, skeleton: list[dict], *, regenerate_ids: bool = False) -> list[dict]:
        return self._page.evaluate(
            """(args) => {
                const [skeleton, opts] = args;
                const elements = window.__convertToExcalidrawElements(skeleton, opts);
                return JSON.parse(JSON.stringify(elements));
            }""",
            [skeleton, {"regenerateIds": regenerate_ids}],
        )

    def export_to_canvas(
        self,
        elements: list[dict],
        appstate: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        *,
        scale: float = 2.0,
        padding: int = 16,
    ) -> CanvasResult:
        appstate = {**(appstate or {})}
        appstate.setdefault("viewBackgroundColor", "#ffffff")
        appstate.setdefault("isBindingEnabled", True)
        result = self._page.evaluate(
            """async (args) => {
                const [elements, appState, files, opts] = args;
                const canvas = await window.__exportToCanvas({
                    elements, appState, files, ...opts
                });
                return {
                    dataurl: canvas.toDataURL("image/png"),
                    width: canvas.width,
                    height: canvas.height,
                };
            }""",
            [elements, appstate, files or {}, {"exportPadding": padding, "exportScale": scale}],
        )
        b64 = result["dataurl"].split(",", 1)[1]
        return CanvasResult(
            png_bytes=base64.b64decode(b64),
            width=int(result["width"]),
            height=int(result["height"]),
        )

    def export_to_svg(
        self,
        elements: list[dict],
        appstate: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        *,
        padding: int = 16,
    ) -> SvgResult:
        appstate = {**(appstate or {})}
        appstate.setdefault("viewBackgroundColor", "#ffffff")
        appstate.setdefault("isBindingEnabled", True)
        result = self._page.evaluate(
            """async (args) => {
                const [elements, appState, files, opts] = args;
                const svg = await window.__exportToSvg({
                    elements, appState, files, ...opts
                });
                const xml = new XMLSerializer().serializeToString(svg);
                const w = parseFloat(svg.getAttribute("width") || "0");
                const h = parseFloat(svg.getAttribute("height") || "0");
                return { xml, width: w, height: h };
            }""",
            [elements, appstate, files or {}, {"exportPadding": padding}],
        )
        return SvgResult(
            xml=result["xml"],
            width=float(result["width"]),
            height=float(result["height"]),
        )

    def close(self) -> None:
        try:
            self._browser.close()
        finally:
            self._pw.stop()


_BRIDGE: Bridge | None = None


def get_bridge() -> Bridge:
    global _BRIDGE
    if _BRIDGE is None:
        _BRIDGE = Bridge()
        atexit.register(_close_bridge)
    return _BRIDGE


def _close_bridge() -> None:
    global _BRIDGE
    if _BRIDGE is not None:
        try:
            _BRIDGE.close()
        except Exception:
            pass
        _BRIDGE = None


def convert_skeleton(skeleton: list[dict], *, regenerate_ids: bool = False) -> list[dict]:
    return get_bridge().convert(skeleton, regenerate_ids=regenerate_ids)


def export_to_canvas(
    elements: list[dict],
    appstate: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    *,
    scale: float = 2.0,
    padding: int = 16,
) -> CanvasResult:
    return get_bridge().export_to_canvas(
        elements, appstate, files, scale=scale, padding=padding
    )


def export_to_svg(
    elements: list[dict],
    appstate: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    *,
    padding: int = 16,
) -> SvgResult:
    return get_bridge().export_to_svg(elements, appstate, files, padding=padding)


def _main() -> None:
    parser = argparse.ArgumentParser(description="Convert skeleton to full Excalidraw elements")
    parser.add_argument("--spec", help="JSON skeleton spec (inline)")
    parser.add_argument("--file", type=Path, help="Path to JSON skeleton")
    parser.add_argument("--regenerate-ids", action="store_true")
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()

    if args.spec:
        skeleton = json.loads(args.spec)
    elif args.file:
        skeleton = json.loads(args.file.read_text())
    elif not sys.stdin.isatty():
        skeleton = json.load(sys.stdin)
    else:
        print("ERROR: provide --spec, --file, or pipe JSON", file=sys.stderr)
        sys.exit(1)

    elements = convert_skeleton(skeleton, regenerate_ids=args.regenerate_ids)
    payload = json.dumps(elements, indent=2)
    if args.output:
        args.output.write_text(payload)
    else:
        print(payload)


if __name__ == "__main__":
    _main()
