"""Import cleaned n8n car listings into the local CRM database."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[2]
CRM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scraper import MODERN_USER_AGENT, is_strict_car_listing  # noqa: E402


CRM_DB = CRM_ROOT / "prisma" / "dev.db"
VALUATION_DB = CRM_ROOT / "work" / "vehicle-valuation.db"
N8N_DB = Path.home() / ".n8n" / "database.sqlite"
IMAGE_DIR = CRM_ROOT / "public" / "listing-images"
SQLITE_TIMEOUT_SECONDS = 30
SQLITE_BUSY_TIMEOUT_MS = 30_000
PAGE_TITLE_SUFFIX_PATTERN = re.compile(
    r"(?i)\s*\|\s*Facebook Marketplace\s*\|\s*Facebook\s*$"
)
TITLE_SPLIT_PATTERN = re.compile(
    r"\s+(?:-|\u2013|\u2014|â€“|â€”|Ã¢â‚¬â€œ)\s+"
)
ITEM_ID_PATTERN = re.compile(r"/marketplace/item/(\d+)")
MAKE_PATTERN = re.compile(
    r"(?i)\b("
    r"toyota|nissan|mazda|honda|suzuki|subaru|mitsubishi|ford|holden|"
    r"volkswagen|vw|bmw|mercedes|mercedes-benz|audi|lexus|hyundai|kia|"
    r"peugeot|renault|volvo|jeep|dodge|mini|skoda|tesla"
    r")\b"
)
YEAR_PATTERN = re.compile(r"\b(19[7-9]\d|20[0-3]\d)\b")
AVAILABILITY_STATUSES = {
    "ACTIVE",
    "NEEDS_REVIEW",
    "POSSIBLY_SOLD",
    "CONFIRMED_SOLD",
    "UNAVAILABLE",
    "EXPIRED",
    "UNKNOWN",
}
AVAILABILITY_CONFIDENCES = {"HIGH", "MEDIUM", "LOW"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect_crm_db() -> sqlite3.Connection:
    connection = sqlite3.connect(CRM_DB, timeout=SQLITE_TIMEOUT_SECONDS)
    connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    return connection


def console_text(value: str) -> str:
    single_line = re.sub(r"\s+", " ", value).strip()
    encoding = sys.stdout.encoding or "utf-8"
    return single_line.encode(encoding, errors="replace").decode(encoding)


def sqlite_timestamp(value: str | None) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat(
            timespec="milliseconds"
        )
    except ValueError:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def cents_from_price(value: Any) -> int:
    return int(round(float(value) * 100))


def optional_sqlite_timestamp(value: str | None) -> str | None:
    if not value:
        return None
    return sqlite_timestamp(value)


def normalize_availability_status(value: Any) -> str | None:
    status = str(value or "").strip().upper()
    if status == "SOLD":
        return "CONFIRMED_SOLD"
    return status if status in AVAILABILITY_STATUSES else None


def normalize_availability_confidence(value: Any) -> str:
    confidence = str(value or "").strip().upper()
    return confidence if confidence in AVAILABILITY_CONFIDENCES else "LOW"


def is_active_passenger_car_row(row: dict[str, Any]) -> bool:
    """Return whether an n8n row is safe to import as visible inventory."""
    return (
        normalize_availability_status(row.get("availabilityStatus")) == "ACTIVE"
        and is_strict_car_listing(
            str(row.get("title") or ""),
            str(row.get("category") or ""),
        )
    )


def facebook_item_id(url: str) -> str | None:
    match = ITEM_ID_PATTERN.search(urlparse(url).path)
    return match.group(1) if match else None


def stable_id(url: str) -> str:
    return "listing_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:24]


def extract_year_make_model(title: str) -> tuple[int | None, str | None, str | None]:
    year_match = YEAR_PATTERN.search(title)
    make_match = MAKE_PATTERN.search(title)
    year = int(year_match.group(1)) if year_match else None
    make = make_match.group(1).replace("vw", "Volkswagen").title() if make_match else None

    model = None
    if make_match:
        tail = title[make_match.end() :].strip(" -|,")
        words = [word for word in re.split(r"\s+", tail) if word]
        if words:
            model = " ".join(words[:3]).strip(" -|,")

    return year, make, model or None


def clean_title(value: str) -> str:
    title = PAGE_TITLE_SUFFIX_PATTERN.sub("", value).strip()
    parts = TITLE_SPLIT_PATTERN.split(title)
    return parts[0].strip(" ,-|") if parts else title


def parse_category(page_title: str) -> str | None:
    cleaned = PAGE_TITLE_SUFFIX_PATTERN.sub("", page_title).strip()
    parts = [part.strip() for part in TITLE_SPLIT_PATTERN.split(cleaned)]
    if len(parts) >= 3:
        return parts[-2]
    return None


def get_n8n_rows() -> list[dict[str, Any]]:
    if not N8N_DB.exists():
        raise FileNotFoundError(f"n8n database not found: {N8N_DB}")

    with sqlite3.connect(N8N_DB) as connection:
        connection.row_factory = sqlite3.Row
        table_row = connection.execute(
            "SELECT id FROM data_table WHERE name = ?", ("car_listings",)
        ).fetchone()
        if table_row is None:
            return []

        table_name = f"data_table_user_{table_row['id']}"
        available_columns = [
            row["name"] for row in connection.execute(f'PRAGMA table_info("{table_name}")')
        ]
        requested_columns = [
            "title",
            "price",
            "url",
            "firstSeen",
            "category",
            "availabilityStatus",
            "availabilityConfidence",
            "filterReason",
            "lastSeen",
            "sourceSearchUrl",
        ]
        selected_columns = [
            column for column in requested_columns if column in available_columns
        ]
        if not {"title", "price", "url", "firstSeen"}.issubset(selected_columns):
            return []
        return [
            dict(row)
            for row in connection.execute(
                f'SELECT {", ".join(selected_columns)} FROM "{table_name}" ORDER BY id'
            )
        ]


def get_crm_state() -> dict[str, dict[str, Any]]:
    with connect_crm_db() as connection:
        connection.row_factory = sqlite3.Row
        return {
            row["facebookUrl"]: dict(row)
            for row in connection.execute(
                """
                SELECT facebookUrl, thumbnailPath, remoteImageUrl, title
                , availabilityStatus, availabilityConfidence, availabilityReason
                FROM Listing
                """
            )
        }


def get_crm_stats() -> dict[str, int]:
    with connect_crm_db() as connection:
        count = connection.execute("SELECT COUNT(*) FROM Listing").fetchone()[0]
        with_images = connection.execute(
            "SELECT COUNT(*) FROM Listing WHERE thumbnailPath IS NOT NULL"
        ).fetchone()[0]
    return {"stored": count, "with_images": with_images}


def row_needs_import(
    row: dict[str, Any],
    crm_state: dict[str, dict[str, Any]],
    refresh_existing: bool,
) -> bool:
    if refresh_existing:
        return True

    existing = crm_state.get(str(row["url"]))
    if existing is None:
        # Once the market-index service is installed, new n8n rows are published
        # by the valuation endpoint only after comparable evidence is available.
        return not VALUATION_DB.exists()

    return not existing.get("thumbnailPath")


async def fetch_listing_detail(page: Any, row: dict[str, Any]) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "title": row["title"],
        "category": None,
        "remoteImageUrl": None,
    }
    try:
        await page.goto(row["url"], wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(2_500)
        data = await page.evaluate(
            """() => ({
                pageTitle: document.title || "",
                h1: Array.from(document.querySelectorAll("h1"))
                    .map((element) => element.textContent || "")
                    .map((text) => text.trim())
                    .filter(Boolean)
                    .slice(0, 3),
                ogImage: Array.from(
                    document.querySelectorAll('meta[property="og:image"], meta[name="twitter:image"]')
                )
                    .map((element) => element.getAttribute("content") || "")
                    .filter(Boolean)
                    .slice(0, 3)
            })"""
        )
    except PlaywrightTimeoutError:
        return detail
    except Exception:
        return detail

    h1_values = data.get("h1") or []
    if h1_values:
        detail["title"] = str(h1_values[0]).strip()
    elif data.get("pageTitle"):
        detail["title"] = clean_title(str(data["pageTitle"]))

    detail["category"] = parse_category(str(data.get("pageTitle") or ""))
    image_values = data.get("ogImage") or []
    if image_values:
        detail["remoteImageUrl"] = image_values[0]

    return detail


def cache_thumbnail(item_id: str, image_url: str | None) -> tuple[str | None, str | None]:
    if not image_url:
        return None, None

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    image_path = IMAGE_DIR / f"{item_id}.jpg"
    public_path = f"/listing-images/{item_id}.jpg"

    if image_path.exists() and image_path.stat().st_size > 0:
        return public_path, image_url

    try:
        response = requests.get(
            image_url,
            headers={"User-Agent": MODERN_USER_AGENT},
            timeout=25,
        )
        response.raise_for_status()
    except requests.RequestException:
        return None, image_url

    image_path.write_bytes(response.content)
    return public_path, image_url


def upsert_listing(connection: sqlite3.Connection, row: dict[str, Any]) -> None:
    availability_status = normalize_availability_status(
        row.get("availabilityStatus")
    ) or "ACTIVE"
    availability_confidence = normalize_availability_confidence(
        row.get("availabilityConfidence")
    )
    availability_reason = str(row.get("availabilityReason") or "").strip() or None
    last_seen_at = optional_sqlite_timestamp(row.get("lastSeen"))
    consecutive_unavailable_checks = 1 if availability_status == "POSSIBLY_SOLD" else 0
    unavailable_since = row.get("lastSeen") if availability_status == "POSSIBLY_SOLD" else None

    connection.execute(
        """
        INSERT INTO Listing (
            id,
            facebookUrl,
            facebookItemId,
            title,
            askingPriceCents,
            category,
            source,
            thumbnailPath,
            remoteImageUrl,
            imageCachedAt,
            status,
            riskLevel,
            extractedYear,
            make,
            model,
            availabilityStatus,
            availabilityConfidence,
            availabilityReason,
            lastVerifiedAt,
            lastSeenAt,
            consecutiveUnavailableChecks,
            unavailableCheckCount,
            unavailableSince,
            firstSeenAt,
            createdAt,
            updatedAt
        )
        VALUES (?, ?, ?, ?, ?, ?, 'FACEBOOK_MARKETPLACE', ?, ?, ?, 'NEW', 'UNKNOWN', ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(facebookUrl) DO UPDATE SET
            title = excluded.title,
            askingPriceCents = excluded.askingPriceCents,
            category = COALESCE(excluded.category, Listing.category),
            thumbnailPath = COALESCE(excluded.thumbnailPath, Listing.thumbnailPath),
            remoteImageUrl = COALESCE(excluded.remoteImageUrl, Listing.remoteImageUrl),
            imageCachedAt = COALESCE(excluded.imageCachedAt, Listing.imageCachedAt),
            extractedYear = COALESCE(excluded.extractedYear, Listing.extractedYear),
            make = COALESCE(excluded.make, Listing.make),
            model = COALESCE(excluded.model, Listing.model),
            availabilityStatus = excluded.availabilityStatus,
            availabilityConfidence = excluded.availabilityConfidence,
            availabilityReason = COALESCE(excluded.availabilityReason, Listing.availabilityReason),
            lastVerifiedAt = COALESCE(excluded.lastVerifiedAt, Listing.lastVerifiedAt),
            lastSeenAt = CASE
                WHEN excluded.availabilityStatus = 'ACTIVE' THEN COALESCE(excluded.lastSeenAt, CURRENT_TIMESTAMP)
                WHEN excluded.lastSeenAt IS NOT NULL THEN excluded.lastSeenAt
                ELSE Listing.lastSeenAt
            END,
            unavailableSince = CASE
                WHEN excluded.availabilityStatus = 'ACTIVE' THEN NULL
                WHEN excluded.availabilityStatus = 'POSSIBLY_SOLD' THEN COALESCE(Listing.unavailableSince, excluded.unavailableSince)
                ELSE Listing.unavailableSince
            END,
            consecutiveUnavailableChecks = CASE
                WHEN excluded.availabilityStatus = 'ACTIVE' THEN 0
                WHEN excluded.availabilityStatus = 'POSSIBLY_SOLD' THEN MAX(Listing.consecutiveUnavailableChecks, 1)
                ELSE Listing.consecutiveUnavailableChecks
            END,
            unavailableCheckCount = CASE
                WHEN excluded.availabilityStatus = 'ACTIVE' THEN 0
                WHEN excluded.availabilityStatus = 'POSSIBLY_SOLD' THEN MAX(Listing.unavailableCheckCount, 1)
                ELSE Listing.unavailableCheckCount
            END,
            firstSeenAt = MIN(Listing.firstSeenAt, excluded.firstSeenAt),
            updatedAt = CURRENT_TIMESTAMP
        """,
        (
            stable_id(row["url"]),
            row["url"],
            facebook_item_id(row["url"]),
            row["title"],
            row["askingPriceCents"],
            row["category"],
            row["thumbnailPath"],
            row["remoteImageUrl"],
            row["imageCachedAt"],
            row["extractedYear"],
            row["make"],
            row["model"],
            availability_status,
            availability_confidence,
            availability_reason,
            last_seen_at,
            last_seen_at,
            consecutive_unavailable_checks,
            consecutive_unavailable_checks,
            optional_sqlite_timestamp(unavailable_since),
            row["firstSeenAt"],
        ),
    )


def sync_existing_listing_metadata(
    connection: sqlite3.Connection,
    rows: list[dict[str, Any]],
) -> int:
    """Update lightweight n8n status metadata for rows already in the CRM."""
    updated = 0
    for row in rows:
        url = str(row.get("url") or "").strip()
        if not url:
            continue

        availability_status = normalize_availability_status(
            row.get("availabilityStatus")
        )
        if availability_status is None:
            continue

        availability_confidence = normalize_availability_confidence(
            row.get("availabilityConfidence")
        )
        availability_reason = str(row.get("filterReason") or "").strip() or None
        last_seen_at = optional_sqlite_timestamp(row.get("lastSeen"))
        unavailable_since = (
            last_seen_at if availability_status == "POSSIBLY_SOLD" else None
        )

        cursor = connection.execute(
            """
            UPDATE Listing
            SET
              availabilityStatus = ?,
              availabilityConfidence = ?,
              availabilityReason = COALESCE(?, availabilityReason),
              lastVerifiedAt = COALESCE(?, lastVerifiedAt),
              lastSeenAt = CASE
                WHEN ? = 'ACTIVE' THEN COALESCE(?, CURRENT_TIMESTAMP)
                WHEN ? IS NOT NULL THEN ?
                ELSE lastSeenAt
              END,
              unavailableSince = CASE
                WHEN ? = 'ACTIVE' THEN NULL
                WHEN ? = 'POSSIBLY_SOLD' THEN COALESCE(unavailableSince, ?)
                ELSE unavailableSince
              END,
              consecutiveUnavailableChecks = CASE
                WHEN ? = 'ACTIVE' THEN 0
                WHEN ? = 'POSSIBLY_SOLD' THEN MAX(consecutiveUnavailableChecks, 1)
                ELSE consecutiveUnavailableChecks
              END,
              unavailableCheckCount = CASE
                WHEN ? = 'ACTIVE' THEN 0
                WHEN ? = 'POSSIBLY_SOLD' THEN MAX(unavailableCheckCount, 1)
                ELSE unavailableCheckCount
              END,
              updatedAt = CURRENT_TIMESTAMP
            WHERE facebookUrl = ?
            """,
            (
                availability_status,
                availability_confidence,
                availability_reason,
                last_seen_at,
                availability_status,
                last_seen_at,
                last_seen_at,
                last_seen_at,
                availability_status,
                availability_status,
                unavailable_since,
                availability_status,
                availability_status,
                availability_status,
                availability_status,
                url,
            ),
        )
        updated += cursor.rowcount

    return updated


def archive_existing_non_car_rows(
    connection: sqlite3.Connection,
    rows: list[dict[str, Any]],
) -> int:
    """Hide previously imported rows that are clearly not passenger cars."""
    archived = 0
    for row in rows:
        url = str(row.get("url") or "").strip()
        category = str(row.get("category") or "").strip()
        if not url or not category:
            continue
        if is_strict_car_listing(str(row.get("title") or ""), category):
            continue
        cursor = connection.execute(
            """
            UPDATE Listing
            SET
              status = 'ARCHIVED',
              availabilityStatus = 'UNAVAILABLE',
              availabilityConfidence = 'HIGH',
              availabilityReason = 'excluded_non_passenger_vehicle',
              updatedAt = CURRENT_TIMESTAMP
            WHERE facebookUrl = ?
            """,
            (url,),
        )
        archived += cursor.rowcount
    return archived


async def import_rows(
    limit: int | None,
    skip_images: bool,
    refresh_existing: bool = False,
) -> dict[str, int]:
    all_rows = get_n8n_rows()
    if limit:
        all_rows = all_rows[-limit:]
    rows = [row for row in all_rows if is_active_passenger_car_row(row)]
    filtered_out = len(all_rows) - len(rows)

    CRM_DB.parent.mkdir(parents=True, exist_ok=True)
    if not CRM_DB.exists():
        raise FileNotFoundError(
            f"CRM database not found: {CRM_DB}. Run `npm.cmd run db:init` first."
        )

    crm_state = get_crm_state()
    rows_to_process = [
        row for row in rows if row_needs_import(row, crm_state, refresh_existing)
    ]

    if not rows_to_process:
        with connect_crm_db() as connection:
            metadata_updated = sync_existing_listing_metadata(connection, all_rows)
            archived_non_cars = archive_existing_non_car_rows(connection, all_rows)
            connection.commit()
        stats = get_crm_stats()
        return {
            "read": len(all_rows),
            "processed": 0,
            "skipped_existing": len(rows),
            "filtered_out": filtered_out,
            "metadata_updated": metadata_updated,
            "archived_non_cars": archived_non_cars,
            **stats,
        }

    prepared: list[dict[str, Any]] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=MODERN_USER_AGENT,
            viewport={"width": 1440, "height": 1200},
            locale="en-NZ",
            extra_http_headers={"Accept-Language": "en-NZ,en;q=0.9"},
        )
        page = await context.new_page()
        for index, row in enumerate(rows_to_process, 1):
            url = str(row["url"])
            item_id = facebook_item_id(url) or hashlib.sha1(url.encode()).hexdigest()[:16]
            detail = await fetch_listing_detail(page, row)
            thumbnail_path, remote_image_url = (
                (None, detail.get("remoteImageUrl"))
                if skip_images
                else cache_thumbnail(item_id, detail.get("remoteImageUrl"))
            )
            title = str(detail.get("title") or row["title"]).strip()
            extracted_year, make, model = extract_year_make_model(title)
            prepared.append(
                {
                    "url": url,
                    "title": title,
                    "askingPriceCents": cents_from_price(row["price"]),
                    "category": detail.get("category"),
                    "availabilityStatus": row.get("availabilityStatus"),
                    "availabilityConfidence": row.get("availabilityConfidence"),
                    "availabilityReason": row.get("filterReason"),
                    "lastSeen": row.get("lastSeen"),
                    "thumbnailPath": thumbnail_path,
                    "remoteImageUrl": remote_image_url,
                    "imageCachedAt": now_iso() if thumbnail_path else None,
                    "extractedYear": extracted_year,
                    "make": make,
                    "model": model,
                    "firstSeenAt": sqlite_timestamp(row.get("firstSeen")),
                }
            )
            print(
                f"[IMPORT] {index}/{len(rows_to_process)} {console_text(title)}",
                flush=True,
            )
            await asyncio.sleep(0.25)

        await context.close()
        await browser.close()

    with connect_crm_db() as connection:
        for row in prepared:
            upsert_listing(connection, row)
        metadata_updated = sync_existing_listing_metadata(connection, all_rows)
        archived_non_cars = archive_existing_non_car_rows(connection, all_rows)
        connection.commit()
    stats = get_crm_stats()
    return {
        "read": len(all_rows),
        "processed": len(prepared),
        "skipped_existing": len(rows) - len(prepared),
        "filtered_out": filtered_out,
        "metadata_updated": metadata_updated,
        "archived_non_cars": archived_non_cars,
        **stats,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--skip-images", action="store_true")
    parser.add_argument("--refresh-existing", action="store_true")
    return parser.parse_args()


async def main() -> None:
    started = time.monotonic()
    args = parse_args()
    result = await import_rows(args.limit, args.skip_images, args.refresh_existing)
    result["elapsed_seconds"] = int(time.monotonic() - started)
    print(f"[IMPORT] Completed: {result}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
