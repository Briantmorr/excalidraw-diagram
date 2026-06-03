---
name: excalidraw-diagram
description: Create and edit Excalidraw diagrams that argue visually — using batch helpers to eliminate boilerplate while you control all artistic decisions (positions, sizes, colors, visual hierarchy). Use when user wants to create, modify, or compose .excalidraw files.
disallowed-tools:
  - Bash(rm -rf*)
  - Bash(git push*)
  - mcp__sap-github__merge_pr
---

# Excalidraw Diagram

Generate `.excalidraw` files that **argue visually** — using batch helpers to eliminate boilerplate while you control all artistic decisions (positions, sizes, colors, visual hierarchy).

Helpers: `~/.claude/skills/excalidraw-diagram/helpers/`

---

## Workflow: Plan → Batch → Connect → Verify → Done

### 1. Design (in your head, not on disk)

Before any tool call, complete the full design process. **Spend more time designing than generating.** The tool calls are fast — bad design is the bottleneck.

1. **Depth assessment** — Is this simple/conceptual or comprehensive/technical?
2. **Concept → pattern mapping** — What visual pattern fits each concept? (See Pattern Library below)
3. **Shape choice** — What shape fits this context? Default to rectangles. Only introduce ellipses or diamonds when they add meaning that color alone cannot convey. In cycles and pipelines, prefer ONE shape type for all steps — let color carry the distinction.
4. **Size as meaning** — Important things are LARGE. Supporting things are small. Size variation IS the visual argument. If all shapes are the same size, redesign.
5. **Layout sketch** — Where does each element go? Trace the eye path. Plan whitespace deliberately.
6. **Element list** — Build the complete spec with explicit x, y, width, height for every element.
7. **Connection list** — Which elements connect? Use real arrows, not text approximations.

**Anti-patterns to avoid:**
- Text like ">>>" or "X" where an arrow or visual element should be
- Colored borders on ANY shape — ALL shape strokeColor = `#000000`. The `bg` fill carries the color; the border is always black.
- Multiple shape types within a single cycle or pipeline (pick ONE and reuse it)
- Diamonds containing multi-word labels (diamonds clip text — use rectangles unless 1-2 short words)
- Diagonal arrows crossing through unrelated elements (rearrange layout instead)
- **Cramming multiple concepts into one label** — if a shape's text contains `\n`-separated items that are DIFFERENT things (not a name + subtitle), break them into separate elements

### 2. Create elements (one or two `batch_add` calls)

```bash
python3 ~/.claude/skills/excalidraw-diagram/helpers/batch_add.py <file> '<json_array>'
```

The JSON array is your element spec — compact, explicit coordinates:
```json
[
  {"id": "title", "type": "text", "text": "Diagram Title", "x": 350, "y": 20, "text_size": 28},
  {"id": "hub", "type": "ellipse", "text": "Core", "bg": "#e7f5ff", "x": 400, "y": 300, "width": 180, "height": 120},
  {"id": "spoke1", "type": "rectangle", "text": "Module A", "bg": "#e0f4e8", "x": 100, "y": 100, "width": 140, "height": 70}
]
```

### 3. Connect elements (one `connect_elements` call per arrow)

```bash
python3 ~/.claude/skills/excalidraw-diagram/helpers/connect_elements.py <file> --from hub --to spoke1
python3 ~/.claude/skills/excalidraw-diagram/helpers/connect_elements.py <file> --from hub --to spoke2 --label "Yes"
```

Chain multiple in one bash call with `&&`.

### 4. Verify (run after every diagram)

```bash
python3 ~/.claude/skills/excalidraw-diagram/helpers/canvas_info.py <file> --compact
python3 ~/.claude/skills/excalidraw-diagram/helpers/check_collision.py <file>
python3 ~/.claude/skills/excalidraw-diagram/helpers/place/tighten.py <file>
python3 ~/.claude/skills/excalidraw-diagram/helpers/validate/check_argument.py <file>
python3 ~/.claude/skills/excalidraw-diagram/helpers/validate/check_title.py <file>
python3 ~/.claude/skills/excalidraw-diagram/helpers/validate/check_hierarchy.py <file>
```

Run `place/tighten.py` as the FINAL layout-verification step alongside `check_collision.py`. It grid-snaps shape positions, re-aligns spines (>=3 shapes sharing an x- or y-center) to their cluster median, and shrinks loose canvases toward a gold-derived tight target — reverting any move that would introduce a new shape-vs-shape overlap.

