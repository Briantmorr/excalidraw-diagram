---
name: excalidraw-diagram
description: Create and edit Excalidraw diagrams that argue visually — architecture diagrams, system flows, and visualizations of papers or ideas. Batch helpers eliminate boilerplate while you control every artistic decision (positions, sizes, colors, hierarchy). Use when the user wants to create, modify, or compose .excalidraw files.
---


# Excalidraw Diagram

Generate `.excalidraw` files that **argue visually** — architecture and system diagrams, and visualizations of a paper's or a codebase's core idea. Pick a pattern, generate, check, ship. Don't hand-place coordinates unless no pattern fits.

CLI: `~/.claude/skills/excalidraw-diagram/excd <subcommand> ...` (every subcommand has `--help`).

**Scope:** this skill draws *structured diagrams* — boxes, arrows, grids, hierarchies. It does not draw freehand scenes or hand-sketched metaphors. If a prompt genuinely wants an illustrated scene rather than a diagram, that's out of scope; say so rather than faking it with labeled rectangles.

---

## Workflow

1. **Read the prompt.** What kind of input is this? See **Input-type heuristics** below — the input shape tells you which pattern family to consider first.
2. **Plan.** What is the single argument this diagram makes? Write the title in *action voice*: "Pipeline ships in 3 stages", not "Pipeline diagram".
3. **Pattern.** Match the argument to a pattern below. **Stress test:** if you picked the first pattern that loosely fit and it took <30 seconds to draft, you probably picked the lazy one. Try a second pattern, draft both titles, ask which one would surface a *non-obvious* fact. If neither does, the prompt deserves a custom layout (`excd place`).
4. **Generate.** `excd pattern <name> out.excalidraw '<json-spec>'` — writes the file in one call.
5. **Gate.** `excd check out.excalidraw` must exit 0 (see **Hard gate** below).

That's the fast path — deterministic, no vision round-trip. When *you and the user are iterating live* and want the diagram to be genuinely polished (not just correct), add: `excd render out.excalidraw -o out.png`, **Read the PNG**, then `excd patch` / `excd connect` / `excd tighten` for surgical fixes. Reserve that visual loop for live refinement — the structural gate is enough for batch or subagent use.

### Input-type heuristics

What the prompt is shaped like points to the right pattern family. Don't memorise these — use them as a tie-breaker when stress-testing.

- **Repo / codebase** ("look at this repo, draw…") → start with `fanout` (entry-point dispatching), `nested` (module hierarchy), or `pipeline` (call chain). Encode something *real* in size — LOC, traffic, blast radius. Don't draw a class diagram.
- **Paper / blog post** ("read this and visualize…") → look for the central tension (X vs Y, before vs after, claim vs counter-claim). `comparison_grid` and `paired_contrast` carry tensions; `weight_map` carries rankings; `pipeline` carries a mechanism or method's steps.
- **Daily lesson** ("teach me X with a visual") → think *pedagogically*, not *taxonomically*. The diagram should make the concept stick — formula → concrete instance → iterated rule beats one big tree. Composites of 2-3 small bands often outperform one big shape.

---

## Synthesis jobs: diagramming a whole repo or paper

Some requests aren't "draw this one argument" — they're "look at this repo / read this
paper and help me understand it." These are **synthesis jobs**: ingest a large source,
*select* the few arguments worth drawing, then present them as **one cohesive canvas** —
3-5 stacked panes that read top-to-bottom as a single visual explanation, NOT a scatter
of separate files. Selection is the hard, high-value part — pick what a newcomer actually
needs, and never dump a class diagram or a bullet list as boxes.

Run this as: **explore → select 3-5 insights → `compose` them into one canvas → gate**.

- **Selection is autonomous** — you pick the insights using the heuristics below — **unless
  the user named them** in their request ("show me the auth flow and the data model"), in
  which case draw exactly those. When autonomous, open your reply with the one-line list of
  panes you chose so the user can course-correct.
- **Pane count is adaptive, 3-5.** A small repo gets 3 (primary flow + module map + one
  mechanism); a big one with multiple subsystems earns up to 5. More than 5 becomes a
  scroll, not a glance — cut ruthlessly.
