"""Core monitor: connects to the printer's local MQTT and fires notifications."""
import json
import ssl
import subprocess
import threading
import time
from dataclasses import dataclass, field

import paho.mqtt.client as mqtt

import camera
import kde

MQTT_PORT = 8883
USER = "bblp"
SNAP_PATH = "/tmp/bambu-frame.jpg"


@dataclass
class PrinterState:
    connected: bool = False
    serial: str = ""
    gcode_state: str = "OFFLINE"
    percent: int = 0
    layer: int = 0
    total_layers: int = 0
    remaining_min: int = 0
    file: str = ""
    nozzle: float = 0.0
    bed: float = 0.0
    start_time: float = 0.0
    fired_milestones: set = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def summary(self):
        with self.lock:
            if self.gcode_state == "RUNNING":
                return (f"{self.percent}% · layer {self.layer}/{self.total_layers} · "
                        f"~{self.remaining_min} min left")
            return self.gcode_state.title()


def notify(title, body="", urgency="normal", image=None):
    cmd = ["notify-send", "-a", "Bambu Monitor", "-u", urgency]
    if image:
        cmd += ["-i", image]
    cmd += [title, body]
    subprocess.run(cmd, check=False)


class PrinterMonitor:
    def __init__(self, config, state: PrinterState):
        self.cfg = config
        self.state = state
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"bambu-monitor-{int(time.time())}",
        )
        self.client.username_pw_set(USER, config["access_code"])
        self.client.tls_set(cert_reqs=ssl.CERT_NONE)
        self.client.tls_insecure_set(True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        self.client.reconnect_delay_set(5, 30)

    def run(self):
        self.client.connect_async(self.cfg["printer_ip"], MQTT_PORT, keepalive=30)
        self.client.loop_start()

    # ---- printer control (device/<serial>/request) ----

    def send_command(self, payload):
        with self.state.lock:
            serial = self.state.serial
        if not serial:
            return False
        payload.setdefault("sequence_id", "0")
        topic = f"device/{serial}/request"
        root = "system" if payload.get("command") == "ledctrl" else "print"
        self.client.publish(topic, json.dumps({root: payload}))
        return True

    def pause(self):
        return self.send_command({"command": "pause"})

    def resume(self):
        return self.send_command({"command": "resume"})

    def stop(self):
        return self.send_command({"command": "stop"})

    def set_speed(self, level):
        # 1 silent, 2 standard, 3 sport, 4 ludicrous
        return self.send_command({"command": "print_speed", "param": str(level)})

    def light(self, on):
        return self.send_command({
            "command": "ledctrl", "led_node": "chamber_light",
            "led_mode": "on" if on else "off",
            "led_on_time": 500, "led_off_time": 500,
            "loop_times": 0, "interval_time": 0,
        })

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            client.subscribe("device/+/report")
            with self.state.lock:
                self.state.connected = True
            notify("Bambu Monitor", f"Connected to printer at {self.cfg['printer_ip']}")
        else:
            notify("Bambu Monitor", f"Auth failed (code {reason_code}) — check access code",
                   "critical")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        with self.state.lock:
            self.state.connected = False
            if self.state.gcode_state not in ("OFFLINE",):
                self.state.gcode_state = "OFFLINE"

    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload).get("print", {})
        except (json.JSONDecodeError, AttributeError):
            return
        if not data:
            return

        serial = msg.topic.split("/")[1]
        new_state = data.get("gcode_state")

        with self.state.lock:
            s = self.state
            s.serial = serial
            s.percent = int(data.get("mc_percent", s.percent) or 0)
            s.layer = int(data.get("layer_num", s.layer) or 0)
            s.total_layers = int(data.get("total_layer_num", s.total_layers) or 0)
            s.remaining_min = int(data.get("mc_remaining_time", s.remaining_min) or 0)
            s.file = data.get("gcode_file", s.file) or s.file
            s.nozzle = float(data.get("nozzle_temper", s.nozzle) or 0)
            s.bed = float(data.get("bed_temper", s.bed) or 0)

            prev = s.gcode_state
            if new_state:
                s.gcode_state = new_state

            events = []
            if new_state and new_state != prev:
                events = self._transition(prev, new_state)
            events += self._milestones()

        for title, body, urgency, snap, phone in events:
            self._dispatch(title, body, urgency, snap, phone)

    def _dispatch(self, title, body, urgency, snapshot, phone):
        if self.cfg.get("notifications", True):
            if snapshot and self.cfg.get("camera_snapshots", True):
                threading.Thread(target=self._notify_with_snap,
                                 args=(title, body, urgency), daemon=True).start()
            else:
                notify(title, body, urgency)
        if phone and self.cfg.get("notify_phone", True):
            kde.ping(f"{title} — {body}" if body else title,
                     self.cfg.get("kdeconnect_device"))

    def _notify_with_snap(self, title, body, urgency):
        ok = camera.grab_frame(self.cfg["printer_ip"], self.cfg["access_code"],
                               SNAP_PATH)
        notify(title, body, urgency, image=SNAP_PATH if ok else None)

    def _transition(self, prev, new):
        """Return events as (title, body, urgency, snapshot, phone)."""
        s = self.state
        fname = s.file.split("/")[-1].rsplit(".", 1)[0] or "print"
        if new == "RUNNING" and prev in ("IDLE", "PREPARE", "OFFLINE", "PAUSE"):
            s.start_time = s.start_time or time.time()
            s.fired_milestones = set()
            if prev != "PAUSE":
                return [("Print started", fname, "normal", False, False)]
            return [("Print resumed", f"{fname} — {s.percent}%", "normal",
                     False, False)]
        if new == "FINISH":
            dur = int((time.time() - s.start_time) / 60) if s.start_time else 0
            s.start_time = 0
            return [("Print finished", f"{fname} ({dur} min)" if dur else fname,
                     "normal", True, True)]
        if new == "FAILED":
            return [("Print FAILED", f"{fname} at {s.percent}%", "critical",
                     True, True)]
        if new == "PAUSE":
            return [("Print paused", f"{fname} — {s.percent}%", "normal",
                     False, True)]
        if new == "IDLE":
            s.start_time = 0
            s.percent = 0
        return []

    def _milestones(self):
        s = self.state
        if s.gcode_state != "RUNNING":
            return []
        out = []
        for m in self.cfg.get("milestones", [25, 50, 75]):
            if s.percent >= m and m not in s.fired_milestones:
                s.fired_milestones.add(m)
                out.append((f"Print {m}%", f"~{s.remaining_min} min left",
                            "low", False, False))
        return out
