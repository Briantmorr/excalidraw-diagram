from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers import place
from helpers.place import (
    Below, Explicit, Like, Near, PlaceSpec, RightOf, Role, Row, Spine,
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text())


class TestPlace(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "diagram.excalidraw"

    def test_role_defaults_from_core(self) -> None:
        spec = PlaceSpec(id="hub1", role=Role.HUB, text="Center", anchor=Explicit(x=0, y=0))
        result = place.place(self.path, [spec])
        self.assertTrue(result.ok, msg=str(result))
        data = _read(self.path)
        shape = next(e for e in data["elements"] if e["id"] == "hub1")
        self.assertEqual(shape["width"], 240)
        self.assertEqual(shape["height"], 120)
        self.assertEqual(shape["strokeColor"], "#000000")
        self.assertEqual(shape["strokeWidth"], 3)
        self.assertEqual(shape["backgroundColor"], "#e7f5ff")

    def test_anchor_right_of_chains(self) -> None:
        specs = [
            PlaceSpec(id="a", text="A", anchor=Explicit(x=100, y=100), width=160, height=60),
            PlaceSpec(id="b", text="B", anchor=RightOf(id="a", gap=25), width=160, height=60),
            PlaceSpec(id="c", text="C", anchor=RightOf(id="b", gap=25), width=160, height=60),
        ]
        result = place.place(self.path, specs)
        self.assertTrue(result.ok)
        data = _read(self.path)
        b = next(e for e in data["elements"] if e["id"] == "b")
        c = next(e for e in data["elements"] if e["id"] == "c")
        self.assertEqual(b["x"], 100 + 160 + 25)
        self.assertEqual(c["x"], b["x"] + 160 + 25)

    def test_row_centered(self) -> None:
        specs = [
            PlaceSpec(id=f"s{i}", text=f"S{i}",
                      anchor=Row(y=200, index=i, total=3, gap=25, width=140, center_x=500))
            for i in range(3)
        ]
        result = place.place(self.path, specs)
        self.assertTrue(result.ok)
        data = _read(self.path)
        # Row total width = 140*3 + 25*2 = 470. center 500 => x_start = 265.
        s0 = next(e for e in data["elements"] if e["id"] == "s0")
        s2 = next(e for e in data["elements"] if e["id"] == "s2")
        self.assertEqual(s0["x"], 265.0)
        self.assertEqual(s2["x"], 265.0 + 2 * (140 + 25))
        for sid in ("s0", "s1", "s2"):
            self.assertEqual(next(e for e in data["elements"] if e["id"] == sid)["y"], 200)

    def test_spine_vertical(self) -> None:
        specs = [
            PlaceSpec(id=f"n{i}", text=f"N{i}",
                      anchor=Spine(x=400, y_index=i, gap=100, y_start=50), width=160)
            for i in range(3)
        ]
        result = place.place(self.path, specs)
        self.assertTrue(result.ok)
        data = _read(self.path)
        for i in range(3):
            n = next(e for e in data["elements"] if e["id"] == f"n{i}")
            self.assertEqual(n["x"], 400 - 80)  # centered at x=400
            self.assertEqual(n["y"], 50 + i * 100)

    def test_monotonic_indices_and_shape_before_text(self) -> None:
        specs = [
            PlaceSpec(id=f"e{i}", text=f"T{i}", anchor=Explicit(x=i * 200, y=0))
            for i in range(4)
        ]
        result = place.place(self.path, specs)
        self.assertTrue(result.ok)
        data = _read(self.path)
        elements = data["elements"]
        indices = [e["index"] for e in elements]
        self.assertEqual(indices, sorted(indices), msg=f"indices not monotonic: {indices}")
        # Shape must come before its bound text in the array.
        for i in range(4):
            shape_idx = next(j for j, e in enumerate(elements) if e["id"] == f"e{i}")
            text_idx = next(j for j, e in enumerate(elements) if e["id"] == f"e{i}_text")
            self.assertLess(shape_idx, text_idx)

    def test_duplicate_id_rejected(self) -> None:
        ok = place.place(self.path, [PlaceSpec(id="x", anchor=Explicit(x=0, y=0))])
        self.assertTrue(ok.ok)
        dup = place.place(self.path, [PlaceSpec(id="x", anchor=Explicit(x=10, y=10))])
        self.assertFalse(dup.ok)
        self.assertIn("duplicate", dup.errors[0])

    def test_like_copies_size_and_style(self) -> None:
        result = place.place(self.path, [
            PlaceSpec(id="src", role=Role.HUB, anchor=Explicit(x=0, y=0)),
            PlaceSpec(id="dst", anchor=Like(id="src"), x=300, y=300),
        ])
        self.assertTrue(result.ok)
        data = _read(self.path)
        src = next(e for e in data["elements"] if e["id"] == "src")
        dst = next(e for e in data["elements"] if e["id"] == "dst")
        self.assertEqual(src["width"], dst["width"])
        self.assertEqual(src["height"], dst["height"])
        self.assertEqual(src["backgroundColor"], dst["backgroundColor"])

    def test_near_falls_back_when_blocked(self) -> None:
        # First place an anchor and immediately surround it on right side.
        place.place(self.path, [
            PlaceSpec(id="anchor", anchor=Explicit(x=200, y=200), width=160, height=60),
            PlaceSpec(id="block_r", anchor=Explicit(x=200 + 160 + 30, y=200), width=160, height=60),
        ])
        # Now ask for `near` direction=right; should pick a different free side.
        result = place.place(self.path, [
            PlaceSpec(id="probe", anchor=Near(id="anchor", direction="right", gap=30),
                      width=140, height=60),
        ])
        self.assertTrue(result.ok)
        data = _read(self.path)
        probe = next(e for e in data["elements"] if e["id"] == "probe")
        # Must NOT overlap block_r at x in [390, 550]
        self.assertFalse(390 <= probe["x"] < 550 and probe["y"] == 200,
                         msg=f"probe should not collide: x={probe['x']} y={probe['y']}")

    def test_cli_json_array(self) -> None:
        # Drive via from_dict path to mimic CLI consumption.
        raw = [
            {"id": "t1", "role": "title", "text": "Hello", "anchor": {"rel": "explicit", "x": 0, "y": 0}},
            {"id": "r1", "text": "Body",
             "anchor": {"rel": "row", "y": 100, "index": 0, "total": 1, "width": 200}},
        ]
        specs = [PlaceSpec.from_dict(d) for d in raw]
        result = place.place(self.path, specs)
        self.assertTrue(result.ok, msg=str(result))
        data = _read(self.path)
        title = next(e for e in data["elements"] if e["id"] == "t1")
        self.assertEqual(title["type"], "text")
        self.assertEqual(title["fontSize"], 28)

    def test_invariants_appstate_and_source(self) -> None:
        place.place(self.path, [PlaceSpec(id="a", anchor=Explicit(x=0, y=0))])
        data = _read(self.path)
        self.assertEqual(data["appState"]["viewBackgroundColor"], "#ffffff")
        self.assertTrue(data["appState"]["isBindingEnabled"])
        self.assertIn("obsidian-excalidraw", data["source"])


if __name__ == "__main__":
    unittest.main()
