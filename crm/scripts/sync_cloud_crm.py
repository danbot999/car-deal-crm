"""Backfill and continuously refresh the hosted CRM from the local CRM database."""

from __future__ import annotations

import argparse
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

import requests


CRM_ROOT = Path(__file__).resolve().parents[1]
CRM_DB = CRM_ROOT / "prisma" / "dev.db"
CLOUD_ENV_FILE = CRM_ROOT / ".env.cloud"
DEFAULT_CLOUD_URL = "https://car-deal-crm.onrender.com"
REQUEST_TIMEOUT_SECONDS = 90
DEFAULT_BATCH_SIZE = 100


def load_local_environment() -> dict[str, str]:
    values: dict[str, str] = {}
    if not CLOUD_ENV_FILE.exists():
        return values
    for raw_line in CLOUD_ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def cloud_settings() -> tuple[str, str]:
    file_values = load_local_environment()
    base_url = (
        os.getenv("CRM_CLOUD_URL")
        or file_values.get("CRM_CLOUD_URL")
        or DEFAULT_CLOUD_URL
    ).rstrip("/")
    token = os.getenv("CRM_INGEST_TOKEN") or file_values.get("CRM_INGEST_TOKEN") or ""
    if not token:
        raise RuntimeError(
            f"CRM_INGEST_TOKEN is missing. Add it to {CLOUD_ENV_FILE}."
        )
    return base_url, token


def load_local_listings() -> list[dict[str, Any]]:
    if not CRM_DB.exists():
        raise FileNotFoundError(f"Local CRM database not found: {CRM_DB}")

    with sqlite3.connect(CRM_DB, timeout=30) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
              facebookUrl,
              title,
              askingPriceCents,
              category,
              remoteImageUrl,
              extractedYear,
              make,
              model,
              variant,
              kms,
              transmission,
              fuelType,
              bodyType,
              region,
              marketValuationStatus,
              marketValuationError,
              marketValueCents,
              marketComparableCount,
              marketLowestComparableCents,
              marketHighestComparableCents,
              marketAucklandMedianCents,
              marketDifferenceCents,
              marketDifferencePercent,
              marketRelation,
              marketVerdict,
              marketConfidence,
              marketValuationMethod,
              marketRawMedianCents,
              marketExactComparableCount,
              marketAdjustmentJson,
              marketCoverageJson,
              marketSearchIdentity,
              marketSearchStage,
              marketSearchProgressJson,
              marketConfigurationWarning,
              marketReason,
              marketTargetSellCents,
              marketMaxBuyCents,
              marketExpectedSpreadCents,
              marketSourcesAttempted,
              marketSourcesSuccessful,
              marketSourceBreakdownJson,
              marketComparablesJson,
              marketValuedAt,
              marketValuationRunId,
              availabilityStatus,
              availabilityConfidence,
              availabilityReason,
              firstSeenAt,
              lastSeenAt,
              lastVerifiedAt
            FROM Listing
            ORDER BY firstSeenAt ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def post_batch(
    session: requests.Session,
    endpoint: str,
    token: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            response = session.post(
                endpoint,
                headers={"Authorization": f"Bearer {token}"},
                json={"items": items},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            if not payload.get("ok"):
                raise RuntimeError(f"Cloud CRM rejected the batch: {payload}")
            return payload
        except (requests.RequestException, ValueError, RuntimeError) as error:
            last_error = error
            if attempt < 3:
                time.sleep(attempt * 2)
    raise RuntimeError(f"Cloud CRM sync failed after 3 attempts: {last_error}")


def sync_cloud_once(batch_size: int = DEFAULT_BATCH_SIZE) -> dict[str, int]:
    if batch_size < 1 or batch_size > 200:
        raise ValueError("batch_size must be between 1 and 200")

    base_url, token = cloud_settings()
    endpoint = f"{base_url}/api/ingest/listings"
    rows = load_local_listings()
    summary = {"read": len(rows), "stored": 0, "created": 0, "updated": 0}

    with requests.Session() as session:
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            result = post_batch(session, endpoint, token, batch)
            summary["stored"] += int(result.get("stored", 0))
            summary["created"] += int(result.get("created", 0))
            summary["updated"] += int(result.get("updated", 0))
            print(
                f"[CLOUD SYNC] {min(start + len(batch), len(rows))}/{len(rows)} "
                f"stored (created {summary['created']}, updated {summary['updated']}).",
                flush=True,
            )

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = sync_cloud_once(batch_size=args.batch_size)
    print(f"[CLOUD SYNC] Completed: {result}", flush=True)


if __name__ == "__main__":
    main()
