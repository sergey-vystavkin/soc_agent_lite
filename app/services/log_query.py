from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

# Default path to sample logs resolved from current working directory (cwd).
# This avoids relying on __file__ so the module can be relocated without breaking.
# Expected layout when running from project root: app/data/samples/sample_logs.json
_DEFAULT_LOG_PATH = Path.cwd() / "app" / "data" / "samples" / "sample_logs.json"

_cache: List[Dict[str, Any]] | None = None


def _load_logs(path: Path | None = None) -> List[Dict[str, Any]]:
    """Load logs from JSON file.

    Simpler design: read once per process and cache in memory. If a different
    path is provided, load directly from that path (no caching between paths).
    """
    global _cache
    target = Path(path) if path else _DEFAULT_LOG_PATH
    if _cache is not None and path is None:
        return _cache

    if not target.exists():
        raise FileNotFoundError(f"Log store not found: {target}")

    with target.open("r", encoding="utf-8") as f:
        data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("Log store must be a JSON array of objects")

        for i, item in enumerate(data):
            if not isinstance(item, dict):
                raise ValueError(f"Log entry at index {i} is not an object")

    if path is None:
        _cache = data
    return data


def by_ip(ip: str, *, path: str | os.PathLike[str] | None = None) -> List[Dict[str, Any]]:
    """
    Return all log entries where field 'ip' equals the provided ip.
    Case-sensitive match as data is expected to be normalized; no regex.
    """
    logs = _load_logs(Path(path) if path else None)
    return [entry for entry in logs if str(entry.get("ip")) == ip]


def by_user(user: str, *, path: str | os.PathLike[str] | None = None) -> List[Dict[str, Any]]:
    """
    Return all log entries where field 'user' equals the provided user.
    Case-sensitive match; no regex.
    """
    logs = _load_logs(Path(path) if path else None)
    return [entry for entry in logs if str(entry.get("user")) == user]


if __name__ == "__main__":
    # Simple manual checks
    print("CWD:", Path.cwd())
    print("Using log file:", _DEFAULT_LOG_PATH)
    try:
        print("by_ip('10.0.0.5') =>")
        print(json.dumps(by_ip("10.0.0.5"), indent=2))
        print("\nby_user('alice') =>")
        print(json.dumps(by_user("alice"), indent=2))
    except Exception as e:
        print("Error:", e)
