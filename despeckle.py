#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Despeckle: find, highlight, or delete small objects in Inkscape.

An element "matches" when its measured size is less than or equal to the
threshold. Size can be measured four ways (see ``--metric``) so the same tool
handles tiny specks, thin slivers, short open lines, and small polygons.

All measurements are in SVG user units (px in a typical document), taken in
the document coordinate system (each element's composed transform is applied).
"""

import inkex
from inkex import bezier

# Leaf vector shapes we consider. Containers (Group, Layer) are walked into
# but never measured themselves; text is opt-in via --include_text.
SHAPE_TYPES = (
    inkex.PathElement,
    inkex.Rectangle,
    inkex.Circle,
    inkex.Ellipse,
    inkex.Line,
    inkex.Polyline,
    inkex.Polygon,
)


class Despeckle(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--tab", default="options")
        pars.add_argument(
            "--metric",
            default="bbox_area",
            help="bbox_area | max_dim | geom_area | path_length",
        )
        pars.add_argument("--threshold", type=float, default=25.0)
        pars.add_argument(
            "--mode", default="highlight", help="highlight | delete"
        )
        pars.add_argument("--scope", default="all", help="all | selection")
        pars.add_argument("--highlight_color", default="#ff00ff")
        pars.add_argument("--include_text", type=inkex.Boolean, default=False)

    # --- geometry helpers ---------------------------------------------------

    def _superpath(self, elem):
        """Element geometry as a cubic superpath in document coordinates."""
        try:
            path = elem.path.transform(elem.composed_transform())
            return path.to_superpath()
        except Exception:
            return None

    def measure(self, elem):
        """Return the element's size under the chosen metric, or None."""
        metric = self.options.metric

        if metric in ("bbox_area", "max_dim"):
            bbox = elem.bounding_box()
            if bbox is None:
                return None
            if metric == "bbox_area":
                return bbox.width * bbox.height
            return max(bbox.width, bbox.height)

        csp = self._superpath(elem)
        if not csp:
            return None
        if metric == "geom_area":
            return abs(bezier.csparea(csp))
        if metric == "path_length":
            result = bezier.csplength(csp)
            # inkex.bezier.csplength returns (per-subpath lengths, total);
            # the grand total is the last element. Older/standalone builds
            # may instead return a bare float.
            return float(result[-1]) if isinstance(result, (list, tuple)) else float(result)
        return None

    # --- traversal ----------------------------------------------------------

    def _candidates(self):
        if self.options.scope == "selection" and len(self.svg.selection):
            roots = list(self.svg.selection.values())
        else:
            roots = [self.svg]
        seen = set()
        for root in roots:
            for elem in root.iter():
                key = id(elem)
                if key in seen:
                    continue
                seen.add(key)
                yield elem

    # --- main ---------------------------------------------------------------

    def effect(self):
        types = SHAPE_TYPES
        if self.options.include_text:
            types = types + (inkex.TextElement,)

        threshold = self.options.threshold
        matched = []
        for elem in self._candidates():
            if not isinstance(elem, types):
                continue
            value = self.measure(elem)
            if value is None:
                continue
            if value <= threshold:
                matched.append(elem)

        mode = self.options.mode

        if mode == "delete":
            for elem in matched:
                try:
                    elem.delete()
                except Exception:
                    pass  # already detached (e.g. parent removed first)
        else:  # highlight
            color = self.options.highlight_color
            for elem in matched:
                elem.style["fill"] = color
                elem.style["stroke"] = color
                elem.style["fill-opacity"] = "1"
                elem.style["stroke-opacity"] = "1"
                elem.style["opacity"] = "1"

        self.msg(
            "Despeckle: {n} object(s) matched ({metric} <= {thr:g}); "
            "action = {mode}.".format(
                n=len(matched),
                metric=self.options.metric,
                thr=threshold,
                mode=mode,
            )
        )


if __name__ == "__main__":
    Despeckle().run()
