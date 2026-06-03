#!/usr/bin/env python3
"""Chat2SVG Stage-1: text prompt -> LLM-generated SVG -> Excalidraw freedraw.

Implements Stage 1 of Chat2SVG (CVPR 2025) without GPU/diffvg dependencies.
Uses Claude via the SAP gateway (ANTHROPIC_BASE_URL/ANTHROPIC_AUTH_TOKEN env)
to expand a text prompt and emit a constrained SVG, then samples the SVG
primitives into Excalidraw freedraw point arrays.

Stage 2 (SDXL+ControlNet detail) and Stage 3 (VAE optimization) are CUDA-only
and skipped here.

Usage:
    python3 chat2svg_sketch.py "a unicorn eating a carrot" out.excalidraw
    python3 chat2svg_sketch.py "lighthouse on cliff" out.excalidraw --refine 1
    python3 chat2svg_sketch.py "apple" out.excalidraw --scale 1.5 --x 100 --y 100
"""

import argparse
import json
import math
import os
import random
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


# ---------------------------------------------------------------------------
# Chat2SVG Stage-1 prompts (lifted from kingnobro/Chat2SVG prompts.yaml)
# ---------------------------------------------------------------------------

SKETCH_SYSTEM_PROMPT = """You are a sketch artist who draws using only outlined strokes — like pencil or pen on paper.

# Your tasks:
  - Task 1: **Expand Text Prompt**. Imagine the subject as a hand-drawn line sketch. Identify the contour lines, gesture lines, and key feature lines that define the subject's form.
  - Task 2: **Write SVG Code**. Translate the sketch into SVG using strokes only — no fills.
  - Task 3: **Code Improvement**. Fix any visual oddities while preserving the hand-drawn line-art feel.

# HARD CONSTRAINTS:
  1. EVERY shape must use `fill="none"` and `stroke="#1a1a1a"` (or another dark color). NO filled regions, no background.
  2. Use `polyline` and short `path` elements for gesture lines and contours. Avoid solid filled shapes.
  3. `circle`, `ellipse`, `rect` are acceptable ONLY as outline shapes (with `fill="none"`).
  4. Allowed elements: `circle`, `ellipse`, `line`, `polyline`, `polygon` (with fill="none"), `path` (up to 8 commands).
  5. Canvas: 512x512 viewBox.
  6. Stacking order matters; later elements draw over earlier ones.
  7. Think contour lines, not silhouettes. A face is two eye circles, a mouth curve, and a head outline — not a filled oval.
  8. Use multiple short strokes rather than one long polygon when sketching organic forms.
  9. Action and atmosphere are first-class: if the prompt says "reading", "walking", "swirling", "windy", "foggy", "at dusk" — these MUST appear as concrete strokes (motion lines, asymmetric pose, wisps, sun arc). A static symmetric figure when the prompt names an action is a failure.
  10. Frame budget: the named primary subject occupies 30-50% of the canvas AND its bounding box must be the LARGEST of any single object — including effects it emits. If the subject emits a beam, smoke, splash, or shadow, the effect's max linear extent (beam length, smoke height, splash radius) must be no more than 2x the emitter's longest dimension. A 60-px lighthouse with a 200-px beam is a failure — shrink the beam or grow the lighthouse. Do not draw any object whose name does not appear in (or directly imply) the prompt — no surprise boxes, benches, or luggage.
  11. Iconic shape vocabulary: common nouns must be drawn with their recognizable silhouette, not a vague line cluster. Minimum forms:
     - book = rectangle outline + a vertical center line (spine) + 2-3 short page lines; never just horizontal lines on a desk.
     - leaf = pointed oval (almond) + short stem tick; never an oval blob.
     - tree = a vertical trunk (two parallel lines) ROOTED on the ground line at the bottom of the tree's bounding box, rising upward 40-60% of the bbox height; branches FORK OUTWARD AND UPWARD from the TOP of the trunk in a Y/V pattern (3-7 branches); leaf ticks/clusters cling to branch tips. NEVER a single oval/cloud canopy outline, and NEVER a radial composition where branches emit from a center point like a sun or compass — the tree must read as a vertical figure standing on the ground, not a radial burst.
     - laptop screen = rectangle + at least one inner hint (a horizontal bar for a UI strip, a small rectangle for a window, or a short blinking-cursor line); never an empty rectangle.
     - tree trunk = TWO parallel vertical lines (not a single 'Y' line) before branches fork.
     - flower = stem line + 4-5 radial petal ticks (not a single dot).
  12. Stroke economy: if a contour can be expressed as one polyline, draw it ONCE. Do not stack 2-3 near-duplicate strokes on the same edge — that reads as messy overdraw, not gestural confidence. Reserve repeated strokes for deliberate texture (bark, fur, motion).

Note: You are drawing a sketch as a human artist would — fast, gestural, lines-only. Do NOT fill any shapes."""

