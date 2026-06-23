"""Cross-source comparable deduplication."""

from __future__ import annotations

from hashlib import sha256
from typing import Any, Iterable

from .normalization import normalize_token


def dedupe_key(item: Any) -> str:
    plate = normalize_token(getattr(item, "plate", None))
    vin = normalize_token(getattr(item, "vin", None))
    stock = normalize_token(getattr(item, "stock_number", None))
    seller = normalize_token(getattr(item, "seller_name", None))
    if vin:
        raw = f"vin|{vin}"
    elif plate:
        raw = f"plate|{plate}"
    elif stock and seller:
        raw = f"stock|{seller}|{stock}"
    elif getattr(item, "image_hash", None):
        raw = "|".join(
            str(value or "")
            for value in (
                "image", getattr(item, "image_hash", None), getattr(item, "year", None),
                normalize_token(getattr(item, "make", None)),
                normalize_token(getattr(item, "model", None)),
            )
        )
    else:
        kms = getattr(item, "kms", None)
        price = getattr(item, "asking_price_cents", 0)
        rounded_kms = round(kms / 1000) * 1000 if kms else 0
        rounded_price = round(price / 10_000) * 10_000 if price else 0
        raw = "|".join(
            str(value or "")
            for value in (
                getattr(item, "year", None), normalize_token(getattr(item, "make", None)),
                normalize_token(getattr(item, "model", None)), normalize_token(getattr(item, "variant", None)),
                rounded_kms, rounded_price, seller, normalize_token(getattr(item, "region", None)),
            )
        )
    return sha256(raw.encode("utf-8")).hexdigest()


def deduplicate(items: Iterable[Any]) -> list[Any]:
    by_key: dict[str, Any] = {}
    for item in items:
        key = getattr(item, "dedupe_key", None) or dedupe_key(item)
        current = by_key.get(key)
        if current is None:
            by_key[key] = item
            continue
        current_seen = getattr(current, "last_seen_at", None)
        candidate_seen = getattr(item, "last_seen_at", None)
        is_newer = bool(
            candidate_seen
            and (
                not current_seen
                or candidate_seen.timestamp() > current_seen.timestamp()
            )
        )
        if is_newer:
            by_key[key] = item
    return list(by_key.values())
