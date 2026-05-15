#!/usr/bin/env python3
"""Shared canvas utilities for excalidraw helpers."""


def get_element_bounds(element: dict) -> dict:
    return {
        "x": element["x"],
        "y": element["y"],
        "x2": element["x"] + element.get("width", 0),
        "y2": element["y"] + element.get("height", 0),
    }


def get_canvas_bounds(elements: list[dict]) -> dict | None:
    """Compute bounding box of all non-deleted, non-text elements."""
    active = [e for e in elements if not e.get("isDeleted") and e["type"] != "text"
              and e.get("width", 0) > 0]
    if not active:
        return None
    min_x = min(e["x"] for e in active)
    min_y = min(e["y"] for e in active)
    max_x = max(e["x"] + e.get("width", 0) for e in active)
    max_y = max(e["y"] + e.get("height", 0) for e in active)
    return {"x": min_x, "y": min_y, "x2": max_x, "y2": max_y}


def detect_frames(elements: list[dict]) -> list[dict]:
    """Find frame rectangles: transparent-bg rects enclosing >50% of non-text elements.

    Returns list of bounds dicts for each detected frame.
    """
    non_text = [e for e in elements if e["type"] != "text" and not e.get("isDeleted")
                and e.get("width", 0) > 0]
    if not non_text:
        return []

    canvas = get_canvas_bounds(elements)
    canvas_area = ((canvas["x2"] - canvas["x"]) * (canvas["y2"] - canvas["y"])) if canvas else 1

    frames = []
    for e in elements:
        if e.get("isDeleted") or e["type"] != "rectangle":
            continue
        if e.get("backgroundColor") not in (None, "transparent"):
            continue
        eb = get_element_bounds(e)
        e_area = (eb["x2"] - eb["x"]) * (eb["y2"] - eb["y"])

        # Count how many non-text elements this rect fully contains
        others = [o for o in non_text if o["id"] != e["id"]]
        if not others:
            continue
        contained = sum(1 for o in others
                        if eb["x"] <= o["x"] and eb["y"] <= o["y"]
                        and eb["x2"] >= o["x"] + o.get("width", 0)
                        and eb["y2"] >= o["y"] + o.get("height", 0))

        # Frame if it contains >50% of elements OR covers >60% of canvas area
        if contained > len(others) * 0.5 or e_area > canvas_area * 0.6:
            frames.append({"id": e["id"], **eb})

    return frames


def get_frame_ids(elements: list[dict]) -> set[str]:
    """Return set of element IDs that are detected as frames."""
    return {f["id"] for f in detect_frames(elements)}
