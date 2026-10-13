"""PNG renders of the board for review."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch
from matplotlib.path import Path
from shapely.geometry import MultiPolygon, Polygon


def _patch(ax, geom, **kw):
    polys = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    for p in polys:
        if p.is_empty or not isinstance(p, Polygon):
            continue
        verts, codes = [], []
        for ring in [p.exterior] + list(p.interiors):
            xy = list(ring.coords)
            verts += xy
            codes += [Path.MOVETO] + [Path.LINETO] * (len(xy) - 2) + [Path.CLOSEPOLY]
        ax.add_patch(PathPatch(Path(verts, codes), **kw))


NET_COL = {"GND": "#6b7280", "VBUS": "#dc2626", "3V3": "#ea580c", "DRAIN": "#7c3aed"}


def render(b, path, layer="top", labels=True, scale=14):
    W = b.outline.bounds[2]
    H = b.outline.bounds[3]
    fig, ax = plt.subplots(figsize=(W / 25.4 * scale / 4, H / 25.4 * scale / 4), dpi=120)
    ax.set_aspect("equal")
    ax.set_xlim(-1, W + 1)
    ax.set_ylim(H + 1, -1)
    ax.set_facecolor("#0f3d2e")
    _patch(ax, b.outline, facecolor="#14532d", edgecolor="#facc15", lw=1)
    if layer in b.pour:
        _patch(ax, b.pour[layer], facecolor="#3f6f55", edgecolor="none", alpha=0.9)
    for k in b.keepout[layer]:
        _patch(ax, k, facecolor="none", edgecolor="#fca5a5", lw=0.6, ls="--")
    other = "bot" if layer == "top" else "top"
    for net, ly, pts, w in b.tracks:
        g = b.track_shape(pts, w)
        if ly == layer:
            _patch(ax, g, facecolor=NET_COL.get(net, "#f59e0b"), edgecolor="none")
        else:
            _patch(ax, g, facecolor=NET_COL.get(net, "#60a5fa"), edgecolor="none", alpha=0.25)
    for c in b.comps:
        cy = c.courtyard()
        _patch(ax, cy, facecolor="none", edgecolor="#e5e7eb", lw=0.4, alpha=0.6)
        for p in c.pads:
            if p.npth:
                _patch(ax, p.shape, facecolor="black", edgecolor="#e5e7eb", lw=0.4)
            elif layer in p.layers:
                _patch(ax, p.shape, facecolor="#fbbf24" if p.net != "GND" else "#9ca3af", edgecolor="black", lw=0.2)
        if labels:
            x, y = c.x, c.y
            ax.text(x, y, c.ref, color="white", fontsize=5, ha="center", va="center", weight="bold")
    for net, x, y in b.vias:
        from shapely.geometry import Point
        _patch(ax, Point(x, y).buffer(b.r["via_d"] / 2), facecolor="#d1d5db", edgecolor="black", lw=0.2)
        _patch(ax, Point(x, y).buffer(b.r["via_drill"] / 2), facecolor="black", edgecolor="none")
    if labels:
        for c in b.comps:
            for p in c.pads:
                if p.net and p.net not in ("GND", "NC") and layer in p.layers:
                    ax.text(p.cx, p.cy, p.net, color="#111827", fontsize=2.2, ha="center", va="center")
    ax.set_title(f"{layer} layer", color="white")
    fig.patch.set_facecolor("#111827")
    ax.tick_params(colors="#9ca3af", labelsize=6)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
