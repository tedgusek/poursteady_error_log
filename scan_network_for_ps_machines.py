import base64
import urllib.request
import urllib.error
import ssl
import re
import json

POSSIBLE_ENDPOINTS = [
    "/device_map.json",
    "/device_map.js",
    "/ajax/device_info",
    "/ajax/device_map.json",
    "/ajax/device_list",
    "/attached_devices.json",
    "/DEV_device_info.htm",
    "/AttachedDevices.htm",
    "/attached_devices.htm",
    "/DEVICEINFOv2.htm",
]

SCHEMES = ["http", "https"]


def fetch_orbi_raw(router_ip, username, password):
    auth = base64.b64encode(f"{username}:{password}".encode()).decode()

    headers = {
        "Authorization": f"Basic {auth}",
        "User-Agent": "Mozilla/5.0",
    }

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    for scheme in SCHEMES:
        for ep in POSSIBLE_ENDPOINTS:
            url = f"{scheme}://{router_ip}{ep}"
            req = urllib.request.Request(url, headers=headers)

            try:
                resp = urllib.request.urlopen(req, timeout=5, context=ctx)
                raw = resp.read().decode("utf-8", errors="ignore")

                if "device_changed" in raw and "device=" in raw:
                    return raw, url

            except:
                pass

    return None, None


def parse_orbi_devices(raw_text):
    clean = raw_text.strip()

    device_match = re.search(r"device\s*=\s*(\[.*\])", clean, re.DOTALL)
    if not device_match:
        return None

    device_json_text = device_match.group(1)

    try:
        return json.loads(device_json_text)
    except:
        return None


def filter_ps_devices(devices):
    results = []
    for d in devices:
        name = d.get("name", "")
        ip = d.get("ip", "")
        if re.search(r"ps", name, re.IGNORECASE):
            results.append((name, ip))
    return results


def main():
    router_ip = input("Router IP: ").strip()
    username = input("Username (default admin): ").strip() or "admin"
    password = input("Password: ").strip()

    raw, url = fetch_orbi_raw(router_ip, username, password)
    if not raw:
        print("Could not locate device list endpoint.")
        return

    devices = parse_orbi_devices(raw)
    if not devices:
        print("Could not parse device list.")
        return

    ps_devices = filter_ps_devices(devices)

    # ==========================
    # NEW OUTPUT FORMAT
    # one line per device: name,ip
    # ==========================
    for name, ip in ps_devices:
        print(f"{name},{ip}")


if __name__ == "__main__":
    main()
