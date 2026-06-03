from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any

from helpers._rubric_targets import (
    DEFAULT_SIZES,
    PER_PATTERN,
    RUBRIC_TARGETS,
    pattern_target,
)

BORDER_COLOR: str = "#000000"
ARROW_COLOR: str = "#3a3428"
BG_COLOR: str = "#ffffff"
TEXT_BODY: str = "#0a0a0a"
TEXT_SUBORDINATE: str = "#868e96"
DEFAULT_FONT_FAMILY: int = 1
TEXT_BBOX_RATIO: float = 0.62

PALETTE: dict[str, str] = {
    "grey": "#eae8e4",
    "blue": "#e7f5ff",
    "green": "#e0f4e8",
    "mint": "#d3f9d8",
    "yellow": "#fff9db",
    "red": "#ffd4d0",
    "cream": "#fff4e0",
    "silver": "#f1f3f5",
    "charcoal_arrow": ARROW_COLOR,
    "black_border": BORDER_COLOR,
    "body_text": TEXT_BODY,
    "subordinate_text": TEXT_SUBORDINATE,
}


SHAPE_DEFAULTS: dict[str, Any] = {
    "fillStyle": "solid",
    "strokeWidth": 2,
    "strokeStyle": "solid",
    "strokeColor": BORDER_COLOR,
    "roughness": 1,
    "opacity": 100,
    "angle": 0,
    "groupIds": [],
    "boundElements": [],
    "link": None,
    "locked": False,
    "isDeleted": False,
    "frameId": None,
    "roundness": None,
    "hasTextLink": False,
}

TEXT_DEFAULTS: dict[str, Any] = {
    **SHAPE_DEFAULTS,
    "fontFamily": DEFAULT_FONT_FAMILY,
    "strokeColor": TEXT_BODY,
    "backgroundColor": "transparent",
    "strokeWidth": 1,
    "roughness": 0,
    "lineHeight": 1.25,
    "autoResize": True,
}

ARROW_DEFAULTS: dict[str, Any] = {
    "fillStyle": "solid",
    "strokeWidth": 2,
    "strokeStyle": "solid",
    "strokeColor": ARROW_COLOR,
    "backgroundColor": "transparent",
    "roughness": 1,
    "opacity": 100,
    "angle": 0,
    "groupIds": [],
    "boundElements": [],
    "link": None,
    "locked": False,
    "isDeleted": False,
    "frameId": None,
    "roundness": {"type": 2},
    "startArrowhead": None,
    "endArrowhead": "arrow",
    "elbowed": False,
    "hasTextLink": False,
}


@dataclass(frozen=True)
class RolePreset:
    width: int
    height: int
    text_size: int
    bg: str | None = None
    stroke_width: int = 2
    shape: str = "rectangle"


ROLE_PRESETS: dict[str, RolePreset] = {
    "stage":      RolePreset(width=210, height=80,  text_size=18, stroke_width=3, bg=PALETTE["grey"]),
    "branch":     RolePreset(width=220, height=120, text_size=16, bg=PALETTE["yellow"], shape="diamond"),
    "hub":        RolePreset(width=240, height=120, text_size=18, stroke_width=3, bg=PALETTE["blue"]),
    "spoke":      RolePreset(width=140, height=60,  text_size=14, bg=PALETTE["blue"]),
    "sink":       RolePreset(width=240, height=120, text_size=18, stroke_width=3, bg=PALETTE["green"]),
    "step":       RolePreset(width=150, height=50,  text_size=14, bg=PALETTE["grey"]),
    "barrier":    RolePreset(width=80,  height=200, text_size=14, bg=PALETTE["red"]),
    "container":  RolePreset(width=400, height=300, text_size=16, bg=None),
    "weight_heavy": RolePreset(width=220, height=130, text_size=16, bg=PALETTE["red"]),
    "weight_light": RolePreset(width=110, height=65,  text_size=12, bg=PALETTE["grey"]),
    "annotation": RolePreset(width=0, height=0, text_size=12, shape="text"),
    "title":      RolePreset(width=0, height=0, text_size=28, shape="text"),
}


