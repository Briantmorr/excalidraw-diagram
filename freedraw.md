---
name: freedraw
description: Generate pencil-style freehand sketches using Excalidraw freedraw elements. Use when the user wants illustrative/hand-drawn content like simple scenes, objects, or doodles.
---

# Freedraw Sketching

Generate pencil-style freehand illustrations using Excalidraw's `freedraw` element type. Each stroke is a series of [x, y] coordinate pairs that trace a pencil line.

Helper: `~/.claude/skills/excalidraw-diagram/helpers/freedraw_add.py`

---

## How It Works

A freedraw element is a polyline rendered with hand-drawn style:
```json
{
  "id": "stroke1",
  "points": [[0,0], [5,2], [12,6], [20,4], ...],
  "x": 100, "y": 100,
  "stroke": "#000000",
  "width": 2
}
```

- `points` — LOCAL coordinates relative to element's (x, y). First point is always [0,0].
- `x`, `y` — absolute position on canvas where the stroke starts.
- `stroke` — color (default black).
- `width` — line thickness: 1 (pencil, DEFAULT), 2 (pen), 4 (marker bold).

**IMPORTANT**: Always use `"width": 1` for pencil sketches. Width 2+ creates thick marker appearance.

---

## Usage

```bash
python3 ~/.claude/skills/excalidraw-diagram/helpers/freedraw_add.py <file> '<json_array>'
```

---

## Planning Phase (REQUIRED)

Before generating any points or code, you MUST produce a written plan. Sketching without planning produces spatially incoherent output. The plan is your blueprint — every coordinate in the code traces back to a decision made here.

### Step 1: Scene Description (1-2 sentences)
What is the scene? What emotion or story does it convey? Name the key elements.

### Step 2: Layout Skeleton
Define the spatial skeleton as a coordinate map. Use exact pixel values:

```
Canvas: 800 × 400
Ground: y=350

Scene 1 (x=0..250):
  - Figure A: head_cx=120, head_cy=200, r=13 → body starts (120, 209)
    Posture: standing, arms at sides
  - Tree: trunk base (200, 350), height 100px, canopy center (200, 270) r=35

Scene 2 (x=280..520):
  - Bridge deck: y=220, x=290..510
  - Figure B: head_cx=400, head_cy=155, standing ON deck (feet at y=220)
  - Arch: below deck, center (400, 240), radius 80, half-circle
```

**Every element gets explicit coordinates.** No "somewhere to the right" — only pixel positions.

### Step 3: Stroke Inventory
List each stroke with its purpose, approximate point count, and color:

```
1. s1_ground — horizontal line x=0..250 at y=350, 50pts, #1a1a1a
2. s1_head — circle r=13 at (120, 200), 28pts, #1a1a1a
3. s1_body — stick figure from (120, 209) down, 45pts, #1a1a1a
4. s1_trunk — vertical line (200, 350) to (200, 290), 15pts, #1a1a1a
5. s1_canopy — organic blob r=35 at (200, 270), 40pts, #e8a030
Total: 5 strokes
```

**Constraint check before proceeding:**
- Total strokes ≤ 8 per scene (24 max for 3 scenes)
- Every figure's `body_start_y = head_cy + head_r - 4`
- Head circles use 25-30 points (not 50+)
- Figures are 40-60% of scene height
- No two atmospheric elements overlap vertically (8px+ separation)
- Colors: max 2 (black + one accent)

### Step 4: Generate Code
Only after Steps 1-3 are complete, write the Python script that produces the strokes. The script should reference the plan coordinates directly — don't recalculate positions inside the code without reason.

---

## Drawing Technique

### Coordinate System
- Canvas is ~800×600 for a typical sketch.
- Place the sketch centered around (100, 100) to (700, 500).
- Points are relative to the stroke's (x, y), so each stroke's points start at [0, 0].

### Stroke Density — CRITICAL

