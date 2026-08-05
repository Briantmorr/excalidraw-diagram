---
name: excalidraw-diagram
description: Create and edit Excalidraw diagrams that argue visually — using batch helpers to eliminate boilerplate while you control all artistic decisions (positions, sizes, colors, visual hierarchy). Use when user wants to create, modify, or compose .excalidraw files.
---


# Excalidraw Diagram

Generate `.excalidraw` files that **argue visually**. Pick a pattern, render, Read the PNG, patch what's wrong. Don't hand-place coordinates unless no pattern fits.

CLI: `~/.claude/skills/excalidraw-diagram/excd <subcommand> ...` (every subcommand has `--help`).

---

## Workflow

1. **Read the prompt.** What kind of input is this? See **Input-type heuristics** below — the input shape tells you which pattern family to consider first.
2. **Plan.** What is the single argument this diagram makes? Write the title in *action voice*: "Pipeline ships in 3 stages", not "Pipeline diagram".
3. **Pattern.** Match the argument to a pattern below. **Stress test:** if you picked the first pattern that loosely fit and it took <30 seconds to draft, you probably picked the lazy one. Try a second pattern, draft both titles, ask which one would surface a *non-obvious* fact. If neither does, the prompt deserves a custom layout (`excd place`) or sketch mode (`excd sketch`).
4. **Generate.** `excd pattern <name> out.excalidraw '<json-spec>'` — writes the file in one call.
5. **Render & Inspect.** `excd render out.excalidraw -o out.png` then **Read out.png**. The PNG is your feedback loop; the JSON is not.
6. **Patch.** `excd patch`, `excd connect`, `excd remove` for surgical fixes. `excd tighten` to grid-snap and compress gaps.
7. **Gate.** `excd check out.excalidraw` must exit 0. Walk the **Visual review checklist** (Hard gate section) before declaring done.

### Input-type heuristics

What the prompt is shaped like points to the right pattern family. Don't memorise these — use them as a tie-breaker when stress-testing.

- **Repo / codebase** ("look at this repo, draw…") → start with `fanout` (entry-point dispatching), `nested` (module hierarchy), or `pipeline` (call chain). Encode something *real* in size — LOC, traffic, blast radius. Don't draw a class diagram.
- **Paper / blog post** ("read this and visualize…") → look for the central tension (X vs Y, before vs after, claim vs counter-claim). `comparison_grid` and `paired_contrast` carry tensions; `weight_map` carries rankings. If the post is *narrative* (short story, parable, walkthrough), reach for sketch mode or `storyboard`.
- **Daily lesson** ("teach me X with a visual") → think *pedagogically*, not *taxonomically*. The diagram should make the concept stick — formula → concrete instance → iterated rule beats one big tree. Composites of 2-3 small bands often outperform one big shape.
- **Conversation / journal / transcript** ("visualize this dialogue") → run the **metaphor-extraction pass** below as a *required first step* before picking any pattern. Sketch mode is the default for D-class; only fall back to a pattern if extraction yields nothing. **Preserve speaker labels verbatim** — if the input says `you·`, keep "you" in the output. Don't infer the speaker's name.

#### Metaphor-extraction pass (REQUIRED for D-class prompts)

Before considering any pattern, write down the answers to these three prompts in your reasoning, *out loud*:

1. **Quote the most concrete image** in the conversation. A literal physical thing or action — *"leaning on me as medicine"*, *"a lantern left behind"*, *"standing between two truths"*, *"the bridge is straining"*, *"a closed door"*. Quote the exact words.
2. **Name the visual it implies.** What would you draw? *"Two figures, one supporting the other on a bridge over dark water."* *"A figure stepping back, leaving a lit lantern behind."* *"A doorway with light on one side, dark on the other."*
3. **If you have a quoted image AND a drawable visual** → sketch mode is the right tool. Use `excd sketch "<your visual>" out.excalidraw`. Don't fall back to a pattern just because patterns are easier; the metaphor IS the visual argument.

If extraction yields no clear physical image after honest reading, then fall back to a pattern: `paired_contrast` for held tensions, `timeline` for belief progression, `weight_map` for theme prominence. Patterns are the *fallback*, not the default. The user said "visualize this dialogue" — the dialogue's metaphor is what makes the visualization not just adequate but delightful.

### Lazy-pattern smell check

