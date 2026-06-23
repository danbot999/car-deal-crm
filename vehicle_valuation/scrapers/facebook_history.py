"""Comparable adapter over already-collected Facebook Marketplace history."""

from __future__ import annotations

import sqlite3
import time

from ..config import CRM_DATABASE_PATH
from ..normalization import NormalizedVehicle, vehicle_from_text
from .base import RawListing, SearchResult


class FacebookHistoryAdapter:
    source_id = "facebook_marketplace"

    def search(self, target: NormalizedVehicle, deadline: float) -> SearchResult:
        result = SearchResult(source_id=self.source_id, pages_scanned=1)
        if not CRM_DATABASE_PATH.exists() or not target.make or not target.model:
            result.status = "SKIPPED"
            result.error = "Local CRM history or target identity is unavailable."
            return result
        if time.monotonic() >= deadline:
            result.status = "SKIPPED"
            result.error = "Live-search deadline reached."
            return result
        with sqlite3.connect(CRM_DATABASE_PATH, timeout=30) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT facebookUrl, facebookItemId, title, askingPriceCents,
                       extractedYear, make, model, kms, firstSeenAt,
                       lastSeenAt, availabilityStatus
                FROM Listing
                WHERE lower(COALESCE(make, title)) LIKE ?
                  AND lower(COALESCE(model, title)) LIKE ?
                ORDER BY COALESCE(lastSeenAt, firstSeenAt) DESC
                LIMIT 250
                """,
                (f"%{target.make.lower()}%", f"%{target.model.lower()}%"),
            ).fetchall()
        for row in rows:
            vehicle = vehicle_from_text(
                row["title"],
                supplied={"year": row["extractedYear"], "make": row["make"], "model": row["model"], "kms": row["kms"]},
            )
            result.listings.append(
                RawListing(
                    source_id=self.source_id, source_listing_id=row["facebookItemId"] or row["facebookUrl"],
                    url=row["facebookUrl"], title=row["title"], asking_price_cents=row["askingPriceCents"],
                    year=vehicle.year, make=vehicle.make, model=vehicle.model, variant=vehicle.variant,
                    kms=vehicle.kms, transmission=vehicle.transmission, fuel_type=vehicle.fuel_type,
                    body_type=vehicle.body_type, region="Auckland", seller_type="PRIVATE",
                    status="ACTIVE" if row["availabilityStatus"] == "ACTIVE" else "HISTORICAL",
                )
            )
        return result
