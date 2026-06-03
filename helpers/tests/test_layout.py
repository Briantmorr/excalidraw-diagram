from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from helpers import layout
from helpers.layout import (
    EdgeSpec,
    GraphSpec,
    NodeSpec,
    _build_dot,
    _build_skeleton,
    _derive_roles,
    _resolve_overlaps,
    _PositionedNode,
    _size_for,
    _snap,
    layout_dag,
)


def _fake_convert(skeleton):
    out = []
    for i, s in enumerate(skeleton):
        e = dict(s)
        e.setdefault("id", f"el{i}")
        e["index"] = f"a{i:02d}"
        out.append(e)
    return out


class SnapAndSizingTests(unittest.TestCase):
    def test_snap_to_grid(self) -> None:
        self.assertEqual(_snap(0), 0)
        self.assertEqual(_snap(19), 20)
        self.assertEqual(_snap(21), 20)
        self.assertEqual(_snap(30), 40)

    def test_size_hierarchy_hero_larger_than_spoke(self) -> None:
        n = NodeSpec(id="x", text="X", type="rectangle")
        hero_w, hero_h = _size_for(n, "hero")
        spoke_w, spoke_h = _size_for(n, "secondary")
        self.assertGreater(hero_w * hero_h, spoke_w * spoke_h)

    def test_role_derivation_hub_and_leaf(self) -> None:
        nodes = [NodeSpec(id="hub", text="H"),
                 NodeSpec(id="a", text="A"),
                 NodeSpec(id="b", text="B"),
                 NodeSpec(id="c", text="C")]
        edges = [EdgeSpec("hub", "a"), EdgeSpec("hub", "b"), EdgeSpec("hub", "c")]
        roles = _derive_roles(nodes, edges)
        self.assertEqual(roles["hub"], "hero")
        self.assertEqual(roles["a"], "secondary")
        self.assertEqual(roles["b"], "secondary")
        self.assertEqual(roles["c"], "secondary")


class DotSourceTests(unittest.TestCase):
    def test_dot_skips_self_loops(self) -> None:
        nodes = [NodeSpec(id="a", text="A")]
        edges = [EdgeSpec("a", "a")]
        sizes = {"a": (150, 50)}
        src = _build_dot(nodes, edges, sizes, "dot", "DOWN")
        self.assertNotIn('"a" -> "a"', src)
        self.assertIn("rankdir=TB", src)

    def test_dot_direction_mapping(self) -> None:
        nodes = [NodeSpec(id="a", text="A")]
        sizes = {"a": (150, 50)}
        self.assertIn("rankdir=LR", _build_dot(nodes, [], sizes, "dot", "RIGHT"))
        self.assertIn("rankdir=BT", _build_dot(nodes, [], sizes, "dot", "UP"))


class SkeletonAndOverlapTests(unittest.TestCase):
    def test_overlap_resolution_pushes_right(self) -> None:
        a = _PositionedNode(NodeSpec(id="a", text="A"), 0, 0, 100, 50, "primary")
        b = _PositionedNode(NodeSpec(id="b", text="B"), 20, 0, 100, 50, "primary")
        _resolve_overlaps([a, b])
        self.assertGreaterEqual(b.x, a.x + a.width)

    def test_skeleton_drops_self_loops_and_dangling(self) -> None:
        a = _PositionedNode(NodeSpec(id="a", text="A", bg="#eae8e4"), 0, 0, 150, 50, "primary")
        b = _PositionedNode(NodeSpec(id="b", text="B"), 200, 0, 150, 50, "primary")
        edges = [EdgeSpec("a", "a"), EdgeSpec("a", "b"), EdgeSpec("a", "ghost")]
        skel = _build_skeleton([a, b], edges)
        arrows = [s for s in skel if s["type"] == "arrow"]
        self.assertEqual(len(arrows), 1)
        self.assertEqual(arrows[0]["start"]["id"], "a")
        self.assertEqual(arrows[0]["end"]["id"], "b")
        node_a = next(s for s in skel if s.get("id") == "a")
        self.assertEqual(node_a["strokeColor"], "#000000")
        self.assertEqual(node_a["backgroundColor"], "#eae8e4")
        self.assertEqual(node_a["label"]["fontSize"], 16)

    def test_arrow_color_is_warm_charcoal(self) -> None:
        a = _PositionedNode(NodeSpec(id="a", text="A"), 0, 0, 150, 50, "primary")
        b = _PositionedNode(NodeSpec(id="b", text="B"), 200, 0, 150, 50, "primary")
        skel = _build_skeleton([a, b], [EdgeSpec("a", "b", label="step")])
        arrow = next(s for s in skel if s["type"] == "arrow")
        self.assertEqual(arrow["strokeColor"], "#3a3428")
        self.assertEqual(arrow["label"]["text"], "step")


class LayoutDagIntegrationTests(unittest.TestCase):
    def test_layout_dag_pipeline(self) -> None:
        spec = GraphSpec(
            nodes=[NodeSpec(id="a", text="Alpha"),
                   NodeSpec(id="b", text="Beta"),
                   NodeSpec(id="c", text="Gamma")],
            edges=[EdgeSpec("a", "b"), EdgeSpec("b", "c")],
        )
        with patch.object(layout, "_run_graphviz", return_value={
            "bb": "0,0,400,100",
            "objects": [
                {"name": "a", "pos": "50,80"},
                {"name": "b", "pos": "200,80"},
                {"name": "c", "pos": "350,80"},
            ],
        }), patch("helpers.skeleton_bridge.convert_skeleton", side_effect=_fake_convert):
            elements = layout_dag(spec)
        types = [e["type"] for e in elements]
        self.assertEqual(types.count("rectangle"), 3)
        self.assertEqual(types.count("arrow"), 2)
        # shapes before arrows
        first_arrow_idx = types.index("arrow")
        self.assertTrue(all(t != "arrow" for t in types[:first_arrow_idx]))

    def test_layout_dag_empty_spec(self) -> None:
        self.assertEqual(layout_dag(GraphSpec()), [])


if __name__ == "__main__":
    unittest.main()
