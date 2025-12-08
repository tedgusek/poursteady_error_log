# models.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Machine:
    name: str
    ip: str


# Strict naming rules
PS1_RE = re.compile(r"^PS\d{4}$")     # PS####
PS2_RE = re.compile(r"^PS\d{7}$")     # PS#######


def normalize_name(name: str) -> str:
    return (name or "").strip().upper()


def is_ps1_name(name: str) -> bool:
    return bool(PS1_RE.match(normalize_name(name)))


def is_ps2_name(name: str) -> bool:
    return bool(PS2_RE.match(normalize_name(name)))


def is_ps_any(name: str) -> bool:
    n = normalize_name(name)
    return bool(PS1_RE.match(n) or PS2_RE.match(n))


def infer_model_from_name(name: str) -> Optional[str]:
    if is_ps1_name(name):
        return "PS1"
    if is_ps2_name(name):
        return "PS2"
    return None
