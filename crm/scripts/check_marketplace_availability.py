"""Re-check Facebook Marketplace listing URLs and hide stale CRM rows."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[2]
CRM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scraper import MODERN_USER_AGENT, UNAVAILABLE_PATTERN  # noqa: E402
from scraper import _primary_detail_text  # noqa: E402


CRM_DB = CRM_ROOT / "prisma" / "dev.db"
SQLITE_TIMEOUT_SECONDS = 30
SQLITE_BUSY_TIMEOUT_MS = 30_000
DETAIL_TIMEOUT_MS = 15_000
DETAIL_WAIT_MS = 1_500
AVAILABILITY_CONCURRENCY = 4
VISIBLE_STATUSES = {"ACTIVE", "NEEDS_REVIEW", "POSSIBLY_SOLD", "UNKNOWN"}
HIDDEN_STATUSES = {"CONFIRMED_SOLD", "SOLD", "UNAVAILABLE", "EXPIRED"}
SOLD_LIKE_STATUSES = {"POSSIBLY_SOLD", "CONFIRMED_SOLD", "SOLD", "UNAVAILABLE"}
RECHECKABLE_STATUSES = VISIBLE_STATUSES | {"SOLD", "EXPIRED"}
SOLD_PATTERN = re.compile(
    r"(?i)\b(marked as sold|listing sold|item sold|vehicle sold|has been sold)\b"
)
GENERIC_FACEBOOK_TITLES = {
    "facebook",
    "marketplace",
    "facebook marketplace",
    "log in to facebook",
}


@dataclass(frozen=True)
class AvailabilityResult:
    status: str
    reason: str


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect_crm_db() -> sqlite3.Connection:
    connection = sqlite3.connect(CRM_DB, timeout=SQLITE_TIMEOUT_SECONDS)
    connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    return connection


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def console_text(value: str) -> str:
    text = clean_text(value)
    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding)


def is_strong_listing_title(value: str) -> bool:
    title = clean_text(value)
    if not title:
        return False
    normalized = title.lower()
    if normalized in GENERIC_FACEBOOK_TITLES:
        return False
    if "facebook marketplace" in normalized and len(title) < 35:
        return False
    return True


def classify_detail_text(
    page_title: str,
    body_text: str,
    h1_values: list[str] | None = None,
    open_graph_titles: list[str] | None = None,
) -> AvailabilityResult:
    """Classify Marketplace availability using page text and metadata."""
    h1_values = h1_values or []
    open_graph_titles = open_graph_titles or []
    primary_body_text = _primary_detail_text(body_text)
    haystack = clean_text(
        " ".join([page_title, primary_body_text, *h1_values, *open_graph_titles])
    )
    line_haystack = "\n".join(
        [page_title, primary_body_text, *h1_values, *open_graph_titles]
    )

    if SOLD_PATTERN.search(haystack) or re.search(
        r"(?im)^\s*sold\s*$",
        line_haystack,
    ):
        return AvailabilityResult("SOLD", "facebook_sold_signal")

    if UNAVAILABLE_PATTERN.search(haystack):
        return AvailabilityResult("UNAVAILABLE", "facebook_unavailable_signal")

    strong_titles = [
        value
        for value in [*h1_values, *open_graph_titles, page_title]
        if is_strong_listing_title(value)
    ]
    if strong_titles:
        return AvailabilityResult("ACTIVE", "detail_page_loaded")

    if "marketplace" in haystack.lower() and "$" in haystack:
        return AvailabilityResult("ACTIVE", "marketplace_price_signal")

    if "log in" in haystack.lower() or "login" in haystack.lower():
        return AvailabilityResult("UNKNOWN", "facebook_login_or_blocked")

    return AvailabilityResult("UNKNOWN", "missing_active_detail_signals")


def load_candidate_rows(
    connection: sqlite3.Connection,
    *,
    include_hidden: bool,
    limit: int | None,
    stale_hours: int,
) -> list[dict[str, Any]]:
    connection.row_factory = sqlite3.Row
    if include_hidden:
        status_clause = "1 = 1"
        params: list[Any] = []
    else:
        placeholders = ",".join("?" for _ in RECHECKABLE_STATUSES)
        status_clause = f'"availabilityStatus" IN ({placeholders})'
        params = sorted(RECHECKABLE_STATUSES)

    rows = [
        dict(row)
        for row in connection.execute(
            f"""
            SELECT
              Listing.id,
              Listing.title,
              Listing.facebookUrl,
              Listing.availabilityStatus,
              Listing.availabilityConfidence,
              Listing.unavailableCheckCount,
              Listing.consecutiveUnavailableChecks,
              Listing.unavailableSince,
              Listing.lastCheckedAt,
              Listing.lastVerifiedAt,
              Listing.marketValuationStatus,
              Listing.marketValuedAt
            FROM Listing
            LEFT JOIN AdminFlip ON AdminFlip.listingId = Listing.id
            WHERE facebookUrl LIKE '%/marketplace/item/%'
              AND {status_clause}
            ORDER BY
              CASE WHEN AdminFlip.id IS NULL THEN 1 ELSE 0 END,
              CASE WHEN Listing.marketValuationStatus = 'VALUED' THEN 0 ELSE 1 END,
              CASE WHEN Listing.lastCheckedAt IS NULL THEN 0 ELSE 1 END,
              Listing.lastCheckedAt ASC,
              Listing.firstSeenAt DESC
            """,
            params,
        )
    ]

    if stale_hours <= 0:
        filtered = rows
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=stale_hours)
        filtered = []
        for row in rows:
            checked_at = parse_timestamp(row.get("lastCheckedAt"))
            valued_at_raw = row.get("marketValuedAt")
            valued_at = None
            if isinstance(valued_at_raw, (int, float)) and valued_at_raw > 0:
                valued_at = datetime.fromtimestamp(valued_at_raw / 1000, tz=timezone.utc)
            needs_post_valuation_check = bool(
                row.get("marketValuationStatus") == "VALUED"
                and valued_at
                and (checked_at is None or checked_at < valued_at)
            )
            if needs_post_valuation_check or checked_at is None or checked_at <= cutoff:
                filtered.append(row)

    return filtered[:limit] if limit else filtered


async def check_url(page: Any, url: str) -> AvailabilityResult:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=DETAIL_TIMEOUT_MS)
        await page.wait_for_timeout(DETAIL_WAIT_MS)
        data = await page.evaluate(
            """() => ({
                pageTitle: document.title || "",
                bodyText: (document.body && document.body.innerText || "").slice(0, 12000),
                h1: Array.from(document.querySelectorAll("h1"))
                    .map((element) => element.textContent || "")
                    .map((text) => text.trim())
                    .filter(Boolean)
                    .slice(0, 5),
                openGraphTitle: Array.from(
                    document.querySelectorAll('meta[property="og:title"], meta[name="twitter:title"]')
                )
                    .map((element) => element.getAttribute("content") || "")
                    .filter(Boolean)
                    .slice(0, 5)
            })"""
        )
    except PlaywrightTimeoutError:
        return AvailabilityResult("UNKNOWN", "detail_page_timeout")
    except Exception as error:
        return AvailabilityResult("UNKNOWN", f"detail_page_error:{type(error).__name__}")

    return classify_detail_text(
        page_title=str(data.get("pageTitle") or ""),
        body_text=str(data.get("bodyText") or ""),
        h1_values=[str(value) for value in data.get("h1") or []],
        open_graph_titles=[
            str(value) for value in data.get("openGraphTitle") or []
        ],
    )


def update_listing(
    connection: sqlite3.Connection | None,
    row: dict[str, Any],
    result: AvailabilityResult,
    *,
    failure_threshold: int,
    dry_run: bool,
) -> dict[str, Any]:
    checked_at = now_iso()
    previous_status = str(row.get("availabilityStatus") or "ACTIVE")
    previous_count = int(
        row.get("consecutiveUnavailableChecks")
        or row.get("unavailableCheckCount")
        or 0
    )
    unavailable_since = row.get("unavailableSince")

    if result.status == "ACTIVE":
        next_status = "ACTIVE"
        next_count = 0
        next_unavailable_since = None
        reason = result.reason
        confidence = "HIGH"
        last_seen_at = checked_at
    elif result.status in {"SOLD", "UNAVAILABLE"}:
        next_count = previous_count + 1 if previous_status in SOLD_LIKE_STATUSES else 1
        next_unavailable_since = unavailable_since or checked_at
        if next_count >= failure_threshold:
            next_status = (
                "CONFIRMED_SOLD" if result.status == "SOLD" else "UNAVAILABLE"
            )
            reason = f"confirmed_after_{next_count}_checks:{result.reason}"
            confidence = "HIGH"
        else:
            next_status = "POSSIBLY_SOLD"
            reason = f"pending_second_confirmation:{result.reason}"
            confidence = "MEDIUM"
        last_seen_at = None
    else:
        next_count = previous_count if previous_status in SOLD_LIKE_STATUSES else 0
        next_status = (
            "POSSIBLY_SOLD" if previous_status == "POSSIBLY_SOLD" else "NEEDS_REVIEW"
        )
        next_unavailable_since = unavailable_since
        reason = (
            f"awaiting_confirmation:{result.reason}"
            if next_status == "POSSIBLY_SOLD"
            else f"needs_review:{result.reason}"
        )
        confidence = "LOW"
        last_seen_at = None

    if not dry_run and connection is not None:
        connection.execute(
            """
            UPDATE Listing
            SET
              availabilityStatus = ?,
              availabilityConfidence = ?,
              availabilityReason = ?,
              lastVerifiedAt = ?,
              lastCheckedAt = ?,
              lastSeenAt = COALESCE(?, lastSeenAt),
              unavailableSince = ?,
              consecutiveUnavailableChecks = ?,
              unavailableCheckCount = ?,
              updatedAt = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                next_status,
                confidence,
                reason,
                checked_at,
                checked_at,
                last_seen_at,
                next_unavailable_since,
                next_count,
                next_count,
                row["id"],
            ),
        )

    return {
        "id": row["id"],
        "title": row["title"],
        "previousStatus": previous_status,
        "nextStatus": next_status,
        "reason": reason,
        "confidence": confidence,
        "unavailableCheckCount": next_count,
    }


