from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers.canvas_view import (
    CanvasInfo,
    ElementRecord,
    canvas_info,
    format_compact,
    format_full,
    summarize,
)


def _write(elements: list[dict]) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".excalidraw", delete=False)
    json.dump({"type": "excalidraw", "version": 2, "elements": elements,
               "appState": {"viewBackgroundColor": "#ffffff"}}, f)
    f.close()
    return Path(f.name)


def _rect(eid: str, x: float, y: float, w: float = 150, h: float = 50,
          bg: str | None = None, bound: list[str] | None = None) -> dict:
    return {
        "id": eid, "type": "rectangle", "x": x, "y": y, "width": w, "height": h,
        "backgroundColor": bg or "transparent",
        "boundElements": [{"id": b, "type": "text"} for b in (bound or [])],
        "isDeleted": False,
    }


def _text(eid: str, x: float, y: float, txt: str, container: str | None = None,
          w: float = 100, h: float = 25) -> dict:
    return {
        "id": eid, "type": "text", "x": x, "y": y, "width": w, "height": h,
        "text": txt, "fontSize": 16, "containerId": container,
        "isDeleted": False,
    }


def _arrow(eid: str, x: float, y: float, dx: float, dy: float,
           start: str | None = None, end: str | None = None) -> dict:
    return {
        "id": eid, "type": "arrow", "x": x, "y": y, "width": dx, "height": dy,
        "points": [[0, 0], [dx, dy]],
        "startBinding": {"elementId": start, "focus": 0, "gap": 8} if start else None,
        "endBinding": {"elementId": end, "focus": 0, "gap": 8} if end else None,
        "isDeleted": False,
    }


class InspectTests(unittest.TestCase):
    def test_empty_canvas(self) -> None:
        path = _write([])
        info = canvas_info(path)
        self.assertEqual(info.n_elements, 0)
        self.assertIsNone(info.bounds)
        out = summarize(path, "compact")
        self.assertIn("empty canvas", out)

    def test_compact_groups_text_under_shape(self) -> None:
        elems = [
            _rect("r1", 0, 0, 150, 50, bound=["t1"]),
            _text("t1", 25, 12, "Hello", container="r1"),
        ]
        path = _write(elems)
        out = format_compact(canvas_info(path))
        self.assertIn("r1", out)
        self.assertIn('"Hello"', out)
        # text not printed as standalone [text] line
        self.assertNotIn("[text] t1", out)

    def test_arrow_endpoints_and_binding(self) -> None:
        elems = [
            _rect("a", 0, 0),
            _rect("b", 300, 0),
            _arrow("ar1", 150, 25, 150, 0, start="a", end="b"),
        ]
        path = _write(elems)
        out = format_compact(canvas_info(path))
        self.assertIn("(150,25)→(300,25)", out)
        self.assertIn("[a→b]", out)

    def test_canvas_info_metrics(self) -> None:
        elems = [
            _rect("s1", 0, 0, 100, 50),
            _rect("s2", 150, 0, 100, 50),
            _rect("s3", 300, 0, 100, 50),
        ]
        info = canvas_info(_write(elems))
        self.assertEqual(info.n_shapes, 3)
        self.assertEqual(info.n_arrows, 0)
        self.assertEqual(info.canvas_size, (400.0, 50.0))
        self.assertAlmostEqual(info.gap_h_median or 0, 50.0)
        # area_ratio = 3 * 100*50 / (400*50) = 0.75
        self.assertAlmostEqual(info.area_ratio, 0.75)
        self.assertIn("flat", info.hierarchy_verdict)

    def test_hierarchy_strong(self) -> None:
        elems = [
            _rect("hub", 0, 0, 240, 120),
            _rect("sp1", 300, 0, 100, 50),
            _rect("sp2", 300, 80, 100, 50),
        ]
        info = canvas_info(_write(elems))
        self.assertIn("strong", info.hierarchy_verdict)

    def test_json_format_is_valid(self) -> None:
        elems = [_rect("r1", 0, 0), _arrow("ar1", 150, 25, 100, 0)]
        out = summarize(_write(elems), "json")
        parsed = json.loads(out)
        self.assertEqual(parsed["n_shapes"], 1)
        self.assertEqual(parsed["n_arrows"], 1)
        self.assertEqual(len(parsed["elements"]), 2)

    def test_full_format_per_element_lines(self) -> None:
        elems = [
            _rect("r1", 0, 0, bg="#e0f4e8"),
            _text("t1", 25, 12, "Hi", container="r1"),
        ]
        out = format_full(canvas_info(_write(elems)))
        self.assertIn("r1", out)
        self.assertIn("t1", out)
        self.assertIn("bg=#e0f4e8", out)
        self.assertIn("container=r1", out)

    def test_dataclass_records_typed(self) -> None:
        info = canvas_info(_write([_rect("r1", 0, 0)]))
        self.assertIsInstance(info, CanvasInfo)
        self.assertIsInstance(info.elements[0], ElementRecord)
        self.assertEqual(info.elements[0].id, "r1")


if __name__ == "__main__":
    unittest.main()
