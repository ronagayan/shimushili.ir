#!/usr/bin/env python3
"""Generate tv_codes.h from the Flipper-IRDB TV database (CC0).

Usage: python3 gen_tv_codes.py <path-to-Flipper-IRDB/TVs> > ../tv_codes.h

For each brand it groups the parsed signals by protocol+address ("code set"),
keeps the most common command for each standard key, ranks sets by how many
remotes use them, and writes up to MAX_SETS sets per brand.
"""
import os
import re
import sys
from collections import Counter, defaultdict

KEYS = ["power", "vol_up", "vol_down", "mute", "ch_up", "ch_down", "input",
        "up", "down", "left", "right", "ok", "back", "home"]

# normalized Flipper key name -> (our key, priority: lower wins)
NAME_MAP = {
    "power": ("power", 0), "volup": ("vol_up", 0), "vol+": ("vol_up", 0), "volumeup": ("vol_up", 1),
    "voldn": ("vol_down", 0), "voldown": ("vol_down", 0), "vol-": ("vol_down", 0), "volumedown": ("vol_down", 1),
    "mute": ("mute", 0), "chnext": ("ch_up", 0), "chup": ("ch_up", 0), "ch+": ("ch_up", 0), "channelup": ("ch_up", 1),
    "chprev": ("ch_down", 0), "chdown": ("ch_down", 0), "ch-": ("ch_down", 0), "channeldown": ("ch_down", 1),
    "source": ("input", 0), "input": ("input", 0), "up": ("up", 0), "down": ("down", 0),
    "left": ("left", 0), "right": ("right", 0), "ok": ("ok", 0), "enter": ("ok", 1), "select": ("ok", 1),
    "back": ("back", 0), "return": ("back", 1), "exit": ("back", 2),
    "home": ("home", 0), "smarthub": ("home", 1), "menu": ("home", 2),
}

# (folder, display name, max sets)
BRANDS = [
    ("Samsung", "Samsung", 2), ("LG", "LG", 2), ("TCL", "TCL", 2), ("Hisense", "Hisense", 3),
    ("Xiaomi", "Xiaomi", 1), ("Sony", "Sony", 2), ("Philips", "Philips", 3), ("Toshiba", "Toshiba", 3),
    ("Panasonic", "Panasonic", 0), ("Sharp", "Sharp", 2), ("Haier", "Haier", 1), ("Hitachi", "Hitachi", 2),
    ("JVC", "JVC", 2), ("Grundig", "Grundig", 1), ("Akai", "Akai", 1), ("Telefunken", "Telefunken", 2),
    ("Sanyo", "Sanyo", 2), ("Blaupunkt", "Blaupunkt", 1), ("Thomson", "Thomson", 1), ("Daewoo", "Daewoo", 1),
]

PROTO = {"NEC": 1, "NECext": 2, "Samsung32": 3, "SIRC": 4, "SIRC15": 5, "SIRC20": 6,
         "RC5": 7, "RC5X": 7, "RC6": 8, "RCA": 9}
P_PANA, P_RAW = 10, 11

# Panasonic: Kaseikyo in the DB; use the well-known encodePanasonic(0x4004, 0x01, 0x00, fn) codes.
PANA = {"power": 0xBC, "vol_up": 0x04, "vol_down": 0x84, "mute": 0x4C, "ch_up": 0x2C,
        "ch_down": 0xAC, "input": 0xA0}


def norm(name):
    return re.sub(r"[^a-z0-9+\-]", "", name.lower().replace("_", ""))


def parse_file(path):
    blocks, cur = [], {}
    for line in open(path, encoding="utf-8", errors="ignore"):
        line = line.strip()
        if line.startswith("#") or not line:
            if cur:
                blocks.append(cur)
                cur = {}
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            cur[k.strip()] = v.strip()
    if cur:
        blocks.append(cur)
    return [b for b in blocks if "name" in b]


def b(hexstr, i):
    return int(hexstr.split()[i], 16)


def addr_cmd(sig):
    p, a, c = sig["protocol"], sig["address"], sig["command"]
    if p in ("NECext",):
        return b(a, 0) | b(a, 1) << 8, b(c, 0) | b(c, 1) << 8
    if p == "SIRC20":
        return b(a, 0) | b(a, 1) << 8, b(c, 0)
    return b(a, 0), b(c, 0)


