#!/usr/bin/env python3
"""Validate that a diagram has a title per SKILL.md.

A title is a free-floating text element (containerId is null/missing) that:
  - has fontSize >= 22
  - sits in the top 25% of the diagram bbox by Y
  - is not a shape-anchored annotation (does not vertically overlap any
    shape's Y-span while sitting within 30px horizontally of that shape)

Emits:
  FAIL:NO_TITLE         no element matches
  WARN:TITLE_SIZE       title fontSize is < 24 or > 30
  INFO:TITLE_PATTERN    title looks like a topic ("Architecture") not a takeaway

Exit code 0 unless usage error or unreadable file. (Validators don't fail
the build by exit code; collisions/check_title share output style.)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_HELPERS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HELPERS))

from core.excalidraw_core import get_canvas_bounds, get_element_bounds  # noqa: E402

TITLE_FS_MIN = 22
TITLE_FS_LOW_WARN = 24
TITLE_FS_HIGH_WARN = 30
TOP_BAND_RATIO = 0.25
SHAPE_EDGE_GAP = 30

_SHAPE_TYPES = {"rectangle", "ellipse", "diamond"}

_VERB_LIKE = re.compile(
    r"\b("
    r"is|are|was|were|be|been|being|"
    r"has|have|had|"
    r"do|does|did|"
    r"can|cannot|can't|won't|will|wont|shall|should|would|could|may|might|must|"
    r"makes?|made|"
    r"runs?|ran|"
    r"shows?|showed|"
    r"works?|worked|"
    r"goes|went|"
    r"flows?|flowed|"
    r"loops?|looped|"
    r"branches|branched|"
    r"becomes?|became|"
    r"deepens?|deepened|"
    r"delivers?|delivered|"
    r"routes?|routed|"
    r"processes|processed|"
    r"teaches|taught|"
    r"argues?|argued|"
    r"compares?|compared|"
    r"connects?|connected|"
    r"separates?|separated|"
    r"transforms?|transformed|"
    r"converts?|converted|"
    r"sends?|sent|"
    r"receives?|received|"
    r"calls?|called|"
    r"triggers?|triggered|"
    r"falls?|fell|"
    r"rises?|rose|"
    r"grows?|grew|"
    r"drops?|dropped|"
    r"means?|meant|"
    r"creates?|created|"
    r"breaks?|broke|"
    r"saves?|saved|"
    r"costs?|cost|"
    r"needs?|needed|"
    r"requires?|required|"
    r"meets?|met|"
    r"crosses|crossed|"
    r"steps?|stepped|"
    r"works?|worked|"
    r"leads?|led|"
    r"keeps?|kept|"
    r"holds?|held"
    r")\b",
    re.IGNORECASE,
)


def _free_text_elements(elements: list[dict]) -> list[dict]:
    out = []
    for e in elements:
        if e.get("isDeleted"):
            continue
        if e.get("type") != "text":
            continue
        cid = e.get("containerId")
        if cid:
            continue
        out.append(e)
    return out


def _diagram_bbox(elements: list[dict]) -> dict | None:
    """Bbox of non-text shapes if any exist; otherwise bbox of free text.

    Falls back to text-only so a text-only / sketch-only canvas still has a
    band to measure against.
    """
    cb = get_canvas_bounds(elements)
    if cb:
        return cb
    free = _free_text_elements(elements)
    if not free:
        return None
    xs = [e["x"] for e in free]
    ys = [e["y"] for e in free]
    x2s = [e["x"] + e.get("width", 0) for e in free]
    y2s = [e["y"] + e.get("height", 0) for e in free]
    return {"x": min(xs), "y": min(ys), "x2": max(x2s), "y2": max(y2s)}


def _is_shape_anchored_annotation(text_el: dict, shapes: list[dict], gap: float) -> bool:
    """True if the text reads as a shape-adjacent label rather than a free title.

    A title sits ABOVE the diagram body with whitespace; an annotation sits
    among or beside shapes. Heuristic: the text overlaps a shape vertically
    (its Y-span intersects a shape's Y-span) AND is within `gap` horizontally,
    OR it sits inside a shape's Y-span entirely. Titles that sit fully above
    every shape (text bottom <= shape top) are never flagged.
    """
    tb = get_element_bounds(text_el)
    for s in shapes:
        sb = get_element_bounds(s)
        # Vertical overlap between text and shape (0 = no overlap).
        v_overlap = min(tb["y2"], sb["y2"]) - max(tb["y"], sb["y"])
        if v_overlap <= 0:
            continue
        # Horizontal proximity.
        dx = max(sb["x"] - tb["x2"], tb["x"] - sb["x2"], 0)
        if dx < gap:
            return True
    return False


def _looks_like_action_title(text: str) -> bool:
    """True if the text reads like a takeaway sentence rather than a topic label.

    Heuristics:
      - More than 4 words AND contains a verb-like token, OR
      - Contains a colon followed by descriptive content ("X: Y"), OR
      - Ends with sentence punctuation, OR
      - Contains a digit + unit phrase suggesting a metric ("6x", "500 records").
    """
    flat = text.replace("\n", " ").strip()
    if not flat:
        return False
    words = flat.split()
    has_verb = bool(_VERB_LIKE.search(flat))
    if len(words) > 4 and has_verb:
        return True
    if ":" in flat and len(flat.split(":", 1)[1].strip().split()) >= 2:
        return True
    if flat.endswith((".", "!", "?")):
        return True
    if re.search(r"\b\d+\s*(x|%|ms|s|min|hrs?|days?|records?|users?|requests?)\b",
                 flat, re.IGNORECASE):
        return True
    if re.search(r"\bfrom\s+\w+\s+to\s+\w+", flat, re.IGNORECASE):
        return True
    return False


def check_title(filepath: str) -> tuple[int, list[str]]:
    """Run the title check. Returns (exit_code, lines)."""
    data = json.loads(Path(filepath).read_text())
    elements = data.get("elements", [])

    bbox = _diagram_bbox(elements)
    if bbox is None:
        return 0, ["FAIL:NO_TITLE — empty diagram (no elements to anchor a title)"]

    height = bbox["y2"] - bbox["y"]
    if height <= 0:
        height = 1
    top_band_y = bbox["y"] + TOP_BAND_RATIO * height

    free_texts = _free_text_elements(elements)
    shapes = [e for e in elements
              if not e.get("isDeleted")
              and e.get("type") in _SHAPE_TYPES
              and e.get("width", 0) > 0]

    candidates: list[dict] = []
    for t in free_texts:
        fs = t.get("fontSize", 0) or 0
        if fs < TITLE_FS_MIN:
            continue
        if t.get("y", 0) > top_band_y:
            continue
        if _is_shape_anchored_annotation(t, shapes, SHAPE_EDGE_GAP):
            continue
        candidates.append(t)

    if not candidates:
        return 0, ["FAIL:NO_TITLE — no free-floating text "
                   f"(fontSize >= {TITLE_FS_MIN}, in top {int(TOP_BAND_RATIO*100)}% by Y, "
                   f"not adjacent to a shape) found"]

    # Pick the topmost candidate; tie-break by larger fontSize.
    title = min(candidates, key=lambda e: (e.get("y", 0), -e.get("fontSize", 0)))
    fs = title.get("fontSize", 0)
    text = title.get("text", "") or ""
    preview = text.replace("\n", " ")[:60]

    lines: list[str] = []
    if fs < TITLE_FS_LOW_WARN or fs > TITLE_FS_HIGH_WARN:
        lines.append(
            f"WARN:TITLE_SIZE — title fontSize={fs} (expected "
            f"{TITLE_FS_LOW_WARN}-{TITLE_FS_HIGH_WARN}); text={preview!r}"
        )
    if not _looks_like_action_title(text):
        lines.append(
            f"INFO:TITLE_PATTERN — title looks like a topic, not a takeaway; "
            f"text={preview!r}"
        )

    if not lines:
        lines.append(f"OK: title found (fs={fs}) — {preview!r}")
    return 0, lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate diagram has a title.")
    parser.add_argument("file", help="Path to .excalidraw file")
    args = parser.parse_args()

    try:
        code, lines = check_title(args.file)
    except FileNotFoundError:
        print(f"ERROR: file not found: {args.file}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: not a valid JSON .excalidraw file: {exc}", file=sys.stderr)
        return 2

    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
