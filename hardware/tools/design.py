"""Shimushili IR blaster – board design (placement, nets, routing).

Run:  python3 design.py   -> builds the board, routes it, checks it, writes ../output/
"""
import math
import os
import sys

from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

sys.path.insert(0, os.path.dirname(__file__))
from pcbgen import Board, Component, Footprint  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FP = os.path.join(HERE, "..", "footprints")


def fp(name):
    return Footprint(os.path.join(FP, name + ".kicad_mod"))


R = 35.0                       # board radius: round, lies flat, LEDs all around the rim
W, H = 2 * R, 2 * R
C = R                          # centre (C, C)
RULES = dict(
    grid=0.1, grid_margin=0.03,
    clearance=0.15,      # JLCPCB 2-layer min 0.127
    edge_clear=0.4,
    pour_clear=0.3, pour_edge=0.6,
    via_d=0.6, via_drill=0.3,
    hole_to_hole=0.5, npth_clear=0.3,   # JLC: 0.5 mm between holes of different nets
    gnd="GND",
)
W_SIG, W_PWR, W_LED = 0.2, 0.5, 0.4

# 8 rim LEDs (angles in degrees, maths convention: 0 = right, 90 = up/antenna side).
# The antenna sits in a 70 deg gap at the top; the other seven gaps are equal (~41 deg).
GAP = 70.0
RIM = [90.0 - GAP / 2, 90.0 + GAP / 2] + [90.0 + GAP / 2 + (360.0 - GAP) / 7 * k for k in range(1, 7)]
# strings of two (first LED gets the series resistor), never across the antenna gap
STRINGS = [("A", 7, 0), ("B", 1, 2), ("C", 3, 4), ("D", 5, 6)]   # indices into RIM
LED_TIP_INSET = 0.4            # lens tip this far inside the board edge
LED_TIP = 12.41                # lens tip distance from the pad row (O3.81 footprint)


def polar(r, ang):
    a = math.radians(ang)
    return C + r * math.cos(a), C - r * math.sin(a)