SYSTEM_PROMPT = """You are a vector graphics designer tasked with creating Scalable Vector Graphics (SVG) from a given text prompt.

# Your tasks:
  - Task 1: **Expand Text Prompt**. The provided prompt is simple, concise and abstract. The first task is imagining what will appear in the image, making it more detailed.
  - Task 2: **Write SVG Code**. Using the expanded prompt as a guide, translate it into SVG code.
  - Task 3: **Code Improvement**. Although the SVG code may align with the text prompt, the rendered image could reveal oddities from human perception. Adjust the SVG code to correct these visual oddities.

# Constraints:
  1. SVG Elements: Use only the specified elements: `rect`, `circle`, `ellipse`, `line`, `polyline`, `polygon`, and short `path` (up to 5 commands).
  2. Canvas Details: The SVG canvas is defined by a `512`x`512` unit viewBox. Coordinates start at (0, 0) in the top-left and extend to (512, 512) at the bottom-right.
  3. Element Stacking Order: The sequencing of SVG elements matters; elements defined later in the code will overlap earlier ones.
  4. Colors: Use hexadecimal color values (e.g., #FF0000). For layers fully enclosed by others, differentiate with distinct colors.
  5. Simplicity: Keep the SVG code simple and clear.
  6. Realism: While using simple shapes, strive to create recognizable and proportionate representations of objects.

Note: The SVG you create will serve as an initial draft using simple shapes rather than a fully polished final product with complex paths. Focus on creating a recognizable representation of the prompt using basic geometric forms."""

