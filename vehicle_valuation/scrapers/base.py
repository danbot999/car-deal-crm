"""Shared scraper contracts and factual listing shape."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from ..normalization import NormalizedVehicle


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RawListing:
    source_id: str
    source_listing_id: str
    url: str
    title: str
    asking_price_cents: int
    year: int | None = None
    make: str | None = None
    model: str | None = None
    variant: str | None = None
    kms: int | None = None
    transmission: str | None = None
    fuel_type: str | None = None
    body_type: str | None = None
    region: str | None = None
    seller_name: str | None = None
    seller_type: str = "UNKNOWN"
    sale_type: str = "FIXED_PRICE"
    stock_number: str | None = None
    plate: str | None = None
    vin: str | None = None
    image_url: str | None = None
    image_hash: str | None = None
    status: str = "ACTIVE"
    raw_facts: dict[str, object] = field(default_factory=dict)
    observed_at: datetime = field(default_factory=utcnow)


@dataclass
class SearchResult:
    source_id: str
    listings: list[RawListing] = field(default_factory=list)
    pages_scanned: int = 0
    rejected: int = 0
    status: str = "SUCCESS"
    error: str | None = None


class SourceAdapter(Protocol):
    source_id: str

    def search(self, target: NormalizedVehicle, deadline: float) -> SearchResult:
        ...