def build():
    b = Board(Point(C, C).buffer(R, 256), RULES)
    # ------------------------------------------------------------ footprints
    WROOM = fp("ESP32-S3-WROOM-1")
    USB = fp("USB_C_Receptacle_HRO_TYPE-C-31-M-12")
    SOT223 = fp("SOT-223-3_TabPin2")
    SOT23 = fp("SOT-23")
    R0603 = fp("R_0603_1608Metric")
    R1206 = fp("R_1206_3216Metric")
    C0603 = fp("C_0603_1608Metric")
    C0805 = fp("C_0805_2012Metric")
    LED0603 = fp("LED_0603_1608Metric")
    LED5 = fp("LED_D5.0mm")
    LED5H = fp("LED_D5.0mm_Horizontal_O3.81mm_Z3.0mm")  # leads bent 3.8 mm from the body
    IRRX = fp("Vishay_MOLD-3Pin")
    IRLED = ("TSAL6400 940nm", "C94857", "Vishay TSAL6400")

    # ------------------------------------------------------------ module (antenna at the top edge)
    top = C - math.sqrt(R ** 2 - 9.9 ** 2) + 0.1   # antenna corners just inside the circle
    MX, MY = C, top + 15.75
    wroom_nets = {str(i): "NC" for i in range(1, 42)}
    wroom_nets.update({"1": "GND", "2": "3V3", "3": "EN", "5": "IR_RX", "13": "USB_DM", "14": "USB_DP",
                       "20": "IR_TX", "27": "BOOT", "39": "LED_STAT", "40": "GND", "41": "GND"})
    u1 = b.add(Component("U1", WROOM, MX, MY, 0, "ESP32-S3-WROOM-1-N16R8", "C2913202", "ESP32-S3-WROOM-1-N16R8", wroom_nets))
    u1.cpl_center = (MX, MY - 3.0)  # module body centre (18 x 25.5 mm)
    ant = box(MX - 9 - 5, -1, MX + 9 + 5, MY - 9.8 + 0.2)  # no copper around the antenna, both layers
    b.keepout["top"].append(ant)
    b.keepout["bot"].append(ant)
    b.route_block["bot"].append(box(MX - 9.0, MY - 9.8, MX + 9.0, MY + 9.75))
    b.route_block["top"].append(box(MX - 8.0, MY - 9.8, MX + 8.0, MY + 8.9))

    # ------------------------------------------------------------ rim LEDs: 5 mm, leads bent 90 deg, lens pointing outward
    rp = R - LED_TIP_INSET - LED_TIP       # radius of the pad pair
    led_ref = {}
    for k, ang in enumerate(RIM):
        rot = ang + 90.0                    # footprint +y (lens direction) -> outward
        mx, my = polar(rp, ang)             # midpoint between the two pads
        a = math.radians(rot)
        ox, oy = mx - 1.27 * math.cos(a), my + 1.27 * math.sin(a)
        led_ref[k] = (f"D{k + 1}", ox, oy, rot)
    nets = {}
    for s, i1, i2 in STRINGS:
        nets[i1] = (f"LED{s}1", f"LED{s}2")   # anode, cathode
        nets[i2] = (f"LED{s}2", "DRAIN")
    for k, (ref, ox, oy, rot) in led_ref.items():
        an, ca = nets[k]
        c = b.add(Component(ref, LED5H, ox, oy, rot, *IRLED, {"2": an, "1": ca}, tht=True))
        c.dnp = True        # hand-fitted (lying flat, leads bent): not in the JLC assembly files
        c.hand = True
    # string resistors, inboard of the gap between the two LEDs of each string
    for n, (s, i1, i2) in enumerate(STRINGS):
        a1, a2 = RIM[i1], RIM[i2] if RIM[i2] > RIM[i1] else RIM[i2] + 360
        x, y = polar(19.5, (a1 + a2) / 2)
        b.add(Component(("R6", "R7", "R8", "R13")[n], R1206, x, y, (a1 + a2) / 2 + 90, "22R 1206", "C17958", "UNI-ROYAL 1206W4F220JT5E",
                        {"1": "VBUS", "2": f"LED{s}1"}))

    # ------------------------------------------------------------ up-facing LED in the middle (bounces off the ceiling)
    b.add(Component("D9", LED5, C - 1.27, 37.0, 0, *IRLED, {"2": "LEDU2", "1": "DRAIN"}, tht=True))
    b.add(Component("R11", R1206, 29.0, 41.6, 90, "22R 1206", "C17958", "UNI-ROYAL 1206W4F220JT5E", {"1": "VBUS", "2": "LEDU1"}))
    b.add(Component("R12", R1206, 32.0, 42.6, 90, "22R 1206", "C17958", "UNI-ROYAL 1206W4F220JT5E", {"1": "LEDU1", "2": "LEDU2"}))

    # ------------------------------------------------------------ LED driver: AO3400A low-side switch for all strings
    b.add(Component("Q1", SOT23, 42.0, 41.0, 0, "AO3400A", "C20917", "AO3400A", {"1": "GATE", "2": "GND", "3": "DRAIN"}))
    b.add(Component("R4", R0603, 39.0, 36.6, 90, "100R", "C22775", "0603WAF1000T5E", {"1": "IR_TX", "2": "GATE"}))
    b.add(Component("R5", R0603, 38.6, 44.0, 90, "10k", "C25804", "0603WAF1002T5E", {"1": "GATE", "2": "GND"}))
    b.add(Component("C7", C0805, 46.6, 37.0, 90, "22uF", "C45783", "CL21A226MAQNNNE", {"1": "VBUS", "2": "GND"}))
    b.add(Component("C9", C0805, 23.6, 37.0, 90, "22uF", "C45783", "CL21A226MAQNNNE", {"1": "VBUS", "2": "GND"}))

    # ------------------------------------------------------------ USB-C (power + native USB for flashing), bottom edge
    UX, UY = C, H - 3.2
    usb_nets = {"A1": "GND", "B12": "GND", "B1": "GND", "A12": "GND", "S1": "GND",
                "A4": "VBUS", "B9": "VBUS", "B4": "VBUS", "A9": "VBUS",
                "A5": "CC1", "B5": "CC2", "A6": "USB_DP", "B6": "USB_DP", "A7": "USB_DM", "B7": "USB_DM",
                "A8": "NC", "B8": "NC"}
    j1 = b.add(Component("J1", USB, UX, UY, 0, "TYPE-C-31-M-12", "C165948", "HRO TYPE-C-31-M-12", usb_nets))
    j1.cpl_center = (UX, UY)
    b.via_block.append(box(UX - 4.6, UY - 3.4, UX + 4.6, H))
    b.add(Component("R1", R0603, UX - 3.2, UY - 8.6, 180, "5.1k", "C23186", "0603WAF5101T5E", {"1": "CC1", "2": "GND"}))
    b.add(Component("R2", R0603, UX + 3.2, UY - 8.6, 180, "5.1k", "C23186", "0603WAF5101T5E", {"1": "CC2", "2": "GND"}))

    # ------------------------------------------------------------ 3.3 V regulator (pins towards the USB connector)
    b.add(Component("U2", SOT223, C, 51.6, 90, "AMS1117-3.3", "C6186", "AMS1117-3.3",
                    {"1": "GND", "2": "3V3", "3": "VBUS"}))
    b.add(Component("C1", C0805, C + 5.8, 51.0, 90, "10uF", "C15850", "CL21A106KAYNNNE", {"1": "VBUS", "2": "GND"}))
    b.add(Component("C2", C0805, C - 6.6, 50.0, 90, "22uF", "C45783", "CL21A226MAQNNNE", {"1": "3V3", "2": "GND"}))
    # module decoupling next to the 3V3 pin, EN reset RC
    b.add(Component("C4", C0603, MX - 11.4, MY - 8.2, 180, "100nF", "C14663", "CC0603KRX7R9BB104", {"1": "3V3", "2": "GND"}))
    b.add(Component("R3", R0603, MX - 10.9, MY - 5.7, 0, "10k", "C25804", "0603WAF1002T5E", {"1": "3V3", "2": "EN"}))
    b.add(Component("C5", C0603, MX - 10.9, MY - 4.0, 180, "1uF", "C15849", "CL10A105KB8NNNC", {"1": "EN", "2": "GND"}))
    b.add(Component("C3", C0805, MX - 13.4, MY + 11.8, 0, "22uF", "C45783", "CL21A226MAQNNNE", {"1": "3V3", "2": "GND"}))

    # ------------------------------------------------------------ IR receiver at the left rim, dome facing outward
    ra = 184.0
    b.add(Component("U3", IRRX, 5.0, C + 2.0 - 2.54, 270, "TSOP38238", "C141632", "Vishay TSOP38238",
                    {"1": "IR_RX", "2": "GND", "3": "RX_VCC"}, tht=True))
    b.add(Component("R10", R0603, 16.4, 36.4, 90, "100R", "C22775", "0603WAF1000T5E", {"1": "3V3", "2": "RX_VCC"}))
    b.add(Component("C6", C0603, 9.4, 40.6, 90, "100nF", "C14663", "CC0603KRX7R9BB104", {"1": "RX_VCC", "2": "GND"}))
    b.add(Component("C8", C0805, 13.4, 37.4, 90, "10uF", "C15850", "CL21A106KAYNNNE", {"1": "RX_VCC", "2": "GND"}))

    # ------------------------------------------------------------ status LED (visible from above, next to the up LED)
    b.add(Component("R9", R0603, 43.0, 31.2, 0, "1k", "C21190", "0603WAF1001T5E", {"1": "LED_STAT", "2": "STAT_A"}))
    b.add(Component("D10", LED0603, 39.6, 31.2, 180, "Green", "C125098", "LTST-C191KGKT", {"2": "STAT_A", "1": "GND"}))

    # ------------------------------------------------------------ test pads: BOOT (GPIO0) + GND, for recovery flashing
    from pcbgen import Pad
    tp = Footprint.__new__(Footprint)
    tp.name, tp.silk, tp.crt = "TestPoint_Pad_D1.5mm", [], []
    tp.pads = [Pad("1", "smd", "circle", 0, 0, 0, 1.5, 1.5, None, ["F.Cu", "F.Mask"])]
    b.add(Component("TP1", tp, MX + 12.0, MY + 12.6, 0, "BOOT", "", "", {"1": "BOOT"}))
    b.add(Component("TP2", tp, MX + 14.8, MY + 12.6, 0, "GND", "", "", {"1": "GND"}))

    # ------------------------------------------------------------ mounting holes (M2), in the gaps between rim LEDs
    mh = Footprint.__new__(Footprint)
    mh.name, mh.silk, mh.crt = "MountingHole_2.2mm_M2", [], []
    mh.pads = [Pad("", "np_thru_hole", "circle", 0, 0, 0, 2.2, 2.2, (2.2, 2.2), ["*.Cu", "*.Mask"])]
    for k, (s, i1, i2) in enumerate(STRINGS):
        a1, a2 = RIM[i1], RIM[i2] if RIM[i2] > RIM[i1] else RIM[i2] + 360
        x, y = polar(29.6, (a1 + a2) / 2)
        c = b.add(Component(f"H{k + 1}", mh, x, y, 0, "M2", "", "", {}))
        c.dnp = True
        b.keepout["top"].append(Point(x, y).buffer(2.2))
        b.keepout["bot"].append(Point(x, y).buffer(2.2))
    add_silk(b)
    return b