SKETCH_EXPAND_TEMPLATE = """**Task 1**: Plan a hand-drawn line sketch of the prompt. Follow these steps:

Step 1. **Visualize as a sketch**. Describe the subject as a sketch artist would see it: what contours, gesture lines, and feature lines capture its essence? Avoid talking about colors or fills.

Step 2. **Identify the lines**. List the specific lines/strokes a human artist would draw, in drawing order. For each line, name what it represents and roughly where it goes. Examples:
  - "Gentle arc from (200, 300) curving up to (350, 280) — top of the back"
  - "Two short tick marks at (240, 220) and (260, 220) — eyes"
  - "Wavy line from (180, 350) to (380, 350) — ground line"

Step 3. **Frame Composition (REQUIRED)**. On a 512x512 canvas, assign every named noun and every action/atmosphere word from the prompt to one of three depth bands and confirm none are dropped:
  - Foreground (lower-third, 0-40% of frame): the named primary subject — give it 30-50% of frame area, no more.
  - Midground (middle band, ~30% of frame): supporting named objects — must be SMALLER than the primary and not crowd it.
  - Background (upper band, sparse): atmosphere/setting words.
  Action verbs ("reading", "walking", "swirling", "parting") MUST be conveyed by stroke direction, asymmetric pose, motion lines, or duplicated/displaced contours — NOT by static symmetric figures. Atmosphere words ("fog", "dusk", "wind") MUST be drawn as concrete strokes (e.g. fog = 3-5 short horizontal wisps; wind = curved trailing lines off moving objects; dusk = a low sun arc + horizon).

Step 4. **Verify coverage AND iconicity**. For every noun in the prompt, list (a) the strokes representing it, (b) its approximate bounding box on the 512x512 canvas, and (c) whether its silhouette matches the expected icon (book = rectangle+spine, leaf = pointed oval+stem, laptop screen has at least one inner hint, tree trunk has two parallel sides, flower has petal ticks). Then confirm the named primary subject's bounding box is the LARGEST of any single object. If a noun has zero strokes, fails the icon check, or is smaller than a supporting object, fix it before moving on. Repeat for every verb and atmosphere word. Action-contact check: if the prompt names an action with an object (reading a book, holding a candle, riding a bike), the actor must have AT LEAST ONE visible arm/hand or leg/foot stroke whose endpoint lies inside or touching the named object's bounding box. If you cannot draw a convincing arm, draw a single straight line from shoulder coordinate to the object as a simplified arm — omitting the limb entirely is a failure. Finally, scan your line list — every entry must trace back to a prompt word; delete any stroke group that does not.

# Worked Sketch Example:
Provided: "a cat chasing a butterfly in a garden"

Expanded:
###
Scene: a cat mid-leap toward a butterfly above flowers. Action conveyed by tilted body and trailing motion lines.

Word coverage:
- cat (foreground): arched body outline, four legs (front pair extended forward, back pair pushing off), tail curving up, two ear triangles, whisker ticks.
- chasing (action): cat body tilted ~20deg, three short motion-line strokes trailing behind tail.
- butterfly (midground, smaller): two figure-8 wing curves + short body line, positioned ahead and above the cat.
- garden (background): 3-4 small flower marks (stem + 5-petal star) along ground, single horizon line.

Line list (drawing order):
1. Ground line: polyline (40,420) -> (480,425), gentle dip mid-frame.
2. Cat back: arc from (180,360) to (300,300) — tilted forward.
3. Cat belly: arc from (190,395) to (300,355).
4. Front legs extended: two short lines (290,355)->(330,395), (300,360)->(335,400).
5. Back legs pushing off: (200,395)->(180,420), (210,395)->(195,420).
6. Tail curving up and back: polyline (180,360) -> (155,330) -> (170,300).
7. Head + ears: small circle r=18 at (310,295), two triangle ears on top.
8. Whiskers: 4 short tick marks at (325,300).
9. Motion lines (chasing): three short strokes at (130,340), (135,360), (140,380).
10. Butterfly wings: two figure-8 curves centered at (400,220), each ~40 wide.
11. Butterfly body: short line (395,215)->(405,225).
12. Flowers (background): 3 small stems at x=80, 250, 450 with 5-tick petal stars on top.
###

Refer to this example. Avoid unnecessary dialogue.
Here is the prompt: "{text_prompt}\""""

SKETCH_WRITE_PROMPT = """**Task 2** Write the SVG code as a hand-drawn line sketch. Adhere to:
1. EVERY element MUST have `fill="none"` and `stroke="#1a1a1a"` (or dark color). NO filled regions.
2. Use `polyline` for most gesture/contour lines (e.g., `<polyline points="200,300 220,290 250,285 ..." fill="none" stroke="#1a1a1a" stroke-width="2"/>`).
3. Use short `path` (max 8 commands) for curved contours.
4. `circle`, `ellipse` allowed only as OUTLINE shapes with fill="none" (e.g. eyes, sun, wheels).
5. NO background rectangle. NO filled polygons.
6. viewBox 512x512.
7. 12-35 elements total — a sketch is sparse but must include enough strokes to make each named object iconic (see system-prompt iconic vocabulary). If you exceed 35, you are overdrawing; merge duplicate contours into single polylines.
8. Before emitting, re-read the prompt and confirm every noun, action verb, and atmosphere word from the prompt has at least one corresponding stroke in your SVG. If any word is unrepresented, add strokes for it.
9. Stick figures must reflect the named action: a "reading" figure has arms angled down toward a book; a "walking" figure has legs offset (one forward, one back) and torso tilted; symmetric T-pose stick figures are a failure mode.
8. Each element gets unique id="path_N" (1-indexed) and a brief comment.

Output ONLY the SVG inside a fenced block:
```svg
<svg ...>
  ...
</svg>
```"""

