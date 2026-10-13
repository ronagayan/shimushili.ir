# IRBlaster – ESP32 IR remote (AC + TV)

Firmware for an ESP32 IR transmitter/receiver board, with a Hebrew web UI.

## Install / update
- **Quick:** upload `IRBlaster.bin` from the device's Settings → firmware update page (`/update` or `/u`).
- **From source:** open `IRBlaster.ino` in Arduino IDE (ESP32 core 3.x), board "ESP32 Dev Module",
  partition "Default 4MB with spiffs". No extra libraries needed – IRremoteESP8266 is vendored in `src/`.
  To make a .bin for web upload: Sketch → Export Compiled Binary.

## Layout
| Path | What |
|---|---|
| `IRBlaster.ino` | firmware |
| `web/` | UI pages (`index.html`, `portal.html`, `update.html`, `icon.png`) |
| `web_assets.h` | gzipped copy of `web/` – regenerate with `python3 tools/build_web.py` |
| `tv_codes.h` | TV code sets – regenerate with `python3 tools/gen_tv_codes.py <Flipper-IRDB>/TVs > tv_codes.h` |
| `src/IRremoteESP8266/` | IRremoteESP8266 v2.9.0 (LGPL-2.1), only the needed protocols enabled |
| `tools/config_ir_lib.py` | chooses which IR protocols are compiled (saves ~60KB) |

## HTTP API (all need the device key: header `X-Key` or `?k=`)
- `/api/ac?power=on|off|toggle&mode=cool|heat|auto|dry|fan&temp=24|up|down&fan=auto|low|medium|high&swing=on|off`
- `/api/tv?key=power|vol_up|vol_down|mute|ch_up|ch_down|input|up|down|left|right|ok|back|home`
- `/api/custom?id=N`, `/api/state`, `/export/android.json` (HTTP Shortcuts import)

## Security model
- Per-device random key on every API call → other web pages can't send commands (CSRF).
- Host header must be the device IP / `irblaster.local` → blocks DNS rebinding.
- Optional admin password (Basic auth, user `admin`) for firmware update, pins, WiFi reset.
- Firmware update is refused while the open `IR_WIFI` setup network is active.
- Not covered: plain HTTP on the LAN (no TLS), WiFi password stored unencrypted in flash.

TV codes: [Flipper-IRDB](https://github.com/Lucaslhm/Flipper-IRDB) (CC0).
