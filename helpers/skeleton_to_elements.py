#!/usr/bin/env python3
"""
Convert Excalidraw skeleton elements to full elements using the official API
running in a real browser context (via Playwright).

Stdin: JSON array of ExcalidrawElementSkeleton objects
Stdout: JSON array of fully-qualified ExcalidrawElement objects

Usage:
    echo '[{"type":"rectangle","x":0,"y":0,"label":{"text":"Hello"}}]' | python3 skeleton_to_elements.py
    python3 skeleton_to_elements.py --spec '[...]'
    python3 skeleton_to_elements.py --file input.json
"""

import json
import sys
import argparse
from playwright.sync_api import sync_playwright


HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>
<div id="status">loading</div>
<script type="module">
try {
    const mod = await import("https://esm.sh/@excalidraw/excalidraw@0.18.0?bundle&deps=react@18,react-dom@18");
    window.__convertToExcalidrawElements = mod.convertToExcalidrawElements;
    window.__ready = true;
    document.getElementById("status").textContent = "ready";
} catch (e) {
    window.__error = e.message;
    document.getElementById("status").textContent = "error: " + e.message;
}
</script>
</body>
</html>"""


def convert_skeleton(skeleton: list[dict], regenerate_ids: bool = False) -> list[dict]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.on("console", lambda msg: None)  # suppress console noise
        page.set_content(HTML_TEMPLATE)
        page.wait_for_function("window.__ready === true || window.__error", timeout=30000)

        error = page.evaluate("window.__error")
        if error:
            browser.close()
            raise RuntimeError(f"Failed to load Excalidraw: {error}")

        result = page.evaluate(
            """(args) => {
                const [skeleton, opts] = args;
                const elements = window.__convertToExcalidrawElements(skeleton, opts);
                return JSON.parse(JSON.stringify(elements));
            }""",
            [skeleton, {"regenerateIds": regenerate_ids}],
        )

        browser.close()
        return result


def main():
    parser = argparse.ArgumentParser(description="Convert skeleton to full Excalidraw elements")
    parser.add_argument("--spec", help="JSON skeleton spec (inline)")
    parser.add_argument("--file", help="Path to JSON file with skeleton spec")
    parser.add_argument("--regenerate-ids", action="store_true", help="Regenerate element IDs")
    parser.add_argument("--output", "-o", help="Output file path (default: stdout)")
    args = parser.parse_args()

    if args.spec:
        skeleton = json.loads(args.spec)
    elif args.file:
        with open(args.file) as f:
            skeleton = json.load(f)
    elif not sys.stdin.isatty():
        skeleton = json.load(sys.stdin)
    else:
        print("ERROR: provide --spec, --file, or pipe JSON to stdin", file=sys.stderr)
        sys.exit(1)

    elements = convert_skeleton(skeleton, regenerate_ids=args.regenerate_ids)

    output = json.dumps(elements, indent=2)
    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
    else:
        print(output)


if __name__ == "__main__":
    main()