EXPAND_PROMPT_TEMPLATE = """**Task 1**: Expand the given text prompt to detail the abstract concept. Follow these steps in your response:
Step 1. **Expand the Short Text Prompt**. Expand the short text prompt into a more detailed description of the scene. Focus on what objects appear, not abstract ideas.
Step 2. **Object Breakdown and Component Analysis**.
  - 2.1. For each object, add details (color, size, shape, status).
  - 2.2. Break each object into components, listing how each is depicted with the allowed SVG elements (rect, circle, ellipse, line, polyline, polygon, short path).
Step 3. **Scene Layout and Composition**. Specify positions, sizes, colors, spatial relations on a 512x512 canvas.

Guidelines:
1. Avoid adding excessive new objects.
2. Be vivid but clear; no overly complex descriptions.
3. List ALL essential parts, even if not explicitly mentioned.

# Unicorn Example:
Provided: "A unicorn is eating a carrot."

Expanded:
###
Scene Description:
"The pink unicorn is standing in side view. The unicorn's mouth is open, biting an orange carrot."

Object Detail:
# Object 1 (Unicorn): pink body, yellow horn, brown tail, four legs, pink head, small black eye.
# Object 2 (Carrot): orange with two green leaves at the top.

Component Breakdown:
# Object 1 (Unicorn): horizontal pink body (ellipse), pink head (ellipse), thin neck (rectangle), four legs (rectangles), brown tail (polyline), yellow horn (polygon), eye (circle), mouth (path)
# Object 2 (Carrot): orange triangle (polygon), two green leaves (polygons)

Key Components Layout:
# Object 1: Unicorn
1. Body: ellipse cx=256 cy=256 rx=90 ry=60, pink.
2. Head: ellipse cx=342 cy=166 rx=30 ry=25.
3. Neck: rectangle 50x10 at (312, 168).
4. Legs: four rects 10x80 at (185,296), (220,311), (293,307), (316,296).
5. Tail: polyline (168,258) -> (122,298) -> (142,252).
6. Horn: polygon (331,140) (336,110) (341,140), yellow.
7. Eye: circle r=5 at (352,164).
8. Mouth: short path at (342,178).

# Object 2: Carrot
1. Body: polygon (369,180) (348,200) (356,172), orange #FFA500.
2. Leaves: two small triangles around (363,174), green #00FF00.
###

Refer to this example. Avoid unnecessary dialogue.
Here is the text prompt: "{text_prompt}\""""

WRITE_SVG_PROMPT = """**Task 2** Write the SVG code following the expanded prompt and layout, adhering to:
1. Allowed elements only: rect, circle, ellipse, line, polyline, polygon, short path (<=5 commands). NO text, gradient, clipPath. Path must end with Z.
2. viewBox: 512x512.
3. Stacking: later elements overlap earlier. Background first.
4. Hex colors. Distinct colors for nested shapes.
5. Concise comments per element explaining semantic meaning.
6. Every shape needs unique id="path_N" (1-indexed).

Output ONLY the SVG inside a fenced block:
```svg
<svg ...>
  ...
</svg>
```"""

REFINE_SVG_PROMPT = """**Task 3** Examine your SVG code for visual oddities (misalignments, hidden elements, disproportions, color clashes, wrong stacking). Fix them while preserving structure. Re-emit the full SVG in the same format. Keep ids unique and continuous (path_1, path_2, ...).

Output ONLY the SVG inside a fenced block:
```svg
<svg ...>
  ...
</svg>
```"""

SKETCH_REFINE_PROMPT = """**Task 3** Examine the SVG for sketch-specific failure modes and list ALL problems you find before fixing. Common sketch failures:
  1. Missing prompt words: a noun, verb, or atmosphere word from the prompt has zero strokes representing it.
  2. Action dropped: prompt names an action ("reading", "walking", "swirling") but figures are static/symmetric.
  3. Atmosphere dropped: "fog", "wind", "dusk", "rain" have no concrete strokes.
  4. Frame imbalance: a supporting element (fence, cliff, background) is larger than the named primary subject, or the primary fills <20% or >60% of frame.
  5. Generic stick figure: the figure's pose does not reflect what the prompt says it is doing.
  6. Misalignments / disproportions / wrong stacking order.
For each problem, propose and apply a stroke-level fix (add motion lines, resize, reposition, swap pose). Do NOT delete elements except to rewrite. Re-emit the full SVG with continuous ids path_1, path_2, ...

Output ONLY the SVG inside a fenced block:
```svg
<svg ...>
  ...
</svg>
```"""


