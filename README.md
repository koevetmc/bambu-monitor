# bambu-monitor

A lightweight Linux system-tray monitor for Bambu Lab 3D printers. Talks to the
printer's local MQTT broker over your LAN — no cloud, no Bambu account needed.

## Features

- Tray icon showing live print progress (color-coded ring: green running,
  yellow paused, red failed)
- Menu with live status: state, filename, layer count, ETA, nozzle/bed temps
- Desktop notifications for print **started / resumed / finished / paused /
  failed**, plus configurable percent milestones
- **Tray controls**: pause / resume / stop (with confirm), speed modes
  (silent → ludicrous), chamber light on/off
- **Phone notifications** via KDE Connect — finished/failed/paused pings
  reach your phone even away from the desk
- **Camera snapshot** attached to finished/failed notifications
  (requires the printer's local camera stream — see note below)
- Auto-discovers the printer on the LAN via SSDP (falls back to a fixed IP)
- Runs as a `systemd --user` service — starts at login

## Requirements

- Python 3.10+
- A desktop environment with an AppIndicator-capable tray
  (GNOME on Ubuntu works out of the box)
- Printer and PC on the same network

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.example.json config.json
```

Edit `config.json`:

- `printer_ip` — `"auto"` for SSDP discovery, or a fixed IP
- `access_code` — 8-digit code from the printer screen
  (Settings → Network/LAN → Access Code) or Bambu Handy → printer → Settings
- `milestones` — progress percentages that trigger a notification
- `notify_phone` — ping paired phones through KDE Connect on
  finished / failed / paused
- `kdeconnect_device` — `"auto"` picks the first reachable device, or set a
  specific device id from `kdeconnect-cli -a`
- `camera_snapshots` — attach a live camera frame to finished/failed
  notifications

## Run

```bash
.venv/bin/python tray.py
```

## Autostart (systemd user service)

```bash
mkdir -p ~/.config/systemd/user
cp bambu-monitor.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now bambu-monitor
```

Optionally copy `bambu-monitor.desktop` to `~/.local/share/applications/`
(and fix the `Exec` path if you cloned somewhere other than `~/bambu-monitor`).

## How it works

Bambu printers run a local MQTT broker on port 8883 (TLS, self-signed).
Auth is user `bblp` + the printer access code. Status reports arrive on
`device/<serial>/report` as JSON — this app subscribes, tracks state
transitions, and fires `notify-send` for events you care about. Commands go
the other way on `device/<serial>/request`.

### Camera snapshot caveat

Some Bambu models/firmware refuse local camera connections while in
cloud-connected mode (the stream is only served in **LAN mode**). If
`camera.py` can't pull a frame, notifications are still sent — just without
an image. Enable LAN mode on the printer to unlock snapshots (note: this
disables Bambu Handy cloud access).

## Files

| File | Purpose |
|---|---|
| `tray.py` | Entry point — tray icon, menu, refresh loop |
| `monitor.py` | MQTT client, state tracking, notification rules, printer commands |
| `camera.py` | Grabs a JPEG frame from the printer camera (port 6000) |
| `kde.py` | Phone push notifications via `kdeconnect-cli` |
| `discovery.py` | SSDP printer discovery (port 2021) |
| `config.example.json` | Config template |
| `bambu-monitor.service` | systemd user unit |
| `bambu-monitor.desktop` | app-menu entry |
