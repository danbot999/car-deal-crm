"""Continuously sync n8n car_listings rows into the local CRM database."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from check_marketplace_availability import check_rows as check_availability_rows
from check_marketplace_availability import connect_crm_db
from check_marketplace_availability import load_candidate_rows
from import_n8n_listings import import_rows
from sync_cloud_crm import sync_cloud_once


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime_health import write_heartbeat  # noqa: E402


LOCK_FILE = Path(__file__).resolve().parents[1] / "work" / "crm-sync.lock"


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_process_running(pid: int) -> bool:
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


def acquire_single_instance_lock() -> int | None:
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

            if is_process_running(existing_pid):
                print(
                    f"[CRM SYNC] {timestamp()} sync is already running "
                    f"(PID {existing_pid}). Exiting.",
                    flush=True,
                )
                return None

            try:
                LOCK_FILE.unlink()
            except FileNotFoundError:
                continue


def release_single_instance_lock(file_descriptor: int | None) -> None:
    if file_descriptor is None:
        return
    os.close(file_descriptor)
    try:
        LOCK_FILE.unlink()
    except FileNotFoundError:
        pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--skip-images", action="store_true")
    parser.add_argument("--skip-availability", action="store_true")
    parser.add_argument("--availability-interval-seconds", type=int, default=600)
    parser.add_argument("--availability-limit", type=int, default=30)
    parser.add_argument("--availability-stale-hours", type=int, default=6)
    parser.add_argument("--availability-failure-threshold", type=int, default=2)
    parser.add_argument("--cloud-sync-interval-seconds", type=int, default=600)
    parser.add_argument("--skip-cloud", action="store_true")
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


async def run_once(args: argparse.Namespace) -> dict[str, int]:
    result = await import_rows(
        limit=args.limit,
        skip_images=args.skip_images,
        refresh_existing=False,
    )
    print(f"[CRM SYNC] {timestamp()} {result}", flush=True)
    write_heartbeat("crm-sync", "healthy", **result)
    return result


async def run_availability_once(args: argparse.Namespace) -> dict[str, int]:
    with connect_crm_db() as connection:
        rows = load_candidate_rows(
            connection,
            include_hidden=False,
            limit=args.availability_limit,
            stale_hours=args.availability_stale_hours,
        )

    results = await check_availability_rows(
        rows,
        dry_run=False,
        failure_threshold=args.availability_failure_threshold,
    )
    by_status: dict[str, int] = {}
    for result in results:
        status = str(result["nextStatus"])
        by_status[status] = by_status.get(status, 0) + 1

    summary = {"checked": len(results), **by_status}
    print(f"[CRM AVAILABILITY] {timestamp()} {summary}", flush=True)
    return summary


async def main() -> None:
    args = parse_args()
    if args.interval_seconds < 10:
        raise ValueError("--interval-seconds must be at least 10")
    if args.availability_interval_seconds < 60:
        raise ValueError("--availability-interval-seconds must be at least 60")
    if args.cloud_sync_interval_seconds < 60:
        raise ValueError("--cloud-sync-interval-seconds must be at least 60")

    last_availability_run = 0.0
    last_cloud_sync = 0.0

    while True:
        try:
            await run_once(args)
            should_check_availability = (
                not args.skip_availability
                and time.monotonic() - last_availability_run
                >= args.availability_interval_seconds
            )
            if should_check_availability:
                await run_availability_once(args)
                last_availability_run = time.monotonic()

            should_sync_cloud = (
                not args.skip_cloud
                and time.monotonic() - last_cloud_sync
                >= args.cloud_sync_interval_seconds
            )
            if should_sync_cloud:
                try:
                    cloud_result = await asyncio.to_thread(sync_cloud_once)
                    print(
                        f"[CLOUD SYNC] {timestamp()} {cloud_result}",
                        flush=True,
                    )
                    last_cloud_sync = time.monotonic()
                except Exception as error:
                    print(
                        f"[CLOUD SYNC] {timestamp()} failed: {error}",
                        flush=True,
                    )
        except Exception as error:
            print(f"[CRM SYNC] {timestamp()} failed: {error}", flush=True)
            write_heartbeat("crm-sync", "degraded", error=str(error)[:500])

        if args.once:
            break

        await asyncio.sleep(args.interval_seconds)


if __name__ == "__main__":
    lock_fd = acquire_single_instance_lock()
    if lock_fd is None:
        raise SystemExit(0)

    try:
        asyncio.run(main())
    finally:
        release_single_instance_lock(lock_fd)
