"""System tray icon: shows print progress, menu with live status."""
import json
import sys
import threading
import time

import pystray
from PIL import Image, ImageDraw

from discovery import discover
from monitor import PrinterMonitor, PrinterState

SIZE = 64


def make_icon(state: PrinterState):
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    with state.lock:
        running = state.gcode_state == "RUNNING"
        pct = state.percent
        color = (46, 204, 113) if running else (120, 120, 120)
        if state.gcode_state == "FAILED":
            color = (231, 76, 60)
        elif state.gcode_state == "PAUSE":
            color = (241, 196, 15)
    d.ellipse((2, 2, SIZE - 2, SIZE - 2), fill=(30, 30, 30, 220))
    if running and pct:
        d.arc((6, 6, SIZE - 6, SIZE - 6), start=-90, end=-90 + pct * 3.6,
              fill=color, width=6)
    d.text((SIZE // 2, SIZE // 2), str(pct if running else "P"),
           fill=color, anchor="mm")
    return img


def build_menu(state: PrinterState):
    def st(fn):
        # text callable tolerant of whatever pystray passes it
        return pystray.MenuItem(lambda *a: fn(), None, enabled=False)

    return pystray.Menu(
        st(lambda: f"State: {state.gcode_state.title()}"),
        st(lambda: f"Job: {state.file.split('/')[-1] or '—'}"),
        st(lambda: f"Progress: {state.percent}%  ·  layer {state.layer}/{state.total_layers}"),
        st(lambda: f"ETA: ~{state.remaining_min} min  ·  "
                   f"Nozzle {state.nozzle:.0f}°C  Bed {state.bed:.0f}°C"),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", lambda icon, item: icon.stop()),
    )


def refresh_loop(icon, state):
    last = None
    while True:
        with state.lock:
            cur = (state.percent, state.gcode_state, state.connected)
        if cur != last:
            icon.icon = make_icon(state)
            icon.title = f"Bambu: {state.summary()}"
            last = cur
        time.sleep(2)


def main():
    cfg = json.load(open("config.json"))

    if cfg.get("printer_ip") in (None, "", "auto"):
        print("Discovering printer on LAN…")
        printers = discover()
        if not printers:
            sys.exit("No Bambu printer found on the network.")
        cfg["printer_ip"] = printers[0]["ip"]
        print(f"Found {printers[0]['name']} ({printers[0]['model']}) at {cfg['printer_ip']}")

    if not cfg.get("access_code"):
        sys.exit("Missing access_code in config.json — printer Settings → Network/LAN.")

    state = PrinterState()
    PrinterMonitor(cfg, state).run()

    icon = pystray.Icon("bambu-monitor", make_icon(state), "Bambu Monitor",
                      build_menu(state))
    threading.Thread(target=refresh_loop, args=(icon, state), daemon=True).start()
    icon.run()


if __name__ == "__main__":
    main()
