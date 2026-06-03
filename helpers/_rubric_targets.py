"""Rubric targets for diagram quality scoring.

Empirically calibrated from gold set test_set_v13. BEYOND_GOLD comments mark
where we deliberately exceed gold defaults for sharper rubric scores.

Wiring status (as of Round 7): GlobalTargets fields are read by patterns.py
(font_size_*, max_distinct_fills, text_bbox_ratio) and validate.py (color
constants, font_family). PatternTargets fields gap_h/gap_v/canvas_max are
read by patterns.py per-pattern. Other fields are documented intent that
validators may consume in later rounds.
"""

from __future__ import annotations

from typing import TypedDict


class PatternTargets(TypedDict):
    gap_h: int
    gap_v: int
    canvas_max: tuple[int, int]


class GlobalTargets(TypedDict):
    font_size_title: int
    font_size_body: int
    font_size_subordinate: int
    font_size_annotation: int
    max_distinct_fills: int
    text_bbox_ratio: float
    text_color_body: str
    text_color_subordinate: str
    border_color: str
    arrow_color: str
    background_color: str
    font_family: int


# Global rubric targets: applied across every pattern.
RUBRIC_TARGETS: GlobalTargets = {
    "font_size_title": 28,
    "font_size_body": 16,
    "font_size_subordinate": 14,
    "font_size_annotation": 12,
    "max_distinct_fills": 5,         # BEYOND_GOLD: gold uses 4-5; cap at 5
    "text_bbox_ratio": 0.62,         # BEYOND_GOLD: was 0.55, empirically 0.62 fits Excalifont
    "text_color_body": "#0a0a0a",
    "text_color_subordinate": "#868e96",
    "border_color": "#000000",
    "arrow_color": "#3a3428",
    "background_color": "#ffffff",
    "font_family": 1,
}


# Per-pattern overrides. Defaults derived from gold; beyond-gold deviations inline.
PER_PATTERN: dict[str, PatternTargets] = {
    "pipeline": {
        "gap_h": 25,                  # BEYOND_GOLD: gold t7 60-80 was loose; lock 25 for tight L→R scan
        "gap_v": 30,
        "canvas_max": (1100, 200),
    },
    "fanout": {
        "gap_h": 35,
        "gap_v": 100,
        "canvas_max": (900, 450),
    },
    "decision_tree": {
        "gap_h": 40,
        "gap_v": 80,
        "canvas_max": (700, 600),
    },
    "comparison_grid": {
        "gap_h": 0,
        "gap_v": 0,
        "canvas_max": (700, 400),
    },
    "weight_map": {
        "gap_h": 40,
        "gap_v": 40,
        "canvas_max": (800, 550),
    },
    "timeline": {
        "gap_h": 200,                 # gold t5 ~90 between shape edges (full step ~340 center-to-center)
        "gap_v": 0,
        "canvas_max": (1300, 220),
    },
    "side_by_side": {
        "gap_h": 60,
        "gap_v": 25,
        "canvas_max": (900, 500),
    },
    "hub_spoke": {
        "gap_h": 35,
        "gap_v": 100,
        "canvas_max": (900, 600),
    },
    "storyboard": {
        "gap_h": 60,
        "gap_v": 0,
        "canvas_max": (1000, 350),
    },
    "nested_container": {
        "gap_h": 25,
        "gap_v": 25,
        "canvas_max": (800, 500),
    },
}


# Default shape sizes per role. Body shapes derive from gold medians
# (rectangle 150x50, ellipse 145x80, diamond 170x120).
DEFAULT_SIZES: dict[str, tuple[int, int]] = {
    "rectangle": (150, 50),
    "ellipse": (145, 80),
    "diamond": (170, 120),
    "hub_rectangle": (240, 120),     # BEYOND_GOLD: hub default scaled for 3.43 area ratio
    "hub_ellipse": (220, 130),
    "spoke_rectangle": (140, 60),
    "spoke_ellipse": (140, 70),
    "weight_heavy": (220, 130),      # BEYOND_GOLD: weight_map heavy default
    "weight_light": (110, 65),       # area ratio 220*130 / 110*65 = 4.0
}


def pattern_target(pattern: str) -> PatternTargets:
    """Return per-pattern targets, falling back to pipeline defaults if unknown."""
    return PER_PATTERN.get(pattern, PER_PATTERN["pipeline"])
