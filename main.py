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
from scraper import fetch_marketplace_listings


REQUEST_TIMEOUT_SECONDS = 30
LOCK_FILE = Path(__file__).with_name("work") / "monitor.lock"


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


async def run_scan() -> None:
    """Run one Marketplace scan and transmit its full result to n8n."""
    items = await fetch_marketplace_listings()
    payload = {"items": items}

    try:
        status_code = await asyncio.to_thread(_post_payload, payload)
    except requests.RequestException as exc:
        print(
            f"[ERROR] Scanned {len(items)} items, but n8n transmission failed: {exc}",
            flush=True,
        )
        return
    except Exception as exc:
        print(
            f"[ERROR] Unexpected n8n transmission failure after scanning "
            f"{len(items)} items: {exc}",
            flush=True,
        )
        return

    print(
        f"[LOG] Scanned {len(items)} items. Payload transmitted successfully "
        f"to n8n (HTTP {status_code}).",
        flush=True,
    )


async def main() -> None:
    """Run scans continuously at the configured start-to-start interval."""
    interval = max(1, config.SCAN_INTERVAL_SECONDS)
    print(
        f"[LOG] Marketplace monitor started. Scanning every {interval} seconds.",
        flush=True,
    )

    while True:
        scan_started_at = time.monotonic()
        try:
            await run_scan()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[ERROR] Scan loop recovered from an unexpected error: {exc}", flush=True)

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