def main(root):
    out_sets, raw_blobs, brand_names = [], [], []
    for bi, (folder, disp, max_sets) in enumerate(BRANDS):
        brand_names.append(disp)
        if folder == "Panasonic":
            out_sets.append((bi, P_PANA, 0x0100, {k: PANA.get(k) for k in KEYS}, 1))
            continue
        d = os.path.join(root, folder)
        files = [os.path.join(dp, f) for dp, _, fs in os.walk(d) for f in fs if f.endswith(".ir")]
        if folder == "Xiaomi":  # raw-only remote
            sigs = parse_file(files[0])
            keys = {}
            for s in sigs:
                n = norm(s["name"])
                k = "power" if n == "open" else NAME_MAP.get(n, (None,))[0]
                if k and k not in keys and s.get("type") == "raw":
                    data = [int(x) for x in s["data"].split()]
                    # keep the first frame only (split at the first long gap)
                    for i, v in enumerate(data):
                        if i % 2 == 1 and v > 5000:
                            data = data[:i]
                            break
                    keys[k] = len(raw_blobs)
                    raw_blobs.append(data)
            out_sets.append((bi, P_RAW, 0, keys, 1))
            continue
        groups = defaultdict(lambda: {"files": set(), "cmds": defaultdict(Counter)})
        for f in files:
            for s in parse_file(f):
                if s.get("type") != "parsed" or s.get("protocol") not in PROTO:
                    continue
                m = NAME_MAP.get(norm(s["name"]))
                if not m:
                    continue
                key, prio = m
                a, c = addr_cmd(s)
                g = groups[(PROTO[s["protocol"]], a)]
                g["files"].add(f)
                g["cmds"][key][(prio, c)] += 1
        ranked = []
        for (p, a), g in groups.items():
            cmds = {}
            for k, cnt in g["cmds"].items():
                best_prio = min(pr for pr, _ in cnt)
                cmds[k] = Counter({c: n for (pr, c), n in cnt.items() if pr == best_prio}).most_common(1)[0][0]
            if "power" not in cmds:
                continue
            ranked.append((len(g["files"]), len(cmds), p, a, cmds))
        ranked.sort(key=lambda r: (-r[0], -r[1]))
        for files_n, _, p, a, cmds in ranked[:max_sets]:
            out_sets.append((bi, p, a, cmds, files_n))

    w = sys.stdout.write
    w("// Generated by tools/gen_tv_codes.py from Flipper-IRDB (CC0). Do not edit by hand.\n#pragma once\n\n")
    w("#define TV_NKEYS %d\n" % len(KEYS))
    w("static const char *const TV_KEYS[TV_NKEYS] = {%s};\n" % ", ".join('"%s"' % k for k in KEYS))
    w("enum : uint8_t { P_NEC = 1, P_NECX, P_SAMSUNG, P_SIRC12, P_SIRC15, P_SIRC20, P_RC5, P_RC6, P_RCA, P_PANA, P_RAW };\n")
    w("static const char *const TV_BRAND_NAMES[] = {%s};\n" % ", ".join('"%s"' % n for n in brand_names))
    w("#define TV_NBRANDS %d\n\n" % len(brand_names))
    w("struct TvSet { uint8_t brand; uint8_t proto; uint16_t addr; uint16_t cmd[TV_NKEYS]; };  // 0xFFFF = none\n")
    for i, blob in enumerate(raw_blobs):
        w("static const uint16_t TV_RAW_%d[] PROGMEM = {%s};\n" % (i, ",".join(map(str, blob))))
    w("static const uint16_t *const TV_RAW[] = {%s};\n" % ", ".join("TV_RAW_%d" % i for i in range(len(raw_blobs))))
    w("static const uint16_t TV_RAW_LEN[] = {%s};\n\n" % ", ".join(str(len(x)) for x in raw_blobs))
    w("static const TvSet TV_SETS[] PROGMEM = {\n")
    for bi, p, a, cmds, n in out_sets:
        vals = ", ".join("0x%X" % cmds[k] if cmds.get(k) is not None else "0xFFFF" for k in KEYS)
        w("  {%d, %d, 0x%X, {%s}},  // %s (%d remotes)\n" % (bi, p, a, vals, brand_names[bi], n))
    w("};\n#define TV_NSETS (sizeof(TV_SETS) / sizeof(TV_SETS[0]))\n")


if __name__ == "__main__":
    main(sys.argv[1])
