---
name: excalidraw-diagram
description: Edit existing Excalidraw diagrams with surgical precision. Use when the user wants to modify, resize, move, add to, or remove from an existing .excalidraw file — without rewriting it from scratch.
---

# Excalidraw — Edit Mode

Helpers: `~/.claude/skills/excalidraw-diagram/helpers/`

## Decision Tree

```
User request
├── Modify existing element (resize/move/recolor/relabel/font)  → patch_element.py
├── Add new element                                              → add_element.py (auto-checks collision)
├── Remove element                                              → remove_element.py
├── Connect two elements with an arrow                          → connect_elements.py
├── Batch of patches                                            → batch_patch.py
├── Check for overlaps / boundary issues                        → check_collision.py
└── New diagram from scratch                                    → see "From Scratch" section
```

## Workflow

**1. Inspect** — always run first:
```bash
python3 ~/.claude/skills/excalidraw-diagram/helpers/canvas_info.py <file.excalidraw> --compact
```
Returns: element IDs, types, positions, colors, grouped with labels — ~10 lines.
Use `--json` for machine-readable output.

**2. Operate** — pick the right helper (see below).

**3. Render & verify:**
Open the `.excalidraw` file in Excalidraw (desktop app, obsidian plugin, or excalidraw.com) to verify.

---

## Helpers

### patch_element.py — modify an existing element
```
python3 .../patch_element.py <file> --id <id> [flags]
```
| Flag | Effect |
|------|--------|
| `--width N --height N` | Resize (auto-recenters contained text) |
| `--x N --y N` | Move (moves associated text too) |
| `--text "..."` | Change label |
| `--bg "#hex"` | Background color |
| `--stroke "#hex"` | Stroke color |
| `--stroke-width N` | Stroke width |
| `--font-size N` | Font size (text elements) |

Flags combine freely: `--x 400 --y 200 --width 250 --bg "#ff0000"`

---

### add_element.py — insert a new element
```
python3 .../add_element.py <file> --type <type> --id <new-id> [placement] [style]
```
**Types:** `ellipse` `rectangle` `diamond` `text` `line`

**Placement — auto (relative):**
```
--near <existing-id>  --direction right|left|above|below  --gap N
```

**Placement — manual:**
```
--x N --y N
```

**Style flags:** `--width N` `--height N` `--bg "#hex"` `--stroke "#hex"` `--text "..."`

Example:
```bash
python3 .../add_element.py diagram.excalidraw \
  --type ellipse --id node-b \
  --near node-a --direction right --gap 40 \
  --width 160 --height 100 --bg "#d4e8ff" --text "New Step"
```

---

### remove_element.py — delete an element
```
python3 .../remove_element.py <file> --id <id>
```

---

### connect_elements.py — add arrow between elements
```
python3 .../connect_elements.py <file> --from <id> --to <id> [--label "..."] [--style dashed]
```

---

### skeleton_to_elements.py — convert skeleton to full Excalidraw elements (via browser)
```
python3 .../skeleton_to_elements.py --spec '[{"type":"rectangle","x":0,"y":0,"id":"a","label":{"text":"Hello"}}]'
python3 .../skeleton_to_elements.py --file input.json -o output.json
echo '[...]' | python3 .../skeleton_to_elements.py
```
Uses the official `convertToExcalidrawElements` API in a headless Chromium. Handles:
- Real font-metric text sizing (no approximation)
- Arrow binding computation (focus, gap) from actual shape geometry
- Container auto-sizing to fit labels
- All boilerplate fields (seed, version, index, boundElements)

Skeleton format: `{type, x, y, id?, width?, height?, backgroundColor?, label?: {text}, start?: {id}, end?: {id}}`

---

### layout_graph_native.py — full diagram from graph spec (graphviz + native API)
```
python3 .../layout_graph_native.py <file> --spec '{"nodes":[...],"edges":[...]}' [--engine dot] [--direction DOWN]
```
Combines graphviz for node positioning with the official Excalidraw API for element finalization.
Produces diagrams with proper bindings, accurate text sizing, and hierarchical layout.

**Preferred over `layout_graph.py`** — produces higher-fidelity output. Requires network (loads Excalidraw from CDN on first call).

Spec format:
```json
{
  "nodes": [{"id": "x", "text": "Label", "type": "rectangle", "bg": "#color"}],
  "edges": [{"from": "x", "to": "y", "label": "optional", "style": "dashed"}]
}
```

---

### batch_patch.py — multiple patches in one call
```
python3 .../batch_patch.py <file> '[{"id":"x","width":200},{"id":"y","bg":"#f00"}]'
```
Also supports `--stdin` for large patch sets.

---

### batch_add.py — add multiple elements in one call
```
python3 .../batch_add.py <file> [--row-at Y] [--below <id>] [--gap N] [--width N] [--height N] '<json>'
```
JSON: `[{"type":"rectangle","id":"r1","text":"LABEL","bg":"#hex"}, ...]`
Auto-distributes evenly. Each element can override width/height/x/y individually.

---

### check_collision.py — detect overlaps and boundary violations
```
python3 .../check_collision.py <file> [--id <element>] [--ignore id1 id2]
```
Auto-detects frame rectangles (transparent bg, enclosing >50% of elements).
Reports: element-vs-element overlaps + boundary violations (element exceeds frame).
`add_element.py` runs this automatically after placement.

**When you see a BOUNDARY warning**: either (1) shrink the new element to fit, (2) pick manual x/y inside the frame, or (3) expand the frame with `patch_element.py --id <frame> --width N`.

---

## Style Inheritance

Copy style from an existing element instead of specifying all flags:
```bash
python3 .../add_element.py <file> --type ellipse --id new-node --like existing-node --text "Label"
```
Copies: width, height, backgroundColor, strokeColor, strokeWidth, roughness, fillStyle, fontSize.
Explicit flags override the inherited values.

---

## Chaining Operations

No need to re-run `canvas_info` between sequential patches on the same file:
```bash
python3 .../patch_element.py file.excalidraw --id node-a --width 200 --height 200
python3 .../add_element.py file.excalidraw --type ellipse --id node-b --near node-a --direction right --text "New"
```

---

## From Scratch

For new diagrams not based on an existing file:

### Graph/Flow diagrams (preferred):
Use `layout_graph_native.py` — define nodes + edges, get a fully laid-out diagram:
```bash
python3 .../layout_graph_native.py output.excalidraw --spec '{"nodes":[...],"edges":[...]}'
```

### Freeform diagrams (custom layout):
1. Build a skeleton JSON array: `[{type, x, y, id, label?, ...}]`
2. Pipe through `skeleton_to_elements.py` to get full elements
3. Wrap in `{"type":"excalidraw","version":2,"elements":[...],"appState":{"gridSize":null}}`
4. Write to your desired output path

---

## Output Rules

- Format: plain JSON with `.excalidraw` extension
- Never `.excalidraw.md`

---

## First-Time Setup

Ensure `graphviz` is installed for the layout engine:
```bash
brew install graphviz  # macOS
```
