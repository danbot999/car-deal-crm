"""Invalidate shallow valuations and requeue every active dashboard vehicle."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from sqlalchemy import update


ROOT = Path(__file__).resolve().parents[2]
CRM_DB = ROOT / "crm" / "prisma" / "dev.db"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vehicle_valuation.database import init_database, session_scope  # noqa: E402
from vehicle_valuation.models import ComparableListing, ComparableSearch, ValuationJob  # noqa: E402
from vehicle_valuation.normalization import vehicle_from_text  # noqa: E402
from vehicle_valuation.service import queue_existing_crm  # noqa: E402


def reset_crm_market_fields(preserve_exact: bool = False) -> int:
    preserve_clause = "AND marketValuationStatus != 'VALUED'" if preserve_exact else ""
    with sqlite3.connect(CRM_DB, timeout=30) as connection:
        cursor = connection.execute(
            f"""
            UPDATE Listing
            SET marketValuationStatus = 'PENDING',
                marketValuationError = NULL,
                marketValueCents = NULL,
                marketComparableCount = 0,
                marketLowestComparableCents = NULL,
                marketHighestComparableCents = NULL,
                marketAucklandMedianCents = NULL,
                marketDifferenceCents = NULL,
                marketDifferencePercent = NULL,
                marketRelation = NULL,
                marketVerdict = NULL,
                marketConfidence = NULL,
                marketReason = 'Queued for exhaustive nationwide comparable research.',
                marketTargetSellCents = NULL,
                marketMaxBuyCents = NULL,
                marketExpectedSpreadCents = NULL,
                marketSourcesAttempted = 0,
                marketSourcesSuccessful = 0,
                marketSourceBreakdownJson = NULL,
                marketComparablesJson = NULL,
                marketValuedAt = NULL,
                marketValuationRunId = NULL,
                marketValuationMethod = NULL,
                marketRawMedianCents = NULL,
                marketExactComparableCount = 0,
                marketAdjustmentJson = NULL,
                marketCoverageJson = NULL,
                marketSearchStage = 'QUEUED',
                marketSearchProgressJson = '{{"stage":"QUEUED"}}'
            WHERE availabilityStatus = 'ACTIVE'
              AND status NOT IN ('SOLD', 'ARCHIVED')
              {preserve_clause}
            """
        )
        connection.commit()
        return cursor.rowcount


def recanonicalize_active_identities() -> dict[str, int]:
    updated = 0
    incomplete = 0
    with sqlite3.connect(CRM_DB, timeout=30) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, title, listingDescription, kms
            FROM Listing
            WHERE availabilityStatus = 'ACTIVE' AND status NOT IN ('SOLD', 'ARCHIVED')
            """
        ).fetchall()
        for row in rows:
            vehicle = vehicle_from_text(
                row["title"], row["listingDescription"] or "",
                {"kms": row["kms"], "region": "Auckland"},
            )
            connection.execute(
                """
                UPDATE Listing
                SET extractedYear=?, make=?, model=?, variant=?, kms=?, transmission=?,
                    fuelType=?, bodyType=?, region='Auckland'
                WHERE id=?
                """,
                (
                    vehicle.year, vehicle.make, vehicle.model, vehicle.variant,
                    vehicle.kms, vehicle.transmission, vehicle.fuel_type,
                    vehicle.body_type, row["id"],
                ),
            )
            updated += 1
            incomplete += int(not vehicle.year or not vehicle.make or not vehicle.model)
        connection.commit()
    return {"identitiesRecanonicalized": updated, "identitiesStillIncomplete": incomplete}


def invalidate_index() -> dict[str, int]:
    with session_scope() as session:
        comparable_count = session.execute(
            update(ComparableListing)
            .where(ComparableListing.status.in_(["ACTIVE", "HISTORICAL"]))
            .values(status="STALE_REVALIDATE")
        ).rowcount or 0
        search_count = session.execute(
            update(ComparableSearch).values(
                status="QUEUED",
                stage="IDENTIFYING_VEHICLE",
                cache_expires_at=None,
                last_error=None,
            )
        ).rowcount or 0
        job_count = session.execute(
            update(ValuationJob)
            .where(ValuationJob.status.in_(["PENDING", "RUNNING", "RETRY", "EXPANDING_SEARCH"]))
            .values(status="PENDING", progress_stage="QUEUED", next_retry_at=None, last_error=None)
        ).rowcount or 0
    return {"comparablesInvalidated": comparable_count, "searchesReset": search_count, "jobsReset": job_count}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preserve-exact", action="store_true")
    parser.add_argument("--keep-index", action="store_true")
    args = parser.parse_args()
    init_database()
    active = reset_crm_market_fields(preserve_exact=args.preserve_exact)
    identity = recanonicalize_active_identities()
    reset = {"comparablesInvalidated": 0, "searchesReset": 0, "jobsReset": 0}
    if not args.keep_index:
        reset = invalidate_index()
    queued = queue_existing_crm(force=True, skip_valued=args.preserve_exact)
    print({"activeListingsReset": active, "queued": queued, **identity, **reset})


if __name__ == "__main__":
    main()
