"""Evidence-backed exact and provisional NZ asking-market valuations."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Iterable

from .dedupe import deduplicate
from .matching import MatchResult, compatible, same_identity, same_price_identity
from .normalization import NormalizedVehicle, model_year_is_plausible, normalize_token, price_family

MIN_SAFE_EXACT_COMPARABLES = 5
MIN_SAFE_SOURCES = 2
MIN_GENERATION_COMPARABLES = 3
MIN_MODEL_ADJUSTED_COMPARABLES = 5
MIN_MAKE_CLASS_COMPARABLES = 8
MIN_NZ_CLASS_COMPARABLES = 12
MODEL_ADJUSTED_MAX_YEAR_DELTA = 5


@dataclass
class ComparableDecision:
    item: Any
    match: MatchResult


@dataclass
class ValuationResult:
    status: str
    market_value_cents: int | None
    comparable_count: int
    lowest_cents: int | None
    highest_cents: int | None
    auckland_median_cents: int | None
    difference_cents: int | None
    difference_percent: float | None
    relation: str | None
    verdict: str | None
    confidence: str
    reason: str
    target_sell_cents: int | None
    max_buy_cents: int | None
    expected_spread_cents: int | None
    source_breakdown: dict[str, int] = field(default_factory=dict)
    decisions: list[ComparableDecision] = field(default_factory=list)
    method: str = "EXPANDING_SEARCH"
    raw_median_cents: int | None = None
    exact_count: int = 0
    adjustment_summary: dict[str, Any] = field(default_factory=dict)


def verdict_for_percentage(value: float) -> tuple[str, str]:
    if value > 10:
        return "EXCELLENT_DEAL", "BELOW_MARKET"
    if value >= 5:
        return "GOOD_DEAL", "BELOW_MARKET"
    if value > -5:
        return "FAIR_MARKET_VALUE", "AT_MARKET"
    if value >= -10:
        return "OVERPRICED", "ABOVE_MARKET"
    return "VERY_OVERPRICED", "ABOVE_MARKET"


def usable(item: Any) -> bool:
    return (
        int(getattr(item, "asking_price_cents", 0) or 0) > 0
        and getattr(item, "sale_type", "FIXED_PRICE") == "FIXED_PRICE"
        and getattr(item, "status", "ACTIVE") in {"ACTIVE", "HISTORICAL"}
    )


def same_make(target: NormalizedVehicle, item: Any) -> bool:
    return bool(
        normalize_token(target.make)
        and normalize_token(target.make) == normalize_token(getattr(item, "make", None))
    )


def year_delta(target: NormalizedVehicle, item: Any) -> int | None:
    item_year = getattr(item, "year", None)
    return abs(target.year - item_year) if target.year and item_year else None


def has_core_identity(target: NormalizedVehicle) -> bool:
    return bool(
        normalize_token(target.make)
        and normalize_token(target.model)
        and target.year
        and model_year_is_plausible(target)
    )


def requires_variant_match(target: NormalizedVehicle) -> bool:
    return bool(normalize_token(target.make) == "bmw" and normalize_token(target.variant))


def same_required_variant(target: NormalizedVehicle, item: Any) -> bool:
    return same_price_identity(target, item)


def robust_price_items(items: list[Any]) -> tuple[list[Any], set[int]]:
    if len(items) < 7:
        return items, set()
    middle = float(median(int(item.asking_price_cents) for item in items))
    deviations = [abs(int(item.asking_price_cents) - middle) for item in items]
    mad = float(median(deviations))
    threshold = max(middle * 0.50, mad * 3.5, 100_000)
    accepted = [item for item in items if abs(int(item.asking_price_cents) - middle) <= threshold]
    rejected = {id(item) for item in items if item not in accepted}
    return accepted, rejected


def distinct_sources(items: list[Any]) -> set[str]:
    return {
        str(getattr(item, "source_id", "")).strip()
        for item in items
        if str(getattr(item, "source_id", "")).strip()
    }


def class_compatible(target: NormalizedVehicle, item: Any) -> bool:
    if not target.body_type and not target.fuel_type:
        return False
    checks = []
    if target.body_type:
        checks.append(compatible(target.body_type, getattr(item, "body_type", None)))
    if target.fuel_type:
        checks.append(compatible(target.fuel_type, getattr(item, "fuel_type", None)))
    return all(checks) if checks else True


def median_slope(points: list[tuple[int, int]], cap: int) -> int:
    slopes: list[float] = []
    for index, (x_one, y_one) in enumerate(points):
        for x_two, y_two in points[index + 1:]:
            if x_one != x_two:
                slopes.append((y_two - y_one) / (x_two - x_one))
    if not slopes:
        return 0
    return round(max(-cap, min(cap, median(slopes))))


def adjusted_prices(
    target: NormalizedVehicle,
    items: list[Any],
    *,
    adjust_kms: bool,
) -> tuple[list[int], dict[str, Any]]:
    prices = [int(item.asking_price_cents) for item in items]
    raw_median = round(median(prices))
    year_points = [
        (int(item.year), int(item.asking_price_cents))
        for item in items if getattr(item, "year", None)
    ]
    year_cap = max(50_000, round(raw_median * 0.20))
    year_slope = median_slope(year_points, year_cap)
    km_points = [
        (int(item.kms), int(item.asking_price_cents))
        for item in items if getattr(item, "kms", None)
    ]
    km_slope = median_slope(km_points, 100) if adjust_kms and target.kms else 0
    adjusted: list[int] = []
    for item in items:
        value = int(item.asking_price_cents)
        if target.year and getattr(item, "year", None):
            value += year_slope * (target.year - int(item.year))
        if target.kms and getattr(item, "kms", None) and km_slope:
            value += km_slope * (target.kms - int(item.kms))
        adjusted.append(max(50_000, value))
    return adjusted, {
        "rawMedianCents": raw_median,
        "observedYearSlopeCents": year_slope,
        "observedKmSlopeCentsPerKm": km_slope,
    }


def select_cohort(target: NormalizedVehicle, items: list[Any]) -> tuple[str, list[Any], list[int], dict[str, Any]]:
    if not has_core_identity(target):
        invalid_year = bool(target.year and target.make and target.model)
        return "EXPANDING_SEARCH", [], [], {
            "reason": (
                "The supplied year is not plausible for this model, so the listing is quarantined until its identity is verified."
                if invalid_year
                else "A numeric market value needs a confirmed year, make, and model before comparables are trusted."
            ),
            "safeStatus": "AWAITING_SAFE_EVIDENCE",
        }

    exact_model = [item for item in items if usable(item) and same_identity(target, item)]
    exact_identity = [item for item in exact_model if same_required_variant(target, item)]
    exact_year = [
        item for item in exact_identity
        if target.year is not None and getattr(item, "year", None) == target.year
    ]
    exact_year, outlier_ids = robust_price_items(exact_year)
    exact_sources = distinct_sources(exact_year)
    if len(exact_year) >= MIN_SAFE_EXACT_COMPARABLES and len(exact_sources) >= MIN_SAFE_SOURCES:
        prices = [int(item.asking_price_cents) for item in exact_year]
        return "EXACT", exact_year, prices, {
            "rawMedianCents": round(median(prices)),
            "sourceCount": len(exact_sources),
            "sources": sorted(exact_sources),
            "statisticalOutliersExcluded": len(outlier_ids),
            "priceFamily": price_family(target),
        }
    if exact_year or outlier_ids:
        return "EXPANDING_SEARCH", [], [], {
            "reason": (
                f"Only {len(exact_year)} compatible same-year comparables from {len(exact_sources)} source(s) passed safety checks; "
                f"at least {MIN_SAFE_EXACT_COMPARABLES} comparables from {MIN_SAFE_SOURCES} sources are required."
            ),
            "safeStatus": "AWAITING_SAFE_EVIDENCE",
            "compatibleExactFound": len(exact_year),
            "sourceCount": len(exact_sources),
            "statisticalOutliersExcluded": len(outlier_ids),
            "priceFamily": price_family(target),
        }

    generation = [
        item for item in exact_identity
        if year_delta(target, item) is not None and year_delta(target, item) <= 2
    ]
    if len(generation) >= MIN_GENERATION_COMPARABLES:
        _adjusted, summary = adjusted_prices(target, generation, adjust_kms=True)
        return "EXPANDING_SEARCH", [], [], {
            **summary,
            "reason": "Near-year evidence exists, but only same-year compatible listings may publish a safe deal score.",
            "safeStatus": "AWAITING_SAFE_EVIDENCE",
            "nearGenerationFound": len(generation),
        }

    model_window = [
        item for item in exact_identity
        if year_delta(target, item) is not None
        and year_delta(target, item) <= MODEL_ADJUSTED_MAX_YEAR_DELTA
    ]
    if (
        len(model_window) >= MIN_MODEL_ADJUSTED_COMPARABLES
        and any((year_delta(target, item) or 99) <= 3 for item in model_window)
    ):
        _adjusted, summary = adjusted_prices(target, model_window, adjust_kms=True)
        return "EXPANDING_SEARCH", [], [], {
            **summary,
            "reason": "Model evidence exists outside the exact year, but it is not safe enough to publish a deal score.",
            "safeStatus": "AWAITING_SAFE_EVIDENCE",
            "yearWindow": f"+/-{MODEL_ADJUSTED_MAX_YEAR_DELTA}",
            "safetyRule": "Far-newer or far-older same-model listings are not used for known-year targets.",
        }

    make_class = [
        item for item in items
        if usable(item)
        and same_make(target, item)
        and class_compatible(target, item)
        and year_delta(target, item) is not None
        and year_delta(target, item) <= 2
    ]
    if len(make_class) >= MIN_MAKE_CLASS_COMPARABLES:
        return "EXPANDING_SEARCH", [], [], {
            "reason": "Only make/class evidence is available; it is retained for audit but cannot publish a valuation.",
            "safeStatus": "AWAITING_SAFE_EVIDENCE",
            "makeClassFound": len(make_class),
        }

    nz_class = [
        item for item in items
        if usable(item)
        and class_compatible(target, item)
        and year_delta(target, item) is not None
        and year_delta(target, item) <= 2
    ]
    if len(nz_class) >= MIN_NZ_CLASS_COMPARABLES:
        return "EXPANDING_SEARCH", [], [], {
            "reason": "Only broad NZ class evidence is available; it is retained for audit but cannot publish a valuation.",
            "safeStatus": "AWAITING_SAFE_EVIDENCE",
            "nzClassFound": len(nz_class),
        }
    return "EXPANDING_SEARCH", [], [], {
        "reason": (
            "No safe evidence cohort is ready yet. The worker will keep searching instead of using "
            "far-newer, far-older, or unidentified vehicles as the market median."
        ),
        "sameModelFound": len(exact_model),
        "sameRequiredVariantFound": len(exact_identity),
        "nearGenerationFound": len(generation),
        "modelWindowFound": len(model_window),
        "makeClassFound": len(make_class),
        "nzClassFound": len(nz_class),
        "safeStatus": "AWAITING_SAFE_EVIDENCE",
    }


def confidence_for(method: str, count: int) -> str:
    if method == "EXACT":
        if count >= 10:
            return "EXACT_HIGH"
        if count >= 5:
            return "EXACT_MEDIUM"
        return "EXACT_LOW"
    return method


def value_vehicle(target: NormalizedVehicle, asking_price_cents: int, items: Iterable[Any]) -> ValuationResult:
    unique_items = deduplicate(items)
    method, accepted_items, calculated_prices, adjustment = select_cohort(target, unique_items)
    exact_count = sum(
        1 for item in unique_items
        if (
            usable(item)
            and same_identity(target, item)
            and same_required_variant(target, item)
            and target.year
            and getattr(item, "year", None) == target.year
        )
    )
    accepted_ids = {id(item) for item in accepted_items}

    def exclusion_reason(item: Any) -> str:
        if not usable(item):
            return "not_usable_fixed_price"
        if not same_identity(target, item):
            return "make_model_mismatch"
        if target.year != getattr(item, "year", None):
            return "year_or_generation_mismatch"
        if not same_price_identity(target, item):
            return "price_sensitive_variant_mismatch"
        return "outside_safe_evidence_cohort"

    decisions = [
        ComparableDecision(
            item=item,
            match=MatchResult(
                id(item) in accepted_ids,
                method if id(item) in accepted_ids else None,
                100.0 if id(item) in accepted_ids else 0.0,
                None if id(item) in accepted_ids else exclusion_reason(item),
            ),
        )
        for item in unique_items
    ]

    if not accepted_items:
        reason = str(
            adjustment.get("reason")
            or "No usable prices are indexed yet; the worker will keep expanding the nationwide search."
        )
        return ValuationResult(
            status=str(adjustment.get("safeStatus") or "AWAITING_SAFE_EVIDENCE"), market_value_cents=None, comparable_count=0,
            lowest_cents=None, highest_cents=None, auckland_median_cents=None,
            difference_cents=None, difference_percent=None, relation=None, verdict=None,
            confidence="SEARCHING", reason=reason,
            target_sell_cents=None, max_buy_cents=None, expected_spread_cents=None,
            decisions=decisions, method=method, exact_count=exact_count,
            adjustment_summary=adjustment,
        )

    raw_prices = [int(item.asking_price_cents) for item in accepted_items]
    market_value = round(median(calculated_prices))
    raw_median = round(median(raw_prices))
    difference = market_value - asking_price_cents
    percentage = round((difference / market_value) * 100, 2) if market_value else 0.0
    verdict, relation = verdict_for_percentage(percentage)
    confidence = confidence_for(method, len(accepted_items))
    auckland_prices = [
        int(item.asking_price_cents)
        for item in accepted_items
        if normalize_token(getattr(item, "region", None)) == "auckland"
    ]
    auckland_median = round(median(auckland_prices)) if len(auckland_prices) >= 5 else None
    source_counts = Counter(str(getattr(item, "source_id", "unknown")) for item in accepted_items)
    target_sell = round(market_value * 0.8)
    direction = "below" if difference > 0 else "above" if difference < 0 else "at"
    if method == "EXACT":
        target_name = f"{target.year} {target.make} {target.model}"
        if requires_variant_match(target):
            target_name = f"{target_name} {target.variant}"
        reason = (
            f"The asking price is {abs(percentage):.1f}% {direction} the nationwide raw median "
            f"of every {target_name} fixed-price listing found ({len(accepted_items)} deduplicated)."
        )
    else:
        reason = (
            f"The asking price is {abs(percentage):.1f}% {direction} a {method.lower().replace('_', ' ')} "
            f"estimate based on {len(accepted_items)} deduplicated NZ asking prices. The raw evidence median was "
            f"${raw_median / 100:,.0f}."
        )
    return ValuationResult(
        status="VALUED",
        market_value_cents=market_value,
        comparable_count=len(accepted_items),
        lowest_cents=min(raw_prices), highest_cents=max(raw_prices),
        auckland_median_cents=auckland_median,
        difference_cents=difference, difference_percent=percentage,
        relation=relation, verdict=verdict, confidence=confidence, reason=reason,
        target_sell_cents=target_sell, max_buy_cents=target_sell - 100_000,
        expected_spread_cents=target_sell - asking_price_cents,
        source_breakdown=dict(source_counts), decisions=decisions, method=method,
        raw_median_cents=raw_median, exact_count=exact_count,
        adjustment_summary={**adjustment, "adjustedMedianCents": market_value},
    )
