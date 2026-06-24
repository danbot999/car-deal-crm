"""Durable valuation worker and n8n reconciliation loop."""

from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime

from .config import (
    DIRECTORY_REFRESH_SECONDS, INDEX_REFRESH_SECONDS, INDEX_TARGET_LIMIT,
    MAX_GROUP_WORKERS, RECONCILE_SECONDS, WORKER_POLL_SECONDS, WORK_DIR,
)
from .database import init_database, session_scope
from .repositories import (
    claim_next_job, claim_publication, recover_stale_work, seed_sources,
)
from .service import (
    backfill_publication_outbox, deliver_publication, discover_dealer_inventory_sites,
    process_job, queue_existing_crm, reconcile_n8n, refresh_market_index,
)


_LOCK_HANDLE = None


def acquire_worker_lock() -> bool:
    global _LOCK_HANDLE
    lock_path = WORK_DIR / "vehicle-valuation-worker.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError):
        handle.close()
        return False
    _LOCK_HANDLE = handle
    return True


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def work_once() -> bool:
    with session_scope() as session:
        seed_sources(session)
        job = claim_next_job(session)
        job_id = job.id if job else None
    if not job_id:
        return False
    print(f"[VALUATION] {timestamp()} processing {job_id}", flush=True)
    try:
        result = process_job(job_id)
        print(f"[VALUATION] {timestamp()} completed {job_id}: {result['status']}", flush=True)
    except Exception as error:
        print(f"[VALUATION] {timestamp()} failed {job_id}: {error}", flush=True)
    return True


def process_logged(job_id: str) -> dict[str, object]:
    print(f"[VALUATION] {timestamp()} processing {job_id}", flush=True)
    result = process_job(job_id)
    print(f"[VALUATION] {timestamp()} completed {job_id}: {result['status']}", flush=True)
    return result


def claim_job_id() -> str | None:
    with session_scope() as session:
        seed_sources(session)
        job = claim_next_job(session)
        return job.id if job else None


def publish_once() -> bool:
    with session_scope() as session:
        publication = claim_publication(session)
        publication_id = publication.id if publication else None
    if not publication_id:
        return False
    try:
        result = deliver_publication(publication_id)
        print(f"[VALUATION] {timestamp()} publication {publication_id}: {result}", flush=True)
    except Exception as error:
        print(f"[VALUATION] {timestamp()} publication failed {publication_id}: {error}", flush=True)
    return True


def run_daemon() -> None:
    init_database()
    with session_scope() as session:
        seed_sources(session)
        recovered = recover_stale_work(session)
    if any(recovered.values()):
        print(f"[VALUATION] {timestamp()} recovered stale work: {recovered}", flush=True)
    created_publications = backfill_publication_outbox()
    if created_publications:
        print(f"[VALUATION] {timestamp()} recovered {created_publications} publication records", flush=True)
    last_reconcile = 0.0
    last_index_refresh = 0.0
    last_directory_refresh = 0.0
    futures: dict[Future[dict[str, object]], str] = {}
    with ThreadPoolExecutor(max_workers=MAX_GROUP_WORKERS) as executor:
        while True:
            for future, job_id in list(futures.items()):
                if not future.done():
                    continue
                try:
                    future.result()
                except Exception as error:
                    print(f"[VALUATION] {timestamp()} failed {job_id}: {error}", flush=True)
                del futures[future]

            if time.monotonic() - last_reconcile >= RECONCILE_SECONDS:
                try:
                    queued = reconcile_n8n()
                    print(f"[VALUATION] {timestamp()} reconciled {queued} n8n rows", flush=True)
                except Exception as error:
                    print(f"[VALUATION] {timestamp()} reconciliation failed: {error}", flush=True)
                last_reconcile = time.monotonic()

            while len(futures) < MAX_GROUP_WORKERS:
                job_id = claim_job_id()
                if not job_id:
                    break
                future = executor.submit(process_logged, job_id)
                futures[future] = job_id

            publish_once()

            if not futures and time.monotonic() - last_index_refresh >= INDEX_REFRESH_SECONDS:
                try:
                    result = refresh_market_index(INDEX_TARGET_LIMIT)
                    print(f"[VALUATION] {timestamp()} rolling index refresh: {result}", flush=True)
                except Exception as error:
                    print(f"[VALUATION] {timestamp()} index refresh failed: {error}", flush=True)
                last_index_refresh = time.monotonic()
            if not futures and time.monotonic() - last_directory_refresh >= DIRECTORY_REFRESH_SECONDS:
                try:
                    result = discover_dealer_inventory_sites()
                    print(f"[VALUATION] {timestamp()} dealer discovery: {result}", flush=True)
                except Exception as error:
                    print(f"[VALUATION] {timestamp()} dealer discovery failed: {error}", flush=True)
                last_directory_refresh = time.monotonic()
            time.sleep(1 if futures else WORKER_POLL_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--backfill", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    init_database()
    if args.backfill:
        print(f"[VALUATION] queued {queue_existing_crm(args.limit, force=args.force)} CRM listings", flush=True)
    if args.once:
        work_once()
    else:
        if not acquire_worker_lock():
            print("[VALUATION] Another valuation worker is already running; exiting.", flush=True)
            return
        run_daemon()


if __name__ == "__main__":
    main()
