"""Staged comparable matching."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .normalization import (
    NormalizedVehicle,
    engine_capacity_band,
    normalize_token,
    price_family,
)


@dataclass
class MatchResult:
    accepted: bool
    tier: str | None
    score: float
    reason: str | None = None


def same_identity(target: NormalizedVehicle, item: Any) -> bool:
    target_make = normalize_token(target.make)
    item_make = normalize_token(getattr(item, "make", None))
    target_model = normalize_token(target.model)
    item_model = normalize_token(getattr(item, "model", None))
    if not target_make or not target_model or not item_make or not item_model:
        return False
    return target_make == item_make and target_model == item_model


def compatible(target_value: str | None, item_value: str | None) -> bool:
    if not target_value or not item_value:
        return True
    return normalize_token(target_value) == normalize_token(item_value)


def same_price_identity(target: NormalizedVehicle, item: Any) -> bool:
    if price_family(target) != price_family(item):
        return False
    target_engine = engine_capacity_band(target)
    item_engine = engine_capacity_band(item)
    if target_engine and item_engine and abs(target_engine - item_engine) > 250:
        return False
    return True


def match_comparable(target: NormalizedVehicle, item: Any) -> MatchResult:
    if not same_identity(target, item):
        return MatchResult(False, None, 0, "make_model_mismatch")
    if getattr(item, "sale_type", "FIXED_PRICE") != "FIXED_PRICE":
        return MatchResult(False, None, 0, "not_fixed_price")
    if getattr(item, "status", "ACTIVE") not in {"ACTIVE", "HISTORICAL"}:
        return MatchResult(False, None, 0, "inactive")
    if not same_price_identity(target, item):
        return MatchResult(False, None, 0, "price_sensitive_variant_mismatch")

    item_year = getattr(item, "year", None)
    item_kms = getattr(item, "kms", None)
    year_delta = abs(target.year - item_year) if target.year and item_year else None
    km_delta = abs(target.kms - item_kms) if target.kms and item_kms else None
    strict_km = max(20_000, round(target.kms * 0.25)) if target.kms else None
    wide_km = max(30_000, round(target.kms * 0.35)) if target.kms else None
    fields_compatible = all(
        (
            compatible(target.transmission, getattr(item, "transmission", None)),
            compatible(target.fuel_type, getattr(item, "fuel_type", None)),
            compatible(target.body_type, getattr(item, "body_type", None)),
        )
    )
    item_variant = getattr(item, "variant", None)
    variant_exact = compatible(target.variant, item_variant)
    strict_variant = not target.variant or bool(item_variant and variant_exact)
    strict_kms_ok = (
        target.kms is None
        or bool(item_kms is not None and km_delta is not None and strict_km is not None and km_delta <= strict_km)
    )
    wide_kms_ok = (
        target.kms is None
        or bool(item_kms is not None and km_delta is not None and wide_km is not None and km_delta <= wide_km)
    )

    if year_delta is not None and year_delta <= 1 and strict_kms_ok and fields_compatible and strict_variant:
        tier = "STRICT"
    elif year_delta is not None and year_delta <= 2 and wide_kms_ok and fields_compatible:
        tier = "WIDENED"
    elif year_delta is None or year_delta <= 3:
        tier = "BROAD"
    else:
        return MatchResult(False, None, 0, "outside_year_range")

    score = 40.0
    if year_delta is not None:
        score += max(0, 20 - year_delta * 7)
    else:
        score += 7
    if km_delta is not None and wide_km:
        score += max(0, 20 * (1 - km_delta / max(wide_km, 1)))
    else:
        score += 6
    score += 12 if variant_exact else 2
    score += 8 if fields_compatible else 0
    return MatchResult(True, tier, round(min(score, 100), 2))