@dataclass
class Bounds:
    x: float
    y: float
    x2: float
    y2: float

    @property
    def width(self) -> float: return self.x2 - self.x
    @property
    def height(self) -> float: return self.y2 - self.y
    @property
    def cx(self) -> float: return (self.x + self.x2) / 2
    @property
    def cy(self) -> float: return (self.y + self.y2) / 2


@dataclass
class Element:
    id: str
    type: str
    x: float
    y: float
    width: float = 0
    height: float = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type, "x": self.x, "y": self.y,
                "width": self.width, "height": self.height, **self.extra}


@dataclass
class Spec:
    id: str
    role: str
    text: str = ""
    x: float = 0
    y: float = 0
    width: float | None = None
    height: float | None = None
    bg: str | None = None
    shape: str | None = None


def gen_seed() -> int:
    return random.randint(100_000, 9_999_999)


def gen_nonce() -> int:
    return random.randint(100_000_000, 2_147_483_647)


def now_ms() -> int:
    return int(time.time() * 1000)


_BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def frac_index(base: str, n: int) -> str:
    if not (0 <= n < 36 * 36):
        raise ValueError(f"frac_index n must be in [0, {36 * 36}); got {n}")
    hi, lo = divmod(n, 36)
    return f"{base}{_BASE36[hi]}{_BASE36[lo]}"


def next_index(elements: list[dict]) -> str:
    indices = sorted(e["index"] for e in elements if e.get("index"))
    if not indices:
        return "a00"
    return indices[-1] + "0"


def text_width(s: str, fs: int | float) -> float:
    if not s:
        return 0.0
    longest = max((line for line in s.split("\n")), key=len, default="")
    return len(longest) * fs * TEXT_BBOX_RATIO


def text_height(lines: int, fs: int | float) -> float:
    return lines * fs * 1.25


def SAFE_BINDING(element_id: str, focus: float = 0.5, gap: int = 8) -> dict[str, Any]:
    return {"elementId": element_id, "focus": focus, "gap": gap}


def emit_bound_text(parent: dict, text: str, font_size: int = 14) -> dict[str, Any]:
    text = text.replace("\\n", "\n")
    lines = text.split("\n")
    tw = text_width(text, font_size)
    th = text_height(len(lines), font_size)
    px = parent["x"]
    py = parent["y"]
    pw = parent.get("width", 0)
    ph = parent.get("height", 0)
    parent_id = parent["id"]
    text_id = f"{parent_id}_text"
    return {
        **TEXT_DEFAULTS,
        "type": "text",
        "id": text_id,
        "x": px + (pw - tw) / 2,
        "y": py + (ph - th) / 2,
        "width": tw,
        "height": th,
        "text": text,
        "originalText": text,
        "rawText": text,
        "fontSize": font_size,
        "fontFamily": DEFAULT_FONT_FAMILY,
        "textAlign": "center",
        "verticalAlign": "middle",
        "strokeColor": TEXT_BODY,
        "seed": gen_seed(),
        "version": 1,
        "versionNonce": gen_nonce(),
        "updated": now_ms(),
        "containerId": parent_id,
    }


def emit_free_text(
    text: str,
    x: float,
    y: float,
    font_size: int = 14,
    color: str = TEXT_BODY,
    align: str = "left",
    text_id: str | None = None,
) -> dict[str, Any]:
    text = text.replace("\\n", "\n")
    lines = text.split("\n")
    tw = text_width(text, font_size)
    th = text_height(len(lines), font_size)
    return {
        **TEXT_DEFAULTS,
        "type": "text",
        "id": text_id or f"text_{gen_nonce()}",
        "x": x,
        "y": y,
        "width": tw,
        "height": th,
        "text": text,
        "originalText": text,
        "rawText": text,
        "fontSize": font_size,
        "fontFamily": DEFAULT_FONT_FAMILY,
        "textAlign": align,
        "verticalAlign": "top",
        "strokeColor": color,
        "seed": gen_seed(),
        "version": 1,
        "versionNonce": gen_nonce(),
        "updated": now_ms(),
        "containerId": None,
    }


