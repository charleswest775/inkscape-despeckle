#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Despeckle: find, highlight, or delete small objects in Inkscape.

An element "matches" when its measured size is less than or equal to the
threshold. Size can be measured four ways (see ``--metric``) so the same tool
handles tiny specks, thin slivers, short open lines, and small polygons.

Traced / laser / stencil artwork is almost always a single compound path
whose specks are *subpaths*, not separate elements. With ``--subpaths`` (on
by default) each subpath of a multi-subpath path is measured individually:
Delete rebuilds the path without the tiny subpaths; Highlight draws a
magenta preview overlay of them.

All measurements are in SVG user units (px in a typical document), taken in
the document coordinate system (each element's composed transform is applied).
"""

import inkex
from inkex import bezier, CubicSuperPath

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
        pars.add_argument("--subpaths", type=inkex.Boolean, default=True)

    # --- geometry helpers ---------------------------------------------------

    def _superpath(self, elem):
        """Element geometry as a cubic superpath in document coordinates."""
        try:
            path = elem.path.transform(elem.composed_transform())
            return path.to_superpath()
        except Exception:
            return None

    @staticmethod
    def _csp_length(csp, steps=16):
        """Total outline length of a cubic superpath.

        Computed by flattening each Bezier segment ourselves rather than via
        inkex.bezier.csplength: that helper's result varies with the
        inkex/numpy versions present, which made the metric non-deterministic
        across the CI matrix. Pure arithmetic here is stable everywhere.
        """
        total = 0.0
        for sub in csp:
            for i in range(1, len(sub)):
                p0, p1 = sub[i - 1][1], sub[i - 1][2]
                p2, p3 = sub[i][0], sub[i][1]
                prev = p0
                for s in range(1, steps + 1):
                    t = s / steps
                    mt = 1.0 - t
                    a = mt * mt * mt
                    b = 3 * mt * mt * t
                    c = 3 * mt * t * t
                    d = t * t * t
                    cur = (
                        a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                        a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1],
                    )
                    total += ((cur[0] - prev[0]) ** 2
                              + (cur[1] - prev[1]) ** 2) ** 0.5
                    prev = cur
        return total

    @staticmethod
    def _flatten_sub(sub, steps=8):
        """One cubic-superpath subpath -> list of (x, y) sample points."""
        pts = []
        for i, node in enumerate(sub):
            if i == 0:
                pts.append((node[1][0], node[1][1]))
                continue
            p0, p1 = sub[i - 1][1], sub[i - 1][2]
            p2, p3 = node[0], node[1]
            for s in range(1, steps + 1):
                t = s / steps
                mt = 1.0 - t
                a = mt * mt * mt
                b = 3 * mt * mt * t
                c = 3 * mt * t * t
                d = t * t * t
                pts.append((
                    a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                    a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1],
                ))
        return pts

    @staticmethod
    def _poly_area(pts):
        """Shoelace area of a flattened subpath (deterministic, no numpy)."""
        total = 0.0
        for i in range(len(pts)):
            x0, y0 = pts[i - 1]
            x1, y1 = pts[i]
            total += x0 * y1 - x1 * y0
        return abs(total) * 0.5

    @staticmethod
    def _poly_bbox(pts):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (max(xs) - min(xs), max(ys) - min(ys))

    def _measure_subpath(self, sub):
        """Size of a single subpath under the chosen metric, or None."""
        pts = self._flatten_sub(sub)
        if len(pts) < 2:
            return 0.0
        metric = self.options.metric
        if metric == "bbox_area":
            w, h = self._poly_bbox(pts)
            return w * h
        if metric == "max_dim":
            w, h = self._poly_bbox(pts)
            return max(w, h)
        if metric == "geom_area":
            return self._poly_area(pts)
        if metric == "path_length":
            return self._csp_length([sub])
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
            return self._csp_length(csp)
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
        mode = self.options.mode
        do_subpaths = self.options.subpaths

        matched = []          # whole-element matches
        overlay_subs = []     # document-coord subpaths to preview (highlight)

        for elem in self._candidates():
            if not isinstance(elem, types):
                continue

            if do_subpaths and isinstance(elem, inkex.PathElement):
                try:
                    local_csp = elem.path.to_superpath()
                    doc_csp = elem.path.transform(
                        elem.composed_transform()).to_superpath()
                except Exception:
                    local_csp = doc_csp = None
                if (local_csp is not None and len(local_csp) > 1
                        and len(doc_csp) == len(local_csp)):
                    keep, drop_doc = [], []
                    for i, sub in enumerate(doc_csp):
                        value = self._measure_subpath(sub)
                        if value is not None and value <= threshold:
                            drop_doc.append(sub)
                        else:
                            keep.append(local_csp[i])
                    if drop_doc:
                        if mode == "delete":
                            if keep:
                                elem.path = CubicSuperPath(keep).to_path()
                            else:
                                try:
                                    elem.delete()
                                except Exception:
                                    pass
                        else:
                            overlay_subs.extend(drop_doc)
                    continue  # this path was handled at subpath level

            value = self.measure(elem)
            if value is None:
                continue
            if value <= threshold:
                matched.append(elem)

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
            if overlay_subs:
                overlay = inkex.PathElement()
                overlay.path = CubicSuperPath(overlay_subs).to_path()
                overlay.set("id",
                            self.svg.get_unique_id("despeckle-preview"))
                overlay.style = inkex.Style({
                    "fill": color,
                    "stroke": "none",
                    "fill-opacity": "1",
                    "opacity": "1",
                })
                self.svg.add(overlay)


if __name__ == "__main__":
    Despeckle().run()
