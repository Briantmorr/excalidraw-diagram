#!/usr/bin/env python3
"""Remove an element from an excalidraw canvas by ID."""

import json
import argparse
from pathlib import Path


def remove(filepath: str, element_id: str) -> str:
    path = Path(filepath)
    data = json.loads(path.read_text())
    elements = data.get("elements", [])

    original_count = len(elements)
    elements = [e for e in elements if e["id"] != element_id]

    if len(elements) == original_count:
        return f"ERROR: element '{element_id}' not found"

    data["elements"] = elements
    path.write_text(json.dumps(data, indent=2))
    return f"OK: removed '{element_id}' ({original_count} -> {len(elements)} elements)"


def main():
    parser = argparse.ArgumentParser(description="Remove element from excalidraw canvas")
    parser.add_argument("file", help="Path to .excalidraw file")
    parser.add_argument("--id", required=True, help="Element ID to remove")

    args = parser.parse_args()
    print(remove(args.file, args.id))


if __name__ == "__main__":
    main()
