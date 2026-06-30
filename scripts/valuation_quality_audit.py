"""Quarantine published valuations that do not satisfy the current safety contract."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vehicle_valuation.config import CRM_DATABASE_PATH, DATABASE_PATH  # noqa: E402
from vehicle_valuation.repositories import ALGORITHM_VERSION  # noqa: E402
from vehicle_valuation.service import queue_existing_crm  # noqa: E402


MIN_SAFE_COMPARABLES = 5
MIN_SAFE_SOURCES = 2


def source_count(value: str | None) -> int:
    try:
        parsed = json.loads(value or "{}")
    except ValueError:
        return 0
    return len([key for key, count in parsed.items() if key and int(count or 0) > 0]) if isinstance(parsed, dict) else 0


def safe_run(row: sqlite3.Row | dict[str, Any] | None) -> bool:
    if row is None:
        return False
    data = dict(row)
    return bool(
        data.get("status") == "VALUED"
        and data.get("algorithm_version") == ALGORITHM_VERSION
        and data.get("valuation_method") == "EXACT"
        and data.get("market_value_cents") is not None
        and int(data.get("comparable_count") or 0) >= MIN_SAFE_COMPARABLES
        and source_count(data.get("source_breakdown_json")) >= MIN_SAFE_SOURCES
    )


def latest_runs() -> dict[str, sqlite3.Row]:
    if not DATABASE_PATH.exists():
        return {}
    with sqlite3.connect(DATABASE_PATH, timeout=30) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT t.crm_listing_id, r.*
            FROM target_vehicles t
            JOIN valuation_runs r ON r.target_id = t.id
            JOIN (
              SELECT target_id, MAX(created_at) AS latest_created_at
              FROM valuation_runs
              GROUP BY target_id
            ) latest ON latest.target_id = r.target_id AND latest.latest_created_at = r.created_at
            """
        ).fetchall()
    return {str(row["crm_listing_id"]): row for row in rows}


def quarantine_unsafe(*, dry_run: bool = False) -> dict[str, Any]:
    runs = latest_runs()
    if not CRM_DATABASE_PATH.exists():
        return {"checked": 0, "quarantined": 0, "reason": "CRM database is missing"}
    with sqlite3.connect(CRM_DATABASE_PATH, timeout=30) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        listings = connection.execute(
            """
            SELECT id, title, marketValuationStatus, marketValuationRunId
            FROM Listing
            WHERE availabilityStatus = 'ACTIVE'
              AND status NOT IN ('SOLD', 'ARCHIVED')
              AND marketValuationStatus IN ('VALUED', 'PROVISIONAL', 'INDICATIVE')
            """
        ).fetchall()
        unsafe = [row for row in listings if not safe_run(runs.get(str(row["id"])))]
        if not dry_run:
            for row in unsafe:
                run = runs.get(str(row["id"]))
                reason = (
                    "Automation quarantined this value because it did not pass the current identity, evidence, "
                    "multi-source, and algorithm-version safety checks. It has been requeued."
                )
                if run is not None and run["reason"]:
                    reason = f"{reason} Latest evidence: {str(run['reason'])[:1200]}"
                connection.execute(
                    """
                    UPDATE Listing SET
                      marketValuationStatus='QUARANTINED', marketValuationError=?,
                      marketValueCents=NULL, marketComparableCount=0,
                      marketLowestComparableCents=NULL, marketHighestComparableCents=NULL,
                      marketAucklandMedianCents=NULL, marketDifferenceCents=NULL,
                      marketDifferencePercent=NULL, marketRelation=NULL, marketVerdict=NULL,
                      marketConfidence=NULL, marketRawMedianCents=NULL,
                      marketTargetSellCents=NULL, marketMaxBuyCents=NULL,
                      marketExpectedSpreadCents=NULL, marketValuedAt=NULL,
                      marketSearchStage='QUARANTINED', marketReason=?
                    WHERE id=?
                    """,
                    (reason, reason, row["id"]),
                )
            connection.commit()
    return {
        "checked": len(listings),
        "quarantined": len(unsafe),
        "listingIds": [str(row["id"]) for row in unsafe],
        "algorithmVersion": ALGORITHM_VERSION,
        "dryRun": dry_run,
    }


def active_crm_listing_ids() -> set[str]:
    if not CRM_DATABASE_PATH.exists():
        return set()
    with sqlite3.connect(CRM_DATABASE_PATH, timeout=30) as connection:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT id FROM Listing WHERE availabilityStatus='ACTIVE' AND status NOT IN ('SOLD','ARCHIVED')"
            )
        }


def cancel_inactive_jobs() -> int:
    active_ids = active_crm_listing_ids()
    if not DATABASE_PATH.exists():
        return 0
    with sqlite3.connect(DATABASE_PATH, timeout=30) as connection:
        connection.execute("PRAGMA busy_timeout=30000")
        placeholders = ",".join("?" for _ in active_ids)
        clause = f"AND t.crm_listing_id NOT IN ({placeholders})" if active_ids else ""
        result = connection.execute(
            f"""
            UPDATE valuation_jobs
            SET status='CANCELLED', progress_stage='CANCELLED', next_retry_at=NULL,
                last_error='Listing is no longer active in the CRM.'
            WHERE id IN (
              SELECT j.id FROM valuation_jobs j
              JOIN target_vehicles t ON t.id=j.target_id
              WHERE j.status IN ('PENDING','RETRY','EXPANDING_SEARCH','AWAITING_SAFE_EVIDENCE')
              {clause}
            )
            """,
            tuple(active_ids),
        )
        connection.commit()
        return int(result.rowcount or 0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--requeue", action="store_true")
    args = parser.parse_args()
    result = quarantine_unsafe(dry_run=args.dry_run)
    if args.requeue and not args.dry_run:
        result["cancelledInactiveJobs"] = cancel_inactive_jobs()
        result["queued"] = queue_existing_crm(
            force=True,
            listing_ids=list(result.get("listingIds") or []),
        )
    print(json.dumps(result, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
