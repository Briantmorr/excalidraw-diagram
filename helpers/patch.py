#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from helpers.core import recenter_text, text_width

LINE_HEIGHT: float = 1.25
ALIASES: dict[str, str] = {
    "bg": "backgroundColor",
    "stroke": "strokeColor",
    "stroke_width": "strokeWidth",
    "font_size": "fontSize",
}
GEOMETRY_KEYS: frozenset[str] = frozenset({"x", "y", "width", "height"})


@dataclass
class PatchSpec:
    id: str
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    text: str | None = None
    bg: str | None = None
    stroke: str | None = None
    stroke_width: int | None = None
    font_size: int | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PatchSpec":
        valid = {f.name for f in fields(cls)}
        inv = {v: k for k, v in ALIASES.items()}
        return cls(**{inv.get(k, k): v for k, v in raw.items() if inv.get(k, k) in valid})

    def to_props(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for f in fields(self):
            if f.name == "id":
                continue
            v = getattr(self, f.name)
            if v is None:
                continue
            key = ALIASES.get(f.name, f.name)
            if key in GEOMETRY_KEYS or key == "fontSize":
                out[key] = float(v)
            elif key == "strokeWidth":
                out[key] = int(v)
            else:
                out[key] = v
        return out


@dataclass
class PatchOp:
    spec: PatchSpec
    old_x: float
    old_y: float
    old_w: float
    old_h: float


@dataclass
class PatchResult:
    patched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    collisions: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing

    def summary(self) -> str:
        parts = [f"patched={len(self.patched)}"]
        if self.removed:
            parts.append(f"removed={len(self.removed)}")
        if self.missing:
            parts.append(f"missing={','.join(self.missing)}")
        if self.collisions:
            parts.append(f"collisions={len(self.collisions)}")
        return f"{'OK' if self.ok else 'PARTIAL'}: {' '.join(parts)}"


def _apply_text_update(target: dict[str, Any], val: str) -> None:
    val = val.replace("\\n", "\n")
    target["text"] = val
    target["originalText"] = val
    if "rawText" in target:
        target["rawText"] = val
    if target.get("type") == "text":
        fs = target.get("fontSize", 14)
        lh = target.get("lineHeight", LINE_HEIGHT)
        lines = val.split("\n")
        target["width"] = text_width(max(lines, key=len), fs)
        target["height"] = len(lines) * fs * lh


def _collisions_for(elements: list[dict[str, Any]], eid: str) -> list[str]:
    try:
        from helpers.validate import check_collisions
    except ImportError:
        return []
    return [f"{eid}: {getattr(f, 'message', str(f))}"
            for f in check_collisions(elements, target_id=eid)
            if getattr(f, "severity", "") in ("FAIL", "WARN")]


def patch(filepath: Path, patches: list[PatchSpec]) -> PatchResult:
    path = Path(filepath)
    data = json.loads(path.read_text())
    elements: list[dict[str, Any]] = data.get("elements", [])
    index: dict[str, dict[str, Any]] = {e["id"]: e for e in elements}
    result = PatchResult()
    moved: list[str] = []

    for spec in patches:
        target = index.get(spec.id)
        if target is None:
            result.missing.append(spec.id)
            continue
        props = spec.to_props()
        op = PatchOp(spec, target.get("x", 0.0), target.get("y", 0.0),
                     target.get("width", 0.0), target.get("height", 0.0))
        for key, val in props.items():
            if key == "text":
                _apply_text_update(target, val)
            else:
                target[key] = val
        target["version"] = target.get("version", 1) + 1
        if target["type"] != "text":
            recenter_text(elements, target, op.old_x, op.old_y, op.old_w, op.old_h)
        result.patched.append(spec.id)
        if any(k in props for k in GEOMETRY_KEYS):
            moved.append(spec.id)

    data["elements"] = elements
    path.write_text(json.dumps(data, indent=2))
    for eid in moved:
        result.collisions.extend(_collisions_for(elements, eid))
    return result


def patch_batch(filepath: Path, patches: list[PatchSpec]) -> PatchResult:
    return patch(filepath, patches)


def remove(filepath: Path, ids: list[str]) -> PatchResult:
    path = Path(filepath)
    data = json.loads(path.read_text())
    elements: list[dict[str, Any]] = data.get("elements", [])
    drop = set(ids)
    present = {e["id"] for e in elements}

    result = PatchResult()
    result.missing = [i for i in ids if i not in present]
    result.removed = [i for i in ids if i in present]

    cascade = set(drop)
    for e in elements:
        if e.get("type") == "arrow":
            sb = e.get("startBinding") or {}
            eb = e.get("endBinding") or {}
            if sb.get("elementId") in drop or eb.get("elementId") in drop:
                cascade.add(e["id"])

    kept: list[dict[str, Any]] = []
    for e in elements:
        if e["id"] in cascade:
            continue
        if e.get("boundElements"):
            e["boundElements"] = [b for b in e["boundElements"] if b.get("id") not in cascade]
        kept.append(e)

    data["elements"] = kept
    path.write_text(json.dumps(data, indent=2))
    return result


def _parse_patches(raw: str) -> list[PatchSpec]:
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError("patches must be a JSON array")
    return [PatchSpec.from_dict(p) for p in parsed]


def main() -> None:
    p = argparse.ArgumentParser(description="v4 patch")
    p.add_argument("file", type=Path)
    p.add_argument("patches", nargs="?")
    p.add_argument("--id")
    p.add_argument("--remove", nargs="+")
    for k in ("x", "y", "width", "height"):
        p.add_argument(f"--{k}", type=float)
    p.add_argument("--text")
    p.add_argument("--bg")
    p.add_argument("--stroke")
    p.add_argument("--stroke-width", dest="stroke_width", type=int)
    p.add_argument("--font-size", dest="font_size", type=int)
    args = p.parse_args()

    if args.remove:
        result = remove(args.file, args.remove)
    elif args.patches:
        result = patch(args.file, _parse_patches(args.patches))
    elif args.id:
        raw = {"id": args.id}
        for k in ("x", "y", "width", "height", "text", "bg", "stroke",
                 "stroke_width", "font_size"):
            v = getattr(args, k, None)
            if v is not None:
                raw[k] = v
        result = patch(args.file, [PatchSpec.from_dict(raw)])
    else:
        p.error("provide JSON patches, --id, or --remove")

    print(result.summary())
    sys.exit(0 if result.ok else 1)


if __name__ == "__main__":
    main()