def persist_listing_update(
    row: dict[str, Any],
    result: AvailabilityResult,
    *,
    failure_threshold: int,
) -> dict[str, Any]:
    last_error: sqlite3.OperationalError | None = None
    for attempt in range(3):
        try:
            with connect_crm_db() as connection:
                updated = update_listing(
                    connection,
                    row,
                    result,
                    failure_threshold=failure_threshold,
                    dry_run=False,
                )
                connection.commit()
                return updated
        except sqlite3.OperationalError as error:
            last_error = error
            message = str(error).lower()
            if "locked" not in message and "busy" not in message:
                raise
            if attempt == 2:
                break
            time.sleep(1.5 * (attempt + 1))

    if last_error is not None:
        raise last_error
    raise RuntimeError("Could not persist listing availability update")


async def check_rows(
    rows: list[dict[str, Any]],
    *,
    dry_run: bool,
    failure_threshold: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=MODERN_USER_AGENT,
            viewport={"width": 1440, "height": 1200},
            locale="en-NZ",
            extra_http_headers={"Accept-Language": "en-NZ,en;q=0.9"},
        )
        semaphore = asyncio.Semaphore(AVAILABILITY_CONCURRENCY)

        async def check_one(index: int, row: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                page = await context.new_page()
                try:
                    result = await check_url(page, row["facebookUrl"])
                finally:
                    await page.close()
            if dry_run:
                updated = update_listing(
                    None,
                    row,
                    result,
                    failure_threshold=failure_threshold,
                    dry_run=True,
                )
            else:
                updated = await asyncio.to_thread(
                    persist_listing_update,
                    row,
                    result,
                    failure_threshold=failure_threshold,
                )

            print(
                "[AVAILABILITY] "
                f"{index}/{len(rows)} {updated['nextStatus']} "
                f"{console_text(str(row['title']))}",
                flush=True,
            )
            return updated

        results = list(await asyncio.gather(*(
            check_one(index, row) for index, row in enumerate(rows, 1)
        )))
        await context.close()
        await browser.close()

    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--stale-hours", type=int, default=12)
    parser.add_argument("--failure-threshold", type=int, default=2)
    parser.add_argument("--include-hidden", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if args.failure_threshold < 1:
        raise ValueError("--failure-threshold must be at least 1")
    if not CRM_DB.exists():
        raise FileNotFoundError(f"CRM database not found: {CRM_DB}")

    started = time.monotonic()
    with connect_crm_db() as connection:
        rows = load_candidate_rows(
            connection,
            include_hidden=args.include_hidden,
            limit=args.limit,
            stale_hours=args.stale_hours,
        )

    results = await check_rows(
        rows,
        dry_run=args.dry_run,
        failure_threshold=args.failure_threshold,
    )
    summary = {
        "checked": len(results),
        "dryRun": args.dry_run,
        "elapsedSeconds": int(time.monotonic() - started),
        "byStatus": {},
    }
    for result in results:
        status = result["nextStatus"]
        summary["byStatus"][status] = summary["byStatus"].get(status, 0) + 1

    print(f"[AVAILABILITY] Completed: {json.dumps(summary, sort_keys=True)}")


if __name__ == "__main__":
    asyncio.run(main())