These are the failure modes to avoid:
- **Flat pipeline** when the prompt is conceptual or generative — surfaces nothing the words don't already say. Try `fanout`, `weight_map`, or `paired_contrast`.
- **Bag of identically-sized rectangles** in two columns — that's `side_by_side` doing nothing. Either swap to `paired_contrast` (with row labels and brackets) or restructure as a sequence with arrows.
- **Generic title** ("X diagram", "Y overview") — rewrite until it states the takeaway, even if it makes the title longer.

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

### `timeline` — horizontal spine, annotations above
Argument: "events happen at these times". Spine is one arrow; ticks mark events; annotations sit above each marker (consistent side, never alternating — zigzag breaks the eye-scan).
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

### `paired_contrast` — two columns held in tension by row labels
Argument: "two truths about X" or "before/after pairs that belong together". Each row names one paired tension; left and right cells say each side; optional dashed bracket between them. Use this *instead of* `comparison_grid` when the rows are conceptual tensions, not tabular data.
```
excd pattern paired_contrast out.excalidraw '{"title":"Two truths still holding","left_label":"What I feel","right_label":"What is true","rows":[{"label":"Ending","left":"finality the other day","right":"40-yr friendship"},{"label":"Stepping back","left":"can step back","right":"cannot leave her"}]}'
```
Kwargs: `left_label`, `right_label`, `rows` (list[{label, left, right, bg_left?, bg_right?}], ≥1), `bracket` (bool, default true — dashed line between paired cells).

---

## When no pattern fits: `excd place`

Declarative role-based layout. You name elements by role and anchor; `place` resolves coordinates.
```
excd place out.excalidraw '[{"id":"a","role":"rectangle","label":"A","row":0,"col":0},{"id":"b","role":"rectangle","label":"B","row":0,"col":1}]'
```
Then connect with `excd connect --from a --to b out.excalidraw`. Use `excd place --help` for the full role/anchor schema.

### Recipe: sequence diagram (two columns, ordered crossing arrows)

For request/response protocols, handshakes, RPC traces — anything where two parties exchange ordered messages. Not yet a pattern; build from primitives.

1. `excd place` two columns of cells (one per message), aligning vertically — cell row = sequence step.
2. `excd connect` arrows that cross between columns: client→server alternating with server→client, top to bottom.
3. Use `style: "dashed"` for the final arrow if it represents steady-state (e.g., encrypted application data after handshake completes).
4. Title in action voice: "TLS 1.3 reaches a shared key in one round-trip" beats "TLS handshake".
5. Optional: phase-color the cell backgrounds to group handshake stages (greet / agree / verify / done).

Don't use `side_by_side` here — it pairs rows but draws no arrows, which kills the sequence's causality.

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
| `excd compose file '<spec>'` | Stack multiple patterns vertically on one canvas |

Always `--help` a subcommand before guessing. The `--spec` flag on `patch` accepts a JSON array for batch edits.

---

## Composites

For one diagram per file, just call a pattern. For multiple diagrams on a single canvas (e.g. a brief that shows architecture, decision tree, and metrics together), use `excd compose` — it stacks patterns top→bottom, namespaces ids per band, and reorders elements so shapes always precede arrows:

```
excd compose out.excalidraw '[
  {"pattern":"pipeline","spec":{"title":"Three-stage pipeline","stages":["Ingest","Transform","Serve"]}},
  {"pattern":"fanout","spec":{"title":"Webhook fans out","hub":"Webhook","spokes":["Slack","Email","DB"]}},
  {"pattern":"comparison_grid","spec":{"title":"v3 vs v4","columns":["v3","v4"],"rows":[{"label":"LOC","values":["7300","4400"]}]}}
]'
```

Each element's id is prefixed with `b0_`, `b1_`, ... per band so they don't collide. Bands sit ~80px apart vertically. **Never** lay out composites as 2-column grids — full-width vertical bands keep each pattern legible. For DAGs that don't match a pattern, `excd layout` runs Graphviz dot.

---

## Design principles

The **Visual review checklist** (Hard gate) is the full rubric — title voice, isomorphism, size hierarchy, one-shape-per-role, black borders, edge-label length. These are the load-bearing technical facts behind it:

- **Text fits.** Text width ≈ `len * fontSize * 0.62`; if a label spills, raise container width or lower font-size. The `TEXT_EXCEEDS_CONTAINER` validator catches this.
- **Edge labels ≤1 short word.** `connect` auto-truncates to 8 chars; the `LABEL_TOO_LONG` validator gates the rest. Move a second fact into a node, never into the label.
- **Tight gaps.** Patterns ship with gold-median spacing; don't widen — `tighten` instead.
- **Read the PNG.** Validators catch structure; only your eyes catch the *visual argument*. Read the rendered PNG every iteration.

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

