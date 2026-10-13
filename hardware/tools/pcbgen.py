"""Small PCB generator: KiCad footprints -> placed pads -> grid router -> pours ->
DRC / connectivity checks -> Gerber RS-274X, Excellon, BOM, CPL, PNG renders.

Coordinates are millimetres, KiCad convention (x right, y down) inside this
module. Writers flip y so that fabrication files are y-up.
"""
import heapq
import math
import os
import re

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

# ------------------------------------------------------------------ s-expressions
_tok = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+')


def parse_sexp(text):
    stack, cur = [], []
    for t in _tok.findall(text):
        if t == "(":
            stack.append(cur)
            cur = []
        elif t == ")":
            done = cur
            cur = stack.pop()
            cur.append(done)
        else:
            cur.append(t[1:-1] if t.startswith('"') else t)
    return cur[0]


def find(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def first(node, key):
    r = find(node, key)
    return r[0] if r else None


# ------------------------------------------------------------------ footprints
class Pad:
    def __init__(self, name, kind, shape, x, y, rot, w, h, drill, layers, rr=0.0):
        self.name, self.kind, self.shape = name, kind, shape
        self.x, self.y, self.rot, self.w, self.h = x, y, rot, w, h
        self.drill = drill  # None | (dx, dy)
        self.layers = layers
        self.rr = rr

    def local_shape(self):
        w, h = self.w, self.h
        if self.shape == "circle":
            g = Point(0, 0).buffer(w / 2, 32)
        elif self.shape == "oval":
            r = min(w, h) / 2
            if w >= h:
                g = LineString([(-(w / 2 - r), 0), (w / 2 - r, 0)]).buffer(r, 16) if w > h else Point(0, 0).buffer(r, 32)
            else:
                g = LineString([(0, -(h / 2 - r)), (0, h / 2 - r)]).buffer(r, 16)
        elif self.shape == "roundrect" and self.rr > 0:
            r = min(w, h) * self.rr
            g = box(-w / 2 + r, -h / 2 + r, w / 2 - r, h / 2 - r).buffer(r, 8)
        else:
            g = box(-w / 2, -h / 2, w / 2, h / 2)
        return g


class Footprint:
    def __init__(self, path):
        self.name = os.path.basename(path).replace(".kicad_mod", "")
        tree = parse_sexp(open(path, encoding="utf-8").read())
        self.pads, self.silk, self.crt = [], [], []
        for p in find(tree, "pad"):
            name, kind, shape = p[1], p[2], p[3]
            at = first(p, "at")
            x, y = float(at[1]), float(at[2])
            rot = float(at[3]) if len(at) > 3 else 0.0
            sz = first(p, "size")
            w, h = float(sz[1]), float(sz[2])
            d = first(p, "drill")
            drill = None
            if d:
                if d[1] == "oval":
                    drill = (float(d[2]), float(d[3]))
                else:
                    drill = (float(d[1]), float(d[1]))
            layers = first(p, "layers")[1:]
            rr = first(p, "roundrect_rratio")
            self.pads.append(Pad(name, kind, shape, x, y, rot, w, h, drill, layers, float(rr[1]) if rr else 0.0))
        for ln in find(tree, "fp_line"):
            layer = first(ln, "layer")[1]
            s, e = first(ln, "start"), first(ln, "end")
            seg = ((float(s[1]), float(s[2])), (float(e[1]), float(e[2])))
            if layer == "F.SilkS":
                self.silk.append(seg)
            elif layer == "F.CrtYd":
                self.crt.append(seg)
        for c in find(tree, "fp_circle"):
            layer = first(c, "layer")[1]
            ce, en = first(c, "center"), first(c, "end")
            cx, cy = float(ce[1]), float(ce[2])
            r = math.hypot(float(en[1]) - cx, float(en[2]) - cy)
            pts = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 41)]
            segs = list(zip(pts[:-1], pts[1:]))
            if layer == "F.SilkS":
                self.silk += segs
            elif layer == "F.CrtYd":
                self.crt += segs


def xform(x, y, X, Y, rot):
    """Footprint-local -> board. KiCad rotation (degrees, CCW on screen, y down)."""
    a = math.radians(rot)
    c, s = math.cos(a), math.sin(a)
    return X + x * c + y * s, Y - x * s + y * c