**`simulatePressure: true` means point spacing controls thickness.** Widely-spaced points (>10px apart) render as thick blobs. Closely-spaced points (3-5px apart) render as thin pencil lines.

- **Minimum 20 points** for ANY stroke that must read as thin (rain, glow rays, detail lines)
- **Target density**: one point every 3-5px along the path
- **Short lines** (20-50px): 20-25 points (dense = thin pencil)
- **Medium lines** (50-150px): 20-40 points
- **Long lines** (150-300px): 40-80 points

**Formula**: `num_points = max(15, path_length / 5)`

If you have only 3-5 points on a 100px line, it will look like a thick marker blob, NOT a pencil line.

### How to Draw Objects

**Think in strokes, not shapes.** Each continuous pencil movement is one stroke.

1. **Outline first** — Draw the main contour as 1-2 continuous strokes (prefer single continuous stroke for closed shapes).
2. **Detail strokes** — Add internal features (windows on a house, planks on a bridge).
3. **Ground/context** — Optional wavy lines for ground, grass, water.

### Connecting Strokes
When drawing a closed shape (rectangle, triangle), prefer ONE continuous stroke that returns to the start point rather than separate strokes per side. This eliminates gap artifacts.

```json
// GOOD: single continuous rectangle stroke (40+ points tracing all 4 sides)
{"id": "house_body", "points": [[0,0],[5,0],[10,0],...,[150,0],...,[150,100],...,[0,100],...,[0,0]], "x": 200, "y": 200}

// BAD: 4 separate strokes with 3-4 points each (thick blobs with gaps)
{"id": "wall_left", "points": [[0,0],[0,50],[0,100]], ...}
{"id": "wall_bottom", "points": [[0,0],[75,0],[150,0]], ...}
```

### Point Generation Strategy

For straight lines with hand-drawn wobble:
```python
# Interpolate start→end with many small steps + slight random offset
import math, random
points = []
length = math.hypot(end_x - start_x, end_y - start_y)
num_pts = max(15, int(length / 5))
for i in range(num_pts + 1):
    t = i / num_pts
    x = start_x + (end_x - start_x) * t + random.uniform(-0.8, 0.8)
    y = start_y + (end_y - start_y) * t + random.uniform(-0.8, 0.8)
    points.append([round(x, 1), round(y, 1)])
```

**Wobble calibration**: Use ±0.8px for general sketches. This produces visible hand-drawn character without being ragged. ±0.5px looks too machine-perfect. ±1.5px+ looks shaky.

For curves, use parametric math with density matched to circumference:
- **Small circles** (head, r=12-18px, circumference ~75-113px): use **25-30 points**. NOT 50+. Dense small circles render as heavy thick rings. Target spacing: circumference / 25.
- **Large arcs/circles** (r>30px): `[r*cos(t), r*sin(t)]` for t in linspace(start, end, 35-50)
- **Wavy line**: `[t, amplitude * sin(frequency * t)]` with t step = 3-5px
- **Bezier**: De Casteljau with 20+ sample points
- **Organic blobs** (tree canopy, clouds): overlapping arcs with varying radii

For organic/natural shapes (trees, clouds, bushes):
```python
# Bumpy circle / organic blob — use sine perturbation on radius
points = []
num_pts = 40
base_radius = 60
for i in range(num_pts + 1):
    angle = 2 * math.pi * i / num_pts
    # Perturb radius with multiple sine frequencies for natural look
    r = base_radius + 8 * math.sin(angle * 3) + 5 * math.sin(angle * 7) + random.uniform(-2, 2)
    x = r * math.cos(angle)
    y = r * math.sin(angle)
    points.append([round(x, 1), round(y, 1)])
```

### Sizing Guide
- **Small object** (flower, star): 50-100px bounding box
- **Medium object** (house, tree): 150-250px bounding box  
- **Large scene** (landscape): 400-600px wide

### Composition Rules — CRITICAL

Features must be **spatially anchored** to their parent. Before generating points, define anchor coordinates:

