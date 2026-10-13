#!/usr/bin/env python3
"""Build data/ac_models.json (searchable AC model list) from IRremoteESP8266's SupportedProtocols.md.

Usage: python3 tools/gen_ac_models.py <IRremoteESP8266>/SupportedProtocols.md
Writes data/ac_models.json and android/app/src/main/assets/ac_models.json
"""
import json, os, re, sys

FILE_PROTO = {
    "Airton": "AIRTON", "Airwell": "AIRWELL", "Amcor": "AMCOR", "Argo": "ARGO", "Bosch": "BOSCH144",
    "Carrier": "CARRIER_AC64", "Coolix": "COOLIX", "Corona": "CORONA_AC", "Daikin": "DAIKIN",
    "Delonghi": "DELONGHI_AC", "Ecoclim": "ECOCLIM", "Electra": "ELECTRA_AC", "Eurom": "EUROM",
    "Fujitsu": "FUJITSU_AC", "Goodweather": "GOODWEATHER", "Gree": "GREE", "Haier": "HAIER_AC",
    "Hitachi": "HITACHI_AC", "Kelon": "KELON", "Kelvinator": "KELVINATOR", "LG": "LG", "Midea": "MIDEA",
    "Mirage": "MIRAGE", "Mitsubishi": "MITSUBISHI_AC", "MitsubishiHeavy": "MITSUBISHI_HEAVY_152",
    "Neoclima": "NEOCLIMA", "Panasonic": "PANASONIC_AC", "Rhoss": "RHOSS", "Samsung": "SAMSUNG_AC",
    "Sanyo": "SANYO_AC", "Sharp": "SHARP_AC", "Tcl": "TCL112AC", "Technibel": "TECHNIBEL_AC", "Teco": "TECO",
    "Toshiba": "TOSHIBA_AC", "Transcold": "TRANSCOLD", "Trotec": "TROTEC", "Truma": "TRUMA",
    "Vestel": "VESTEL_AC", "Voltas": "VOLTAS", "Whirlpool": "WHIRLPOOL_AC", "York": "YORK",
}
# Israeli brands with no entries upstream: suggestions to test, in order.
ISRAEL = [
    {"brand": "Tadiran / תדיראן", "model": "", "protos": ["KELON168", "ELECTRA_AC", "GREE"], "guess": True},
    {"brand": "Electra / אלקטרה", "model": "", "protos": ["KELON168", "ELECTRA_AC"], "guess": True},
    {"brand": "Tornado / טורנדו", "model": "", "protos": ["KELON168", "GREE", "MIDEA"], "guess": True},
    {"brand": "Crown / קראון", "model": "", "protos": ["MIDEA", "COOLIX", "GREE"], "guess": True},
    {"brand": "Elco / אלקו", "model": "", "protos": ["KELON168", "ELECTRA_AC"], "guess": True},
]


def main(md):
    out = list(ISRAEL)
    hint_re = re.compile(r"\(([A-Z0-9_]+)\)")
    for line in open(md, encoding="utf-8"):
        if not line.startswith("| ["):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        f = re.match(r"\[([^\]]+)\]", cells[0]).group(1)
        if f not in FILE_PROTO:
            continue
        brand = re.sub(r"\*\*\[([^\]]+)\].*", r"\1", cells[1])
        enums = [e.strip() for e in cells[3].split("<BR>") if e.strip()]
        for item in cells[2].split("<BR>"):
            item = item.strip()
            if not item:
                continue
            proto, model = FILE_PROTO[f], None
            for h in hint_re.findall(item):
                if h in enums: model = h
                elif re.fullmatch(r"[A-Z][A-Z0-9_]+", h) and not h.isdigit(): proto = h
            kind = "remote" if "remote" in item.lower() else "ac"
            text = hint_re.sub("", item).replace("remote", "").replace("A/C", "").strip(" ,")
            e = {"brand": brand, "model": text, "kind": kind, "protos": [proto]}
            if model: e["m"] = model
            out.append(e)
    js = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    for p in ("data/ac_models.json", "android/app/src/main/assets/ac_models.json"):
        path = os.path.join(root, p)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w", encoding="utf-8").write(js)
    print(len(out), "entries,", len(js), "bytes")


if __name__ == "__main__":
    main(sys.argv[1])