class PlacedPad:
    def __init__(self, comp, pad, net):
        self.comp, self.pad, self.net = comp, pad, net
        X, Y, R = comp.x, comp.y, comp.rot
        self.cx, self.cy = xform(pad.x, pad.y, X, Y, R)
        g = affinity.rotate(pad.local_shape(), -(pad.rot + R), origin=(0, 0))
        self.shape = affinity.translate(g, self.cx, self.cy)
        self.tht = pad.kind in ("thru_hole", "np_thru_hole")
        self.npth = pad.kind == "np_thru_hole"
        self.smd_top = pad.kind == "smd"
        self.layers = ("top", "bot") if self.tht else ("top",)
        if self.npth:
            self.layers = ()
        self.drill = pad.drill
        self.drill_rot = pad.rot + R

    @property
    def label(self):
        return f"{self.comp.ref}.{self.pad.name}"


class Component:
    def __init__(self, ref, fp, x, y, rot, value, lcsc="", mpn="", nets=None, tht=False, dnp=False):
        self.ref, self.fp, self.x, self.y, self.rot = ref, fp, x, y, rot
        self.value, self.lcsc, self.mpn, self.tht, self.dnp = value, lcsc, mpn, tht, dnp
        nets = nets or {}
        self.pads = [PlacedPad(self, p, nets.get(p.name, "") if p.kind != "np_thru_hole" else "") for p in fp.pads]
        for pp in self.pads:
            if pp.pad.name and pp.pad.kind != "np_thru_hole" and pp.pad.name not in nets:
                raise ValueError(f"{ref}: pad {pp.pad.name} has no net (use 'NC')")

    def tf(self, x, y):
        return xform(x, y, self.x, self.y, self.rot)

    def courtyard(self):
        pts = [self.tf(*p) for seg in self.fp.crt for p in seg]
        if not pts:
            return unary_union([p.shape for p in self.pads]).envelope
        return shapely.MultiPoint(pts).convex_hull


