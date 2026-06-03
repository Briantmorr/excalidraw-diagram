---
name: excalidraw-diagram
description: Create and edit Excalidraw diagrams that argue visually — using batch helpers to eliminate boilerplate while you control all artistic decisions (positions, sizes, colors, visual hierarchy). Use when user wants to create, modify, or compose .excalidraw files.
disallowed-tools:
  - Bash(rm -rf*)
  - Bash(git push*)
  - mcp__sap-github__merge_pr
---


# Excalidraw Diagram

Generate `.excalidraw` files that **argue visually**. Pick a pattern, render, Read the PNG, patch what's wrong. Don't hand-place coordinates unless no pattern fits.

CLI: `~/.claude/skills/excalidraw-diagram/excd <subcommand> ...` (every subcommand has `--help`).

---

## Workflow

1. **Plan.** What is the single argument this diagram makes? Write the title in *action voice*: "Pipeline ships in 3 stages", not "Pipeline diagram".
2. **Pattern.** Match the argument to a pattern below. If none fits, use `excd place` (custom layout).
3. **Generate.** `excd pattern <name> out.excalidraw '<json-spec>'` — writes the file in one call.
4. **Render & Inspect.** `excd render out.excalidraw -o out.png` then **Read out.png**. The PNG is your feedback loop; the JSON is not.
5. **Patch.** `excd patch`, `excd connect`, `excd remove` for surgical fixes. `excd tighten` to grid-snap and compress gaps.
6. **Gate.** `excd check out.excalidraw` must exit 0. Any `TEXT_OBSCURED` or `ARROW_TEXT` finding blocks shipping — fix and re-render.

---

## Pattern catalog

Every pattern takes a `title` (action-voice) and pattern-specific kwargs. Spec is one JSON object.

### `pipeline` — N sequential stages, one arrow per gap
Argument: "this happens in order". Use for build/deploy/lifecycle flows.
```
excd pattern pipeline out.excalidraw '{"title":"Request flows through 3 layers","stages":["Ingest","Transform","Serve"]}'
```
Kwargs: `stages` (list[str], ≥2), `color` (palette name), `orientation` ("horizontal"|"vertical").

### `fanout` — one source, many targets
Argument: "this triggers many things". Hub left, spokes stacked right with arrows.
```
excd pattern fanout out.excalidraw '{"title":"Webhook fans out to 4 consumers","hub":"Webhook","spokes":["Slack","Email","DB","Audit log"]}'
```
Kwargs: `hub` (str), `spokes` (list[str|{label,description}]), `hub_role` (default "hub").

### `decision_tree` — diamond root, branching outcomes
Argument: "the answer depends on this question". Diamond top, rectangles below per branch.
```
excd pattern decision_tree out.excalidraw '{"title":"Routing depends on user tier","root":"Tier?","branches":[{"label":"free","outcome":"Rate limit"},{"label":"paid","outcome":"Direct"}]}'
```
Kwargs: `root` (str, the question), `branches` (list[{label, outcome}]).

### `comparison_grid` — 2D before/after table
Argument: "X differs from Y on these axes". Header row of columns, one row per dimension.
```
excd pattern comparison_grid out.excalidraw '{"title":"v4 cuts boilerplate vs v3","columns":["v3","v4"],"rows":[{"label":"LOC","cells":["7300","3100"]},{"label":"Patterns","cells":["0","10"]}]}'
```
Kwargs: `columns` (list[str]), `rows` (list[{label, cells}]).

### `weight_map` — size encodes importance
Argument: "these N things are not equal". Largest item top-left, sizes decay with weight.
```
excd pattern weight_map out.excalidraw '{"title":"Three risks dominate the backlog","items":[{"label":"Auth","weight":8},{"label":"Latency","weight":5},{"label":"Docs","weight":2}]}'
```
Kwargs: `items` (list[{label, weight}]).

### `timeline` — horizontal spine, alternating labels above/below
Argument: "events happen at these times". Spine is one arrow; ticks mark events.
```
excd pattern timeline out.excalidraw '{"title":"Migration ships across 4 weeks","items":[{"label":"Plan","when":"W1"},{"label":"Build","when":"W2"},{"label":"Test","when":"W3"},{"label":"Ship","when":"W4"}]}'
```
Kwargs: `items` (list[{label, when}], ≥2), `orientation`.

### `side_by_side` — mirrored parallel structures
Argument: "two systems share this skeleton, differ in detail". Two columns, paired rows, optional dashed-right.
```
excd pattern side_by_side out.excalidraw '{"title":"REST and gRPC share the call shape","left_label":"REST","right_label":"gRPC","pairs":[{"left":"POST /users","right":"CreateUser()"},{"left":"GET /users/1","right":"GetUser(id=1)"}]}'
```
Kwargs: `left_label`, `right_label`, `pairs` (list[{left, right}]), `dashed_right` (bool).

### `nested` — outer container wraps inner items
Argument: "these belong inside that". One outer box; inner items stacked; optional `inner_inner` for a third level.
```
excd pattern nested out.excalidraw '{"title":"Auth module owns 3 services","outer":"auth","inner":["sessions","tokens","mfa"]}'
```
Kwargs: `outer` (str), `inner` (list[str]), `inner_inner` (list[str]|null).

### `hub_spoke` — radial hub + spokes (free placement)
Argument: "this hub touches many peers, equally". Hub center, spokes radiate.
```
excd pattern hub_spoke out.excalidraw '{"title":"Gateway brokers 5 backends","hub":"Gateway","spokes":["Auth","Users","Billing","Logs","Cache"]}'
```
Kwargs: `hub` (str), `spokes` (list[str]), `with_descriptions` (bool).

