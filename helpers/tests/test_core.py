from __future__ import annotations

import unittest

from helpers import core


class TestConstants(unittest.TestCase):
    def test_text_bbox_ratio_flipped_to_062(self) -> None:
        self.assertEqual(core.TEXT_BBOX_RATIO, 0.62)

    def test_color_invariants(self) -> None:
        self.assertEqual(core.BORDER_COLOR, "#000000")
        self.assertEqual(core.ARROW_COLOR, "#3a3428")
        self.assertEqual(core.BG_COLOR, "#ffffff")
        self.assertEqual(core.TEXT_BODY, "#0a0a0a")
        self.assertEqual(core.TEXT_SUBORDINATE, "#868e96")
        self.assertEqual(core.DEFAULT_FONT_FAMILY, 1)

    def test_palette_keys(self) -> None:
        for key in ("grey", "blue", "green", "yellow", "red", "cream", "silver"):
            self.assertIn(key, core.PALETTE)
            self.assertTrue(core.PALETTE[key].startswith("#"))

    def test_appstate_defaults(self) -> None:
        s = core.appstate_defaults()
        self.assertTrue(s["isBindingEnabled"])
        self.assertEqual(s["viewBackgroundColor"], "#ffffff")

    def test_rubric_targets_reexport(self) -> None:
        # RUBRIC_TARGETS lives in helpers._rubric_targets; consumers import it directly.
        from helpers import _rubric_targets as rt
        self.assertEqual(rt.RUBRIC_TARGETS["text_bbox_ratio"], 0.62)
        self.assertIn("pipeline", rt.PER_PATTERN)


class TestIndices(unittest.TestCase):
    def test_frac_index_monotonic_2char(self) -> None:
        self.assertEqual(core.frac_index("a", 0), "a00")
        self.assertEqual(core.frac_index("a", 1), "a01")
        self.assertEqual(core.frac_index("a", 35), "a0z")
        self.assertEqual(core.frac_index("a", 36), "a10")
        self.assertEqual(core.frac_index("a", 36 * 36 - 1), "azz")

    def test_frac_index_lex_monotonic(self) -> None:
        seq = [core.frac_index("a", n) for n in range(0, 200)]
        self.assertEqual(seq, sorted(seq))

    def test_frac_index_out_of_range(self) -> None:
        with self.assertRaises(ValueError):
            core.frac_index("a", -1)
        with self.assertRaises(ValueError):
            core.frac_index("a", 36 * 36)

    def test_next_index_empty(self) -> None:
        self.assertEqual(core.next_index([]), "a00")

    def test_next_index_appends(self) -> None:
        elems = [{"index": "a00"}, {"index": "a05"}, {"index": "a02"}]
        self.assertEqual(core.next_index(elems), "a050")


class TestTextMath(unittest.TestCase):
    def test_text_width_uses_062(self) -> None:
        self.assertAlmostEqual(core.text_width("hello", 14), 5 * 14 * 0.62)

    def test_text_width_uses_longest_line(self) -> None:
        self.assertAlmostEqual(core.text_width("hi\nlonger", 16), len("longer") * 16 * 0.62)

    def test_text_width_empty(self) -> None:
        self.assertEqual(core.text_width("", 14), 0.0)

    def test_text_height(self) -> None:
        self.assertAlmostEqual(core.text_height(2, 16), 2 * 16 * 1.25)


class TestEmitText(unittest.TestCase):
    def _parent(self) -> dict:
        return {"id": "rect_1", "x": 100, "y": 200, "width": 200, "height": 100}

    def test_bound_text_centered_with_required_fields(self) -> None:
        p = self._parent()
        t = core.emit_bound_text(p, "Hello", font_size=16)
        self.assertEqual(t["containerId"], "rect_1")
        self.assertEqual(t["text"], "Hello")
        self.assertEqual(t["originalText"], "Hello")
        self.assertEqual(t["rawText"], "Hello")
        self.assertTrue(t["autoResize"])
        self.assertEqual(t["lineHeight"], 1.25)
        self.assertEqual(t["fontFamily"], 1)
        # centered horizontally
        expected_x = p["x"] + (p["width"] - t["width"]) / 2
        self.assertAlmostEqual(t["x"], expected_x)

    def test_bound_text_normalizes_literal_newlines(self) -> None:
        p = self._parent()
        t = core.emit_bound_text(p, "a\\nb")
        self.assertEqual(t["text"], "a\nb")

    def test_free_text_has_null_container_and_required_fields(self) -> None:
        t = core.emit_free_text("Title", x=10, y=20, font_size=28)
        self.assertIsNone(t["containerId"])
        self.assertEqual(t["originalText"], "Title")
        self.assertEqual(t["rawText"], "Title")
        self.assertTrue(t["autoResize"])
        self.assertEqual(t["lineHeight"], 1.25)
        self.assertEqual(t["x"], 10)
        self.assertEqual(t["y"], 20)


