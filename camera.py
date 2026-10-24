"""Grab a JPEG frame from the printer's built-in camera (TLS, port 6000).

Protocol: 80-byte auth packet, then framed chunks whose payloads are JPEGs.
"""
import socket
import ssl
import struct

CAM_PORT = 6000
USER = "bblp"


def _auth_packet(access_code):
    return (
        struct.pack("<I", 0x40)
        + struct.pack("<I", 0x3000)
        + b"\x00" * 8
        + USER.encode().ljust(32, b"\x00")
        + access_code.encode().ljust(32, b"\x00")
    )


def _read_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def grab_frame(ip, access_code, out_path, timeout=10):
    """Pull one frame and save to out_path. Returns True on success."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        raw = socket.create_connection((ip, CAM_PORT), timeout=timeout)
        with ctx.wrap_socket(raw) as ss:
            ss.settimeout(timeout)
            ss.write(_auth_packet(access_code))
            for _ in range(50):  # scan a bounded number of chunks
                # chunk framing: 4-byte payload size, 16-byte header, payload
                size_b = _read_exact(ss, 4)
                if not size_b:
                    break
                payload_size = struct.unpack("<I", size_b)[0]
                hdr = _read_exact(ss, 16)
                if not hdr:
                    break
                if payload_size <= 0 or payload_size > 8_000_000:
                    continue
                payload = _read_exact(ss, payload_size)
                if not payload:
                    break
                soi = payload.find(b"\xff\xd8")
                eoi = payload.rfind(b"\xff\xd9")
                if soi != -1 and eoi > soi:
                    with open(out_path, "wb") as f:
                        f.write(payload[soi:eoi + 2])
                    return True
    except OSError:
        pass
    return False


if __name__ == "__main__":
    import json, sys
    cfg = json.load(open("config.json"))
    ok = grab_frame(cfg["printer_ip"], cfg["access_code"], "/tmp/bambu-frame.jpg")
    print("frame saved" if ok else "no frame")
    sys.exit(0 if ok else 1)