```python
# Example: House composition
body_x, body_y = 200, 200       # top-left of house body
body_w, body_h = 160, 120       # body dimensions

# Roof base MUST align with body top
roof_base_y = body_y            # no gap!
roof_apex = (body_x + body_w/2, body_y - 60)  # centered above body

# Door: inside body, touching bottom edge
door_w, door_h = body_w * 0.2, body_h * 0.5
door_x = body_x + body_w * 0.3  # offset from left
door_y = body_y + body_h - door_h  # flush with bottom

# Window: inside body, upper area with margins
win_size = body_w * 0.2
win_x = body_x + body_w * 0.65  # right side
win_y = body_y + body_h * 0.2   # upper portion

# Chimney: ON the roof slope, between apex and edge
chim_x = body_x + body_w * 0.7
chim_y = roof_base_y - 30       # sits on roof slope
```

**Rules:**
- Always define parent bounds FIRST, then compute child positions relative to parent.
- Features inside a shape must have coordinates WITHIN the parent's bounds (with 10px+ margin from edges).
- Connecting features (roof↔walls) must share exact coordinates at their join point — no gaps.
- Chimney sits ON the roof slope, not floating above it.

---

## Style Tokens

| Style | stroke | width | Use |
|-------|--------|-------|-----|
| Pencil sketch | `#1a1a1a` | 1 | Default, all strokes |
| Light/background | `#868e96` | 1 | Background elements, horizon |
| Colored accent | `#e8a030` / `#4a7ab5` | 1 | Warm/cool highlights sparingly |

### The Excalidraw Aesthetic

The Excalidraw look is: **minimal, imperfect, breathing.**

**Principles:**
- **Less is more** — 5 well-placed strokes beat 50 cluttered ones. Every stroke must earn its place.
- **Whitespace IS the drawing** — empty space gives remaining strokes impact. Resist filling.
- **Imperfection = life** — the slight wobble of ±0.8px is what makes it feel human, not computed.
- **Simplicity over detail** — a single curved line suggests a hill. Two dots suggest eyes. Don't over-specify.
- **Maximum 8-12 strokes per scene** for simple illustrations. If you have 30+ strokes in a single scene, you're overworking it.

**What NOT to do:**
- Don't add hatching/shading lines to fill space
- Don't draw every detail (individual fingers, facial features, texture)
- Don't add decorative borders or frames
- Don't use more than 2 colors per scene (black + one accent)
- Don't make environment compete with subject for visual weight

---

## Anti-Patterns

- **NEVER use fewer than 15 points per stroke** — this is the #1 cause of thick blobs instead of pencil lines.
- Don't generate hundreds of random points — each point should be intentional.
- Don't use perfectly straight lines (add ±1px wobble for hand-drawn feel).
- Don't place all strokes at (0,0) — offset x,y for each stroke's canvas position.
- Don't draw closed shapes as separate short strokes per side — use one continuous stroke.
- Don't use `"width": 2` or higher for pencil sketches — always use `"width": 1`.

---

## Combining with Diagram Elements

Freedraw strokes can coexist with regular excalidraw shapes. Use `batch_add.py` for boxes/text, then `freedraw_add.py` for illustrative accents:

```bash
# Add diagram structure
python3 .../batch_add.py file.excalidraw '[{"id":"box1","type":"rectangle",...}]'
# Add sketch decoration
python3 .../freedraw_add.py file.excalidraw '[{"id":"doodle1","points":[[0,0],...]}]'
```

---

## Scene Composition (Multi-Element Sketches)

For scenes with multiple objects (landscape, street, room):

1. **Establish ground plane first** — decide where the "floor" is (Y coordinate). Everything anchors to this.
2. **Layer back-to-front** — background elements first (sky, distant hills), then midground (buildings, trees), then foreground (path, fence).
3. **Vertical stacking**:
   - Sky/background: Y = 50-150
   - Main subjects: Y = 150-350
   - Ground/water: Y = 350-450
