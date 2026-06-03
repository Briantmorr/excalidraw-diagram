from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers.patch import (
    PatchSpec,
    PatchResult,
    patch,
    patch_batch,
    remove,
)
from helpers.core import TEXT_BBOX_RATIO


def _shape(eid: str, x: float = 0, y: float = 0, w: float = 100, h: float = 50,
           etype: str = "rectangle", **extra) -> dict:
    return {
        "id": eid,
        "type": etype,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "backgroundColor": "#ffffff",
        "strokeColor": "#000000",
        "strokeWidth": 2,
        "version": 1,
        "boundElements": [],
        **extra,
    }


def _bound_text(tid: str, container: str, x: float, y: float,
                w: float = 40, h: float = 20, text: str = "lbl",
                fs: int = 14) -> dict:
    return {
        "id": tid,
        "type": "text",
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "text": text,
        "originalText": text,
        "rawText": text,
        "fontSize": fs,
        "lineHeight": 1.25,
        "containerId": container,
        "autoResize": True,
        "version": 1,
    }


def _arrow(aid: str, start: str | None, end: str | None) -> dict:
    return {
        "id": aid,
        "type": "arrow",
        "x": 0,
        "y": 0,
        "width": 100,
        "height": 0,
        "startBinding": {"elementId": start, "focus": 0, "gap": 8} if start else None,
        "endBinding": {"elementId": end, "focus": 0, "gap": 8} if end else None,
        "version": 1,
    }


def _write(elements: list[dict]) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".excalidraw", delete=False)
    json.dump({"type": "excalidraw", "elements": elements,
               "appState": {"viewBackgroundColor": "#ffffff",
                            "isBindingEnabled": True}}, f)
    f.close()
    return Path(f.name)


class TestPatch(unittest.TestCase):
    def test_geometry_patch_recenters_bound_text(self) -> None:
        shape = _shape("s1", x=0, y=0, w=100, h=50,
                       boundElements=[{"id": "s1_t", "type": "text"}])
        text = _bound_text("s1_t", "s1", x=30, y=15, w=40, h=20)
        path = _write([shape, text])

        result = patch(path, [PatchSpec(id="s1", x=200, y=100, width=200, height=80)])

        self.assertTrue(result.ok)
        self.assertEqual(result.patched, ["s1"])
        elements = json.loads(path.read_text())["elements"]
        new_text = next(e for e in elements if e["id"] == "s1_t")
        # Text re-centered: x = 200 + (200-40)/2 = 280, y = 100 + (80-20)/2 = 130
        self.assertEqual(new_text["x"], 280)
        self.assertEqual(new_text["y"], 130)

    def test_text_update_recomputes_width_height(self) -> None:
        text_elem = {
            "id": "t1",
            "type": "text",
            "x": 0, "y": 0, "width": 0, "height": 0,
            "text": "hi", "originalText": "hi", "rawText": "hi",
            "fontSize": 16, "lineHeight": 1.25,
            "containerId": None, "autoResize": True, "version": 1,
        }
        path = _write([text_elem])

        result = patch(path, [PatchSpec(id="t1", text="hello\nworld")])

        self.assertTrue(result.ok)
        elements = json.loads(path.read_text())["elements"]
        t = elements[0]
        # Longest line "hello" / "world" both 5 chars * 16 * 0.62 = 49.6
        self.assertAlmostEqual(t["width"], 5 * 16 * TEXT_BBOX_RATIO)
        # Two lines * 16 * 1.25 = 40
        self.assertAlmostEqual(t["height"], 2 * 16 * 1.25)
        self.assertEqual(t["text"], "hello\nworld")
        self.assertEqual(t["originalText"], "hello\nworld")

    def test_alias_bg_and_stroke(self) -> None:
        shape = _shape("s1")
        path = _write([shape])

        result = patch(path, [PatchSpec(id="s1", bg="#e0f4e8", stroke="#000000",
                                        stroke_width=3)])

        self.assertTrue(result.ok)
        e = json.loads(path.read_text())["elements"][0]
        self.assertEqual(e["backgroundColor"], "#e0f4e8")
        self.assertEqual(e["strokeColor"], "#000000")
        self.assertEqual(e["strokeWidth"], 3)
        self.assertEqual(e["version"], 2)

    def test_missing_id_reported_partial(self) -> None:
        path = _write([_shape("s1")])
        result = patch(path, [PatchSpec(id="ghost", x=10)])
        self.assertFalse(result.ok)
        self.assertEqual(result.missing, ["ghost"])
        self.assertEqual(result.patched, [])

    def test_batch_mixed_hits_and_misses(self) -> None:
        path = _write([_shape("a"), _shape("b", x=200)])
        result = patch_batch(path, [
            PatchSpec(id="a", x=50),
            PatchSpec(id="ghost", x=99),
            PatchSpec(id="b", bg="#fff4e0"),
        ])
        self.assertEqual(result.patched, ["a", "b"])
        self.assertEqual(result.missing, ["ghost"])
        elements = {e["id"]: e for e in json.loads(path.read_text())["elements"]}
        self.assertEqual(elements["a"]["x"], 50)
        self.assertEqual(elements["b"]["backgroundColor"], "#fff4e0")

    def test_remove_drops_dead_arrow_bindings(self) -> None:
        a = _shape("a")
        b = _shape("b", x=300)
        c = _shape("c", x=600)
        ab = _arrow("ab", "a", "b")
        bc = _arrow("bc", "b", "c")
        a["boundElements"] = [{"id": "ab", "type": "arrow"}]
        b["boundElements"] = [{"id": "ab", "type": "arrow"},
                              {"id": "bc", "type": "arrow"}]
        c["boundElements"] = [{"id": "bc", "type": "arrow"}]
        path = _write([a, b, c, ab, bc])

        result = remove(path, ["b"])

        self.assertEqual(result.removed, ["b"])
        ids = [e["id"] for e in json.loads(path.read_text())["elements"]]
        # b removed, both arrows touching b dropped
        self.assertNotIn("b", ids)
        self.assertNotIn("ab", ids)
        self.assertNotIn("bc", ids)
        # a and c kept, with stale boundElements pruned
        elements = {e["id"]: e for e in json.loads(path.read_text())["elements"]}
        self.assertEqual(elements["a"]["boundElements"], [])
        self.assertEqual(elements["c"]["boundElements"], [])

    def test_text_only_does_not_recenter_other_elements(self) -> None:
        s = _shape("s1", w=100, h=50,
                   boundElements=[{"id": "s1_t", "type": "text"}])
        t = _bound_text("s1_t", "s1", x=30, y=15)
        path = _write([s, t])

        # Recolor only — no geometry change → text must stay put.
        result = patch(path, [PatchSpec(id="s1", bg="#e7f5ff")])

        self.assertTrue(result.ok)
        elements = {e["id"]: e for e in json.loads(path.read_text())["elements"]}
        self.assertEqual(elements["s1_t"]["x"], 30)
        self.assertEqual(elements["s1_t"]["y"], 15)
        # version of text unchanged (no recenter mutation)
        self.assertEqual(elements["s1_t"]["version"], 1)


if __name__ == "__main__":
    unittest.main()