def add_silk(b):
    """Reference labels (auto-placed so they never touch pads, each other or the edge) + function labels."""
    from fabout import text_polys
    SZ = 1.35  # ~1.0 mm cap height, ~0.2 mm stroke (bold)
    pads = unary_union([p.shape.buffer(0.25) for p in b.pads()])
    inner = b.outline.buffer(-0.5)
    hidden = [c.courtyard() for c in b.comps if c.ref in ("U1", "J1")]  # under bodies: not visible
    taken = []
    tp1 = next(c for c in b.comps if c.ref == "TP1")
    u3 = next(c for c in b.comps if c.ref == "U3")
    j1 = next(c for c in b.comps if c.ref == "J1")
    fixed = [  # (text, candidate positions) – first one that fits wins
        ("BOOT", [(tp1.x, tp1.y - 1.7), (tp1.x - 1.0, tp1.y + 1.7)]),
        ("GND", [(tp1.x + 3.2, tp1.y + 1.7), (tp1.x + 4.6, tp1.y), (tp1.x + 2.8, tp1.y - 1.7)]),
        ("STATUS", [(39.6, 29.4), (39.6, 33.0)]),
        ("LEARN", [(u3.x + 1.0, u3.y - 3.0), (u3.x + 5.0, u3.y - 3.0), (u3.x + 3.6, u3.y + 7.6), (8.6, 44.0)]),
        ("USB-C 5V", [(j1.x, j1.y - 10.8), (j1.x, j1.y - 6.4)]),
        ("UP", [(C, 33.4), (C + 4.0, 37.0)]),
    ]

    def ok(g):
        return (g.within(inner) and not g.intersects(pads) and not any(g.intersects(t) for t in taken)
                and not any(g.intersects(h) for h in hidden))

    for (txt, cands) in fixed:
        for (x, y) in cands:
            g = text_polys(txt, x, y, SZ)
            if ok(g):
                taken.append(g.buffer(0.15))
                b.silk_text.append((txt, x, y, SZ, 0))
                break
        else:
            print("WARN: label does not fit:", txt)
    for c in b.comps:
        if c.ref[0] == "H" or c.ref.startswith("TP") or c.ref in ("U1", "J1"):
            continue
        x0, y0, x1, y1 = c.courtyard().bounds
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        cand = []
        if c.fp.name.startswith("LED_D5.0mm_Horizontal"):  # rim LED: label just inboard of its pads
            rp = R - LED_TIP_INSET - LED_TIP
            cand = [polar(rp - d, c.rot - 90.0) for d in (2.4, 3.0, 3.6)]
            cand += [polar(rp + 4.0, c.rot - 90.0 + da) for da in (-11.0, 11.0, -13.0, 13.0)]
        cand += [(cx, y0 - 0.7), (cx, y1 + 0.7), (x0 - 1.4, cy), (x1 + 1.4, cy),
                (x0 - 1.4, y0 - 0.5), (x1 + 1.4, y0 - 0.5), (x0 - 1.4, y1 + 0.5), (x1 + 1.4, y1 + 0.5)]
        for (x, y) in cand:
            g = text_polys(c.ref, x, y, SZ)
            if ok(g):
                taken.append(g.buffer(0.15))
                b.silk_text.append((c.ref, x, y, SZ, 0))
                break
        else:
            print("note: no room for label", c.ref)
    b.silk_text_bot = [
        ("Shimushili IR", C, 36.0, 2.6, 0),
        ("v0.2  2026-10", C, 40.0, 1.6, 0),
        ("shimushili.com", C, 43.0, 1.6, 0),
    ]


