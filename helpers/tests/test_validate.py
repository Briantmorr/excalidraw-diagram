from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers.validate import (
    Finding,
    ValidationReport,
    _has_directed_cycle,
    check_aesthetics,
    check_all,
    check_argument,
    check_collisions,
    check_hierarchy,
    check_invariants,
    check_title,
    tighten,
)


def _shape(eid: str, x: float, y: float, w: float = 100, h: float = 50,
           type_: str = "rectangle", index: str | None = None,
           **extra) -> dict:
    base = {
        "id": eid, "type": type_, "x": x, "y": y, "width": w, "height": h,
        "strokeColor": "#000000", "backgroundColor": "#eae8e4",
        "isDeleted": False, "boundElements": [],
    }
    if index is not None:
        base["index"] = index
    base.update(extra)
    return base


def _text(eid: str, x: float, y: float, text: str, fs: int = 16,
          container_id: str | None = None, index: str | None = None,
          **extra) -> dict:
    base = {
        "id": eid, "type": "text", "x": x, "y": y,
        "width": len(text) * fs * 0.62, "height": fs * 1.25,
        "text": text, "fontSize": fs, "fontFamily": 1,
        "strokeColor": "#0a0a0a", "isDeleted": False,
        "containerId": container_id,
        "originalText": text, "rawText": text,
        "autoResize": True, "lineHeight": 1.25,
    }
    if index is not None:
        base["index"] = index
    base.update(extra)
    return base


def _arrow(eid: str, src: str, dst: str, x: float = 0, y: float = 0,
           index: str | None = None, **extra) -> dict:
    base = {
        "id": eid, "type": "arrow", "x": x, "y": y,
        "width": 100, "height": 0,
        "points": [[0, 0], [100, 0]],
        "startBinding": {"elementId": src, "focus": 0.0, "gap": 8},
        "endBinding": {"elementId": dst, "focus": 0.0, "gap": 8},
        "strokeColor": "#3a3428", "isDeleted": False,
    }
    if index is not None:
        base["index"] = index
    base.update(extra)
    return base


def _write_doc(elements: list[dict], app_state: dict | None = None,
               source: str | None = "validate-test") -> Path:
    doc: dict = {
        "type": "excalidraw", "version": 2, "elements": elements,
        "appState": app_state or {"isBindingEnabled": True,
                                  "viewBackgroundColor": "#ffffff"},
    }
    if source is not None:
        doc["source"] = source
    fd = tempfile.NamedTemporaryFile(mode="w", suffix=".excalidraw",
                                     delete=False, encoding="utf-8")
    fd.write(json.dumps(doc, indent=2))
    fd.close()
    return Path(fd.name)


class TestCollisions(unittest.TestCase):
    def test_no_collision_when_separated(self) -> None:
        els = [_shape("a", 0, 0), _shape("b", 200, 200)]
        self.assertEqual(check_collisions(els), [])

    def test_overlap_reported_as_warn(self) -> None:
        els = [_shape("a", 0, 0, 100, 100), _shape("b", 50, 50, 100, 100)]
        out = check_collisions(els)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].severity, "WARN")
        self.assertEqual(out[0].code, "COLLISION")
        self.assertEqual(set(out[0].element_ids), {"a", "b"})

    def test_bound_text_inside_shape_skipped(self) -> None:
        shape = _shape("box", 0, 0, 100, 50)
        txt = _text("t", 20, 15, "hi", container_id="box")
        shape["boundElements"] = [{"id": "t", "type": "text"}]
        self.assertEqual(check_collisions([shape, txt]), [])

    def test_target_id_filter(self) -> None:
        els = [_shape("a", 0, 0, 100, 100),
               _shape("b", 50, 50, 100, 100),
               _shape("c", 500, 500)]
        out = check_collisions(els, target_id="c")
        self.assertEqual(out, [])
        out = check_collisions(els, target_id="a")
        self.assertEqual(len(out), 1)