4. **Horizontal spread** — distribute subjects across the canvas width (100-700px range) with gaps between.
5. **Scale = depth** — distant objects are smaller, near objects are larger.

### Multi-Scene Layout (Storyboards)

**DO NOT draw frame/border rectangles around scenes.** Scenes are separated by horizontal spacing alone.

- Arrange scenes left-to-right with 30-50px gaps between them
- Each scene's content should fill its allocated width and use 80%+ of the vertical space
- Ground line at the BOTTOM of the canvas (y=280-300 for a 300px tall canvas)
- Main subjects should be LARGE — vertically spanning from ground (y≈290) up to y≈100
- No decorative borders, panel outlines, or framing rectangles

**Content must fill the space:**
```
WRONG: [tiny drawing in center of 300px panel with empty border]
RIGHT: [drawing fills 250px of 300px height, ground at bottom, sky element at top]
```

### Figure Drawing (People/Characters)

When humans are the subject, they must be the **visual focal point**:

**DRAW FIGURES FIRST, ENVIRONMENT SECOND.** Compute figure coordinates before anything else. The environment wraps around the figures, not the other way around.

- **Figures should be 40-60% of scene height** — if scene is 300px tall, figures are 120-180px tall. This is NON-NEGOTIABLE. If your figure is smaller than 120px in a 300px scene, you MUST rescale.
- **Stick figure anatomy** — each figure = 2 strokes: head circle + body
  - Circle head: radius **12-14px**, drawn with **25-30 points** (NOT 50+ — dense small circles render as thick heavy rings)
  - Body stroke: starts **4px INSIDE the head circle** (overlap compensates for taper)
  - Torso: line, 45-55px downward
  - Legs: two lines from torso bottom, each 40-50px, angled for stance
  - Arms: two lines from upper torso (20% down), each 30-40px
  
  **Head-body overlap — MANDATORY (prevents floating heads):**
  ```python
  # simulatePressure TAPERS strokes at endpoints (thin at start/end).
  # Adjacent strokes always look gapped unless they OVERLAP by 4px+.
  
  head_cx, head_cy = 100, 160
  head_r = 13  # use 12-14px radius
  
  # Body starts 4px ABOVE head bottom — deep into the head circle
  body_start_y = head_cy + head_r - 4  # e.g., 160 + 13 - 4 = 169
  # This places body_start visually inside the head circle, eliminating gap
  ```
  
  **NEVER leave a gap between head and body.** If body_start_y >= head_cy + head_r, you WILL get a floating head. Always use `head_cy + head_r - 4`.

- **Construction order**: 
  1. Set ground_y (e.g., 290)
  2. Compute figure_top = ground_y - 140 (e.g., 150)
  3. Draw head at (cx, figure_top + 12)
  4. Draw body down from head
  5. THEN add environment around the figure
- **Posture conveys emotion**: 
  - Walking: legs apart, one arm forward one back
  - Seated: shorter torso (30px), legs angled forward-down at 45° from hip (knees at bench height), feet dangle or touch ground. Figure's hip_y = bench_seat_y.
  - Strained/hunched: shorter torso, arms pulled in or out for balance
  - Stepping away: one leg extended backward, body leaning away
  - Reaching: one arm extended longer than the other
- **Two figures together**: overlap slightly or have arms touching/reaching. Height difference (10-20%) suggests relationship.
- **Place figures at ground level** — feet touch the ground line, not floating above it.
- **Figure Y position**: `figure_top_y = ground_y - figure_height`. If ground is at y=290 and figure is 140px tall, head is at y=150.

### Bridge Drawing

A bridge has 3 essential elements stacked vertically with gaps:
1. **Deck** (horizontal line, the walking surface) — this is the MOST prominent stroke
2. **Arch** (single smooth CONVEX curve below the deck) — humps UPWARD from endpoints toward the center. This is a structural stone arch, NOT a sagging rope. The highest point of the arch is at center, the endpoints touch the deck ends.
3. **Supports** (2 pillars at the ends where deck meets bank)

