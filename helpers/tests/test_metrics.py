"""Tests for the mechanical metrics harness.

Rendering needs playwright, which may be absent in the test env; measure_file
degrades render_ms to None rather than crashing, so these tests assert on the
structural axes (validator findings, spec_bytes, element counts) and the
baseline-delta math — never on render latency.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from helpers import metrics

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestFixturesClean(unittest.TestCase):
    """The bundled corpus is the regression gate: every fixture must be
    structurally clean (0 FAIL, 0 WARN). If a pattern change introduces a
    crossing/overflow/monoculture, a fixture goes non-clean and this fails."""

    def test_every_fixture_zero_fails_zero_warns(self) -> None:
        files = sorted(FIXTURES.glob("*.excalidraw"))
        self.assertGreaterEqual(len(files), 11, "expected the 11-pattern corpus")
        dirty = []
        for f in files:
            e = metrics.measure_file(f)
            self.assertNotIn("check_error", e, f"validate crashed on {f.name}")
            if e.get("fails") or e.get("warns"):
                dirty.append((f.name, e.get("fails"), e.get("warns"),
                              [x["code"] for x in e.get("findings", [])
                               if x["severity"] in ("FAIL", "WARN")]))
        self.assertEqual(dirty, [], f"non-clean fixtures: {dirty}")

    def test_spec_bytes_present(self) -> None:
        # Every fixture ships with its sibling .spec.json (the token proxy).
        for f in sorted(FIXTURES.glob("*.excalidraw")):
            e = metrics.measure_file(f)
            self.assertIsNotNone(e["spec_bytes"], f"{f.name} has no .spec.json")
            self.assertGreater(e["spec_bytes"], 0)


class TestCollect(unittest.TestCase):
    def test_collect_shape(self) -> None:
        rep = metrics.collect(FIXTURES)
        self.assertEqual(rep["dir"], str(FIXTURES))
        self.assertGreaterEqual(len(rep["files"]), 11)
        for e in rep["files"]:
            self.assertIn("file", e)
            self.assertIn("clean", e)


class TestBaselineDelta(unittest.TestCase):
    def test_delta_math(self) -> None:
        self.assertEqual(metrics._delta(10, 10), "  (=)")
        self.assertEqual(metrics._delta(12, 10), "  (+2)")
        self.assertEqual(metrics._delta(8, 10), "  (-2)")
        self.assertEqual(metrics._delta(None, 10), "")
        self.assertEqual(metrics._delta(10, None), "")


class TestRunMetrics(unittest.TestCase):
    def test_run_writes_json_and_returns_zero(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "m.json"
            rc = metrics.run_metrics(FIXTURES, out=out)
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())
            data = json.loads(out.read_text())
            self.assertIn("files", data)

    def test_missing_dir_returns_one(self) -> None:
        rc = metrics.run_metrics(Path("/nonexistent/xyz"), out=None)
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
