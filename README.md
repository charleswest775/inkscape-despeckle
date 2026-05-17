# Despeckle — Inkscape Small Object Remover

Find and clean up the tiny junk in an SVG: stray specks, hairline slivers,
short open lines, and small polygons. Set a size **threshold**; every object
that size **or smaller** is highlighted, selected, or deleted.

Works on **Windows, macOS and Linux** (Inkscape 1.0+). Pure Python, no
third-party dependencies — it only uses Inkscape's bundled `inkex`.

## Why

Auto-traced bitmaps, imported CAD/maps, and OCR output are full of
sub-pixel debris that bloats files and ruins plotter/laser/cutter jobs.
Despeckle lets you preview exactly what counts as "too small" and remove it
in one pass.

## Install

### Option A — installer script (recommended)

```bash
python3 install.py        # copies the two files into your Inkscape folder
```

Then restart Inkscape. To remove it later: `python3 install.py --uninstall`.
To just see where it installs: `python3 install.py --path`.

### Option B — manual

Copy `despeckle.py` and `despeckle.inx` into your Inkscape **user
extensions** folder, then restart Inkscape:

| OS      | Folder |
|---------|--------|
| Windows | `%APPDATA%\inkscape\extensions\` |
| macOS   | `~/Library/Application Support/org.inkscape.Inkscape/config/inkscape/extensions/` (older builds: `~/.config/inkscape/extensions/`) |
| Linux   | `~/.config/inkscape/extensions/` |

The exact path is also shown in Inkscape under
**Edit ▸ Preferences ▸ System ▸ User extensions**.

## Use it

Open **Extensions ▸ Cleanup ▸ Despeckle (Small Object Remover)**.

1. Tick the **Live preview** checkbox at the bottom of the dialog.
2. Leave **Action** on *Highlight* and drag the **Threshold** slider —
   matching objects recolor on the canvas in real time so you can dial in
   the cutoff.
3. Switch **Action** to *Delete* and click **Apply** to remove them.

`Ctrl+Z` undoes any applied highlight or deletion, so it is safe to
experiment. (Inkscape effect extensions cannot hand a selection back to the
canvas, so *Highlight* — not a "select" mode — is the review step.)

### Size metrics

| Metric | Measures | Good for |
|--------|----------|----------|
| **Bounding-box area** (default) | width × height of the bbox, px² | general specks |
| **Largest dimension** | longest bbox side, px | tiny dots without nuking long thin strokes |
| **Geometric / filled area** | true filled area, px² | small filled polygons |
| **Path / line length** | total outline length, px | short *open* lines (≈ 0 area) |

All values are in **SVG user units** (px in a normal document), measured in
document coordinates with each object's transforms applied. **Scope** can be
limited to the current selection instead of the whole document.

## Development

```bash
python3 -m pip install --no-deps "inkex==1.4.1"
python3 -m pip install lxml cssselect numpy tinycss2 pytest
python3 -m pytest
```

CI runs the test suite on Linux, macOS and Windows across Python 3.9–3.12.

## License

[GPL-2.0-or-later](LICENSE), matching the Inkscape `inkex` library this
extension builds on.