`check_title.py` enforces "every diagram MUST have a title" — fails (`NO_TITLE`) when no free-floating text (fontSize >= 22, top of canvas, not adjacent to a shape) is found, warns on size out of 24-30 (`TITLE_SIZE`), and informs when the title reads as a topic label rather than an action takeaway (`TITLE_PATTERN`).

`check_argument.py` runs the Isomorphism Test — strip text, then warn if shapes are a monoculture with no visible flow (`WEAK_ARGUMENT`) or if every shape is the same size (`NO_SHAPE_VARIETY`). Run it once per diagram; treat warnings as a prompt to redesign for visual variety/flow, not as hard errors.

`check_hierarchy.py` enforces the size-hierarchy rubric (max/min area >= 1.75x across meaningful shapes) and emits `WARN:HIERARCHY_FLAT` with upsize candidates (highest-degree binding hubs first) when too flat. Skips intentional-flat patterns (uniform rows for timelines/storyboards, 2D grids for tables) and segments composites by vertical band so each sub-diagram is checked on its own.

Review the output for:
- **TEXT_OBSCURED**: A text label is hidden behind a shape. Either move the text outside the shape, remove the label, or reposition overlapping shapes.
- **ARROW_TEXT**: Arrow passes through free text. Move text perpendicular to arrow path.
- **OVERLAP**: Two shapes collide. Fix by adjusting positions.
- **LABEL_OVERLAP**: Arrow label collides with non-parent shape. Use free text instead.

**HARD GATE**: If check_collision reports TEXT_OBSCURED or ARROW_TEXT issues, you MUST fix them before moving on. These indicate invisible content. Loop: fix → re-run check_collision → verify clean.

### 5. Done

Open in Obsidian to verify visually.

---

## Decision Tree (for editing existing files)

```
User request
├── Modify existing element (resize/move/recolor/relabel/font)  → patch_element.py
├── Add new element                                              → add_element.py (auto-checks collision)
├── Remove element                                              → remove_element.py
├── Connect two elements with an arrow                          → connect_elements.py
├── Batch of patches                                            → batch_patch.py
├── Check for overlaps / boundary issues                        → check_collision.py
├── **Sketch a physical object / scene / metaphor**             → chat2svg_sketch.py
└── New diagram from scratch                                    → see "From Scratch" section
```

When editing, always inspect first:
```bash
python3 ~/.claude/skills/excalidraw-diagram/helpers/canvas_info.py <file.excalidraw> --compact
```

---

## Helpers

### When to use which placement helper

| Helper | When | Status |
|--------|------|--------|
| **`place/place.py`** | **NEW DIAGRAMS — preferred.** Single declarative tool: each spec carries a `role` (size+style preset) and an `anchor` (`right_of`, `below`, `row`, `spine`, `near`, `like`, or explicit `{x,y}`). Unifies what `batch_add` (`--row-at`, `--below`) and `add_element` (`--near`, `--like`) do today. | preferred |
| `batch_add.py` | Existing callers; legacy `--row-at` / `--below` flags. | backward-compat shim |
| `add_element.py` | Existing callers; single-shot `--near` / `--like`. | backward-compat shim |

### place/place.py — declarative placement (preferred for new diagrams)
```
python3 .../place/place.py <file> '<json-array>'
```
Each spec: `{"id", "type", "text", "role"?, "anchor"?, ...}`. Roles: `stage`, `branch`, `hub`, `spoke`, `annotation`, `title`. Anchors: `{"rel":"right_of"|"below","id":"X","gap":N}`, `{"rel":"row","y":Y,"index":I,"total":T,"gap":N,"width":W,"x_start":X|"center_x":CX}`, `{"rel":"spine","x":X,"y_index":I,"y_start":Y,"gap":N}`, `{"rel":"near","id":"X","direction":...,"gap":N}` (clockwise free-space search), `{"rel":"like","id":"X"}` (copy size+style; supply position separately), or `{"x":X,"y":Y}`. Output preserves shape-before-arrow ordering, monotonic indices, and runs `check_collision` post-place.

