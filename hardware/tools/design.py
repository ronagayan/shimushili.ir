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


W, H = 56.0, 48.0
RULES = dict(
    grid=0.1, grid_margin=0.03,
    clearance=0.15,      # JLCPCB 2-layer min 0.127
    edge_clear=0.4,
    pour_clear=0.3, pour_edge=0.6,
    via_d=0.6, via_drill=0.3,
    hole_to_hole=0.3, npth_clear=0.3,
    gnd="GND",
)
W_SIG, W_PWR, W_LED = 0.2, 0.5, 0.4


def rounded_rect(w, h, r):
    return box(r, r, w - r, h - r).buffer(r, 16)


def build():
    b = Board(rounded_rect(W, H, 3.0), RULES)
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
    IRRX = fp("Vishay_MOLD-3Pin")

    # ------------------------------------------------------------ module
    MX, MY = 28.0, 15.75  # antenna end flush with the top edge (y=0)
    wroom_nets = {str(i): "NC" for i in range(1, 42)}
    wroom_nets.update({"1": "GND", "2": "3V3", "3": "EN", "5": "IR_RX", "13": "USB_DM", "14": "USB_DP",
                       "20": "IR_TX", "27": "BOOT", "39": "LED_STAT", "40": "GND", "41": "GND"})
    u1 = b.add(Component("U1", WROOM, MX, MY, 0, "ESP32-S3-WROOM-1-N16R8", "C2913202", "ESP32-S3-WROOM-1-N16R8", wroom_nets))
    u1.cpl_center = (MX, MY - 3.0)  # module body centre (18 x 25.5 mm)
    # antenna keepout (module zone + 2 mm each side), both layers
    ant = box(MX - 9 - 5, -1, MX + 9 + 5, MY - 9.8 + 0.2)  # module antenna + 5 mm each side
    b.keepout["top"].append(ant)
    b.keepout["bot"].append(ant)
    # keep the ground plane under the module intact: no routing on the bottom under it,
    # and no top routing under the module body
    under = box(MX - 8.0, MY - 9.8, MX + 8.0, MY + 8.9)
    b.route_block["bot"].append(box(MX - 9.0, MY - 9.8, MX + 9.0, MY + 9.75))
    b.route_block["top"].append(under)

    # ------------------------------------------------------------ USB-C (power + native USB for flashing)
    UX, UY = 22.0, H - 3.2
    usb_nets = {"A1": "GND", "B12": "GND", "B1": "GND", "A12": "GND", "S1": "GND",
                "A4": "VBUS", "B9": "VBUS", "B4": "VBUS", "A9": "VBUS",
                "A5": "CC1", "B5": "CC2", "A6": "USB_DP", "B6": "USB_DP", "A7": "USB_DM", "B7": "USB_DM",
                "A8": "NC", "B8": "NC"}
    j1 = b.add(Component("J1", USB, UX, UY, 0, "TYPE-C-31-M-12", "C165948", "HRO TYPE-C-31-M-12", usb_nets))
    j1.cpl_center = (UX, UY)
    b.via_block.append(box(UX - 4.6, UY - 3.4, UX + 4.6, H))  # no vias under the connector shell
    b.add(Component("R1", R0603, 15.6, 38.6, 90, "5.1k", "C23186", "0603WAF5101T5E", {"1": "CC1", "2": "GND"}))
    b.add(Component("R2", R0603, 28.4, 38.6, 90, "5.1k", "C23186", "0603WAF5101T5E", {"1": "CC2", "2": "GND"}))

    # ------------------------------------------------------------ 3.3 V regulator
    b.add(Component("U2", SOT223, 9.0, 31.5, 0, "AMS1117-3.3", "C6186", "AMS1117-3.3",
                    {"1": "GND", "2": "3V3", "3": "VBUS"}))
    b.add(Component("C1", C0805, 5.6, 37.6, 0, "10uF", "C15850", "CL21A106KAYNNNE", {"1": "VBUS", "2": "GND"}))
    b.add(Component("C2", C0805, 12.4, 36.4, 0, "22uF", "C45783", "CL21A226MAQNNNE", {"1": "3V3", "2": "GND"}))
    # module decoupling right at the 3V3 pin
    b.add(Component("C3", C0805, 12.2, 8.6, 90, "22uF", "C45783", "CL21A226MAQNNNE", {"1": "3V3", "2": "GND"}))
    b.add(Component("C4", C0603, 15.4, 7.0, 0, "100nF", "C14663", "CC0603KRX7R9BB104", {"1": "3V3", "2": "GND"}))
    # EN reset RC
    b.add(Component("R3", R0603, 13.2, 11.9, 0, "10k", "C25804", "0603WAF1002T5E", {"1": "3V3", "2": "EN"}))
    b.add(Component("C5", C0603, 13.2, 13.6, 180, "1uF", "C15849", "CL10A105KB8NNNC", {"1": "EN", "2": "GND"}))

    # ------------------------------------------------------------ IR receiver (left, facing front)
    # rot 270: the receiver's dome faces the left edge of the board (window in the enclosure side)
    b.add(Component("U3", IRRX, 6.6, 16.6, 270, "IRM-56384", "C72048", "Everlight IRM-56384",
                    {"1": "IR_RX", "2": "GND", "3": "RX_VCC"}, tht=True))
    # supply filter recommended by the IRM-56384 datasheet (100R + bulk cap)
    b.add(Component("R10", R0603, 11.8, 21.6, 90, "100R", "C22775", "0603WAF1000T5E", {"1": "3V3", "2": "RX_VCC"}))
    b.add(Component("C6", C0603, 11.8, 18.0, 90, "100nF", "C14663", "CC0603KRX7R9BB104", {"1": "RX_VCC", "2": "GND"}))
    b.add(Component("C8", C0805, 9.6, 24.6, 0, "10uF", "C15850", "CL21A106KAYNNNE", {"1": "RX_VCC", "2": "GND"}))

    # ------------------------------------------------------------ IR LED driver: AO3400A low-side switch, 3 strings x 2 LEDs
    b.add(Component("Q1", SOT23, 28.0, 31.5, 0, "AO3400A", "C20917", "AO3400A", {"1": "GATE", "2": "GND", "3": "DRAIN"}))
    b.add(Component("R4", R0603, 25.0, 29.5, 90, "100R", "C22775", "0603WAF1000T5E", {"1": "IR_TX", "2": "GATE"}))
    b.add(Component("R5", R0603, 25.0, 33.0, 90, "10k", "C25804", "0603WAF1002T5E", {"1": "GATE", "2": "GND"}))
    cols = [32.0, 39.0, 46.0]
    rows = [32.5, 39.5]
    for k, x in enumerate(cols):
        s = "ABC"[k]
        top, bot = f"D{k + 1}", f"D{k + 4}"
        # pad 1 = cathode (K), pad 2 = anode (A); string: VBUS -> R -> D(top) -> D(bottom) -> DRAIN
        b.add(Component(top, LED5, x, rows[0], 0, "IR333C-A 940nm", "C5130", "Everlight IR333C-A",
                        {"2": f"LED{s}1", "1": f"LED{s}2"}, tht=True))
        b.add(Component(bot, LED5, x, rows[1], 0, "IR333C-A 940nm", "C5130", "Everlight IR333C-A",
                        {"2": f"LED{s}2", "1": "DRAIN"}, tht=True))
        b.add(Component(f"R{6 + k}", R1206, x + 1.27, 27.6, 0, "22R 1206", "C104701", "RALEC RTT06220JTP",
                        {"1": "VBUS", "2": f"LED{s}1"}))
    b.add(Component("C7", C0805, 54.0, 36.0, 90, "22uF", "C45783", "CL21A226MAQNNNE", {"1": "VBUS", "2": "GND"}))

    # ------------------------------------------------------------ status LED (top right, visible through the front)
    b.add(Component("R9", R0603, 41.0, 8.8, 0, "1k", "C21190", "0603WAF1001T5E", {"1": "LED_STAT", "2": "STAT_A"}))
    b.add(Component("D7", LED0603, 44.6, 8.8, 180, "Green", "C125098", "LTST-C191KGKT", {"2": "STAT_A", "1": "GND"}))

    # ------------------------------------------------------------ test pads: BOOT (GPIO0) + GND, for recovery flashing
    tp = Footprint.__new__(Footprint)
    from pcbgen import Pad
    tp.name, tp.silk, tp.crt = "TestPoint_Pad_D1.5mm", [], []
    tp.pads = [Pad("1", "smd", "circle", 0, 0, 0, 1.5, 1.5, None, ["F.Cu", "F.Mask"])]
    b.add(Component("TP1", tp, 40.5, 24.0, 0, "BOOT", "", "", {"1": "BOOT"}))
    b.add(Component("TP2", tp, 43.3, 24.0, 0, "GND", "", "", {"1": "GND"}))

    # ------------------------------------------------------------ mounting holes (M2)
    mh = Footprint.__new__(Footprint)
    mh.name, mh.silk, mh.crt = "MountingHole_2.2mm_M2", [], []
    mh.pads = [Pad("", "np_thru_hole", "circle", 0, 0, 0, 2.2, 2.2, (2.2, 2.2), ["*.Cu", "*.Mask"])]
    for k, (x, y) in enumerate([(3.5, 3.5), (W - 3.5, 3.5), (3.5, H - 3.5), (W - 3.5, H - 3.5)]):
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
    fixed = [
        ("BOOT", 40.5, 22.3), ("GND", 46.6, 24.0), ("STATUS", 44.6, 11.0),
        ("IR LEDs 940nm", 39.0, 46.2), ("USB-C 5V", 22.0, 38.6),
    ]

    def ok(g):
        return (g.within(inner) and not g.intersects(pads) and not any(g.intersects(t) for t in taken)
                and not any(g.intersects(h) for h in hidden))

    for (txt, x, y) in fixed:
        g = text_polys(txt, x, y, SZ)
        if ok(g):
            taken.append(g.buffer(0.15))
            b.silk_text.append((txt, x, y, SZ, 0))
        else:
            print("WARN: label does not fit:", txt)
    for c in b.comps:
        if c.ref[0] == "H" or c.ref.startswith("TP") or c.ref in ("U1", "J1"):
            continue
        x0, y0, x1, y1 = c.courtyard().bounds
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        cand = [(cx, y0 - 0.7), (cx, y1 + 0.7), (x0 - 1.4, cy), (x1 + 1.4, cy),
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
        ("Shimushili IR", 15.0, 26.0, 2.2, 0),
        ("v0.1  2026-10", 15.0, 29.4, 1.5, 0),
        ("shimushili.com", 15.0, 32.2, 1.5, 0),
    ]


