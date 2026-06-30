"""Small, atomic runtime heartbeat helpers shared by the local services."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
HEARTBEAT_DIR = ROOT / "work" / "heartbeats"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def heartbeat_path(name: str) -> Path:
    safe_name = "".join(character for character in name if character.isalnum() or character in "-_")
    if not safe_name:
        raise ValueError("Heartbeat name is required.")
    return HEARTBEAT_DIR / f"{safe_name}.json"


def write_heartbeat(name: str, status: str = "running", **details: Any) -> dict[str, Any]:
    payload = {
        "service": name,
        "status": status,
        "pid": os.getpid(),
        "updatedAt": utc_iso(),
        **details,
    }
    path = heartbeat_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, default=str, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)
    return payload


def read_heartbeat(name: str) -> dict[str, Any] | None:
    path = heartbeat_path(name)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def heartbeat_age_seconds(name: str) -> float | None:
    payload = read_heartbeat(name)
    if not payload:
        return None
    try:
        updated = datetime.fromisoformat(str(payload["updatedAt"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return None
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - updated).total_seconds())