### batch_add.py — add multiple elements in one call
```
python3 .../batch_add.py <file> [--row-at Y] [--below <id>] [--gap N] [--width N] [--height N] '<json>'
```
JSON: `[{"type":"rectangle","id":"r1","text":"LABEL","bg":"#hex","x":N,"y":N,"width":N,"height":N}, ...]`

### connect_elements.py — add arrow between elements
```
python3 .../connect_elements.py <file> --from <id> --to <id> [--label "..."] [--style dashed] [--stroke-width 1|2|3] [--start-side top|bottom|left|right] [--end-side top|bottom|left|right]
```

### patch_element.py — modify an existing element
```
python3 .../patch_element.py <file> --id <id> [--width N] [--height N] [--x N] [--y N] [--text "..."] [--bg "#hex"] [--stroke "#hex"]
```

### batch_patch.py — multiple patches in one call
```
python3 .../batch_patch.py <file> '[{"id":"x","width":200},{"id":"y","bg":"#f00"}]'
```

### add_element.py — insert a single element
```
python3 .../add_element.py <file> --type <type> --id <new-id> [--near <id> --direction right|left|above|below --gap N] [--x N --y N] [--width N] [--height N] [--bg "#hex"] [--text "..."]
```

### remove_element.py — delete an element
```
python3 .../remove_element.py <file> --id <id>
```

### check_collision.py — detect overlaps and boundary violations
```
python3 .../check_collision.py <file> [--id <element>] [--ignore id1 id2]
```

### canvas_info.py — inspect diagram
```
python3 .../canvas_info.py <file> --compact
```

### layout_graph.py — auto-layout from graph spec (graphviz)
```
python3 .../layout_graph.py <file> --spec '{"nodes":[...],"edges":[...]}' [--engine dot] [--direction DOWN]
```
Use for strict DAGs/hierarchies where manual positioning isn't needed. For artistic diagrams, use batch_add with explicit coordinates instead.

### layout_graph_native.py — graphviz + Excalidraw native API
```
python3 .../layout_graph_native.py <file> --spec '{"nodes":[...],"edges":[...]}' [--engine dot] [--direction DOWN]
```
Higher-fidelity output (proper text sizing, arrow bindings). Requires network.

### skeleton_to_elements.py — skeleton → full Excalidraw elements (browser)
```
python3 .../skeleton_to_elements.py --spec '[{"type":"rectangle","x":0,"y":0,"id":"a","label":{"text":"Hello"}}]'
```

### chat2svg_sketch.py — text → hand-drawn line sketch (LLM-generated SVG → freedraw)
```
python3 .../chat2svg_sketch.py "<prompt>" <file.excalidraw> --sketch [--x N] [--y N] [--scale F] [--save-svg PATH]
```
**Use ONLY for sketch/metaphor/illustration requests** — never for system diagrams, flows, or hierarchies. The `--sketch` flag emits stroke-only line art (no fills); omit it for filled cartoon-style output (rarely useful for our work). Calls Claude via the SAP gateway (no GPU needed).

**File behavior**: each invocation **appends** to the target file (creates it if missing). Prior `chat2svg` strokes are preserved; later calls get an auto-incremented id prefix (`chat2svg_*`, `chat2svg0_*`, `chat2svg1_*`, ...). For storyboards, call once per scene at different `--x`/`--y` offsets — do NOT batch into one call. Layer titles/captions via `batch_add` after all sketches land.

```bash
# Single scene
python3 .../chat2svg_sketch.py "lighthouse on a cliff at dusk" out.excalidraw --sketch --x 50 --y 80

# Three-scene storyboard
python3 .../chat2svg_sketch.py "two figures walking on hillside, golden light" out.excalidraw --sketch --x 50 --y 100 --scale 0.6
python3 .../chat2svg_sketch.py "bridge over dark water in storm" out.excalidraw --sketch --x 400 --y 100 --scale 0.6
python3 .../chat2svg_sketch.py "figure walking away from a glowing lantern" out.excalidraw --sketch --x 750 --y 100 --scale 0.6
# Then add scene titles + caption text:
python3 .../batch_add.py out.excalidraw '[
  {"id":"t1","type":"text","text":"The Walk","x":120,"y":60,"text_size":18},
  {"id":"t2","type":"text","text":"The Lifeline","x":470,"y":60,"text_size":18},
  {"id":"t3","type":"text","text":"The Unthinkable","x":820,"y":60,"text_size":18}
]'
```

---

## Core Design Philosophy

