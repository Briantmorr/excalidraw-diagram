"""Rubric targets for diagram quality scoring.

Empirically calibrated from gold set test_set_v13 (see calibrate.py output).
Five deliberate exceedances tag where we go beyond gold for sharper rubric scores;
those are noted as `# BEYOND_GOLD` comments inline.
"""

from __future__ import annotations

from typing import Literal, TypedDict

ShapeVariety = Literal[
    "uniform",
    "uniform_intentional",
    "hub_distinct",
    "sink_distinct",
    "diamond_root",
    "size_encoded",
    "mirror",
    "barrier_distinct",
    "container_distinct",
]


class PatternTargets(TypedDict):
    area_ratio_min: float
    gap_h: int
    gap_v: int
    canvas_max: tuple[int, int]
    shape_variety: ShapeVariety
    n_arrows_eq_n_shapes_minus_1: bool


class GlobalTargets(TypedDict):
    font_size_title: int
    font_size_body: int
    font_size_subordinate: int
    font_size_annotation: int
    min_font: int
    max_distinct_fills: int
    min_spine_count: int
    canvas_compactness_target: float
    text_bbox_ratio: float
    text_color_body: str
    text_color_subordinate: str
    border_color: str
    arrow_color: str
    background_color: str
    font_family: int
    palette: tuple[str, ...]


# Global rubric targets: applied across every pattern.
RUBRIC_TARGETS: GlobalTargets = {
    "font_size_title": 28,
    "font_size_body": 16,
    "font_size_subordinate": 14,
    "font_size_annotation": 12,
    "min_font": 12,
    "max_distinct_fills": 5,         # BEYOND_GOLD: gold uses 4-5; cap at 5
    "min_spine_count": 3,            # ≥3 same-Y elements must share spine
    "canvas_compactness_target": 0.45,  # gold median ~0.39; BEYOND_GOLD push to 0.45
    "text_bbox_ratio": 0.62,         # BEYOND_GOLD: was 0.55, empirically 0.62 fits Excalifont
    "text_color_body": "#0a0a0a",
    "text_color_subordinate": "#868e96",
    "border_color": "#000000",
    "arrow_color": "#3a3428",
    "background_color": "#ffffff",
    "font_family": 1,
    # Top fills observed in gold (frequency-ordered): neutral, green, blue, orange, red, yellow.
    "palette": (
        "#eae8e4",
        "#e0f4e8",
        "#e7f5ff",
        "#fff4e0",
        "#ffd4d0",
        "#fff9db",
    ),
}


# Per-pattern overrides. Defaults derived from gold computed by calibrate.py;
# beyond-gold deviations called out inline.
PER_PATTERN: dict[str, PatternTargets] = {
    "pipeline": {
        "area_ratio_min": 1.00,
        "gap_h": 25,                  # BEYOND_GOLD: gold t7 60-80 was loose; lock 25 for tight L→R scan
        "gap_v": 30,
        "canvas_max": (1100, 200),
        "shape_variety": "uniform",
        "n_arrows_eq_n_shapes_minus_1": True,
    },
    "fanout": {
        "area_ratio_min": 3.00,       # BEYOND_GOLD: gold t1=2.75; push hub:spoke to 3.43 (240x120 vs 140x60)
        "gap_h": 35,
        "gap_v": 100,
        "canvas_max": (900, 450),
        "shape_variety": "hub_distinct",
        "n_arrows_eq_n_shapes_minus_1": False,
    },
    "convergence": {
        "area_ratio_min": 3.00,
        "gap_h": 35,
        "gap_v": 100,
        "canvas_max": (900, 450),
        "shape_variety": "sink_distinct",
        "n_arrows_eq_n_shapes_minus_1": False,
    },
    "decision_tree": {
        "area_ratio_min": 2.50,       # gold t2=2.43; nudge to 2.50 to make root diamond unmistakable
        "gap_h": 40,
        "gap_v": 80,
        "canvas_max": (700, 600),
        "shape_variety": "diamond_root",
        "n_arrows_eq_n_shapes_minus_1": False,
    },
    "comparison_grid": {
        "area_ratio_min": 1.00,
        "gap_h": 0,
        "gap_v": 0,
        "canvas_max": (700, 400),
        "shape_variety": "uniform_intentional",
        "n_arrows_eq_n_shapes_minus_1": False,
    },
    "weight_map": {
        "area_ratio_min": 3.50,       # BEYOND_GOLD: gold t4=2.75; push to 3.50 for clearer size-encoded weight
        "gap_h": 40,
        "gap_v": 40,
        "canvas_max": (800, 550),
        "shape_variety": "size_encoded",
        "n_arrows_eq_n_shapes_minus_1": False,
    },
    "timeline": {
        "area_ratio_min": 1.00,
        "gap_h": 200,                 # gold t5 ~90 between shape edges (full step ~340 center-to-center)
        "gap_v": 0,
        "canvas_max": (1300, 220),
        "shape_variety": "uniform_intentional",
        "n_arrows_eq_n_shapes_minus_1": True,
    },
    "side_by_side": {
        "area_ratio_min": 2.00,
        "gap_h": 60,
        "gap_v": 25,
        "canvas_max": (900, 500),
        "shape_variety": "mirror",
        "n_arrows_eq_n_shapes_minus_1": False,
    },
    "hub_spoke": {
        "area_ratio_min": 3.00,       # BEYOND_GOLD: same as fanout — 3.43 hub:spoke
        "gap_h": 35,
        "gap_v": 100,
        "canvas_max": (900, 600),
        "shape_variety": "hub_distinct",
        "n_arrows_eq_n_shapes_minus_1": False,
    },
    "storyboard": {
        "area_ratio_min": 1.00,
        "gap_h": 60,
        "gap_v": 0,
        "canvas_max": (1000, 350),
        "shape_variety": "uniform_intentional",
        "n_arrows_eq_n_shapes_minus_1": False,
    },
    "cycle": {
        "area_ratio_min": 1.20,
        "gap_h": 80,
        "gap_v": 80,
        "canvas_max": (700, 600),     # BEYOND_GOLD: gold t7=1260x410 sprawled; tight ring at 700x600
        "shape_variety": "uniform",
        "n_arrows_eq_n_shapes_minus_1": False,
    },
    "gate_barrier": {
        "area_ratio_min": 4.00,
        "gap_h": 60,
        "gap_v": 25,
        "canvas_max": (900, 400),
        "shape_variety": "barrier_distinct",
        "n_arrows_eq_n_shapes_minus_1": False,
    },
    "nested_container": {
        "area_ratio_min": 4.00,
        "gap_h": 25,
        "gap_v": 25,
        "canvas_max": (800, 500),
        "shape_variety": "container_distinct",
        "n_arrows_eq_n_shapes_minus_1": False,
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

# Free-floating text heights (height in px, used by title/annotation roles).
DEFAULT_TEXT_HEIGHTS: dict[str, int] = {
    "title_text": 36,
}


def pattern_target(pattern: str) -> PatternTargets:
    """Return the per-pattern targets, falling back to pipeline defaults if unknown."""
    return PER_PATTERN.get(pattern, PER_PATTERN["pipeline"])