Palette keys (use 2-5 per diagram, never all 9): `grey #eae8e4`, `blue #e7f5ff`, `green #e0f4e8`, `mint #d3f9d8`, `yellow #fff9db`, `red #ffd4d0`, `cream #fff4e0`, `silver #f1f3f5`, `cyan #d3f9f9`. Borders `#000000`, arrows `#3a3428`, body text `#0a0a0a`, subordinate text `#868e96`. Background `#ffffff`. Pass color names (e.g. `"blue"`) to pattern kwargs that accept them; the resolver maps to hex.

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
3. You **Read** `file.png` and walk through the **Visual review checklist** below — *out loud*, in your reasoning, hitting every item. A scan-and-ship pass is not enough; the validators don't see what your eyes do.
4. If any item fails, patch and re-render. Repeat until the checklist is clean. Then ship.

Don't declare done on a diagram you haven't seen. Don't declare done on a diagram you've only glanced at. The judge is your own eyes; nothing else catches what's visually wrong.

### Visual review checklist

Walk through each row. Be honest — if you find yourself rationalising why a defect is "fine," it's not fine.

**Argument**
- *Title:* action voice, states the takeaway in one line, sits at the top, font visibly larger than body.
- *2-second test:* could a stranger glance at this and explain what it claims in two seconds? If they'd need to read every label, the argument isn't visual.
- *Isomorphism test:* if you swapped every label for "lorem", would the geometry still tell the story? If yes, good. If no, the layout is leaning on text instead of doing its job.

**Composition**
- *Hierarchy:* important things visibly bigger. Hubs > spokes. Outer > inner. Headlines > details. If everything's the same size, the eye gets no anchor — fix it.
- *Whitespace:* every shape has breathing room. Margins consistent. Nothing crammed against the canvas edge. No band starved while another sprawls.
- *Alignment:* shapes share grid lines. Rows and columns are visually true. Tighten if drift is visible.
- *Shape variety:* one shape per role, used consistently. Rectangles for steps, diamonds for decisions, ellipses for endpoints. *Not* every box a rectangle — that's a bag-of-rectangles, not a diagram.

**Connections**
- *Arrow endpoints:* every arrow tail and head touches a shape edge cleanly. Arrows ending in whitespace or piercing mid-shape are bugs, not style.
- *No crossings:* arrows don't cross other arrows or pass *through* non-endpoint shapes. If you have crossings, restructure (widen gaps, reorder rows, switch pattern) — don't ignore.
- *Edge labels:* one short token max ("Yes", "No", "ok", "fail"). Never multi-segment ("Yes / Gold", "approved by admin"). If you need more info, move it into a node.
- *Disconnected shapes:* every meaningful shape connects to the argument. Floating orphans signal the layout doesn't actually use them.

**Text**
- *No overlap:* labels don't overlap shapes (other than their parent), other labels, or arrow shafts.
- *Fits inside:* container text doesn't spill the box. Free-text annotations don't bleed into neighboring shapes.
- *Legibility:* nothing tiny, nothing truncated, nothing running off canvas. If you can't read it on first look, neither can anyone else.
- *Title voice:* action ("Pipeline ships in 3 stages"), not topic ("Pipeline diagram"). Re-write if it's descriptive.

**Color & style**
- *Borders:* black `#000000` only. Colored borders are an anti-pattern — color goes in fills.
- *Fill discipline:* 2-5 palette tokens, never all 9. Each color carries meaning (state, group, weight). If color is decorative, drop it.
- *Sketch mode:* if the prompt called for a metaphor or scene, you should see freedraw strokes — not labeled rectangles pretending to be a sketch.

**Honesty pass**
After running the checklist, write one short paragraph stating what you'd want to fix if you had another iteration. If the answer is "nothing," check again — there's almost always one thing. Patch the most impactful one. Then ship.

If you find ≥3 items failing, you probably picked the wrong pattern. Reconsider abstraction before patching geometry.

---

## Setup

- Python 3.11+, no extra Python deps for core CLI.
- `excd render`: needs Playwright (`pip install playwright && playwright install chromium`) — first run downloads the browser.
- `excd layout`: needs Graphviz (`brew install graphviz`).
- `excd sketch`: needs `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN` env vars (SAP gateway).