**Diagrams ARGUE, not DISPLAY.**

A diagram is a visual argument showing relationships, causality, and flow that words alone can't express. The shape should BE the meaning.

**The Isomorphism Test**: Remove all text — does the structure alone communicate the concept? If not, redesign.

**The Education Test**: Does this diagram teach something concrete (real system names, actual numbers, specific outcomes), or just label boxes?

---

## Visual Pattern Library

| If the concept... | Pattern | Shape approach |
|-------------------|---------|----------------|
| Spawns multiple outputs | **Fan-out** | Central element, radial arrows outward |
| Combines inputs into one | **Convergence** | Multiple elements, arrows merging to one |
| Has hierarchy/nesting | **Tree** | Lines + free-floating text |
| Is a sequence of steps | **Timeline** | Line + dots + free-floating labels |
| Loops or improves | **Spiral/Cycle** | Elements in sequence, arrow returning to start |
| Transforms input to output | **Assembly line** | Before → process → after |
| Compares two things | **Side-by-side** | Parallel structures with visual contrast |
| Separates into phases | **Gap/Break** | Whitespace or thin dashed line between sections |
| Is a pipeline (A→B→C) | **Linear flow** | Boxes in a row, arrows between |
| Is a visual metaphor / illustration / scene | **Sketch** | Hand-drawn line art via `chat2svg_sketch.py` |

**Variety rule**: For multi-concept diagrams, each major concept uses a different visual pattern.

**Diagram vs Sketch — pick ONE:**
- **Diagram (default)**: concepts, systems, processes, comparisons, hierarchies, flows. Uses `batch_add` + `connect_elements` + `layout_graph_native`. Geometric shapes carry meaning.
- **Sketch (rare)**: scenes, metaphors, illustrations of physical objects, storyboards (e.g. "two figures at a bridge", "a lighthouse", "a person walking"). Uses `chat2svg_sketch.py` ONLY. Triggers: prompt mentions "sketch", "draw [physical thing]", "illustrate", "scene", "metaphor", "storyboard with figures/objects", or asks for line art.
- **Mixed (storyboard with text panels)**: sketch each scene with `chat2svg_sketch.py` placed at different `--x`/`--y`, then add titles/captions via `batch_add` text elements on the same file.

### Pattern-Specific Techniques

**Cycle/Spiral**: Place thematic summary in geometric center. Use ONE shape type for all nodes. Edge annotations (12-14px) near arrows.

**Timeline**: One horizontal `line` element + small `ellipse` markers (12-20px) on it. Labels are free-floating text above/below the line, NOT bound to the markers. Place inflection labels alternately above/below to avoid stacking. Use a thicker line (`strokeWidth: 2`) for the spine and let dot size encode importance.

**Gap/Break / Phase separator**: A thin dashed `line` element spanning vertically (or horizontally) between sections, with `strokeStyle: "dashed"` and `strokeWidth: 1`. Or just whitespace (~80-120px) — prefer whitespace unless the gap itself needs labeling.

**Convergence**: Reverse of fan-out — multiple sources arrowing into one sink. Use `--end-side top` on all incoming arrows so they hit the same edge, and lay sources out horizontally above the sink.

**Side-by-side comparison**: Mirror same concepts with sizes inverted. Same concept = same color on both sides. Size inverts; color stays constant. Every tier must have a distinct size (~4:2:1 area ratio).

**Pipeline/Linear flow**: Preserve ALL steps. Use ONE shape type (rectangles, ~200×45). Color-code categories. Tight spacing (15-25px gaps for 5+ steps).

**Gate/Barrier**: TALL narrow rectangle (80×250) between columns. Horizontal arrows cross the gate. No diagonal arrows.

**Hub-and-spoke**: Hub is ONE larger element. Spokes are compact. Descriptive detail goes as free-floating text on the OUTSIDE edge of spokes.

**Storyboard/Sequential scenes**: NEVER connect scenes with arrows. Reading order IS the connection. Separate with whitespace (40-60px). Number scenes explicitly.

---

## Shape = Meaning

| Concept Type | Shape | Why |
|--------------|-------|-----|
| Labels, descriptions | **none** (free-floating text) | Typography creates hierarchy |
| Markers on a timeline | small `ellipse` (10-20px) | Anchor, not container |
| Start, trigger, input | `ellipse` | Soft, origin-like |
| Decision, condition | `diamond` | Classic branch symbol |
| Process, action, step | `rectangle` | Contained action |