### `storyboard` — N panels, no arrows
Argument: "look at these scenes". Equal-size frames, captions; no flow implied.
```
excd pattern storyboard out.excalidraw '{"title":"Three failure modes we fixed","panels":[{"caption":"Old: timeout","sketch":""},{"caption":"Mid: retry storm","sketch":""},{"caption":"New: backoff","sketch":""}]}'
```
Kwargs: `panels` (list[{caption, sketch}], ≥2).

---

## When no pattern fits: `excd place`

Declarative role-based layout. You name elements by role and anchor; `place` resolves coordinates.
```
excd place out.excalidraw '[{"id":"a","role":"rectangle","label":"A","row":0,"col":0},{"id":"b","role":"rectangle","label":"B","row":0,"col":1}]'
```
Then connect with `excd connect --from a --to b out.excalidraw`. Use `excd place --help` for the full role/anchor schema.

---

## Primitives

| Command | Purpose |
|---|---|
| `excd new file` | Empty canvas |
| `excd info file [--full] [--json]` | Compact summary; ids and bbox |
| `excd place file '<spec>'` | Role+anchor placement |
| `excd pattern <name> file '<spec>'` | One-shot pattern |
| `excd connect file --from id --to id [--label] [--style] [--start-side] [--end-side]` | Single arrow |
| `excd connect-batch file '<spec>'` | Many arrows in one call |
| `excd patch file --id X [--x --y --width --height --text --bg --stroke --font-size]` | Mutate one element |
| `excd remove file --id X` | Delete element + dead bindings |
| `excd tighten file [--target-bbox WxH] [--snap N]` | Grid-snap, align, compress gaps |
| `excd check file [--strict]` | All validators (rendering + aesthetic gates) |
| `excd render file -o out.png [--svg] [-s scale]` | Headless PNG/SVG |
| `excd layout file '<dag-spec>'` | Graphviz auto-layout for DAGs |
| `excd sketch "prompt" file` | Text → SVG → freedraw strokes |
| `excd bench dir/` | Render+check every .excalidraw in a directory |

Always `--help` a subcommand before guessing. The `--spec` flag on `patch` accepts a JSON array for batch edits.

---

## Composites

Patterns stack vertically. Generate one, then call another with the same file — patterns append below existing content. Use `excd tighten` after stacking. For DAGs that don't match a pattern, `excd layout` runs Graphviz dot.

---

## Design principles

- **Action Title.** Title states the conclusion, not the topic. "Latency drops 4x after caching" beats "Caching diagram".
- **Isomorphism Test.** If you swap labels, the diagram should still look right. If it doesn't, your geometry is encoding the labels — fix the layout, not the text.
- **Size hierarchy.** Bigger = more important. Hubs > spokes. Outer > inner. Don't make everything the same size; the eye gets no anchor.
- **One shape per role.** Rectangles for steps, diamonds for decisions, ellipses for endpoints. Don't mix shapes within a sequence.
- **Black borders only.** All shape borders `#000000`. Color lives in fills (8-token palette below) and arrow color `#3a3428`. Colored borders are an anti-pattern.
- **Tight gaps.** Patterns ship with gold-median spacing; don't widen unless the diagram is overcrowded — `tighten` it instead.
- **Text fits.** Text width is `len * fontSize * 0.62`; if a label spills, raise the container width or lower font-size. The `TEXT_OBSCURED` validator catches this.
- **Read the PNG.** Validators catch structure; only your eyes catch *visual argument*. Read the rendered PNG every iteration.

---

## Anti-patterns

- Hand-coded element JSON when a pattern exists. Patterns enforce all rendering invariants — bypassing them risks plugin hangs.
- Colored borders. Use fills.
- Identically-sized boxes for non-equal things. Use `weight_map`.
- Arrows from a node to itself. Skipped silently by `connect` but indicates broken intent.
- Diagrams without titles, or titles that name the topic instead of the conclusion.
- Re-rendering without Reading the PNG. The validators are necessary, not sufficient.
- Editing `.excalidraw` JSON in a text editor. Use `excd patch`.

---

## Color tokens

Palette keys (use 2-5 per diagram, never all 8): `grey #eae8e4`, `blue #e7f5ff`, `green #e0f4e8`, `mint #d3f9d8`, `yellow #fff9db`, `red #ffd4d0`, `cream #fff4e0`, `silver #f1f3f5`. Borders `#000000`, arrows `#3a3428`, body text `#0a0a0a`, subordinate text `#868e96`. Background `#ffffff`. Pass color names (e.g. `"blue"`) to pattern kwargs that accept them; the resolver maps to hex.

---

## Output rules

- File extension `.excalidraw`, JSON, with `appState.viewBackgroundColor: "#ffffff"` and `appState.isBindingEnabled: true`.
- Indices are monotonic 2-char base36 (`a00`, `a01`, …). Helpers handle this; don't hand-edit.
- Shapes appear in `elements` before arrows that bind to them.
- Standalone text needs `containerId: null` plus `originalText`, `rawText`, `autoResize`, `lineHeight`. Helpers handle this; don't hand-edit.
- Title at top of canvas, action-voice, font-size ≥ body+8.

---

## Hard gate

Before declaring done:

1. `excd check file` exits 0.
2. `excd render file -o file.png` succeeds.
3. You **Read** `file.png` and confirm: title is action-voice, no overlapping text, no dangling arrows, the visual argument is obvious in <2 seconds.

If any check fails, patch and repeat. Don't ship a diagram you haven't seen.

---

## Setup

- Python 3.11+, no extra Python deps for core CLI.
- `excd render`: needs Playwright (`pip install playwright && playwright install chromium`) — first run downloads the browser.
- `excd layout`: needs Graphviz (`brew install graphviz`).
- `excd sketch`: needs `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN` env vars (SAP gateway).
