"""Tests for helpers.patterns — one test class covering all 10 patterns."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers import validate
from helpers.patterns import (
    Branch, GridRow, Pair, Panel, Spoke, TimelineItem, WeightedItem,
    comparison_grid, decision_tree, fanout, hub_spoke, nested, pipeline,
    side_by_side, storyboard, timeline, weight_map,
)


class PatternsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "out.excalidraw"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _assert_no_fails(self, path: Path) -> dict:
        rep = validate.check_all(path)
        fails = [f for f in rep.findings if f.severity == "FAIL"]
        self.assertEqual(fails, [], msg="\n".join(
            f"{f.code} {f.message}" for f in fails))
        return json.loads(path.read_text())

    def test_pipeline_basic(self) -> None:
        pipeline(
            self.path, title="ETL Flow",
            stages=["Extract", "Transform", "Validate", "Load"],
            color="blue",
        )
        data = self._assert_no_fails(self.path)
        shapes = [e for e in data["elements"] if e["type"] == "rectangle"]
        arrows = [e for e in data["elements"] if e["type"] == "arrow"]
        self.assertEqual(len(shapes), 4)
        self.assertEqual(len(arrows), len(shapes) - 1)
        self.assertEqual(len({s["width"] for s in shapes}), 1)
        self.assertEqual(len({s["height"] for s in shapes}), 1)
        titles = [e for e in data["elements"]
                  if e["type"] == "text" and e.get("containerId") is None]
        self.assertTrue(any("ETL" in t["text"] for t in titles))

    def test_fanout(self) -> None:
        fanout(self.path, title="Sources of Truth", hub="Knowledge Graph",
               spokes=["ORD", "ABAP", "CDS Views", "OData", "GraphQL"])
        data = self._assert_no_fails(self.path)
        ids = {e["id"] for e in data["elements"]}
        self.assertIn("hub", ids)
        for i in range(5):
            self.assertIn(f"arrow_hub_spoke_{i}", ids)
        shapes = [e for e in data["elements"]
                  if e["type"] in ("rectangle", "ellipse", "diamond")]
        hub_el = next(s for s in shapes if s["id"] == "hub")
        sp0 = next(s for s in shapes if s["id"] == "spoke_0")
        ratio = (hub_el["width"] * hub_el["height"]) / (sp0["width"] * sp0["height"])
        self.assertGreaterEqual(ratio, 3.0)

    def test_fanout_spoke_dataclass(self) -> None:
        fanout(self.path, title="Mixed", hub="Core",
               spokes=[Spoke(id="x", text="X"), "Y", {"id": "z", "text": "Z"}])
        self._assert_no_fails(self.path)

    def test_decision_tree(self) -> None:
        decision_tree(
            self.path, title="Tier Assignment", root="Score >= 80?",
            branches=[
                Branch(id="gold", label="Gold Tier", condition="yes >=90"),
                Branch(id="silver", label="Silver Tier", condition="80-89"),
                Branch(id="reject", label="Rejected", condition="no <80"),
            ],
        )
        data = self._assert_no_fails(self.path)
        kinds = [e["type"] for e in data["elements"]]
        self.assertEqual(kinds.count("diamond"), 1)
        self.assertEqual(kinds.count("rectangle"), 3)
        self.assertEqual(kinds.count("arrow"), 3)

    def test_comparison_grid(self) -> None:
        result = comparison_grid(
            self.path,
            title="Migration cuts latency 6x at half the cost",
            columns=["Before", "After"],
            rows=[
                GridRow(label="Speed", values=["2.3s", "0.4s"]),
                GridRow(label="Accuracy", values=["82%", "97%"]),
                GridRow(label="Cost", values=["$1.20", "$0.35"]),
            ],
        )
        self.assertTrue(result.ok, msg=str(result))
        data = self._assert_no_fails(self.path)
        cells = [e for e in data["elements"] if e.get("type") == "rectangle"]
        self.assertEqual(len(cells), 4 * 3)
        titles = [e for e in data["elements"]
                  if e.get("type") == "text" and e.get("containerId") is None]
        self.assertTrue(any(t.get("fontSize") == 28 for t in titles))

    def test_weight_map(self) -> None:
        items = [
            WeightedItem("abandon", "Abandonment", 0.95),
            WeightedItem("blame", "Self-Blame", 0.90),
            WeightedItem("step", "Stepping Back", 0.55),
            WeightedItem("honor", "God-Honoring", 0.50),
            WeightedItem("life", "Lifeline", 0.48),
            WeightedItem("grief", "Grief", 0.20),
            WeightedItem("wisdom", "Mom's Wisdom", 0.18),
        ]
        res = weight_map(self.path, title="Emotional Weight Map", items=items)
        self.assertTrue(res.ok, msg=str(res))
        self._assert_no_fails(self.path)

    def test_timeline_horizontal(self) -> None:
        items = [
            TimelineItem("s1", "Opening", "surface"),
            TimelineItem("s2", "First Crack", "vulnerability"),
            TimelineItem("s3", "Core Fear", "depth"),
            TimelineItem("s4", "Turning Point", "insight"),
            TimelineItem("s5", "Resolution", "integration"),
        ]
        timeline(self.path,
                 title="Conversation deepens from surface to insight",
                 items=items)
        self._assert_no_fails(self.path)

    def test_side_by_side(self) -> None:
        side_by_side(
            self.path,
            title="Sync wins clarity, async wins focus.",
            left_label="Sync", right_label="Async",
            pairs=[
                Pair(left="Live debate", right="Written argument"),
                Pair(left="Real-time pairing", right="Code review"),
                Pair(left="Standup", right="Status doc"),
            ],
            dashed_right=True,
        )
        data = self._assert_no_fails(self.path)
        shapes = [e for e in data["elements"]
                  if e.get("type") in ("rectangle", "ellipse", "diamond")]
        self.assertEqual(len(shapes), 6)
        right_styles = {e["id"]: e.get("strokeStyle") for e in shapes
                        if e["id"].startswith("R")}
        self.assertTrue(all(v == "dashed" for v in right_styles.values()))
        l0 = next(e for e in shapes if e["id"] == "L0")
        r0 = next(e for e in shapes if e["id"] == "R0")
        self.assertGreaterEqual(
            (l0["width"] * l0["height"]) / (r0["width"] * r0["height"]),
            2.0,
        )

    def test_nested_two_level(self) -> None:
        nested(self.path,
               title="Three layers keep blast radius bounded",
               outer="Cluster",
               inner=["Service A", "Service B", "Service C"],
               inner_inner=["Pod 1", "Pod 2", "Pod 3", "Pod 4"])
        data = self._assert_no_fails(self.path)
        ids = {e["id"] for e in data["elements"]}
        self.assertIn("nested_outer", ids)
        self.assertIn("nested_inner_0", ids)
        self.assertIn("nested_ii_3", ids)

    def test_hub_spoke(self) -> None:
        pr, cr = hub_spoke(
            self.path,
            title="Service Mesh", hub="API Gateway",
            spokes=["Auth", "Billing", "Catalog", "Search", "Notifications", "Logs"],
            with_descriptions=True,
        )
        self.assertTrue(pr.ok)
        self.assertEqual(len(cr.created), 6)
        self.assertEqual(cr.skipped, [])
        self._assert_no_fails(self.path)
        pr2, cr2 = hub_spoke(self.path, title="Hub", hub="Core",
                             spokes=["A", "B", "C"])
        self.assertTrue(pr2.ok)
        self.assertEqual(len(cr2.created), 3)
        self._assert_no_fails(self.path)

    def test_storyboard(self) -> None:
        panels = [
            Panel(id="p1", caption="Scene 1", subtitle="(setup)"),
            Panel(id="p2", caption="Scene 2", subtitle="(rising)"),
            Panel(id="p3", caption="Scene 3", subtitle="(climax)"),
        ]
        storyboard(self.path, title="Three-Scene Arc", panels=panels)
        data = self._assert_no_fails(self.path)
        rects = [e for e in data["elements"] if e.get("type") == "rectangle"]
        self.assertEqual(len(rects), 3)
        arrows = [e for e in data["elements"] if e.get("type") == "arrow"]
        self.assertEqual(len(arrows), 2)


if __name__ == "__main__":
    unittest.main()
