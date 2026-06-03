"""Tests for place.py — role defaults, anchor variants, and rendering invariants."""
import sys, json, os
from pathlib import Path
sys.path.insert(0, "/Users/I523193/.claude/skills/excalidraw-diagram/helpers")
from place.place import place, ROLE_DEFAULTS

TMP = Path("/tmp/excalidraw-place-test")
TMP.mkdir(exist_ok=True)

def fresh(name):
    p = TMP / name
    p.unlink(missing_ok=True)
    return str(p)

def test_role_stage():
    f = fresh("test_stage.excalidraw")
    place(f, [{"id": "x", "type": "rectangle", "role": "stage",
               "anchor": {"x": 0, "y": 0}, "text": "Hub"}])
    d = json.loads(Path(f).read_text())
    shape = next(e for e in d["elements"] if e["id"] == "x")
    assert shape["width"] == 210, shape
    assert shape["strokeWidth"] == 3, shape
    assert shape["backgroundColor"] == "#eae8e4", shape
    print("OK test_role_stage")

def test_role_title_emits_text():
    f = fresh("test_title.excalidraw")
    place(f, [{"id": "t", "role": "title", "text": "T", "anchor": {"x": 0, "y": 0}}])
    d = json.loads(Path(f).read_text())
    e = next(e for e in d["elements"] if e["id"] == "t")
    assert e["type"] == "text"
    assert e["fontSize"] == 28
    print("OK test_role_title_emits_text")

def test_anchor_right_of():
    f = fresh("test_right_of.excalidraw")
    place(f, [
        {"id": "a", "anchor": {"x": 100, "y": 100}, "width": 100, "height": 50},
        {"id": "b", "anchor": {"rel": "right_of", "id": "a", "gap": 30}, "width": 100, "height": 50},
    ])
    d = json.loads(Path(f).read_text())
    b = next(e for e in d["elements"] if e["id"] == "b")
    assert b["x"] == 230, b  # 100+100+30
    assert b["y"] == 100, b
    print("OK test_anchor_right_of")

def test_anchor_below_centers():
    f = fresh("test_below.excalidraw")
    place(f, [
        {"id": "a", "anchor": {"x": 100, "y": 100}, "width": 200, "height": 50},
        {"id": "b", "anchor": {"rel": "below", "id": "a", "gap": 20}, "width": 100, "height": 50},
    ])
    d = json.loads(Path(f).read_text())
    b = next(e for e in d["elements"] if e["id"] == "b")
    assert b["y"] == 170, b
    # center-aligned to a's center (200): 200 - 100/2 = 150
    assert b["x"] == 150, b
    print("OK test_anchor_below_centers")

def test_anchor_row():
    f = fresh("test_row.excalidraw")
    place(f, [
        {"id": f"r{i}", "anchor": {"rel": "row", "y": 200, "index": i, "total": 3,
                                    "gap": 20, "width": 100, "x_start": 0}}
        for i in range(3)
    ])
    d = json.loads(Path(f).read_text())
    xs = sorted([e["x"] for e in d["elements"] if e["id"].startswith("r") and e["type"]!="text"])
    assert xs == [0, 120, 240], xs
    print("OK test_anchor_row")

def test_anchor_spine():
    f = fresh("test_spine.excalidraw")
    place(f, [
        {"id": f"s{i}", "anchor": {"rel": "spine", "x": 400, "y_index": i,
                                    "y_start": 0, "gap": 100}, "width": 200, "height": 50}
        for i in range(3)
    ])
    d = json.loads(Path(f).read_text())
    for i in range(3):
        e = next(e for e in d["elements"] if e["id"] == f"s{i}")
        assert e["x"] == 300, e  # 400 - 200/2
        assert e["y"] == i * 100, e
    print("OK test_anchor_spine")

def test_anchor_near():
    f = fresh("test_near.excalidraw")
    place(f, [
        {"id": "a", "anchor": {"x": 100, "y": 100}, "width": 100, "height": 50},
        {"id": "b", "anchor": {"rel": "near", "id": "a", "direction": "right", "gap": 20},
         "width": 100, "height": 50},
    ])
    d = json.loads(Path(f).read_text())
    b = next(e for e in d["elements"] if e["id"] == "b")
    assert b["x"] == 220, b
    print("OK test_anchor_near")

def test_anchor_like():
    f = fresh("test_like.excalidraw")
    place(f, [
        {"id": "a", "anchor": {"x": 0, "y": 0}, "width": 200, "height": 80,
         "bg": "#abcdef", "text": "A"},
    ])
    place(f, [
        {"id": "b", "anchor": {"rel": "like", "id": "a", "x": 300, "y": 0}, "text": "B"},
    ])
    d = json.loads(Path(f).read_text())
    b = next(e for e in d["elements"] if e["id"] == "b")
    assert b["width"] == 200, b
    assert b["height"] == 80, b
    assert b["backgroundColor"] == "#abcdef", b
    print("OK test_anchor_like")

def test_invariants():
    f = fresh("test_invariants.excalidraw")
    place(f, [
        {"id": "a", "anchor": {"x": 0, "y": 0}, "text": "A"},
        {"id": "b", "anchor": {"rel": "right_of", "id": "a"}, "text": "B"},
    ])
    d = json.loads(Path(f).read_text())
    els = d["elements"]
    # Borders
    for e in els:
        if e["type"] in ("rectangle", "ellipse", "diamond"):
            assert e["strokeColor"] == "#000000", e
    # fontFamily
    for e in els:
        if e["type"] == "text":
            assert e["fontFamily"] == 1, e
    # bg
    assert d["appState"]["viewBackgroundColor"] == "#ffffff"
    # monotonic indices
    idxs = [e.get("index", "") for e in els]
    assert idxs == sorted(idxs)
    print("OK test_invariants")

def test_chained_anchors_in_one_call():
    """specs[i+1] can reference specs[i] within the same call."""
    f = fresh("test_chain.excalidraw")
    place(f, [
        {"id": "a", "anchor": {"x": 0, "y": 0}, "width": 100, "height": 50},
        {"id": "b", "anchor": {"rel": "right_of", "id": "a", "gap": 10}, "width": 100, "height": 50},
        {"id": "c", "anchor": {"rel": "right_of", "id": "b", "gap": 10}, "width": 100, "height": 50},
    ])
    d = json.loads(Path(f).read_text())
    c = next(e for e in d["elements"] if e["id"] == "c")
    assert c["x"] == 220, c  # a(0,100) + 10 + b(100) + 10 = 220
    print("OK test_chained_anchors_in_one_call")

if __name__ == "__main__":
    test_role_stage()
    test_role_title_emits_text()
    test_anchor_right_of()
    test_anchor_below_centers()
    test_anchor_row()
    test_anchor_spine()
    test_anchor_near()
    test_anchor_like()
    test_invariants()
    test_chained_anchors_in_one_call()
    print("\nALL TESTS PASS")
