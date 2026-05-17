# SPDX-License-Identifier: GPL-2.0-or-later
"""Integration tests: run the extension end-to-end via inkex and inspect SVG."""

import io
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from despeckle import Despeckle  # noqa: E402

SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500"
viewBox="0 0 500 500">
  <rect id="tiny" x="10" y="10" width="4" height="4"/>
  <rect id="big" x="100" y="100" width="200" height="150"/>
  <circle id="dot" cx="50" cy="50" r="1"/>
  <path id="longline" d="M 0,0 L 400,0"/>
  <path id="shortline" d="M 0,0 L 3,0"/>
</svg>"""


def run_ext(tmp_path, args, svg=SVG):
    src = tmp_path / "in.svg"
    src.write_text(svg)
    out = io.BytesIO()
    try:
        Despeckle().run(args + [str(src)], output=out)
    except SystemExit:
        pass
    return out.getvalue().decode("utf-8")


def test_delete_by_bbox_area(tmp_path):
    result = run_ext(
        tmp_path, ["--mode=delete", "--metric=bbox_area", "--threshold=100"]
    )
    assert 'id="big"' in result          # 30000 px² kept
    assert 'id="tiny"' not in result     # 16 px² removed
    assert 'id="dot"' not in result      # ~4 px² removed


def test_delete_by_path_length(tmp_path):
    result = run_ext(
        tmp_path, ["--mode=delete", "--metric=path_length", "--threshold=10"]
    )
    assert 'id="longline"' in result     # length 400 kept
    assert 'id="shortline"' not in result  # length 3 removed


def test_delete_by_geom_area(tmp_path):
    # tiny 4x4 = 16 px² filled, big 200x150 = 30000 px² filled.
    result = run_ext(
        tmp_path, ["--mode=delete", "--metric=geom_area", "--threshold=100"]
    )
    assert 'id="tiny"' not in result
    assert 'id="big"' in result


def test_max_dim_threshold(tmp_path):
    result = run_ext(
        tmp_path, ["--mode=delete", "--metric=max_dim", "--threshold=5"]
    )
    assert 'id="tiny"' not in result     # max side 4 removed
    assert 'id="big"' in result          # max side 200 kept


def test_highlight_recolors_but_never_deletes(tmp_path):
    result = run_ext(
        tmp_path,
        [
            "--mode=highlight",
            "--metric=bbox_area",
            "--threshold=100",
            "--highlight_color=#ff00ff",
        ],
    )
    assert "#ff00ff" in result           # a match was recolored
    # Highlight is the non-destructive review step: nothing is removed.
    for obj_id in ("tiny", "big", "dot", "longline", "shortline"):
        assert 'id="{}"'.format(obj_id) in result


def test_scope_selection_with_nothing_selected_falls_back(tmp_path):
    # No selection passed: scope=selection should fall back to whole document.
    result = run_ext(
        tmp_path,
        ["--mode=delete", "--metric=bbox_area", "--threshold=100",
         "--scope=selection"],
    )
    assert 'id="tiny"' not in result
    assert 'id="big"' in result


# --- compound-path (subpath) despeckling --------------------------------

import re  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402

# One path, three subpaths: big 200x200 (area 40000), 3x3 (area 9), 1x1 (1).
COMPOUND = """<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500"
viewBox="0 0 500 500">
  <path id="cmp" d="M 0,0 H 200 V 200 H 0 Z M 10,10 h 3 v 3 h -3 z
M 50,50 h 1 v 1 h -1 z"/>
</svg>"""


def _subpath_count(svg_text, pid):
    root = ET.fromstring(svg_text)
    for e in root.iter():
        if e.tag.split("}")[-1] == "path" and e.get("id") == pid:
            return len(re.findall(r"[Mm]", e.get("d") or ""))
    return None


def test_subpath_delete_removes_tiny_keeps_big(tmp_path):
    result = run_ext(
        tmp_path,
        ["--mode=delete", "--metric=geom_area", "--threshold=100"],
        svg=COMPOUND,
    )
    assert 'id="cmp"' in result                 # path survives
    assert _subpath_count(result, "cmp") == 1    # 3 subpaths -> 1 (big kept)


def test_subpath_highlight_overlays_without_touching_original(tmp_path):
    result = run_ext(
        tmp_path,
        ["--mode=highlight", "--metric=geom_area", "--threshold=100"],
        svg=COMPOUND,
    )
    assert "despeckle-preview" in result          # overlay added
    assert "#ff00ff" in result                    # overlay is magenta
    assert _subpath_count(result, "cmp") == 3     # original untouched


def test_subpaths_disabled_treats_path_as_one_element(tmp_path):
    # With subpaths off, the whole compound path is a single element:
    # a threshold above its total area deletes the entire path.
    result = run_ext(
        tmp_path,
        ["--mode=delete", "--metric=geom_area", "--threshold=100000",
         "--subpaths=false"],
        svg=COMPOUND,
    )
    assert 'id="cmp"' not in result
