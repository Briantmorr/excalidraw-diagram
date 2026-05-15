# excalidraw-diagram

A Claude Code skill for creating and editing Excalidraw diagrams programmatically.

## Install

```bash
npx skills@latest add Briantmorr/excalidraw-diagram
```

Or manually copy this directory to `~/.claude/skills/excalidraw-diagram/`.

## What it does

Gives Claude Code a suite of Python helpers to:

- **Edit** existing `.excalidraw` files (patch, add, remove elements)
- **Create** new diagrams from a declarative graph spec (nodes + edges)
- **Layout** automatically using graphviz (Sugiyama/hierarchical)
- **Connect** elements with properly-bound arrows
- **Batch** operations for multi-element changes in one call

## Prerequisites

- Python 3.10+
- graphviz (`brew install graphviz` on macOS)

## Structure

```
SKILL.md              — skill instructions (Claude reads this)
color-palette.md      — semantic color system
element-templates.md  — copy-paste JSON templates for each element type
helpers/
  layout_graph.py         — declarative graph → auto-positioned diagram
  layout_graph_native.py  — layout via graphviz + Excalidraw native API
  skeleton_to_elements.py — skeleton JSON → full Excalidraw elements (browser)
  add_element.py          — insert a single element with collision detection
  batch_add.py            — add multiple elements in one call
  patch_element.py        — modify existing element properties
  batch_patch.py          — patch multiple elements in one call
  remove_element.py       — delete an element
  connect_elements.py     — add arrow between two elements
  check_collision.py      — detect overlaps and boundary violations
  canvas_info.py          — inspect diagram (IDs, positions, colors)
  canvas_utils.py         — shared utilities
```

## Usage

Once installed, invoke with `/excalidraw-diagram` in Claude Code. The skill handles tool selection automatically based on what you ask for.

## License

MIT
