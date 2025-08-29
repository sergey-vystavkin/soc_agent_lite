from __future__ import annotations

import os
from typing import Optional


def getenv_int(name: str, default: int) -> int:
    """
    Read an environment variable as int with a safe default.
    Accepts strings like "10". On missing/invalid value returns default.
    """
    val: Optional[str] = os.getenv(name)
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def getenv_float(name: str, default: float) -> float:
    """
    Read an environment variable as float with a safe default.
    Accepts strings like "0.5". On missing/invalid value returns default.
    """
    val: Optional[str] = os.getenv(name)
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default