def route(b):
    # GND pads get vias to the bottom plane (stitching) – done after routing.
    order = [
        ("USB_DP", W_SIG), ("USB_DM", W_SIG), ("CC1", W_SIG), ("CC2", W_SIG), ("EN", W_SIG), ("IR_RX", W_SIG),
        ("BOOT", W_SIG), ("LED_STAT", W_SIG), ("STAT_A", W_SIG), ("IR_TX", W_SIG), ("GATE", W_SIG),
        ("VBUS", W_PWR), ("3V3", W_PWR), ("RX_VCC", W_SIG),
        ("DRAIN", W_LED), ("LEDU1", W_LED), ("LEDU2", W_LED),
        ("LEDA1", W_LED), ("LEDA2", W_LED), ("LEDB1", W_LED), ("LEDB2", W_LED),
        ("LEDC1", W_LED), ("LEDC2", W_LED), ("LEDD1", W_LED), ("LEDD2", W_LED),
    ]
    # USB-C fan-out by hand (0.5 mm pitch, B7 A6 A7 B6 interleaved): join D+ behind the pads and
    # D- in front of the pads, so no vias are needed between the fine-pitch pads.
    J = {p.pad.name: p for p in next(c for c in b.comps if c.ref == "J1").pads}
    U = {p.pad.name: p for p in next(c for c in b.comps if c.ref == "U1").pads}
    back = J["A6"].cy - 0.725 - 0.48
    front = J["A6"].cy + 0.725 + 0.47
    b.tracks.append(("USB_DP", "top", [(J["A6"].cx, J["A6"].cy), (J["A6"].cx, back), (J["B6"].cx, back), (J["B6"].cx, J["B6"].cy)], 0.15))
    b.tracks.append(("USB_DM", "top", [(J["B7"].cx, J["B7"].cy), (J["B7"].cx, front), (J["A7"].cx, front), (J["A7"].cx, J["A7"].cy)], 0.15))
    # VBUS: both VBUS pad pairs drop straight back to a via and are joined on the bottom layer
    vy = J["A4"].cy - 0.725 - 0.75
    for nm in ("A4", "B4"):
        b.tracks.append(("VBUS", "top", [(J[nm].cx, J[nm].cy), (J[nm].cx, vy)], 0.5))
        b.vias.append(("VBUS", J[nm].cx, vy))
    b.tracks.append(("VBUS", "bot", [(J["A4"].cx, vy), (J["B4"].cx, vy)], 0.6))
    # GND vias placed before routing for decoupling caps in the crowded corner next to the module,
    # so no trace can wall their ground pad off from the plane
    P = {p.label: p for p in b.pads()}
    for lab, dx, dy in (("C5.2", -1.1, 0.0),):
        p = P[lab]
        b.tracks.append(("GND", "top", [(p.cx, p.cy), (p.cx + dx, p.cy + dy)], 0.3))
        b.vias.append(("GND", p.cx + dx, p.cy + dy))
    for net, w in order:
        print("routing", net, flush=True)
        if net == "USB_DP":
            b.route(net, w, pads=[J["A6"], U["14"]])
        elif net == "USB_DM":
            b.route(net, w, pads=[J["B7"], U["13"]])
        elif net == "VBUS":
            others = [p for p in b.pads() if p.net == "VBUS" and p.comp.ref != "J1"]
            b.route(net, w, pads=[J["A4"]] + others)
        else:
            b.route(net, w)


