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
