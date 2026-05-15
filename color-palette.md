# Color Palette & Style Guide

**This is the single source of truth for all colors, fonts, and shape styles.** To customize diagrams for your own brand, edit this file — everything else in the skill is universal.

---

## Font

All text uses the Excalidraw default hand-drawn font:

| Property | Value |
|----------|-------|
| `fontFamily` | `1` (Virgil / Excalifont) |

Never use `fontFamily: 3` (monospace) unless rendering code snippets.

---

## Shape Style Defaults

All shapes share these properties unless otherwise specified:

| Property | Value |
|----------|-------|
| `strokeColor` | `#000000` (black borders on everything) |
| `roughness` | `1` (hand-drawn but controlled) |
| `roundness` | `{"type": 3}` (rounded corners on rectangles) |
| `fillStyle` | `"solid"` |
| `strokeWidth` | `2` (use `3` for primary/orchestrator emphasis) |

---

## Shape Colors (Semantic)

Soft, warm fills with black borders. All text inside shapes is black — the fill provides grouping, not the text color.

| Semantic Purpose | Fill | Notes |
|------------------|------|-------|
| Primary/Core | `#eae8e4` | Warm grey — orchestrators, main components |
| AI/LLM | `#e7f5ff` | Light blue — AI processing, intelligence |
| Start/Trigger | `#e0f4e8` | Soft green — entry points, user actions |
| End/Success | `#e4f0e0` | Warm green — successful outcomes |
| Decision | `#fff9db` | Light yellow — **use diamond shape** |
| Warning/Callout | `#fff9db` | Light yellow — annotation boxes, explanatory notes |
| Error | `#ffd4d0` | Warm red — **ONLY for actual error states/failures** |
| External/API | `#fff4e0` | Warm cream — external services, APIs |
| Accent/Highlight | `#e7f5ff` | Light blue — emphasis, key elements |
| Inactive/Disabled | `#f0f0f0` | Light grey — use dashed stroke |

**Rules:**
- All borders are `#000000` (black). No colored strokes.
- Fills are soft/warm — never bold or saturated.
- Decision points **must** use diamond shapes, not rectangles.
- Yellow boxes (`#fff9db`) with dark gold text (`#6b5a10`) serve as callout/annotation notes.
- Red (`#ffd4d0`) is **reserved strictly for error states**. Do not use it for prompts, warnings, disambiguation, or anything that isn't an actual error/failure. Use warm cream (`#fff4e0`) or grey (`#eae8e4`) for non-error interactive states.

---

## Text Colors (Hierarchy)

All text defaults to black. Use weight and size for hierarchy.

| Level | Color | Use For |
|-------|-------|---------|
| Title | `#0a0a0a` | Main headings (fontSize 24-28) |
| Subtitle | `#555555` | Subheadings, secondary labels (fontSize 14-16) |
| Body/Detail | `#6b6b6b` | Descriptions, metadata (fontSize 12-14) |
| On shapes | `#0a0a0a` | Text inside any filled shape (always black) |
| Callout text | `#6b5a10` | Text inside yellow annotation boxes |
| Muted/Annotation | `#888888` | De-emphasized labels (yes/no on arrows, optional info) |

---

## Arrow & Line Colors

| Element | Color |
|---------|-------|
| Arrows | `#3a3428` (warm charcoal) |
| Structural lines | `#3a3428` |

Arrows use `roughness: 1` like everything else. Use `strokeWidth: 2`.

---

## Section Dividers

Use a **filled black rectangle** with minimal height (horizontal) or minimal width (vertical) as a visual divider between diagram sections. This improves clarity when organizing content into rows or columns.

| Orientation | Width | Height | Fill | Stroke |
|-------------|-------|--------|------|--------|
| Horizontal divider | `(span of section)` | `3` | `#000000` | `#000000` |
| Vertical divider | `3` | `(span of section)` | `#000000` | `#000000` |

Properties: `roughness: 0` (sharp, not sketchy), `fillStyle: "solid"`, `roundness: null`, `strokeWidth: 1`, `opacity: 100`.

Place dividers between logical sections (e.g., separating "Input" from "Processing" from "Output" rows).

---

## Evidence Artifact Colors

Used for code snippets, data examples inside diagrams.

| Artifact | Background | Text Color |
|----------|-----------|------------|
| Code snippet | `#1e293b` | `#e2e8f0` (light grey) with `#7dd3fc` (cyan) for keywords |
| JSON/data example | `#1e293b` | `#86efac` (green) |

---

## Background

| Property | Value |
|----------|-------|
| Canvas background | `#ffffff` |