class TestHierarchy(unittest.TestCase):
    def test_flat_hierarchy_warned(self) -> None:
        els = [_shape("a", 0, 0, 100, 50), _shape("b", 200, 0, 105, 50)]
        out = check_hierarchy(els)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].code, "HIERARCHY_FLAT")

    def test_strong_hierarchy_passes(self) -> None:
        els = [_shape("a", 0, 0, 240, 120), _shape("b", 400, 0, 100, 50)]
        self.assertEqual(check_hierarchy(els), [])

    def test_uniform_row_passes(self) -> None:
        els = [_shape(f"s{i}", i * 200, 0, 100, 50) for i in range(4)]
        self.assertEqual(check_hierarchy(els), [])


class TestArgument(unittest.TestCase):
    def test_monoculture_no_flow_warns(self) -> None:
        els = [_shape("a", 0, 0, 100, 50), _shape("b", 200, 0, 100, 50),
               _shape("c", 400, 0, 100, 50), _shape("d", 600, 0, 100, 50),
               _shape("e", 800, 0, 100, 50)]
        out = check_argument(els)
        codes = {f.code for f in out}
        self.assertIn("WEAK_ARGUMENT", codes)
        self.assertIn("NO_SHAPE_VARIETY", codes)

    def test_pipeline_with_arrows_passes_weak_test(self) -> None:
        els = [_shape("a", 0, 0, 150, 50), _shape("b", 250, 0, 150, 50),
               _shape("c", 500, 0, 150, 50), _shape("d", 750, 0, 150, 50)]
        els.extend([_arrow("ar1", "a", "b"), _arrow("ar2", "b", "c"),
                    _arrow("ar3", "c", "d")])
        codes = {f.code for f in check_argument(els)}
        self.assertNotIn("WEAK_ARGUMENT", codes)


class TestTitle(unittest.TestCase):
    def test_no_title_fail(self) -> None:
        els = [_shape("a", 0, 100, 100, 50), _shape("b", 200, 100, 100, 50)]
        out = check_title(els)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].severity, "FAIL")
        self.assertEqual(out[0].code, "NO_TITLE")

    def test_takeaway_title_passes(self) -> None:
        els = [
            _shape("a", 0, 200, 200, 100), _shape("b", 300, 200, 200, 100),
            _text("title", 0, 0, "Pipeline runs 6x faster", fs=28),
        ]
        self.assertEqual(check_title(els), [])

    def test_topic_title_emits_info(self) -> None:
        els = [
            _shape("a", 0, 200, 200, 100), _shape("b", 300, 200, 200, 100),
            _text("title", 0, 0, "Architecture", fs=28),
        ]
        out = check_title(els)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].severity, "INFO")
        self.assertEqual(out[0].code, "TITLE_PATTERN")


class TestInvariants(unittest.TestCase):
    def test_self_loop_fails(self) -> None:
        els = [
            _shape("a", 0, 0, index="a00"),
            {**_arrow("ar", "a", "a"), "index": "a01"},
        ]
        codes = {f.code for f in check_invariants(els)}
        self.assertIn("SELF_LOOP", codes)

    def test_shape_after_arrow_fails(self) -> None:
        els = [
            _shape("a", 0, 0, index="a00"),
            _arrow("ar", "a", "b", index="a01"),
            _shape("b", 200, 0, index="a02"),
        ]
        codes = {f.code for f in check_invariants(els)}
        self.assertIn("SHAPE_AFTER_ARROW", codes)

    def test_dangling_binding_fails(self) -> None:
        els = [
            _shape("a", 0, 0, index="a00"),
            _arrow("ar", "a", "ghost", index="a01"),
        ]
        codes = {f.code for f in check_invariants(els)}
        self.assertIn("DANGLING_BINDING", codes)

    def test_phantom_container_fails(self) -> None:
        els = [_text("t", 0, 0, "hi", container_id="ghost", index="a00")]
        codes = {f.code for f in check_invariants(els)}
        self.assertIn("PHANTOM_CONTAINER", codes)

    def test_index_not_monotonic_fails(self) -> None:
        els = [_shape("a", 0, 0, index="a02"), _shape("b", 200, 0, index="a01")]
        codes = {f.code for f in check_invariants(els)}
        self.assertIn("INDEX_NOT_MONOTONIC", codes)

    def test_app_state_binding_disabled_warns(self) -> None:
        els = [_shape("a", 0, 0)]
        out = check_invariants(els, app_state={"isBindingEnabled": False,
                                               "viewBackgroundColor": "#ffffff"})
        codes = {f.code for f in out}
        self.assertIn("BINDING_DISABLED", codes)

    def test_clean_invariants_pass(self) -> None:
        els = [
            _shape("a", 0, 0, index="a00"),
            _shape("b", 200, 0, index="a01"),
            _arrow("ar", "a", "b", index="a02"),
        ]
        out = check_invariants(els, app_state={"isBindingEnabled": True,
                                               "viewBackgroundColor": "#ffffff"})
        self.assertEqual([f for f in out if f.severity == "FAIL"], [])