def get_element_bounds(e: dict) -> Bounds:
    w = e.get("width", 0) or 0
    h = e.get("height", 0) or 0
    return Bounds(x=e["x"], y=e["y"], x2=e["x"] + w, y2=e["y"] + h)


def get_canvas_bounds(elements: list[dict]) -> Bounds | None:
    active = [e for e in elements
              if not e.get("isDeleted")
              and e.get("type") != "text"
              and (e.get("width", 0) or 0) > 0]
    if not active:
        return None
    min_x = min(e["x"] for e in active)
    min_y = min(e["y"] for e in active)
    max_x = max(e["x"] + e["width"] for e in active)
    max_y = max(e["y"] + e["height"] for e in active)
    return Bounds(min_x, min_y, max_x, max_y)


def detect_frames(elements: list[dict]) -> list[dict]:
    non_text = [e for e in elements
                if e.get("type") != "text"
                and not e.get("isDeleted")
                and (e.get("width", 0) or 0) > 0]
    if not non_text:
        return []

    canvas = get_canvas_bounds(elements)
    canvas_area = canvas.width * canvas.height if canvas else 1.0

    frames: list[dict] = []
    for e in elements:
        if e.get("isDeleted") or e.get("type") != "rectangle":
            continue
        if e.get("backgroundColor") not in (None, "transparent"):
            continue
        eb = get_element_bounds(e)
        e_area = eb.width * eb.height
        others = [o for o in non_text if o["id"] != e["id"]]
        if not others:
            continue
        contained = sum(
            1 for o in others
            if eb.x <= o["x"]
            and eb.y <= o["y"]
            and eb.x2 >= o["x"] + (o.get("width", 0) or 0)
            and eb.y2 >= o["y"] + (o.get("height", 0) or 0)
        )
        if contained > len(others) * 0.5 or e_area > canvas_area * 0.6:
            frames.append({"id": e["id"], "x": eb.x, "y": eb.y, "x2": eb.x2, "y2": eb.y2})
    return frames


def get_frame_ids(elements: list[dict]) -> set[str]:
    return {f["id"] for f in detect_frames(elements)}


def recenter_text(
    elements: list[dict], parent: dict,
    old_x: float, old_y: float, old_w: float, old_h: float,
) -> None:
    new_x = parent.get("x", old_x)
    new_y = parent.get("y", old_y)
    new_w = parent.get("width", old_w)
    new_h = parent.get("height", old_h)
    moved = new_x != old_x or new_y != old_y
    resized = new_w != old_w or new_h != old_h
    if not (moved or resized):
        return
    parent_id = parent["id"]
    old_cx = old_x + old_w / 2
    old_cy = old_y + old_h / 2
    for e in elements:
        if e.get("type") != "text":
            continue
        if e.get("containerId") == parent_id:
            tw, th = e.get("width", 0), e.get("height", 0)
            if resized:
                e["x"] = new_x + (new_w - tw) / 2
                e["y"] = new_y + (new_h - th) / 2
            else:
                e["x"] += new_x - old_x
                e["y"] += new_y - old_y
            e["version"] = e.get("version", 1) + 1
        elif e.get("containerId") is None:
            ew, eh = e.get("width", 0), e.get("height", 0)
            if abs(e["x"] + ew / 2 - old_cx) < 30 and abs(e["y"] + eh / 2 - old_cy) < 30:
                e["x"] = new_x + (new_w - ew) / 2
                e["y"] = new_y + (new_h - eh) / 2
                e["version"] = e.get("version", 1) + 1


def appstate_defaults() -> dict[str, Any]:
    return {"gridSize": None, "viewBackgroundColor": BG_COLOR, "isBindingEnabled": True}
