"""Tests for v4 connect primitive."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from helpers.connect import (  # noqa: E402
    ConnectSpec,
    Edge,
    compute_edge_point,
    connect,
    connect_batch,
    detect_crossing,
)
from helpers.core import EDGE_GAP, shape_edge_point  # noqa: E402


def _shape(eid: str, x: float, y: float, w: float = 100, h: float = 60) -> dict:
    return {
        "type": "rectangle", "id": eid, "x": x, "y": y, "width": w, "height": h,
        "strokeColor": "#000000", "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
        "roughness": 1, "opacity": 100, "angle": 0,
        "seed": 1, "version": 1, "versionNonce": 1,
        "isDeleted": False, "groupIds": [], "boundElements": [],
        "link": None, "locked": False, "frameId": None,
        "roundness": None, "index": "a0", "updated": 0,
    }


def _write(tmp: Path, elements: list[dict]) -> Path:
    f = tmp / "t.excalidraw"
    f.write_text(json.dumps({"type": "excalidraw", "version": 2, "elements": elements,
                              "appState": {}, "files": {}}))
    return f


class TestConnect(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_basic_arrow_creation(self) -> None:
        f = _write(self.tmp, [_shape("a", 0, 0), _shape("b", 300, 0)])
        r = connect(f, [ConnectSpec(from_id="a", to_id="b")])
        self.assertEqual(len(r.created), 1)
        e = r.created[0]
        self.assertFalse(e.elbowed)
        data = json.loads(f.read_text())
        arrows = [el for el in data["elements"] if el["type"] == "arrow"]
        self.assertEqual(len(arrows), 1)
        arrow = arrows[0]
        # SAFE_BINDING form — no fixedPoint
        self.assertNotIn("fixedPoint", arrow["startBinding"])
        self.assertNotIn("fixedPoint", arrow["endBinding"])
        self.assertEqual(arrow["startBinding"]["elementId"], "a")
        self.assertEqual(arrow["endBinding"]["elementId"], "b")
        # Bidirectional boundElements
        a_el = next(el for el in data["elements"] if el["id"] == "a")
        b_el = next(el for el in data["elements"] if el["id"] == "b")
        self.assertTrue(any(b["id"] == arrow["id"] for b in a_el["boundElements"]))
        self.assertTrue(any(b["id"] == arrow["id"] for b in b_el["boundElements"]))
        # appState invariants
        self.assertEqual(data["appState"]["viewBackgroundColor"], "#ffffff")
        self.assertTrue(data["appState"]["isBindingEnabled"])
        # Source field preserved
        self.assertIn("source", data)

    def test_self_loop_silently_skipped(self) -> None:
        f = _write(self.tmp, [_shape("a", 0, 0)])
        r = connect(f, [ConnectSpec(from_id="a", to_id="a")])
        self.assertEqual(r.created, [])
        self.assertEqual(len(r.skipped), 1)
        self.assertIn("self-loop", r.skipped[0])
        data = json.loads(f.read_text())
        self.assertEqual([el for el in data["elements"] if el["type"] == "arrow"], [])

    def test_auto_elbow_on_crossing(self) -> None:
        # A and B at different heights, obstacle directly between them on the
        # straight line so straight crosses but H-then-V can route around.
        elements = [
            _shape("a", 0, 0, w=100, h=60),
            _shape("obs", 200, 100, w=100, h=60),
            _shape("b", 400, 200, w=100, h=60),
        ]
        f = _write(self.tmp, elements)
        r = connect(f, [ConnectSpec(from_id="a", to_id="b")])
        self.assertEqual(len(r.created), 1)
        self.assertTrue(r.created[0].elbowed)
        data = json.loads(f.read_text())
        arrow = next(el for el in data["elements"] if el["type"] == "arrow")
        # Elbow path has 3 points
        self.assertEqual(len(arrow["points"]), 3)

    def test_batch_with_label_global_shift(self) -> None:
        # Short horizontal arrow with long label triggers single global shift.
        f = _write(self.tmp, [_shape("a", 0, 0, w=80, h=60), _shape("b", 90, 0, w=80, h=60)])
        long_label = "a very long label that needs space"
        r = connect_batch(f, [ConnectSpec(from_id="a", to_id="b", label=long_label)])
        self.assertEqual(len(r.created), 1)
        data = json.loads(f.read_text())
        # Target was shifted outward
        b = next(el for el in data["elements"] if el["id"] == "b")
        self.assertGreater(b["x"], 90)
        # Label exists with correct shape
        labels = [el for el in data["elements"] if el["type"] == "text"]
        self.assertEqual(len(labels), 1)
        lbl = labels[0]
        self.assertEqual(lbl["containerId"], r.created[0].arrow_id)
        self.assertIn("originalText", lbl)
        self.assertIn("rawText", lbl)
        self.assertTrue(lbl["autoResize"])

    def test_arrows_appended_after_shapes(self) -> None:
        f = _write(self.tmp, [_shape("a", 0, 0), _shape("b", 200, 0), _shape("c", 400, 0)])
        connect(f, [ConnectSpec(from_id="a", to_id="b"), ConnectSpec(from_id="b", to_id="c")])
        data = json.loads(f.read_text())
        types = [el["type"] for el in data["elements"]]
        # All shapes must precede all arrows in elements ordering.
        last_shape_idx = max(i for i, t in enumerate(types) if t == "rectangle")
        first_arrow_idx = min(i for i, t in enumerate(types) if t == "arrow")
        self.assertLess(last_shape_idx, first_arrow_idx)
        # Indices monotonic and 2-char base36 suffixed
        arrows = [el for el in data["elements"] if el["type"] == "arrow"]
        idxs = [a["index"] for a in arrows]
        self.assertEqual(idxs, sorted(idxs))

    def test_compute_edge_point_geometry_bias(self) -> None:
        # dy > 2*dx → vertical face from source. Auto-side points sit on the
        # true outline offset OUTWARD by EDGE_GAP, so bottom edge 60 → 66.
        a = _shape("a", 0, 0, w=100, h=60)
        b = _shape("b", 0, 400, w=100, h=60)
        x, y, side = compute_edge_point(a, b, None, is_source=True)
        self.assertEqual(side, "bottom")
        self.assertEqual(x, 50)          # centered on the vertical spine
        self.assertEqual(y, 60 + EDGE_GAP)
        # dx > dy → horizontal face; right edge 100 → offset outward by EDGE_GAP.
        c = _shape("c", 500, 0, w=100, h=60)
        x, y, side = compute_edge_point(a, c, None, is_source=True)
        self.assertEqual(side, "right")
        self.assertEqual(x, 100 + EDGE_GAP)
        # Forced side overrides face selection; also offset outward by EDGE_GAP.
        x, y, side = compute_edge_point(a, c, "top", is_source=True)
        self.assertEqual(side, "top")
        self.assertEqual(y, 0 - EDGE_GAP)

    def test_shape_edge_point_ellipse_and_diamond(self) -> None:
        # Ellipse centered at (100,100), semi-axes 100x50. A ray straight down
        # exits the curve at the bottom vertex (100, 150), offset outward by GAP.
        ell = {"type": "ellipse", "id": "e", "x": 0, "y": 50,
               "width": 200, "height": 100}
        x, y = shape_edge_point(ell, (100, 400))
        self.assertAlmostEqual(x, 100, places=6)
        self.assertAlmostEqual(y, 150 + EDGE_GAP, places=6)
        # A 45-degree ray must land on the ellipse curve, strictly inside the
        # bbox corner (the old bbox-midpoint logic would have overshot).
        x, y = shape_edge_point(ell, (100 + 1000, 100 + 1000))
        self.assertLess(x, 200)   # inside right bbox edge
        self.assertLess(y, 150)   # inside bottom bbox edge
        self.assertGreater(x, 100)
        self.assertGreater(y, 100)
        # Diamond |x/hw|+|y/hh|=1: ray down exits bottom tip (100,150)+gap.
        dia = {"type": "diamond", "id": "d", "x": 0, "y": 50,
               "width": 200, "height": 100}
        x, y = shape_edge_point(dia, (100, 400))
        self.assertAlmostEqual(x, 100, places=6)
        self.assertAlmostEqual(y, 150 + EDGE_GAP, places=6)

    def test_detect_crossing_excludes_endpoints(self) -> None:
        a = _shape("a", 0, 0)
        b = _shape("b", 300, 0)
        obs = _shape("obs", 150, -20)
        hits = detect_crossing((50, 30), (350, 30), [a, b, obs], {"a", "b"})
        self.assertEqual(hits, ["obs"])
        # No crossing when path is clear above the obstacle.
        hits = detect_crossing((50, 30), (350, 30), [a, b], {"a", "b"})
        self.assertEqual(hits, [])

    def test_force_elbow(self) -> None:
        f = _write(self.tmp, [_shape("a", 0, 0), _shape("b", 300, 0)])
        r = connect(f, [ConnectSpec(from_id="a", to_id="b", force_elbow=True)])
        self.assertTrue(r.created[0].elbowed)


class NormalizeLabelTests(unittest.TestCase):
    def test_strips_separator_segment(self) -> None:
        from helpers.connect import normalize_label
        self.assertEqual(normalize_label("Yes / Gold"), "Yes")
        self.assertEqual(normalize_label("yes,gold"), "yes")
        self.assertEqual(normalize_label("yes; gold"), "yes")
        self.assertEqual(normalize_label("yes - gold"), "yes")

    def test_truncates_to_eight_chars(self) -> None:
        from helpers.connect import normalize_label
        self.assertEqual(normalize_label("approved!"), "approved")
        self.assertIsNotNone(normalize_label("ok"))

    def test_handles_empty_and_none(self) -> None:
        from helpers.connect import normalize_label
        self.assertIsNone(normalize_label(None))
        self.assertIsNone(normalize_label(""))
        self.assertIsNone(normalize_label("   "))

    def test_connectspec_normalises_in_post_init(self) -> None:
        spec = ConnectSpec(from_id="a", to_id="b", label="Yes / Gold")
        self.assertEqual(spec.label, "Yes")


if __name__ == "__main__":
    unittest.main()