class TestCheckAll(unittest.TestCase):
    def test_check_all_returns_report(self) -> None:
        els = [
            _shape("hub", 300, 300, 240, 120, index="a00"),
            _shape("s1", 600, 300, 100, 50, index="a01"),
            _shape("s2", 600, 400, 100, 50, index="a02"),
            _arrow("ar1", "hub", "s1", index="a03"),
            _arrow("ar2", "hub", "s2", index="a04"),
            _text("title", 300, 200, "Hub processes 500 records", fs=28,
                  index="a05"),
        ]
        path = _write_doc(els)
        try:
            rep = check_all(path)
            self.assertIsInstance(rep, ValidationReport)
            self.assertEqual(rep.fails, [])
        finally:
            path.unlink()

    def test_check_all_flags_missing_source(self) -> None:
        els = [_shape("a", 0, 0, index="a00")]
        path = _write_doc(els, source=None)
        try:
            rep = check_all(path)
            codes = {f.code for f in rep.findings}
            self.assertIn("SOURCE_MISSING", codes)
        finally:
            path.unlink()


class TestTighten(unittest.TestCase):
    def test_tighten_snaps_to_grid(self) -> None:
        els = [
            _shape("a", 7, 13, 100, 50, index="a00"),
            _shape("b", 211, 14, 100, 50, index="a01"),
        ]
        path = _write_doc(els)
        try:
            rep = tighten(path, snap=20)
            self.assertFalse(rep.reverted)
            self.assertGreaterEqual(rep.snapped, 1)
            data = json.loads(path.read_text())
            for e in data["elements"]:
                self.assertEqual(e["x"] % 20, 0)
                self.assertEqual(e["y"] % 20, 0)
        finally:
            path.unlink()

    def test_tighten_reverts_on_new_collision(self) -> None:
        els = [
            _shape("a", 0, 0, 100, 50, index="a00"),
            _shape("b", 110, 0, 100, 50, index="a01"),
            _shape("c", 220, 0, 100, 50, index="a02"),
        ]
        path = _write_doc(els)
        try:
            rep = tighten(path, target_bbox=(50, 50), snap=10)
            if rep.reverted:
                data = json.loads(path.read_text())
                xs = sorted(e["x"] for e in data["elements"])
                self.assertEqual(xs, [0, 110, 220])
        finally:
            path.unlink()

    def test_tighten_dry_run_does_not_write(self) -> None:
        els = [_shape("a", 7, 13, 100, 50, index="a00"),
               _shape("b", 250, 14, 100, 50, index="a01")]
        path = _write_doc(els)
        try:
            before = path.read_text()
            tighten(path, snap=20, dry_run=True)
            self.assertEqual(path.read_text(), before)
        finally:
            path.unlink()