**Arch geometry — CRITICAL:**
A bridge arch is a semicircle below the deck. Its PEAK (highest point) is near the deck center. Its ENDPOINTS drop down to bank level. The arch creates an opening that looks like ∩ (inverted U).

```python
# Bridge arch: ∩ shape below deck
deck_start_x, deck_end_x = 280, 500
deck_y = 200

# Arch endpoints at SAME X as deck, but DROP DOWN to bank level
arch_endpoint_y = deck_y + 50   # banks, 50px below deck
# Arch PEAK at center, just below deck (small gap)
arch_peak_y = deck_y + 8        # 8px gap between deck and arch top

# Generate ∩ arch: center is HIGH (near deck), endpoints are LOW (at banks)
for i in range(num_pts):
    t = i / (num_pts - 1)
    x = deck_start_x + (deck_end_x - deck_start_x) * t
    # sin(π*t) = 0 at ends, 1 at center
    # At ends: y = arch_endpoint_y (deep, at banks)
    # At center: y = arch_peak_y (shallow, near deck)
    drop = arch_endpoint_y - arch_peak_y  # 42px
    y = arch_endpoint_y - drop * math.sin(math.pi * t)
```

Result: endpoints at y=250 (low), center at y=208 (high, near deck). This is a ∩ arch.

**WRONG: endpoints near deck + center deeper = hammock ∪ (iter 4 bug)**
**RIGHT: endpoints at banks + center near deck = stone arch ∩**

**Vertical layout for a bridge scene** (top to bottom):
```
y=50-100:  sky / storm clouds
y=100-180: figure standing ON deck (feet at deck_y)
y=180:     BRIDGE DECK (horizontal line)
y=190-230: air gap + arch curve (arch hangs below deck)
y=240:     gap (air between arch and water)
y=250-290: water ripples
```

The figure's FEET must touch the deck line. Place figure with: `feet_y = deck_y`, `head_y = deck_y - 80` (shorter figure on bridge, ~80px, to leave room for environment above and water below).

DO NOT draw many vertical posts — that reads as a fence or cage. A bridge is: deck line + arch curve + 2 end pillars. Keep it simple.

### Mood & Atmosphere Techniques

**Less is more. One or two strokes can set an entire mood.**

| Mood | Technique |
|------|-----------|
| Warm/golden | **Setting sun on horizon**: large amber arc (r=100-120px) with center BELOW the ground line. Only the TOP portion of the arc is visible above horizon. This creates a "sun peeking over the edge" effect. Position: `center_y = ground_y + 40`, so the arc rises ~60-80px above ground. Figures stand IN FRONT of it (between viewer and sun). |
| Storm | 2-3 SEPARATE short diagonal strokes (each its own freedraw element, 30-40px long, angled ~70° from horizontal). NOT a connected zigzag. Each rain stroke is independent. |
| Night/heavy | Empty space. One light source. Ground line. Nothing else. |
| Tension | Maximum whitespace. Isolation = tension. Fewer strokes = more weight per stroke. |
| Safety | Figures close together. Warm accent color. Simple ground beneath. |

**Rule of 3**: For any atmospheric element (rain, grass, water), use exactly 3 instances. Three rain lines read as "rain" just as well as fifteen — but breathe.

### Architectural Elements (bridges, buildings, fences)

For structures with arcs:
```python
# Arch shape — half circle or partial arc
arch_pts = []
num_pts = 30
for i in range(num_pts + 1):
    angle = math.pi * i / num_pts  # 0 to π for half-circle
    x = radius * math.cos(angle)
    y = -radius * math.sin(angle)  # negative Y = upward
    arch_pts.append([round(x + random.uniform(-0.8, 0.8), 1),
                     round(y + random.uniform(-0.8, 0.8), 1)])
```

