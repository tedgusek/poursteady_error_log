# scanner_orbi.py
from __future__ import annotations

import base64
import urllib.request
import ssl
import re
import json
from dataclasses import dataclass
from typing import List, Optional, Tuple

from models import Machine, normalize_name, is_ps_any


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


@dataclass(frozen=True)
class OrbiCredentials:
    router_ip: str
    username: str
    password: str


class OrbiScanner:
    def __init__(self, creds: OrbiCredentials):
        self.creds = creds

    @classmethod
    def from_env(cls):
        import os
        from dotenv import load_dotenv

        load_dotenv()

        router_ip = os.getenv("ORBI_IP")
        username = os.getenv("ORBI_USER")
        password = os.getenv("ORBI_PASS")

        if not router_ip or not username or not password:
            raise ValueError("Missing ORBI_IP, ORBI_USER, or ORBI_PASS in .env")

        return cls(OrbiCredentials(router_ip, username, password))

    def fetch_orbi_raw(self) -> Tuple[Optional[str], Optional[str]]:
        auth = base64.b64encode(
            f"{self.creds.username}:{self.creds.password}".encode()
        ).decode()

        headers = {
            "Authorization": f"Basic {auth}",
            "User-Agent": "Mozilla/5.0",
        }

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        for scheme in SCHEMES:
            for ep in POSSIBLE_ENDPOINTS:
                url = f"{scheme}://{self.creds.router_ip}{ep}"
                req = urllib.request.Request(url, headers=headers)

                try:
                    resp = urllib.request.urlopen(req, timeout=5, context=ctx)
                    raw = resp.read().decode("utf-8", errors="ignore")

                    if "device_changed" in raw and "device=" in raw:
                        return raw, url
                except:
                    pass

        return None, None

    def parse_orbi_devices(self, raw_text: str):
        clean = raw_text.strip()

        device_match = re.search(r"device\s*=\s*(\[.*\])", clean, re.DOTALL)
        if not device_match:
            return None

        device_json_text = device_match.group(1)

        try:
            return json.loads(device_json_text)
        except:
            return None

    def filter_ps_devices(self, devices) -> List[Machine]:
        """
        Only accept strict PS#### and PS####### names.
        """
        results: List[Machine] = []

        for d in devices:
            name = d.get("name", "") or ""
            ip = d.get("ip", "") or ""

            if not ip:
                continue

            canonical = normalize_name(name)

            if is_ps_any(canonical):
                results.append(Machine(canonical, ip))

        return results

    def scan_ps_machines(self) -> List[Machine]:
        raw, _url = self.fetch_orbi_raw()
        if not raw:
            raise RuntimeError("Could not locate device list endpoint.")

        devices = self.parse_orbi_devices(raw)
        if not devices:
            raise RuntimeError("Could not parse device list.")

        return self.filter_ps_devices(devices)