class TestDirectedCycle(unittest.TestCase):
    def test_closed_loop_detected(self) -> None:
        self.assertTrue(_has_directed_cycle([("a", "b"), ("b", "c"), ("c", "a")]))

    def test_open_chain_not_a_cycle(self) -> None:
        self.assertFalse(_has_directed_cycle([("a", "b"), ("b", "c")]))

    def test_cycle_shapes_exempt_from_hierarchy_and_argument(self) -> None:
        # Three uniform ellipses in a closed arrow loop — a cycle. Uniform size and
        # single shape-type are intentional; neither HIERARCHY_FLAT nor
        # WEAK_ARGUMENT / NO_SHAPE_VARIETY should fire.
        els = [
            _shape("a", 0, 0, 140, 80, type_="ellipse"),
            _shape("b", 300, 0, 140, 80, type_="ellipse"),
            _shape("c", 150, 250, 140, 80, type_="ellipse"),
            _arrow("ar1", "a", "b"), _arrow("ar2", "b", "c"),
            _arrow("ar3", "c", "a"),
        ]
        codes = {f.code for f in check_hierarchy(els)} | {f.code for f in check_argument(els)}
        self.assertNotIn("HIERARCHY_FLAT", codes)
        self.assertNotIn("WEAK_ARGUMENT", codes)
        self.assertNotIn("NO_SHAPE_VARIETY", codes)


class TestArrowCrossesText(unittest.TestCase):
    def test_arrow_through_free_text_fails(self) -> None:
        # Arrow shaft runs horizontally straight through a free-text annotation.
        els = [
            _shape("a", 0, 0, 100, 50),
            _shape("b", 400, 0, 100, 50),
            _text("note", 180, 10, "crossed annotation", fs=16),
            _arrow("ar", "a", "b", x=100, y=25, points=[[0, 0], [300, 0]]),
        ]
        codes = {f.code for f in check_aesthetics(els)}
        self.assertIn("ARROW_CROSSES_TEXT", codes)

    def test_arrow_own_label_not_flagged(self) -> None:
        # An arrow's own bound label sits on the shaft by design — never a crossing.
        arrow = _arrow("ar", "a", "b", x=100, y=25, points=[[0, 0], [300, 0]],
                       boundElements=[{"id": "lbl", "type": "text"}])
        lbl = _text("lbl", 230, 18, "ok", fs=14, container_id="ar")
        els = [_shape("a", 0, 0, 100, 50), _shape("b", 400, 0, 100, 50), arrow, lbl]
        codes = {f.code for f in check_aesthetics(els)}
        self.assertNotIn("ARROW_CROSSES_TEXT", codes)


class TestColorWordInShape(unittest.TestCase):
    def test_red_label_in_red_box_warns(self) -> None:
        box = _shape("s", 0, 0, 150, 60, backgroundColor="#ffd4d0")
        lbl = _text("s_text", 10, 20, "RED: failing test", fs=16, container_id="s")
        codes = {f.code for f in check_aesthetics([box, lbl])}
        self.assertIn("COLOR_WORD_IN_SHAPE", codes)

    def test_neutral_label_in_colored_box_ok(self) -> None:
        box = _shape("s", 0, 0, 150, 60, backgroundColor="#ffd4d0")
        lbl = _text("s_text", 10, 20, "failing test", fs=16, container_id="s")
        codes = {f.code for f in check_aesthetics([box, lbl])}
        self.assertNotIn("COLOR_WORD_IN_SHAPE", codes)


class TestTitleOverhangs(unittest.TestCase):
    def test_runaway_title_warns(self) -> None:
        # Narrow body (~200px), very long title → juts far past both edges.
        title = _text("title", 0, 0,
                      "A very long runaway title that far exceeds the diagram width",
                      fs=28)
        els = [_shape("a", 0, 80, 100, 50), _shape("b", 100, 80, 100, 50), title]
        codes = {f.code for f in check_aesthetics(els)}
        self.assertIn("TITLE_OVERHANGS", codes)

    def test_normal_title_ok(self) -> None:
        title = _text("title", 0, 0, "Short title", fs=28)
        els = [_shape("a", 0, 80, 300, 50), _shape("b", 320, 80, 300, 50), title]
        codes = {f.code for f in check_aesthetics(els)}
        self.assertNotIn("TITLE_OVERHANGS", codes)


if __name__ == "__main__":
    unittest.main()