For water/terrain:
```python
# Water ripples — multiple short wavy lines at DISTINCT Y positions
# Each ripple is a SEPARATE stroke, spaced 8-12px apart vertically
water_pts = []
for t in range(60):
    x = t * 5
    y = 3 * math.sin(t * 0.4) + random.uniform(-0.5, 0.5)
    water_pts.append([round(x, 1), round(y, 1)])
```

**Spacing rule for repeated elements** (water, grass, clouds): Each instance must have a distinct Y position with minimum 8px vertical separation. Overlapping instances create visual mud instead of readable repetition.

---

## Storytelling & Pathos

A sketch becomes meaningful when it makes you FEEL something. Technical correctness (heads attached, arches right) is the foundation — emotion is the goal.

### Principles

1. **Gesture is story.** A figure's posture — the lean of their torso, the reach of an arm, the spread of legs — conveys more than any environmental detail. Before drawing anything else, decide: what is this figure DOING emotionally?
   - Leaning toward another figure = longing/connection
   - Hunched forward, small = burdened/weary
   - Upright with arms wide = triumph/openness
   - One arm extended back toward something left behind = reluctance to leave

2. **One detail, maximum weight.** In a minimal scene, a SINGLE added detail carries enormous emotional freight. Choose it carefully:
   - Two figures' hands touching (a 15px line connecting their arm endpoints)
   - A glow cone radiating from a lantern (3 short lines fanning outward, each 18-25px with 20+ points to stay thin)
   - A scarf or hair line trailing in wind direction
   - A small object on the ground between figures (dropped item = loss)

3. **Environment echoes emotion.** The angle/direction of environmental strokes should mirror the figure's state:
   - Rain angled in the SAME direction the figure leans = walking into the storm
   - Hill slope matching figures' lean toward each other = cradling them
   - Ground line that tilts down ahead of a walking figure = uncertain future

4. **Scale tells relationship.** The relative size of figure to environment communicates vulnerability or mastery:
   - Tiny figure, vast bridge/landscape = overwhelmed, alone
   - Figure fills the scene = confidence, presence
   - Two figures at slightly different heights = care/protection

5. **Negative space is an actor.** Empty canvas between elements isn't "nothing" — it's distance, silence, cold, time. The gap between two figures IS the story of their separation.

### Applying Detail Without Breaking Minimalism

**Budget: +2-3 strokes per scene maximum for "pathos detail."** These are strokes that serve emotion, not structure.

**SPATIAL RULE: Detail strokes must occupy CLEAR SPACE.** They must NOT overlap with figure body strokes. Place them:
- BETWEEN two figures (handhold — requires 30px+ gap between figures)
- AWAY from the figure (glow rays radiating INTO empty space, not back toward body)
- Below/above the figure (shadow, halo) with 10px+ vertical clearance

**Figure spacing for detail:**
- Two figures holding hands: place them 40-50px apart (center-to-center). The handhold line connects their nearest arm endpoints across the GAP. If figures are closer than 30px, the detail will be lost in overlap.
- Glow rays: fan outward from the light source AWAY from the figure. If lantern is to figure's left, rays fan LEFT into darkness.

Examples of pathos strokes:
- A connecting line between two figures' hands (touch) — in the GAP between them
- A glow fan from a light source (warmth reaching into darkness) — radiating AWAY from figure
- A slight curve to the ground ahead (path bending into unknown)
- A wind-trail from hair/scarf — trailing BEHIND the figure, not overlapping body

**Do NOT add:** extra texture, hatching, background fills, decorative swirls, parallel lines for "detail." These add noise, not feeling.

**The body stroke IS the gesture.** Don't add separate "lean" or "hunch" strokes — encode emotion in the ANGLE of the existing torso line. A torso tilted 8° forward IS the hunch. A torso tilted 5° toward another figure IS the lean. No extra strokes needed.

---

1. Generate strokes with coordinate math
2. Screenshot via verify HTML page
3. Assess: does it look like the intended object?
4. Adjust: modify point density, curvature, spacing
5. Repeat until recognizable
