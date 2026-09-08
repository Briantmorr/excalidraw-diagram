"""Design constants for the diagram patterns.

Font sizes, colors, per-pattern gaps/canvas budgets, and default shape sizes —
read by patterns.py and place.py on every pattern call, and by validate.py for
the color/font invariants. These are load-bearing layout constants, not scoring
knobs; change them only with a rendered before/after in hand.
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
    "max_distinct_fills": 5,         # cap at 5 distinct fills
    "text_bbox_ratio": 0.62,         # empirical: 0.62 fits Excalifont
    "text_color_body": "#0a0a0a",
    "text_color_subordinate": "#868e96",
    "border_color": "#000000",
    "arrow_color": "#3a3428",
    "background_color": "#ffffff",
    "font_family": 1,
}


# Per-pattern layout overrides (gaps + canvas budget).
PER_PATTERN: dict[str, PatternTargets] = {
    "pipeline": {
        "gap_h": 25,                  # tight L→R scan
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
        "gap_h": 200,                 # ~340 center-to-center per step
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
    "cycle": {
        "gap_h": 50,                  # min edge separation between ring neighbours
        "gap_v": 50,
        "canvas_max": (760, 760),
    },
}


# Default shape sizes per role (body: rectangle 150x50, ellipse 145x80, diamond 170x120).
DEFAULT_SIZES: dict[str, tuple[int, int]] = {
    "rectangle": (150, 50),
    "ellipse": (145, 80),
    "diamond": (170, 120),
    "hub_rectangle": (240, 120),     # hub scaled for ~3.4x area ratio vs spokes
    "hub_ellipse": (220, 130),
    "spoke_rectangle": (140, 60),
    "spoke_ellipse": (140, 70),
    "weight_heavy": (220, 130),      # weight_map heavy default
    "weight_light": (110, 65),       # area ratio 220*130 / 110*65 = 4.0
}


def pattern_target(pattern: str) -> PatternTargets:
    """Return per-pattern targets, falling back to pipeline defaults if unknown."""
    return PER_PATTERN.get(pattern, PER_PATTERN["pipeline"])