# ---------------------------------------------------------------------------
# Claude HTTP client (stdlib only, talks to ANTHROPIC_BASE_URL gateway)
# ---------------------------------------------------------------------------

class ClaudeSession:
    """Minimal multi-turn Claude client using the Anthropic /v1/messages API."""

    def __init__(self, model: str = "claude-sonnet-latest", system: str = ""):
        self.base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com/").rstrip("/")
        self.token = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")
        if not self.token:
            raise RuntimeError("ANTHROPIC_AUTH_TOKEN or ANTHROPIC_API_KEY must be set")
        self.model = model
        self.system = system
        self.messages: list[dict] = []

    def send(self, user_text: str, max_tokens: int = 4096) -> str:
        self.messages.append({"role": "user", "content": user_text})
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": self.system,
            "messages": self.messages,
        }
        req = urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "anthropic-version": "2023-06-01",
                "x-api-key": self.token,
                "authorization": f"Bearer {self.token}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        text = "".join(b.get("text", "") for b in payload.get("content", []) if b.get("type") == "text")
        self.messages.append({"role": "assistant", "content": text})
        return text


def extract_svg(text: str) -> str:
    m = re.search(r"```svg\s*(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"(<svg[\s\S]*?</svg>)", text)
    if m:
        return m.group(1).strip()
    raise ValueError("No SVG block found in LLM response")


# ---------------------------------------------------------------------------
# SVG -> point-array sampling (handles Chat2SVG's allowed primitives only)
# ---------------------------------------------------------------------------

def _sample_cubic(p0, p1, p2, p3, n=16):
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
        pts.append((x, y))
    return pts


def _sample_quadratic(p0, p1, p2, n=12):
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        x = u**2 * p0[0] + 2 * u * t * p1[0] + t**2 * p2[0]
        y = u**2 * p0[1] + 2 * u * t * p1[1] + t**2 * p2[1]
        pts.append((x, y))
    return pts


def _sample_arc(cx, cy, rx, ry, t_start, t_end, n=24):
    pts = []
    for i in range(n + 1):
        f = i / n
        a = t_start + (t_end - t_start) * f
        pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
    return pts


def _densify(points, min_step=4.0):
    if len(points) < 2:
        return list(points)
    out = [points[0]]
    for i in range(1, len(points)):
        x0, y0 = out[-1]
        x1, y1 = points[i]
        d = math.hypot(x1 - x0, y1 - y0)
        if d <= min_step or d == 0:
            out.append((x1, y1))
            continue
        steps = max(1, int(d / min_step))
        for s in range(1, steps + 1):
            t = s / steps
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return out


PATH_TOKEN_RE = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|-?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _parse_path(d: str) -> list[list[tuple[float, float]]]:
    """Parse an SVG path 'd' attribute into a list of polylines (one per subpath)."""
    tokens = PATH_TOKEN_RE.findall(d)
    i = 0
    subpaths: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []
    x, y = 0.0, 0.0
    start_x, start_y = 0.0, 0.0
    cmd = None

    def num():
        nonlocal i
        v = float(tokens[i])
        i += 1
        return v

    while i < len(tokens):
        t = tokens[i]
        if t.isalpha():
            cmd = t
            i += 1
        # implicit repeats use last cmd
        rel = cmd.islower() if cmd else False
        c = cmd.upper() if cmd else "L"

        if c == "M":
            nx, ny = num(), num()
            x, y = (x + nx, y + ny) if rel else (nx, ny)
            if cur:
                subpaths.append(cur)
            cur = [(x, y)]
            start_x, start_y = x, y
            cmd = "l" if rel else "L"  # subsequent pairs become lineto
        elif c == "L":
            nx, ny = num(), num()
            x, y = (x + nx, y + ny) if rel else (nx, ny)
            cur.append((x, y))
        elif c == "H":
            nx = num()
            x = x + nx if rel else nx
            cur.append((x, y))
        elif c == "V":
            ny = num()
            y = y + ny if rel else ny
            cur.append((x, y))
        elif c == "C":
            x1, y1, x2, y2, nx, ny = num(), num(), num(), num(), num(), num()
            if rel:
                x1, y1, x2, y2, nx, ny = x + x1, y + y1, x + x2, y + y2, x + nx, y + ny
            cur.extend(_sample_cubic((x, y), (x1, y1), (x2, y2), (nx, ny))[1:])
            x, y = nx, ny
        elif c == "Q":
            x1, y1, nx, ny = num(), num(), num(), num()
            if rel:
                x1, y1, nx, ny = x + x1, y + y1, x + nx, y + ny
            cur.extend(_sample_quadratic((x, y), (x1, y1), (nx, ny))[1:])
            x, y = nx, ny
        elif c == "Z":
            cur.append((start_x, start_y))
            x, y = start_x, start_y
            subpaths.append(cur)
            cur = []
            cmd = None
        else:
            # unsupported (S, T, A) — skip the expected operands conservatively
            # treat as line-to to next coordinate pair if possible
            try:
                nx, ny = num(), num()
                x, y = (x + nx, y + ny) if rel else (nx, ny)
                cur.append((x, y))
            except (IndexError, ValueError):
                break
    if cur:
        subpaths.append(cur)
    return subpaths


def _parse_transform(t: str):
    """Return a callable (x, y) -> (x, y) applying a chain of SVG transforms."""
    if not t:
        return lambda x, y: (x, y)
    ops = re.findall(r"(matrix|translate|rotate|scale)\s*\(([^)]*)\)", t)
    funcs = []
    for name, args in ops:
        nums = [float(n) for n in re.findall(r"-?\d+\.?\d*", args)]
        if name == "translate":
            tx = nums[0]
            ty = nums[1] if len(nums) > 1 else 0.0
            funcs.append(lambda x, y, tx=tx, ty=ty: (x + tx, y + ty))
        elif name == "scale":
            sx = nums[0]
            sy = nums[1] if len(nums) > 1 else sx
            funcs.append(lambda x, y, sx=sx, sy=sy: (x * sx, y * sy))
        elif name == "rotate":
            a = math.radians(nums[0])
            cx = nums[1] if len(nums) > 1 else 0.0
            cy = nums[2] if len(nums) > 2 else 0.0
            cos_a, sin_a = math.cos(a), math.sin(a)
            funcs.append(lambda x, y, cx=cx, cy=cy, cos_a=cos_a, sin_a=sin_a:
                         (cx + (x - cx) * cos_a - (y - cy) * sin_a,
                          cy + (x - cx) * sin_a + (y - cy) * cos_a))
        elif name == "matrix" and len(nums) == 6:
            a, b, c, d, e, f = nums
            funcs.append(lambda x, y, a=a, b=b, c=c, d=d, e=e, f=f:
                         (a * x + c * y + e, b * x + d * y + f))

    def apply(x, y):
        for fn in funcs:
            x, y = fn(x, y)
        return (x, y)
    return apply


def _is_background_rect(el, viewbox: tuple[float, float, float, float]) -> bool:
    """Detect rects that span ~the entire viewBox (i.e. backgrounds we should skip)."""
    try:
        x = float(el.get("x", 0))
        y = float(el.get("y", 0))
        w = float(el.get("width", 0))
        h = float(el.get("height", 0))
    except (TypeError, ValueError):
        return False
    vbx, vby, vbw, vbh = viewbox
    return (
        abs(x - vbx) < 2 and abs(y - vby) < 2
        and abs(w - vbw) < 4 and abs(h - vbh) < 4
    )


def svg_to_strokes(svg_text: str, drop_background: bool = True) -> list[dict]:
    """Convert SVG to a list of stroke dicts {points, stroke_color}."""
    # Strip namespace for easier element matching
    svg_text = re.sub(r'\sxmlns(:\w+)?="[^"]*"', '', svg_text)
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError as e:
        raise ValueError(f"SVG parse failed: {e}")

    vb = root.get("viewBox")
    if vb:
        vb_nums = [float(n) for n in re.findall(r"-?\d+\.?\d*", vb)]
        viewbox = tuple(vb_nums[:4]) if len(vb_nums) >= 4 else (0, 0, 512, 512)
    else:
        viewbox = (0, 0, 512, 512)

    strokes: list[dict] = []

    def color_for(el) -> str:
        s = el.get("stroke")
        if s and s.lower() not in ("none", ""):
            return s
        f = el.get("fill")
        if f and f.lower() not in ("none", ""):
            return f
        return "#1a1a1a"

    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if drop_background and tag == "rect" and _is_background_rect(el, viewbox):
            continue
        tf = _parse_transform(el.get("transform", ""))
        col = color_for(el)

        def emit(raw_pts):
            pts = [tf(x, y) for x, y in raw_pts]
            if len(pts) >= 2:
                strokes.append({"points": _densify(pts), "stroke": col})

        try:
            if tag == "rect":
                x = float(el.get("x", 0))
                y = float(el.get("y", 0))
                w = float(el.get("width", 0))
                h = float(el.get("height", 0))
                emit([(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)])
            elif tag == "circle":
                cx = float(el.get("cx", 0))
                cy = float(el.get("cy", 0))
                r = float(el.get("r", 0))
                if r > 0:
                    n = max(24, int(2 * math.pi * r / 6))
                    emit(_sample_arc(cx, cy, r, r, 0, 2 * math.pi, n))
            elif tag == "ellipse":
                cx = float(el.get("cx", 0))
                cy = float(el.get("cy", 0))
                rx = float(el.get("rx", 0))
                ry = float(el.get("ry", 0))
                if rx > 0 and ry > 0:
                    n = max(24, int(math.pi * (rx + ry) / 6))
                    emit(_sample_arc(cx, cy, rx, ry, 0, 2 * math.pi, n))
            elif tag == "line":
                emit([(float(el.get("x1", 0)), float(el.get("y1", 0))),
                      (float(el.get("x2", 0)), float(el.get("y2", 0)))])
            elif tag in ("polyline", "polygon"):
                raw = el.get("points", "")
                nums = [float(n) for n in re.findall(r"-?\d+\.?\d*", raw)]
                pts = list(zip(nums[0::2], nums[1::2]))
                if tag == "polygon" and pts:
                    pts.append(pts[0])
                emit(pts)
            elif tag == "path":
                d = el.get("d", "")
                if d:
                    for sub in _parse_path(d):
                        emit(sub)
        except (ValueError, TypeError):
            continue

    return strokes


# ---------------------------------------------------------------------------
# Excalidraw emission
# ---------------------------------------------------------------------------

def strokes_to_excalidraw(
    strokes: list[dict],
    offset_x: float = 50,
    offset_y: float = 50,
    scale: float = 1.0,
    id_prefix: str = "chat2svg",
    index_offset: int = 0,
) -> dict:
    now = int(time.time() * 1000)
    elements = []
    for i, s in enumerate(strokes):
        pts = [(p[0] * scale, p[1] * scale) for p in s["points"]]
        if not pts:
            continue
        ox = pts[0][0] + offset_x
        oy = pts[0][1] + offset_y
        local = [[round(p[0] - pts[0][0], 1), round(p[1] - pts[0][1], 1)] for p in pts]
        xs = [p[0] for p in local]
        ys = [p[1] for p in local]
        elements.append({
            "type": "freedraw",
            "id": f"{id_prefix}_{i}",
            "x": round(ox, 1),
            "y": round(oy, 1),
            "width": max(xs) - min(xs),
            "height": max(ys) - min(ys),
            "points": local,
            "strokeColor": s["stroke"],
            "backgroundColor": "transparent",
            "strokeWidth": 1,
            "fillStyle": "solid",
            "strokeStyle": "solid",
            "roughness": 0,
            "opacity": 100,
            "angle": 0,
            "groupIds": [],
            "boundElements": [],
            "link": None,
            "locked": False,
            "isDeleted": False,
            "frameId": None,
            "roundness": None,
            "simulatePressure": True,
            "pressures": [],
            "seed": random.randint(100000, 9999999),
            "version": 1,
            "versionNonce": random.randint(100000000, 2147483647),
            "index": f"a{(index_offset + i):03d}",
            "updated": now,
        })
    return {
        "type": "excalidraw",
        "version": 2,
        "source": "https://github.com/zsviczian/obsidian-excalidraw-plugin/releases/tag/2.22.3",
        "elements": elements,
        "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
        "files": {},
    }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_pipeline(prompt: str, model: str, refine_iter: int = 0, sketch_style: bool = False, verbose: bool = False) -> str:
    sys_prompt = SKETCH_SYSTEM_PROMPT if sketch_style else SYSTEM_PROMPT
    expand_template = SKETCH_EXPAND_TEMPLATE if sketch_style else EXPAND_PROMPT_TEMPLATE
    write_prompt = SKETCH_WRITE_PROMPT if sketch_style else WRITE_SVG_PROMPT
    refine_prompt = SKETCH_REFINE_PROMPT if sketch_style else REFINE_SVG_PROMPT

    session = ClaudeSession(model=model, system=sys_prompt)

    if verbose:
        mode = "sketch" if sketch_style else "cartoon"
        print(f"[1/3] Expanding prompt ({mode}): {prompt!r}", file=sys.stderr)
    session.send(expand_template.format(text_prompt=prompt))

    if verbose:
        print("[2/3] Generating SVG...", file=sys.stderr)
    svg_response = session.send(write_prompt)
    svg = extract_svg(svg_response)

    for k in range(refine_iter):
        if verbose:
            print(f"[3/3] Refine pass {k + 1}/{refine_iter}...", file=sys.stderr)
        svg_response = session.send(refine_prompt)
        svg = extract_svg(svg_response)

    return svg


def main():
    parser = argparse.ArgumentParser(description="Chat2SVG Stage-1 -> Excalidraw")
    parser.add_argument("prompt", help="Text prompt (e.g. 'a unicorn eating a carrot')")
    parser.add_argument("output", help="Output .excalidraw path")
    parser.add_argument("--model", default=os.environ.get("CHAT2SVG_MODEL", "claude-sonnet-latest"))
    parser.add_argument("--refine", type=int, default=0, help="Refinement passes (text-only, no render)")
    parser.add_argument("--sketch", action="store_true", help="Use stroke-only sketch prompts (no fills)")
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--x", type=float, default=50)
    parser.add_argument("--y", type=float, default=50)
    parser.add_argument("--save-svg", help="Optional path to save raw SVG")
    parser.add_argument("--seed", type=int)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    svg = run_pipeline(args.prompt, args.model, args.refine, args.sketch, args.verbose)

    if args.save_svg:
        Path(args.save_svg).write_text(svg)
        if args.verbose:
            print(f"Saved SVG to {args.save_svg}", file=sys.stderr)

    strokes = svg_to_strokes(svg)
    if args.verbose:
        print(f"Parsed {len(strokes)} strokes from SVG", file=sys.stderr)

    out_path = Path(args.output)
    existing_elements: list = []
    existing_app_state: dict = {"gridSize": None, "viewBackgroundColor": "#ffffff"}
    existing_files: dict = {}
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text())
            existing_elements = existing.get("elements", [])
            existing_app_state = existing.get("appState", existing_app_state)
            existing_files = existing.get("files", {})
        except (json.JSONDecodeError, OSError):
            existing_elements = []

    # Unique id prefix per call so repeated invocations on the same file don't collide.
    n_existing = sum(1 for e in existing_elements if str(e.get("id", "")).startswith("chat2svg_"))
    call_idx = 0
    while any(str(e.get("id", "")).startswith(f"chat2svg{call_idx}_") for e in existing_elements):
        call_idx += 1
    id_prefix = "chat2svg" if not existing_elements else f"chat2svg{call_idx}"

    new_doc = strokes_to_excalidraw(
        strokes,
        args.x,
        args.y,
        args.scale,
        id_prefix=id_prefix,
        index_offset=len(existing_elements),
    )

    merged_elements = existing_elements + new_doc["elements"]
    data = {
        "type": "excalidraw",
        "version": 2,
        "source": new_doc["source"],
        "elements": merged_elements,
        "appState": existing_app_state,
        "files": existing_files,
    }
    out_path.write_text(json.dumps(data, indent="\t"))
    print(f"OK: appended {len(new_doc['elements'])} freedraw strokes to {args.output} "
          f"(total now {len(merged_elements)} elements; prior chat2svg strokes: {n_existing})")


if __name__ == "__main__":
    main()
