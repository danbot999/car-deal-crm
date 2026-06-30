"""Continuous Facebook Marketplace to n8n orchestration engine."""

from __future__ import annotations

import asyncio
import ctypes
import os
from pathlib import Path
import time
from typing import Any

import requests

import config
from runtime_health import write_heartbeat
from scraper import fetch_marketplace_listings, get_last_scan_diagnostics


REQUEST_TIMEOUT_SECONDS = 30
LOCK_FILE = Path(__file__).with_name("work") / "monitor.lock"


def is_publishable_item(item: dict[str, Any]) -> bool:
    """Allow only verified, in-scope, currently active passenger cars."""
    return (
        item.get("verified") is True
        and item.get("available") is True
        and item.get("in_scope") is True
        and str(item.get("availabilityStatus") or "").upper() == "ACTIVE"
    )


def _is_process_running(pid: int) -> bool:
    """Return whether a local process ID still exists."""
    if pid <= 0:
        return False

    if os.name == "nt":
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information,
            False,
            pid,
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False

    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _acquire_single_instance_lock() -> int | None:
    """Create an exclusive lock file so only one monitor runs."""
    LOCK_FILE.parent.mkdir(exist_ok=True)

    while True:
        try:
            file_descriptor = os.open(
                LOCK_FILE,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
            os.write(file_descriptor, str(os.getpid()).encode("ascii"))
            return file_descriptor
        except FileExistsError:
            try:
                existing_pid = int(LOCK_FILE.read_text(encoding="ascii").strip())
            except (OSError, ValueError):
                existing_pid = 0

            if _is_process_running(existing_pid):
                print(
                    f"[LOG] Marketplace monitor is already running "
                    f"(PID {existing_pid}). Exiting.",
                    flush=True,
                )
                return None

            try:
                LOCK_FILE.unlink()
            except FileNotFoundError:
                continue


def _release_single_instance_lock(file_descriptor: int | None) -> None:
    """Release the monitor lock file."""
    if file_descriptor is None:
        return
    os.close(file_descriptor)
    try:
        LOCK_FILE.unlink()
    except FileNotFoundError:
        pass


def _post_payload(payload: dict[str, Any]) -> int:
    """Send one complete scan payload to n8n and return its HTTP status."""
    response = requests.post(
        config.N8N_WEBHOOK_URL,
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.status_code


async def run_scan() -> dict[str, Any]:
    """Run one scan and transmit only verified active cars to n8n."""
    scanned_items = await fetch_marketplace_listings()
    source_diagnostics = get_last_scan_diagnostics()
    items = [item for item in scanned_items if is_publishable_item(item)]
    payload = {"items": items}
    by_status: dict[str, int] = {}
    for item in scanned_items:
        status = str(item.get("availabilityStatus") or "ACTIVE")
        by_status[status] = by_status.get(status, 0) + 1

    try:
        status_code = await asyncio.to_thread(_post_payload, payload)
    except requests.RequestException as exc:
        print(
            f"[ERROR] Scanned {len(items)} items, but n8n transmission failed: {exc}",
            flush=True,
        )
        return {
            "scanned": len(scanned_items), "published": 0,
            "rejected": len(scanned_items), "availability": by_status,
            "n8nStatus": None, "error": str(exc)[:500],
            "sourceDiagnostics": source_diagnostics,
        }
    except Exception as exc:
        print(
            f"[ERROR] Unexpected n8n transmission failure after scanning "
            f"{len(items)} items: {exc}",
            flush=True,
        )
        return {
            "scanned": len(scanned_items), "published": 0,
            "rejected": len(scanned_items), "availability": by_status,
            "n8nStatus": None, "error": str(exc)[:500],
            "sourceDiagnostics": source_diagnostics,
        }

    print(
        f"[LOG] Scanned {len(scanned_items)} items {by_status}; sent "
        f"{len(items)} verified active cars and rejected "
        f"{len(scanned_items) - len(items)}. Payload transmitted successfully "
        f"to n8n (HTTP {status_code}).",
        flush=True,
    )
    return {
        "scanned": len(scanned_items),
        "published": len(items),
        "rejected": len(scanned_items) - len(items),
        "availability": by_status,
        "n8nStatus": status_code,
        "sourceDiagnostics": source_diagnostics,
        "error": (
            "Marketplace source access failed for one or more configured searches"
            if source_diagnostics.get("failedUrls") or source_diagnostics.get("fatalError")
            else None
        ),
    }


async def main() -> None:
    """Run scans continuously at the configured start-to-start interval."""
    interval = max(1, config.SCAN_INTERVAL_SECONDS)
    print(
        f"[LOG] Marketplace monitor started. Scanning every {interval} seconds.",
        flush=True,
    )
    write_heartbeat("marketplace-monitor", "starting", intervalSeconds=interval)

    while True:
        scan_started_at = time.monotonic()
        try:
            result = await run_scan()
            heartbeat_status = (
                "healthy"
                if result.get("n8nStatus") and not result.get("error")
                else "degraded"
            )
            write_heartbeat("marketplace-monitor", heartbeat_status, **result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[ERROR] Scan loop recovered from an unexpected error: {exc}", flush=True)
            write_heartbeat("marketplace-monitor", "degraded", error=str(exc)[:500])

        elapsed = time.monotonic() - scan_started_at
        await asyncio.sleep(max(0.0, interval - elapsed))


if __name__ == "__main__":
    lock_fd = _acquire_single_instance_lock()
    if lock_fd is None:
        raise SystemExit(0)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[LOG] Marketplace monitor stopped.", flush=True)
    finally:
        _release_single_instance_lock(lock_fd)