**Rule**: Default to no container. Add shapes only when they carry meaning.

**Diamond caution**: Diamonds have ~60% usable text area. If label > 1-2 short words, use rectangle instead.

**Diamond is for branching, not classification.** A node titled "Intent Classification", "Validation", "Routing", or "Filter" is a *process step* — use a rectangle. Only use a diamond when the node has 2+ outgoing edges representing yes/no or category branches with distinct downstream paths.

---

## Color Tokens

| Token | Hex | Use For |
|-------|-----|---------|
| `grey` | `#eae8e4` | Primary/core components |
| `blue` | `#e7f5ff` | AI/LLM, accent, highlight |
| `green` | `#e0f4e8` | Start/trigger, entry points |
| `mint` | `#e4f0e0` | End/success outcomes |
| `yellow` | `#fff9db` | Decision points, callouts |
| `red` | `#ffd4d0` | Error states ONLY |
| `cream` | `#fff4e0` | External services, APIs |
| `silver` | `#f0f0f0` | Inactive/disabled |

**Rules:**
- All shape borders are `#000000` (black). No colored strokes.
- Arrows are `#3a3428` (warm charcoal).
- Use 2-5 tokens per diagram, not all 8.
- Use progression (green→yellow→red) for intensity/sequence.
- Annotation text: use `#868e96` (grey) stroke for secondary labels.

---

## Label Hygiene

Shape labels are SHORT identifiers, not content dumps.

| OK | NOT OK |
|----|--------|
| `"Frontend"` | `"Frontend\nBackend\nDatabase"` |
| `"Step 1\nValidate"` (name + subtitle) | `"One user-visible behavior\nFrontend\nBackend\nDatabase"` (list of items) |
| `"Agent Gate"` | `"Human reviews before agent proceeds"` (sentence) |

**Rules:**
- **Max 2 lines per label** — a name and optional subtitle. Never 3+ lines.
- **Max ~20 chars per line** — if it wraps, the shape is doing too much.
- **One concept per shape** — if you're listing items, each item is its own element.
- **Sentences go in free-floating text**, not inside shapes.
- **If showing layers inside a container**: use separate child shapes positioned inside the larger shape (z-order: container first in batch_add, children after). Do NOT put all layer names as multi-line text in the container's label.

**Container labeling rule**: If a container holds child shapes inside it, do NOT give it bound text (no `"text"` field in batch_add). Bound text is centered and will be hidden by the children. Instead, add a separate free-floating text element positioned at the top-left inside the container (inset 10-15px from top-left corner). This acts as a title bar.

```json
// WRONG — bound label hidden by children:
{"id": "outer", "type": "rectangle", "text": "SDD", "bg": "#fff9db", ...}

// RIGHT — free-floating label at top edge:
{"id": "outer", "type": "rectangle", "bg": "#fff9db", "x": 50, "y": 60, "width": 600, "height": 350},
{"id": "outer_lbl", "type": "text", "text": "SDD", "x": 65, "y": 70, "text_size": 14}
```

---

## Container Discipline

Not every text needs a box around it. Default to free-floating text.

| Use a Container | Use Free-Floating Text |
|-----------------|----------------------|
| Focal point of a section | Labels or descriptions |
| Arrows need to connect to it | Supporting detail |
| Shape carries meaning | Section titles, annotations |
| Represents a distinct "thing" | Phase labels, metadata |

**Target**: <50% of text elements inside containers. Use font size and color for hierarchy.

---

## Layout Principles

### Size IS Meaning
- **Hero**: 200-350px wide — visual anchor
- **Primary**: 140-200px — main elements
- **Secondary**: 100-140px — supporting elements
- **Small**: 60-80px — details, markers

**When the prompt says "weight", "importance", "heaviness", "priority", or "stakes" — encode it as SIZE, not just color.** A weight map of 5 items where every box is the same width fails the Isomorphism Test. The largest item should be ~2-3× the area of the smallest.

### Whitespace = Importance
Most important element has most empty space around it (150-200px+ clearance).

### Flow Direction
Left→right or top→bottom for sequences, radial for hub-and-spoke.

### Vertical Alignment
For top-to-bottom flows, all shapes in main spine share same center X: `x = center_x - width / 2`.