class TestBindings(unittest.TestCase):
    def test_safe_binding_simple_form(self) -> None:
        b = core.SAFE_BINDING("rect_1")
        self.assertEqual(b, {"elementId": "rect_1", "focus": 0.5, "gap": 1})
        self.assertNotIn("fixedPoint", b)
        self.assertNotIn("mode", b)

    def test_safe_binding_custom(self) -> None:
        b = core.SAFE_BINDING("rect_2", focus=-0.3, gap=16)
        self.assertEqual(b["focus"], -0.3)
        self.assertEqual(b["gap"], 16)


class TestBoundsAndFrames(unittest.TestCase):
    def test_get_element_bounds(self) -> None:
        b = core.get_element_bounds({"x": 10, "y": 20, "width": 100, "height": 50})
        self.assertEqual((b.x, b.y, b.x2, b.y2), (10, 20, 110, 70))
        self.assertEqual(b.width, 100)
        self.assertEqual(b.height, 50)
        self.assertEqual(b.cx, 60)
        self.assertEqual(b.cy, 45)

    def test_canvas_bounds_excludes_text_and_deleted(self) -> None:
        elems = [
            {"id": "a", "type": "rectangle", "x": 0, "y": 0, "width": 100, "height": 50},
            {"id": "b", "type": "rectangle", "x": 200, "y": 100, "width": 50, "height": 50},
            {"id": "t", "type": "text", "x": -1000, "y": -1000, "width": 50, "height": 20},
            {"id": "d", "type": "rectangle", "x": -500, "y": 0, "width": 10, "height": 10, "isDeleted": True},
        ]
        b = core.get_canvas_bounds(elems)
        assert b is not None
        self.assertEqual((b.x, b.y, b.x2, b.y2), (0, 0, 250, 150))

    def test_canvas_bounds_empty_returns_none(self) -> None:
        self.assertIsNone(core.get_canvas_bounds([]))

    def test_detect_frames_finds_transparent_enclosing_rect(self) -> None:
        frame = {"id": "frame", "type": "rectangle", "x": 0, "y": 0,
                 "width": 1000, "height": 1000, "backgroundColor": "transparent"}
        elems = [
            frame,
            {"id": "c1", "type": "rectangle", "x": 10, "y": 10, "width": 50, "height": 50,
             "backgroundColor": "#eae8e4"},
            {"id": "c2", "type": "rectangle", "x": 100, "y": 100, "width": 50, "height": 50,
             "backgroundColor": "#eae8e4"},
            {"id": "c3", "type": "rectangle", "x": 200, "y": 200, "width": 50, "height": 50,
             "backgroundColor": "#eae8e4"},
        ]
        ids = core.get_frame_ids(elems)
        self.assertIn("frame", ids)


class TestRecenterText(unittest.TestCase):
    def test_recenter_bound_text_on_resize(self) -> None:
        parent = {"id": "p1", "x": 0, "y": 0, "width": 200, "height": 100}
        text = {"id": "p1_text", "type": "text", "containerId": "p1",
                "x": 50, "y": 40, "width": 100, "height": 20, "version": 1}
        core.recenter_text([text], parent, old_x=0, old_y=0, old_w=200, old_h=100)
        # No move, no resize → unchanged
        self.assertEqual(text["x"], 50)

        parent["width"] = 300
        parent["height"] = 200
        core.recenter_text([text], parent, old_x=0, old_y=0, old_w=200, old_h=100)
        self.assertEqual(text["x"], (300 - 100) / 2)
        self.assertEqual(text["y"], (200 - 20) / 2)
        self.assertEqual(text["version"], 2)

    def test_recenter_translates_on_move(self) -> None:
        parent = {"id": "p2", "x": 50, "y": 60, "width": 100, "height": 100}
        text = {"id": "p2_text", "type": "text", "containerId": "p2",
                "x": 60, "y": 100, "width": 80, "height": 20, "version": 1}
        core.recenter_text([text], parent, old_x=0, old_y=0, old_w=100, old_h=100)
        self.assertEqual(text["x"], 60 + 50)
        self.assertEqual(text["y"], 100 + 60)


class TestRolePresets(unittest.TestCase):
    def test_role_presets_present(self) -> None:
        for role in ("stage", "branch", "hub", "spoke", "sink", "step", "title"):
            self.assertIn(role, core.ROLE_PRESETS)

    def test_role_preset_is_dataclass_instance(self) -> None:
        hub = core.ROLE_PRESETS["hub"]
        self.assertIsInstance(hub, core.RolePreset)
        self.assertGreater(hub.width, 0)


class TestDefaults(unittest.TestCase):
    def test_shape_defaults_has_black_border(self) -> None:
        self.assertEqual(core.SHAPE_DEFAULTS["strokeColor"], "#000000")

    def test_arrow_defaults_charcoal(self) -> None:
        self.assertEqual(core.ARROW_DEFAULTS["strokeColor"], "#3a3428")
        self.assertEqual(core.ARROW_DEFAULTS["endArrowhead"], "arrow")
        self.assertIsNone(core.ARROW_DEFAULTS["startArrowhead"])

    def test_text_defaults_excalifont(self) -> None:
        self.assertEqual(core.TEXT_DEFAULTS["fontFamily"], 1)
        self.assertTrue(core.TEXT_DEFAULTS["autoResize"])


if __name__ == "__main__":
    unittest.main()
