"""Fabrication outputs: Gerber RS-274X (X2 attributes), Excellon drill, JLCPCB BOM + CPL."""
import csv
import datetime
import math
import os
import zipfile

from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import unary_union

UNIT = 1e6  # format 4.6, mm


def _c(v):
    return str(int(round(v * UNIT)))


class Gerber:
    def __init__(self, path, function, polarity="Positive", H=0.0):
        self.f = open(path, "w")
        self.H = H
        self.w(f"%TF.GenerationSoftware,Shimushili,pcbgen,1.0*%")
        self.w(f"%TF.CreationDate,{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')}*%")
        self.w(f"%TF.FileFunction,{function}*%")
        self.w(f"%TF.FilePolarity,{polarity}*%")
        self.w("%FSLAX46Y46*%")
        self.w("%MOMM*%")
        self.w("%LPD*%")
        self.apertures = {}
        self.cur_ap = None

    def w(self, s):
        self.f.write(s + "\n")

    def xy(self, x, y):
        return f"X{_c(x)}Y{_c(self.H - y)}"

    def region(self, poly):
        """Filled polygon with holes (dark exterior, clear holes)."""
        def ring(coords):
            pts = list(coords)
            self.w("G36*")
            self.w(f"{self.xy(*pts[0])}D02*")
            self.w("G01*")
            for p in pts[1:]:
                self.w(f"{self.xy(*p)}D01*")
            self.w("G37*")
        self.w("%LPD*%")
        ring(poly.exterior.coords)
        if poly.interiors:
            self.w("%LPC*%")
            for h in poly.interiors:
                ring(h.coords)
            self.w("%LPD*%")

    def fill(self, geom):
        polys = [p for p in (geom.geoms if hasattr(geom, "geoms") else [geom]) if isinstance(p, Polygon) and not p.is_empty]
        # draw outer polygons first; an island sitting inside another polygon's hole must come
        # after that polygon's clear-polarity hole, so sort by containment depth
        hulls = [Polygon(p.exterior) for p in polys]
        depth = []
        for i, p in enumerate(polys):
            rp = p.representative_point()
            depth.append(sum(1 for j, hh in enumerate(hulls) if j != i and hh.contains(rp)))
        polys = [p for _, p in sorted(zip(depth, polys), key=lambda t: t[0])]
        for p in polys:
            self.region(p)

    def aperture(self, d):
        key = round(d, 4)
        if key not in self.apertures:
            n = 10 + len(self.apertures)
            self.apertures[key] = n
            self.w(f"%ADD{n}C,{d:.4f}*%")
        n = self.apertures[key]
        if self.cur_ap != n:
            self.w(f"D{n}*")
            self.cur_ap = n

    def stroke(self, pts, d):
        self.aperture(d)
        self.w(f"{self.xy(*pts[0])}D02*")
        self.w("G01*")
        for p in pts[1:]:
            self.w(f"{self.xy(*p)}D01*")

    def close(self):
        self.w("M02*")
        self.f.close()


def text_polys(text, x, y, size, rot=0, anchor="center"):
    tp = TextPath((0, 0), text, size=size, prop=FontProperties(family="DejaVu Sans", weight="bold"))
    polys = []
    for poly in tp.to_polygons():
        if len(poly) >= 3:
            polys.append(Polygon(poly).buffer(0))
    # even-odd: build with symmetric difference to get holes right
    g = Polygon()
    for p in polys:
        g = g.symmetric_difference(p)
    minx, miny, maxx, maxy = g.bounds
    if anchor == "center":
        g = affinity.translate(g, -(minx + maxx) / 2, -(miny + maxy) / 2)
    g = affinity.scale(g, 1, -1, origin=(0, 0))  # text path is y-up; board is y-down
    if rot:
        g = affinity.rotate(g, -rot, origin=(0, 0))
    return affinity.translate(g, x, y)