# ------------------------------------------------------------------ board
class Board:
    def __init__(self, outline, rules):
        self.outline = outline  # shapely Polygon
        self.r = rules
        self.comps = []
        self.tracks = []  # (net, layer, [(x,y),...], width)
        self.vias = []  # (net, x, y)
        self.keepout = {"top": [], "bot": []}  # no copper at all
        self.route_block = {"top": [], "bot": []}  # no routing (pour allowed)
        self.via_block = []  # no vias (e.g. under a connector body)
        self.pour = {}
        self.silk_text = []  # (text, x, y, size, rot)
        self.silk_lines = []

    def add(self, c):
        self.comps.append(c)
        for p in c.pads:  # non-plated holes: no copper of any kind near them
            if p.npth:
                k = p.shape.buffer(self.r.get("npth_clear", 0.25), 24)
                self.keepout["top"].append(k)
                self.keepout["bot"].append(k)
        return c

    def pads(self):
        return [p for c in self.comps for p in c.pads]

    def via_shape(self, x, y, d=None):
        return Point(x, y).buffer((d or self.r["via_d"]) / 2, 24)

    def track_shape(self, pts, w):
        if len(pts) == 1:
            return Point(pts[0]).buffer(w / 2, 16)
        return LineString(pts).buffer(w / 2, 16, cap_style="round", join_style="round")

    def copper(self, layer, include_pour=True):
        """List of (net, geometry) on a layer."""
        out = []
        for p in self.pads():
            if layer in p.layers:
                out.append((p.net, p.shape))
        for net, ly, pts, w in self.tracks:
            if ly == layer:
                out.append((net, self.track_shape(pts, w)))
        for net, x, y in self.vias:
            out.append((net, self.via_shape(x, y)))
        if include_pour and layer in self.pour:
            out.append((self.r["gnd"], self.pour[layer]))
        return out

    # -------------------------------------------------------------- router
    def route(self, net, width, pads=None, layers=("top", "bot"), via_cost=40, avoid=None, extra_targets=None):
        """Connect all pads of `net` (or the given pads) into one tree with A* on a grid."""
        g = self.r["grid"]
        minx, miny, maxx, maxy = self.outline.bounds
        nx, ny = int((maxx - minx) / g) + 1, int((maxy - miny) / g) + 1
        xs = minx + np.arange(nx) * g
        ys = miny + np.arange(ny) * g
        XX, YY = np.meshgrid(xs, ys, indexing="ij")
        clr = self.r["clearance"]
        free = {}
        inside = self.outline.buffer(-(self.r["edge_clear"] + width / 2))
        for ly in layers:
            obs = [geom for n, geom in self.copper(ly, include_pour=False) if n != net]
            obs += self.keepout[ly] + self.route_block[ly]
            if avoid:
                obs += avoid.get(ly, [])
            # vias of this net also need to keep away from other-net copper on both layers, handled at via step
            blocked = unary_union(obs).buffer(clr + width / 2 + self.r['grid_margin'], 8) if obs else Polygon()
            ok = shapely.contains_xy(inside, XX, YY) & ~shapely.contains_xy(blocked, XX, YY)
            free[ly] = ok
        # via allowed where a via fits on all layers
        vr = self.r["via_d"] / 2
        vobs = []
        for ly in ("top", "bot"):
            vobs += [geom for n, geom in self.copper(ly, include_pour=False) if n != net]
            vobs += self.keepout[ly]
        vblocked = unary_union(vobs).buffer(clr + vr + self.r['grid_margin'], 8)
        # never drop a via into (or partly into) a pad, even one of the same net (solder wicking)
        own_pads = [p.shape for p in self.pads() if p.net == net]
        if own_pads:
            vblocked = vblocked.union(unary_union(own_pads).buffer(vr + 0.15, 8))
        vinside = self.outline.buffer(-(self.r["edge_clear"] + vr))
        if self.via_block:
            vinside = vinside.difference(unary_union(self.via_block))
        via_ok = shapely.contains_xy(vinside, XX, YY) & ~shapely.contains_xy(vblocked, XX, YY)

        targets = pads if pads is not None else [p for p in self.pads() if p.net == net]
        if len(targets) < 2 and not extra_targets:
            return

        def cells_of(geom, ly):
            m = shapely.contains_xy(geom.buffer(0.02), XX, YY)
            idx = np.argwhere(m)
            return {(int(i), int(j), ly) for i, j in idx}

        def pad_cells(p):
            """Free cells inside the pad, plus the cell(s) at the pad centre (always allowed)."""
            s = set()
            centre = Point(p.cx, p.cy).buffer(g * 0.75)
            for ly in p.layers:
                if ly in layers:
                    for c in cells_of(p.shape, ly):
                        if free[ly][c[0], c[1]]:
                            s.add(c)
                    s |= cells_of(centre, ly)
            return s

        tree = pad_cells(targets[0])
        # existing tracks/vias of this net (e.g. hand-placed fan-out) join the tree
        for n, ly, pts, w in self.tracks:
            if n == net and ly in layers:
                tree |= cells_of(self.track_shape(pts, w), ly)
        for n, x, y in self.vias:
            if n == net:
                for ly in layers:
                    tree |= cells_of(self.via_shape(x, y), ly)
        remaining = list(targets[1:]) + list(extra_targets or [])
        # the pad centre cells are always usable (traces leave pads from their centre)
        for p in targets:
            for (i, j, ly) in pad_cells(p):
                free[ly][i, j] = True
        layer_idx = {ly: k for k, ly in enumerate(layers)}
        moves = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                 (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
        while remaining:
            # route to the nearest remaining target
            tgt = remaining.pop(0)
            goal = pad_cells(tgt) if isinstance(tgt, PlacedPad) else tgt
            if not goal:
                raise RuntimeError(f"{net}: target has no free cells")
            gxs = [c[0] for c in goal]
            gys = [c[1] for c in goal]
            gx0, gx1, gy0, gy1 = min(gxs), max(gxs), min(gys), max(gys)
            gset = goal

            def h(i, j):
                dx = gx0 - i if i < gx0 else (i - gx1 if i > gx1 else 0)
                dy = gy0 - j if j < gy0 else (j - gy1 if j > gy1 else 0)
                return math.hypot(dx, dy)

            # bidirectional not needed; plain A*
            openh = []
            best = {}
            prev = {}
            for c in tree:
                best[c] = 0.0
                heapq.heappush(openh, (h(c[0], c[1]), 0.0, c))
            found = None
            # pre-compute heuristic lazily via cache
            hcache = {}
            while openh:
                f, cost, c = heapq.heappop(openh)
                if cost > best.get(c, 1e18):
                    continue
                if c in gset:
                    found = c
                    break
                i, j, ly = c
                for di, dj, w in moves:
                    ni, nj = i + di, j + dj
                    if 0 <= ni < nx and 0 <= nj < ny and free[ly][ni, nj]:
                        if di and dj and not (free[ly][i + di, j] and free[ly][i, j + dj]):
                            continue
                        nc = (ni, nj, ly)
                        turn = 0.0
                        pc = prev.get(c)
                        if pc is not None and (pc[0] - i, pc[1] - j) != (-di, -dj) and pc[2] == ly:
                            turn = 0.3
                        ncost = cost + w + turn + (2.0 if ly == "bot" else 0.0)
                        if ncost < best.get(nc, 1e18):
                            best[nc] = ncost
                            prev[nc] = c
                            hh = hcache.get((ni, nj))
                            if hh is None:
                                hh = h(ni, nj)
                                hcache[(ni, nj)] = hh
                            heapq.heappush(openh, (ncost + hh, ncost, nc))
                if via_ok[i, j]:
                    for oly in layers:
                        if oly != ly and free[oly][i, j]:
                            nc = (i, j, oly)
                            ncost = cost + via_cost
                            if ncost < best.get(nc, 1e18):
                                best[nc] = ncost
                                prev[nc] = c
                                heapq.heappush(openh, (ncost + h(i, j), ncost, nc))
            if found is None:
                raise RuntimeError(f"route failed: {net} -> {getattr(tgt, 'label', tgt)}")
            path = [found]
            while path[-1] in prev:
                path.append(prev[path[-1]])
            path.reverse()
            # emit segments / vias
            seg = []
            cur_ly = path[0][2]
            for c in path:
                if c[2] != cur_ly:
                    if seg:
                        self._emit(net, cur_ly, seg, width, xs, ys)
                    self.vias.append((net, float(xs[c[0]]), float(ys[c[1]])))
                    seg = []
                    cur_ly = c[2]
                seg.append(c)
            if seg:
                self._emit(net, cur_ly, seg, width, xs, ys)
            # path cells become tree (thicken a bit so later branches can join)
            for c in path:
                tree.add(c)
            tree |= goal
            # newly placed copper blocks nothing for this net; refresh free maps for other nets later

    def _emit(self, net, ly, cells, width, xs, ys):
        pts = [(float(xs[c[0]]), float(ys[c[1]])) for c in cells]
        # simplify collinear
        out = [pts[0]]
        for k in range(1, len(pts) - 1):
            ax, ay = out[-1]
            bx, by = pts[k]
            cx, cy = pts[k + 1]
            if abs((bx - ax) * (cy - by) - (by - ay) * (cx - bx)) > 1e-9:
                out.append(pts[k])
        if len(pts) > 1:
            out.append(pts[-1])
        self.tracks.append((net, ly, out, width))

    # -------------------------------------------------------------- pours
    def make_pours(self, net, layers=("top", "bot"), clearance=None, edge=None, min_width=0.25):
        clr = clearance or self.r["pour_clear"]
        edge = edge or self.r["pour_edge"]
        for ly in layers:
            area = self.outline.buffer(-edge)
            for k in self.keepout[ly]:
                area = area.difference(k)
            others = [g for n, g in self.copper(ly, include_pour=False) if n != net]
            # THT/NPTH holes of other nets and all drills need clearance too
            for p in self.pads():
                if p.npth:
                    others.append(p.shape)
            if others:
                area = area.difference(unary_union(others).buffer(clr, 12))
            # remove thin slivers
            area = area.buffer(-min_width / 2, 8).buffer(min_width / 2, 8)
            own = unary_union([g for n, g in self.copper(ly, include_pour=False) if n == net])
            area = area.intersection(self.outline.buffer(-edge))
            for k in self.keepout[ly]:
                area = area.difference(k)
            self.pour[ly] = area
        self._prune_islands(net, layers)

    def _prune_islands(self, net, layers):
        """Drop pour islands that touch no copper of `net` (pads/tracks/vias)."""
        for ly in layers:
            own = unary_union([g for n, g in self.copper(ly, include_pour=False) if n == net])
            parts = list(self.pour[ly].geoms) if hasattr(self.pour[ly], "geoms") else [self.pour[ly]]
            keep = [p for p in parts if p.intersects(own)]
            self.pour[ly] = unary_union(keep) if keep else Polygon()

    # -------------------------------------------------------------- checks
    def drc(self):
        """Returns list of problems: clearance between different nets, edge clearance, keepouts."""
        probs = []
        clr = self.r["clearance"] - 1e-3
        for ly in ("top", "bot"):
            items = self.copper(ly)
            for a in range(len(items)):
                na, ga = items[a]
                for b in range(a + 1, len(items)):
                    nb, gb = items[b]
                    if na == nb and na:
                        continue
                    if na == "" and nb == "":
                        continue
                    d = ga.distance(gb)
                    lim = clr if not (self.pour.get(ly) is ga or self.pour.get(ly) is gb) else self.r["pour_clear"] - 0.01
                    if d < lim:
                        probs.append(f"{ly}: clearance {d:.3f} between {na or 'NC'} and {nb or 'NC'} at {ga.centroid.x:.2f},{ga.centroid.y:.2f}")
            inner = self.outline.buffer(-self.r["edge_clear"] + 1e-3)
            for n, g in items:
                if not g.within(inner) and not g.is_empty:
                    pt = g.difference(inner).representative_point()
                    probs.append(f"{ly}: copper of {n or 'NC'} too close to edge at {pt.x:.2f},{pt.y:.2f}")
            for k in self.keepout[ly]:
                for n, g in items:
                    if g.intersects(k.buffer(-1e-3)):
                        probs.append(f"{ly}: copper of {n} inside keepout")
        # drill to drill
        holes = self.holes()
        for a in range(len(holes)):
            for b in range(a + 1, len(holes)):
                (xa, ya, da, _, _), (xb, yb, db, _, _) = holes[a], holes[b]
                if math.hypot(xa - xb, ya - yb) - (da + db) / 2 < self.r["hole_to_hole"]:
                    probs.append(f"hole spacing at {xa:.2f},{ya:.2f}")
        return probs

    def connectivity(self):
        """Per net: number of electrically separate copper islands (should be 1)."""
        import networkx as nx
        G = nx.Graph()
        items = []
        for ly in ("top", "bot"):
            for n, g in self.copper(ly):
                if not n or n == "NC":
                    continue
                parts = list(g.geoms) if hasattr(g, "geoms") else [g]
                for part in parts:
                    items.append((n, ly, part))
        for k in range(len(items)):
            G.add_node(k)
        # same layer touching
        for ly in ("top", "bot"):
            idx = [k for k, it in enumerate(items) if it[1] == ly]
            geoms = [items[k][2] for k in idx]
            tree = shapely.STRtree(geoms)
            for a_i, a in enumerate(idx):
                for b_i in tree.query(geoms[a_i], predicate="intersects"):
                    b = idx[b_i]
                    if b != a:
                        if items[a][0] != items[b][0]:
                            raise RuntimeError(f"SHORT between {items[a][0]} and {items[b][0]} on {ly}")
                        G.add_edge(a, b)
        # layer change: vias and THT pads (same xy on both layers)
        drills = [Point(x, y) for (n, x, y) in self.vias] + [Point(p.cx, p.cy) for p in self.pads() if p.tht and not p.npth]
        for d in drills:
            hits = [k for k, it in enumerate(items) if it[2].intersects(d)]
            for a in hits:
                for b in hits:
                    if a < b:
                        if items[a][0] != items[b][0]:
                            raise RuntimeError(f"SHORT via between {items[a][0]} and {items[b][0]}")
                        G.add_edge(a, b)
        res = {}
        nets = sorted({it[0] for it in items})
        for n in nets:
            sub = G.subgraph([k for k, it in enumerate(items) if it[0] == n])
            comps = list(nx.connected_components(sub))
            # which pads are in which component
            pad_groups = []
            for comp in comps:
                labs = []
                for k in comp:
                    for p in self.pads():
                        if p.net == n and p.shape.intersects(items[k][2]) and items[k][1] in p.layers:
                            labs.append(p.label)
                pad_groups.append(sorted(set(labs)))
            pad_groups = [g for g in pad_groups if g]
            res[n] = pad_groups
        return res

    def holes(self):
        """(x, y, drill_d, plated, slot) list; slot = None or (x2,y2) end point for oval drills."""
        out = []
        for n, x, y in self.vias:
            out.append((x, y, self.r["via_drill"], True, None))
        for p in self.pads():
            if not p.drill:
                continue
            dx, dy = p.drill
            plated = not p.npth
            if abs(dx - dy) < 1e-6:
                out.append((p.cx, p.cy, dx, plated, None))
            else:
                d = min(dx, dy)
                L = max(dx, dy) - d
                ang = math.radians(-(p.drill_rot)) + (0 if dx > dy else math.pi / 2)
                ex, ey = math.cos(ang) * L / 2, math.sin(ang) * L / 2
                out.append((p.cx - ex, p.cy - ey, d, plated, (p.cx + ex, p.cy + ey)))
        return out