def route(b):
    # GND pads get vias to the bottom plane (stitching) – done after routing.
    order = [
        ("USB_DP", W_SIG), ("USB_DM", W_SIG), ("CC1", W_SIG), ("CC2", W_SIG), ("VBUS", W_PWR),
        ("3V3", W_PWR), ("RX_VCC", W_SIG),
        ("EN", W_SIG), ("IR_RX", W_SIG), ("IR_TX", W_SIG), ("GATE", W_SIG),
        ("DRAIN", W_LED), ("LEDA1", W_LED), ("LEDA2", W_LED), ("LEDB1", W_LED), ("LEDB2", W_LED),
        ("LEDC1", W_LED), ("LEDC2", W_LED),
        ("LED_STAT", W_SIG), ("STAT_A", W_SIG), ("BOOT", W_SIG),
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

    for p in b.pads():
        if p.net != "GND" or p.tht or p.npth:
            continue
        placed = False
        for rad in (0.0, 0.9, 1.2, 1.5, 1.9):
            for ang in range(0, 360, 30):
                x = p.cx + rad * math.cos(math.radians(ang))
                y = p.cy + rad * math.sin(math.radians(ang))
                if rad == 0.0 and p.shape.area < 1.5:
                    continue
                if free_spot(x, y):
                    b.vias.append(("GND", x, y))  # top pour joins pad and via
                    placed = True
                    break
            if placed:
                break
        if not placed:
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
