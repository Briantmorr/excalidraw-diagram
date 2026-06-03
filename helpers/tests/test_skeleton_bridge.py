from __future__ import annotations

import unittest

from helpers import skeleton_bridge
from helpers.skeleton_bridge import (
    Bridge,
    CanvasResult,
    SvgResult,
    convert_skeleton,
    export_to_canvas,
    export_to_svg,
    get_bridge,
)


class SkeletonBridgeTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        skeleton_bridge._close_bridge()

    def test_get_bridge_singleton(self) -> None:
        b1 = get_bridge()
        b2 = get_bridge()
        self.assertIs(b1, b2)
        self.assertIsInstance(b1, Bridge)

    def test_convert_simple_rectangle(self) -> None:
        skeleton = [{"type": "rectangle", "x": 0, "y": 0, "width": 100, "height": 50}]
        elements = convert_skeleton(skeleton)
        self.assertEqual(len(elements), 1)
        self.assertEqual(elements[0]["type"], "rectangle")
        self.assertIn("id", elements[0])
        self.assertEqual(elements[0]["width"], 100)

    def test_convert_with_label_creates_text(self) -> None:
        skeleton = [
            {
                "type": "rectangle",
                "x": 0,
                "y": 0,
                "width": 200,
                "height": 80,
                "label": {"text": "Hello"},
            }
        ]
        elements = convert_skeleton(skeleton)
        types = [e["type"] for e in elements]
        self.assertIn("rectangle", types)
        self.assertIn("text", types)
        text_el = next(e for e in elements if e["type"] == "text")
        self.assertEqual(text_el["text"], "Hello")

    def test_convert_arrow_with_bindings(self) -> None:
        skeleton = [
            {"type": "rectangle", "id": "a", "x": 0, "y": 0, "width": 100, "height": 50},
            {"type": "rectangle", "id": "b", "x": 200, "y": 0, "width": 100, "height": 50},
            {"type": "arrow", "x": 0, "y": 0, "start": {"id": "a"}, "end": {"id": "b"}},
        ]
        elements = convert_skeleton(skeleton)
        arrow = next(e for e in elements if e["type"] == "arrow")
        self.assertIsNotNone(arrow.get("startBinding"))
        self.assertIsNotNone(arrow.get("endBinding"))

    def test_regenerate_ids_changes_ids(self) -> None:
        skeleton = [
            {"type": "rectangle", "id": "fixed-id", "x": 0, "y": 0, "width": 50, "height": 50}
        ]
        without = convert_skeleton(skeleton, regenerate_ids=False)
        regen = convert_skeleton(skeleton, regenerate_ids=True)
        self.assertEqual(without[0]["id"], "fixed-id")
        self.assertNotEqual(regen[0]["id"], "fixed-id")

    def test_export_to_canvas_returns_png(self) -> None:
        skeleton = [{"type": "rectangle", "x": 0, "y": 0, "width": 100, "height": 50}]
        elements = convert_skeleton(skeleton)
        result = export_to_canvas(elements, scale=1.0)
        self.assertIsInstance(result, CanvasResult)
        self.assertTrue(result.png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(result.width, 0)
        self.assertGreater(result.height, 0)

    def test_export_to_svg_returns_xml(self) -> None:
        skeleton = [{"type": "rectangle", "x": 0, "y": 0, "width": 100, "height": 50}]
        elements = convert_skeleton(skeleton)
        result = export_to_svg(elements)
        self.assertIsInstance(result, SvgResult)
        self.assertIn("<svg", result.xml)
        self.assertGreater(result.width, 0)


if __name__ == "__main__":
    unittest.main()
