"""Push notifications to paired phones via kdeconnect-cli."""
import re
import shutil
import subprocess

_CLI = shutil.which("kdeconnect-cli")


def reachable_devices():
    """Return [(id, name), ...] for devices currently reachable."""
    if not _CLI:
        return []
    try:
        out = subprocess.run([_CLI, "-a"], capture_output=True, text=True,
                             timeout=5).stdout
    except (subprocess.SubprocessError, OSError):
        return []
    return re.findall(r"-\s*(.+?):\s*([0-9a-f]{16,})\s*\(", out)


def ping(message, device_id=None):
    """Send a ping-style notification to the phone. Returns True if sent."""
    if not _CLI:
        return False
    dev = device_id
    if not dev or dev == "auto":
        devices = reachable_devices()
        if not devices:
            return False
        dev = devices[0][0]
    try:
        subprocess.run([_CLI, "--device", dev, "--ping-msg", message],
                       timeout=5, check=False,
                       capture_output=True)
        return True
    except (subprocess.SubprocessError, OSError):
        return False