def write_all(b, outdir, name, H, silk_extra=()):
    os.makedirs(outdir, exist_ok=True)
    files = []

    def path(ext):
        p = os.path.join(outdir, f"{name}.{ext}")
        files.append(p)
        return p

    # ---------------------------------------------------------- copper
    for ly, ext, fn in (("top", "GTL", "Copper,L1,Top"), ("bot", "GBL", "Copper,L2,Bot")):
        g = Gerber(path(ext), fn, H=H)
        geom = unary_union([gg for n, gg in b.copper(ly)])
        g.fill(geom)
        g.close()

    # ---------------------------------------------------------- solder mask (openings)
    exp = 0.05
    for ly, ext, fn in (("top", "GTS", "Soldermask,Top"), ("bot", "GBS", "Soldermask,Bot")):
        g = Gerber(path(ext), fn, polarity="Negative", H=H)
        shapes = []
        for p in b.pads():
            if p.npth or p.tht or (ly == "top" and p.smd_top):
                shapes.append(p.shape.buffer(exp, 16) if not p.npth else p.shape.buffer(0.1, 16))
        g.fill(unary_union(shapes))
        g.close()
    mask_top = unary_union([p.shape.buffer(exp) for p in b.pads() if p.smd_top or p.tht or p.npth])

    # ---------------------------------------------------------- paste
    g = Gerber(path("GTP"), "Paste,Top", H=H)
    g.fill(unary_union([p.shape for p in b.pads() if p.smd_top and not p.comp.ref.startswith("TP")]))
    g.close()

    # ---------------------------------------------------------- silkscreen
    keep_out = mask_top.buffer(0.15)
    silk_w = 0.15
    silk = []
    for c in b.comps:
        for (a, e) in c.fp.silk:
            ln = LineString([c.tf(*a), c.tf(*e)]).buffer(silk_w / 2, 8)
            silk.append(ln)
    for (t, x, y, sz, rot) in b.silk_text:
        silk.append(text_polys(t, x, y, sz, rot))
    for geom in silk_extra:
        silk.append(geom)
    silk_geom = unary_union(silk).difference(keep_out).intersection(b.outline.buffer(-0.2))
    g = Gerber(path("GTO"), "Legend,Top", H=H)
    g.fill(silk_geom)
    g.close()
    g = Gerber(path("GBO"), "Legend,Bot", H=H)
    # positions are in top-view board coordinates; each string is mirrored about its own anchor
    # so it reads correctly when the board is turned over
    bot_silk = unary_union([affinity.scale(text_polys(t, x, y, sz, rot), -1, 1, origin=(x, y))
                            for (t, x, y, sz, rot) in getattr(b, "silk_text_bot", [])])
    mask_bot = unary_union([p.shape.buffer(0.1) for p in b.pads() if p.tht or p.npth])
    bot_silk = bot_silk.difference(mask_bot.buffer(0.15)).intersection(b.outline.buffer(-0.3))
    # bottom legend is mirrored when viewed from the bottom; we write it un-mirrored in board coords
    g.fill(bot_silk)
    g.close()

    # ---------------------------------------------------------- outline
    g = Gerber(path("GKO"), "Profile,NP", H=H)
    g.stroke(list(b.outline.exterior.coords), 0.1)
    g.close()

    # ---------------------------------------------------------- drills
    holes = b.holes()
    for plated, fname in ((True, "PTH"), (False, "NPTH")):
        p = os.path.join(outdir, f"{name}-{fname}.drl")
        files.append(p)
        hs = [h for h in holes if h[3] == plated]
        tools = sorted({round(h[2], 3) for h in hs})
        with open(p, "w") as f:
            f.write("M48\n")
            f.write(f"; DRILL file {name} {'PLATED' if plated else 'NON-PLATED'}\n")
            f.write(f"; #@! TF.FileFunction,{'Plated' if plated else 'NonPlated'},1,2,{'PTH' if plated else 'NPTH'}\n")
            f.write("FMAT,2\nMETRIC\n")
            for k, d in enumerate(tools, 1):
                f.write(f"T{k}C{d:.3f}\n")
            f.write("%\nG90\nG05\n")
            for k, d in enumerate(tools, 1):
                f.write(f"T{k}\n")
                for (x, y, dd, pl, slot) in hs:
                    if round(dd, 3) != d:
                        continue
                    if slot is None:
                        f.write(f"X{x:.3f}Y{H - y:.3f}\n")
                    else:
                        x2, y2 = slot
                        f.write(f"X{x:.3f}Y{H - y:.3f}G85X{x2:.3f}Y{H - y2:.3f}\n")
            f.write("M30\n")
    return files


def write_bom_cpl(b, outdir, name, H):
    groups = {}
    for c in b.comps:
        if c.dnp or not c.lcsc:
            continue
        key = (c.value, c.fp.name, c.lcsc)
        groups.setdefault(key, []).append(c.ref)
    bom = os.path.join(outdir, f"{name}-BOM.csv")
    with open(bom, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC", "Qty", "Manufacturer Part"])
        for (val, fpn, lcsc), refs in sorted(groups.items(), key=lambda kv: kv[1][0]):
            mpn = next(c.mpn for c in b.comps if c.ref == refs[0])
            w.writerow([val, ",".join(sorted(refs, key=lambda r: (r[0], int(''.join(ch for ch in r if ch.isdigit()) or 0)))), fpn, lcsc, len(refs), mpn])
    cpl = os.path.join(outdir, f"{name}-CPL.csv")
    with open(cpl, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for c in b.comps:
            if c.dnp or not c.lcsc:
                continue
            x0, y0, x1, y1 = unary_union([p.shape for p in c.pads]).bounds
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2  # centre of the land pattern
            if hasattr(c, "cpl_center"):
                cx, cy = c.cpl_center
            if c.tht:  # THT parts: use the pad centroid (lead positions)
                cx = sum(p.cx for p in c.pads) / len(c.pads)
                cy = sum(p.cy for p in c.pads) / len(c.pads)
            w.writerow([c.ref, f"{cx:.3f}mm", f"{H - cy:.3f}mm", "Top", f"{c.rot % 360:.0f}"])
    return bom, cpl


def zip_gerbers(files, zpath):
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, os.path.basename(p))
    return zpath