def stitch_gnd(b):
    """A via next to every SMD GND pad so it reaches the bottom plane, plus a grid of stitching vias."""
    from shapely.geometry import Point
    clr = b.r["clearance"]
    vr = b.r["via_d"] / 2

    pad_shapes = [pp.shape for pp in b.pads()]

    def free_spot(x, y):
        p = Point(x, y)
        if any(p.buffer(vr).intersects(v) for v in b.via_block):
            return False
        if any(sh.distance(p) < vr + 0.2 for sh in pad_shapes):
            return False
        if not p.within(b.outline.buffer(-(b.r["pour_edge"] + vr + 0.1))):
            return False
        for ly in ("top", "bot"):
            for k in b.keepout[ly]:
                if p.buffer(vr).intersects(k):
                    return False
            for n, g in b.copper(ly, include_pour=False):
                if n != "GND" and g.distance(p) < vr + b.r["pour_clear"] + 0.05:
                    return False
        for (hx, hy, hd, _, _) in b.holes():
            if math.hypot(hx - x, hy - y) < hd / 2 + vr + b.r["hole_to_hole"] + 0.1:
                return False
        return True

    unplaced = []
    others = unary_union([g for n, g in b.copper("top", include_pour=False) if n != "GND"])
    for p in b.pads():
        if p.net != "GND" or p.tht or p.npth:
            continue
        placed = False
        # a via next to the pad, joined by a short track (the pour alone may not reach a tight spot)
        for rad in (0.0, 0.9, 1.2, 1.5, 1.9, 2.2, 2.6, 3.0, 3.5):
            for ang in range(0, 360, 15):
                x = p.cx + rad * math.cos(math.radians(ang))
                y = p.cy + rad * math.sin(math.radians(ang))
                if rad == 0.0 and p.shape.area < 1.5:
                    continue
                if not free_spot(x, y):
                    continue
                if rad > 0:
                    tr = b.track_shape([(p.cx, p.cy), (x, y)], 0.3)
                    if tr.distance(others) < clr + 0.02:
                        continue
                    b.tracks.append(("GND", "top", [(p.cx, p.cy), (x, y)], 0.3))
                b.vias.append(("GND", x, y))
                placed = True
                break
            if placed:
                break
        if not placed:
            unplaced.append(p)
    # still nothing: let the router find a way from the pad to the nearest GND via
    for p in unplaced:
        near = sorted((pp for pp in b.pads() if pp.net == "GND" and pp is not p and pp not in unplaced and not pp.npth),
                      key=lambda pp: math.hypot(pp.cx - p.cx, pp.cy - p.cy))
        for anchor in near[:4]:
            try:
                b.route("GND", 0.25, pads=[anchor, p])
                break
            except RuntimeError:
                continue
        else:
            print("WARN: no stitching via for", p.label)
    # grid stitching
    y = 2.0
    while y < H:
        x = 2.0
        while x < W:
            if free_spot(x, y):
                b.vias.append(("GND", x, y))
            x += 5.0
        y += 5.0