- **Emit ONE file via `compose`**, one band per insight (see the compose example below).
  Each band is an ordinary pattern; `compose` stacks them, namespaces ids, and centers
  them on a shared axis. Title each band with its takeaway.

### Diagramming a repo

**Explore.** Find the real code (skip deps/venv/node_modules). Read the orchestrators
first — a `main`, a `pipeline`, a `controller`, a `StateGraph`, an app factory. Trace
one path end to end. Note module layout, entry points, and where the LOC concentrates
(size encodes importance later).

**Select 3-5 panes** (a newcomer's 30-second orientation). The reliable core three:
1. **The primary flow** — the main data/request path through the system. Almost always
   the single most useful pane. This is the "controller → service → store" you were asked for.
2. **The module map** — what nests in what; the package/subsystem boundaries.
3. **One non-obvious mechanism** — the clever/subtle bit a newcomer would miss (a routing
   decision, a resolution pass, a retry loop). Skip if the repo has none.

Then add up to two more when the repo earns them: a **second architecture** (many repos
have two — e.g. a linear ingest pipeline AND a branching agent graph; that contrast is
itself insight), a **second key flow**, or a **data model**. Order panes so the canvas
reads as a story: entry/overview first, deep mechanisms last.

**What-you-find → pattern:**

| In the code | Argument | Pattern |
|---|---|---|
| Orchestrator calling services in sequence | "data flows through these stages" | `pipeline` |
| Router / dispatcher / StateGraph with conditional branches | "the path depends on this" | `decision_tree` |
| A feedback / retry / refinement loop | "this repeats until done" | `cycle` |
| `src/` package + subpackages | "these nest inside these" | `nested` |
| One entry point → many handlers | "this triggers many things" | `fanout` |
| Competing implementations of one interface | "these differ on these axes" | `comparison_grid` |

**Encode something real in size** — a stage that's 3× the LOC, a hot path, the blast
radius of a change. Uniform boxes waste the size channel.

**Compose the panes into one canvas.** One `compose` call, one band per insight:
```
excd compose repo.excalidraw '[
  {"pattern":"pipeline","spec":{"title":"Notes flow through extract, store, resolve","stages":["iter_notes","extract","apply_extraction","resolve"]}},
  {"pattern":"decision_tree","spec":{"title":"Chat routes on intent, pausing for approval","root":"chat: intent?","branches":[{"label":"chat","outcome":"reply, end"},{"label":"build","outcome":"assess: pause"},{"label":"query","outcome":"query: Cypher"}]}},
  {"pattern":"nested","spec":{"title":"Agent nodes wrap the core modules","outer":"graphiti","inner":["store","extract","resolve","pipeline"],"inner_inner":["chat","assess","query"]}}
]'
```
Then `excd check` the one file and `excd render` it to read the whole explanation at once.

### Diagramming a paper

**Explore.** Read for the *spine*: the central claim, the method that supports it, the
result that proves it, and the tension it argues against.

**Select 3-5, then `compose` into one canvas** (same as the repo job): (1) **the claim** —
often a `paired_contrast` or `comparison_grid` (their approach vs the prior one); (2) **the
method** — usually a `pipeline` or `cycle` (the mechanism's steps); (3) **the result** — a
`weight_map` or `comparison_grid` if there's a ranking or head-to-head number. Add a
**setup/tension** pane or a **second result** if the paper earns it. Don't diagram the
whole paper; diagram its argument, top-to-bottom as one explanation.

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

### `cycle` — N nodes on a ring, arrows closing the loop
Argument: "this repeats / returns to its start". Use for feedback loops, lifecycles, TDD/red-green-refactor, any process that cycles. A `pipeline` **cannot** make this argument — it reads as terminating. Needs ≥3 nodes (a loop is a triangle minimum). Nodes auto-size to the longest label.
```
excd pattern cycle out.excalidraw '{"title":"TDD repeats the discipline loop","nodes":["Red: write failing test","Green: make it pass","Refactor: clean up"],"center_label":"Define correctness first"}'
```
Kwargs: `nodes` (list[str|{text,bg}], ≥3), `center_label` (str, sits centered in the ring for ≥5 nodes, below it for a tight triangle), `color` (palette name), `clockwise` (bool, default true). Don't hand-build a loop with `place`+`connect` — this pattern routes the ring arrows and closes it for you.

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
| `excd check file [--strict]` | All validators (structural gates) |
| `excd render file -o out.png [--svg] [-s scale]` | Headless PNG/SVG |
| `excd layout file '<dag-spec>'` | Graphviz auto-layout for DAGs |
| `excd metrics [dir] [--baseline m.json]` | Mechanical metrics (render ms, validator findings, spec size) over a dir; deltas vs a baseline |
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
- Naming a shape's fill color in its own label ("RED: ..." in a red box). The fill already carries the color — the word is redundant. `COLOR_WORD_IN_SHAPE` warns on this.
- Hand-building a loop with `place`+`connect`. Use the `cycle` pattern — it routes the ring and closes it, and won't undersize arrow-label containers.
- Titles wider than the diagram body. Even perfectly centered, they jut past both edges and read as unbalanced. `TITLE_OVERHANGS` warns; shorten the title or widen the diagram.
- Identically-sized boxes for non-equal things. Use `weight_map`.
- Arrows from a node to itself. Skipped silently by `connect` but indicates broken intent.
- Diagrams without titles, or titles that name the topic instead of the conclusion.
- Faking an illustrated scene with labeled rectangles. This skill draws structured diagrams; a freehand scene is out of scope.
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

## Hard gate (required, mechanical)

Before declaring done:

1. `excd check file` exits 0 — no FAIL findings.

That's the gate. `check` catches the defects that are actually *wrong*: dangling
bindings, shapes after arrows, self-loops, arrows crossing non-endpoint shapes,
text overflowing its container, labels too long, flat hierarchy, bag-of-rectangles.
It runs in milliseconds, needs no browser, and is deterministic — so it's the gate a
batch job or a subagent uses too. A file that passes `check` is structurally sound.

This gate is **not** a taste judgement. It does not score whitespace balance, canvas
compactness, or whether the abstraction is *insightful* vs merely *adequate*. Those
are human calls, made by looking — see below.

## Live refinement (optional, visual — only when iterating with the user)

When you and the user are polishing a diagram together and want it genuinely good
(not just correct), render it and look:

```
excd render file -o file.png     # then Read file.png
```

Then patch what your eye catches that the validators can't — these are the things
worth a human's attention:

- *Whitespace:* breathing room even; no band starved while another sprawls.
- *Hierarchy reads:* the most important thing is visibly the biggest at a glance.
- *2-second test:* a stranger can say what it claims in two seconds without reading
  every label. If not, the argument isn't carried by the geometry yet.
- *Insight vs literal:* did the abstraction surface something the words don't already
  say? If it's a literal restatement, a different pattern may argue harder.

Fix with `excd patch` / `excd connect` / `excd tighten`, re-render, look again. This
loop costs a vision round-trip per iteration — spend it when a human wants polish,
skip it for throughput work. It buys the last ~15% of polish, not correctness; the
validators already own correctness.

## Measuring changes to the skill

`excd metrics` reports mechanical axes per diagram over a directory — render latency,
validator FAIL/WARN counts (structural accuracy), spec size (a proxy for how much
JSON the model had to emit), element count, canvas size. **No composite score** — each
axis raw, and the only verdict is `clean` (0 FAIL + 0 WARN). Run it against
`helpers/tests/fixtures/` (the bundled 11-pattern corpus) after changing a pattern or
a validator; `--baseline metrics.json` prints deltas so a regression shows up as a
number. It deliberately does not attempt to score taste — that plateaued in past
attempts and is a human call.

---

## Setup

- Python 3.11+, no extra Python deps for core CLI.
- `excd render`: needs Playwright (`pip install playwright && playwright install chromium`) — first run downloads the browser.
- `excd layout`: needs Graphviz (`brew install graphviz`).
