# hosts_repo.py
from __future__ import annotations

import os
from typing import List, Tuple, Optional

from models import Machine, normalize_name


class HostsRepo:
    def __init__(self, path: str):
        self.path = path

    def exists(self) -> bool:
        return os.path.exists(self.path)

    def load(self) -> Tuple[Optional[str], List[Machine]]:
        """
        Format:
          SINCE=YYYYMMDDHHMM
          PS1234,ip
          PS1234567,ip
        """
        if not self.exists():
            return None, []

        with open(self.path, "r", encoding="utf-8") as f:
            lines = [x.strip() for x in f.readlines() if x.strip()]

        if not lines:
            return None, []

        since = None
        idx = 0

        if lines[0].upper().startswith("SINCE="):
            since = lines[0].split("=", 1)[1].strip()
            idx = 1

        machines: List[Machine] = []
        for line in lines[idx:]:
            if "," in line:
                name, ip = line.split(",", 1)
                machines.append(Machine(normalize_name(name), ip.strip()))

        return since, machines

    def write(self, since: str, machines: List[Machine]) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

        with open(self.path, "w", encoding="utf-8") as f:
            f.write(f"SINCE={since}\n")
            for m in machines:
                f.write(f"{normalize_name(m.name)},{m.ip}\n")