if __name__ == "__main__":
    b = build()
    route(b)
    stitch_gnd(b)
    b.make_pours("GND")
    import pickle
    pickle.dump(b, open(os.path.join(HERE, "board.pkl"), "wb"))
    probs = b.drc()
    con = b.connectivity()
    split = {n: g for n, g in con.items() if len(g) != 1}
    print("DRC problems:", len(probs), "| split nets:", split)
    if probs or split:
        sys.exit(1)
    import fabout
    out = os.path.join(HERE, "..", "output")
    files = fabout.write_all(b, out, "shimushili-ir", H)
    bom, cpl = fabout.write_bom_cpl(b, out, "shimushili-ir", H)
    fabout.zip_gerbers(files, os.path.join(out, "shimushili-ir-gerbers.zip"))
    # parts that are fitted by hand after assembly (rim LEDs lie flat, leads bent 90 deg)
    with open(os.path.join(out, "shimushili-ir-hand-fit.csv"), "w", newline="") as f:
        import csv as _csv
        w = _csv.writer(f)
        w.writerow(["Designator", "Part", "LCSC", "Qty per board", "How"])
        hand = [c for c in b.comps if getattr(c, "hand", False)]
        w.writerow([",".join(c.ref for c in hand), hand[0].mpn, hand[0].lcsc, len(hand),
                    "Bend both leads 90 deg at 3.8 mm from the body, lens pointing outward, tip at the board edge; "
                    "square pad = cathode (short lead)"])
    # netlist for review
    import csv
    with open(os.path.join(out, "shimushili-ir-netlist.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Ref", "Value", "Pad", "Net"])
        for c in b.comps:
            for p in c.pads:
                if p.pad.name:
                    w.writerow([c.ref, c.value, p.pad.name, p.net])
    import render
    render.render(b, os.path.join(out, "preview-top.png"), "top")
    render.render(b, os.path.join(out, "preview-bottom.png"), "bot")
    print("outputs in", os.path.abspath(out))