### Compactness
- Simple (3-8 elements): 500-600px longest dimension
- Medium (8-15 elements): 600-700px
- If exceeding 800px, tighten gaps or reduce sizes.

### Minimum Gap
- General layouts: 40px+ between connected shapes
- Tight pipelines (5+ steps): 20-30px gaps

---

## Typography

- **Title**: 24-28px, free-floating, above the diagram. ALWAYS PRESENT.
- **Node labels**: 16-20px inside containers
- **Annotations**: 14-16px, free-floating
- **Font**: Always `fontFamily: 1` (Excalifont)
- **Minimum**: Never below 14px

### The Action Title Pattern

The title IS the takeaway, not a label. It should teach or argue.

| Bad (Label) | Good (Action Title) |
|-------------|---------------------|
| "Enrichment Pipeline" | "Pipeline processes 500 records while you sleep" |
| "System Architecture" | "6 services work together so nothing falls through the cracks" |
| "Sprint Process" | "From grooming to deploy in 2 weeks" |

---

## Aesthetics

- `roughness: 1` — Hand-drawn feel (default)
- `roughness: 0` — Only for dividers or evidence artifacts
- `strokeWidth: 2` — Standard
- `strokeWidth: 1` — Thin dividers, tight pipeline arrows
- `strokeWidth: 3` — Bold emphasis (sparingly)
- `strokeStyle: "dashed"` — ONLY for elements that are explicitly wrong/deprecated/rejected

---

## Z-Ordering (Element Array Order)

Later elements render on top. Order:
1. **Background shapes** (section boundaries, overlays) — FIRST in batch_add
2. **Foreground shapes with text** — AFTER backgrounds
3. **Arrows** — LAST (connect_elements appends)

**CRITICAL**: Shapes MUST come before arrows in the elements array. Plugin hangs otherwise.

---

## Connect Elements — Best Practices

- Computes arrow start/end at shape edges (not centers)
- Arrow labels: keep under 2 words
- **Label minimum gap**: arrow must be longer than label text. If gap < `label_chars × 18px`, use free text instead.
- **Pipeline arrows**: `--stroke-width 1` for tight pipelines (25-35px gaps)
- **Opposing arrows** (A→B and B→A): don't use `--label` on both — labels collide. Use free text.
- **Fan-out uniform sides**: When one node connects to multiple targets in the same direction, use `--start-side` and `--end-side` to force uniform connection points. Example: fan-out downward = `--start-side bottom --end-side top` on ALL arrows from that node.
- **Vertical spine alignment**: In top-to-bottom flows, center all spine elements at the same X coordinate. Use `x = center_x - width/2` for each element.

---

## Composite Diagrams (Multiple on One Canvas)

Stack sub-diagrams vertically, ~600px wide. Separate with thin HR rectangles or whitespace.

**Build order**: Complete each sub-diagram (shapes + arrows) before starting the next. Do NOT batch all shapes then all arrows.

---

## Output Rules

- Format: plain JSON with `.excalidraw` extension
- **Never** `.excalidraw.md`
- **Never modify `viewBackgroundColor`** — always white (`#ffffff`)
- **Every diagram MUST have a title** (24-28px free-floating text)
- **Element ordering: shapes BEFORE arrows**
- **Arrows must use `connect_elements.py`** — never manual arrow JSON
- Never use emojis in text labels

---

## From Scratch

### Graph/Flow diagrams (strict DAGs):
```bash
python3 .../layout_graph.py output.excalidraw --spec '{"nodes":[...],"edges":[...]}'
```

### Artistic/Custom diagrams (preferred for most work):
Use batch_add with explicit x/y coordinates for full artistic control:
```bash
python3 .../batch_add.py output.excalidraw '[...]'
python3 .../connect_elements.py output.excalidraw --from a --to b
```

### Sketch / metaphor / illustration / storyboard (rare):
ONLY when the prompt asks for a hand-drawn scene of physical objects (figures, lighthouse, bridge, lantern, etc.) — not for systems, flows, or hierarchies.
```bash
python3 .../chat2svg_sketch.py "<scene>" output.excalidraw --sketch --x 50 --y 80
```
For storyboards, call once per scene at different `--x`/`--y` (offsets) — file appends. Then layer titles/captions via `batch_add`.

---

## First-Time Setup

```bash
brew install graphviz  # macOS — for layout_graph.py
```
