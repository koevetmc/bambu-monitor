"""Discover Bambu Lab printers on the LAN via SSDP (port 2021)."""
import socket

SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 2021
REQ = (
    "M-SEARCH * HTTP/1.1\r\n"
    f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
    'MAN: "ssdp:discover"\r\n'
    "MX: 3\r\n"
    "ST: urn:bambulab-com:device:3dprinter:1\r\n"
    "\r\n"
)


def discover(timeout=5):
    """Return list of dicts: {ip, serial, model, name} for each printer found."""
    found = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(REQ.encode(), (SSDP_ADDR, SSDP_PORT))
        while True:
            try:
                data, (ip, _) = sock.recvfrom(4096)
            except socket.timeout:
                break
            headers = {}
            for line in data.decode(errors="replace").split("\r\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    headers[k.strip().upper()] = v.strip()
            serial = headers.get("USN", "")
            found[ip] = {
                "ip": ip,
                "serial": serial,
                "model": headers.get("DEVMODEL.BAMBU.COM", "Bambu printer"),
                "name": headers.get("DEVNAME.BAMBU.COM", serial or ip),
            }
    finally:
        sock.close()
    return list(found.values())


if __name__ == "__main__":
    for p in discover():
        print(p)
