"""Evidence-backed exact and provisional NZ asking-market valuations."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Iterable

from .dedupe import deduplicate
from .matching import MatchResult, compatible, same_identity
from .normalization import NormalizedVehicle, normalize_token


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


def class_compatible(target: NormalizedVehicle, item: Any) -> bool:
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
    exact_model = [item for item in items if usable(item) and same_identity(target, item)]
    exact_year = [
        item for item in exact_model
        if target.year is not None and getattr(item, "year", None) == target.year
    ]
    if exact_year:
        prices = [int(item.asking_price_cents) for item in exact_year]
        return "EXACT", exact_year, prices, {"rawMedianCents": round(median(prices))}

    generation = [
        item for item in exact_model
        if year_delta(target, item) is not None and year_delta(target, item) <= 2
    ]
    if generation:
        adjusted, summary = adjusted_prices(target, generation, adjust_kms=True)
        return "GENERATION_ADJUSTED", generation, adjusted, summary

    if exact_model:
        adjusted, summary = adjusted_prices(target, exact_model, adjust_kms=True)
        return "MODEL_ADJUSTED", exact_model, adjusted, summary

    make_class = [
        item for item in items
        if usable(item)
        and same_make(target, item)
        and class_compatible(target, item)
        and (year_delta(target, item) is None or year_delta(target, item) <= 3)
    ]
    if make_class:
        adjusted, summary = adjusted_prices(target, make_class, adjust_kms=True)
        return "MAKE_CLASS_PROVISIONAL", make_class, adjusted, summary

    nz_class = [
        item for item in items
        if usable(item)
        and class_compatible(target, item)
        and (year_delta(target, item) is None or year_delta(target, item) <= 3)
    ]
    if not nz_class:
        nz_class = [item for item in items if usable(item)]
    if nz_class:
        adjusted, summary = adjusted_prices(target, nz_class, adjust_kms=True)
        return "CLASS_PROVISIONAL", nz_class, adjusted, summary
    return "EXPANDING_SEARCH", [], [], {}


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
        if usable(item) and same_identity(target, item) and target.year and getattr(item, "year", None) == target.year
    )
    accepted_ids = {id(item) for item in accepted_items}
    decisions = [
        ComparableDecision(
            item=item,
            match=MatchResult(
                id(item) in accepted_ids,
                method if id(item) in accepted_ids else None,
                100.0 if id(item) in accepted_ids else 0.0,
                None if id(item) in accepted_ids else "outside_selected_evidence_cohort",
            ),
        )
        for item in unique_items
    ]

    if not accepted_items:
        return ValuationResult(
            status="EXPANDING_SEARCH", market_value_cents=None, comparable_count=0,
            lowest_cents=None, highest_cents=None, auckland_median_cents=None,
            difference_cents=None, difference_percent=None, relation=None, verdict=None,
            confidence="SEARCHING", reason="No usable prices are indexed yet; the worker will keep expanding the nationwide search.",
            target_sell_cents=None, max_buy_cents=None, expected_spread_cents=None,
            decisions=decisions, method=method, exact_count=exact_count,
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
        reason = (
            f"The asking price is {abs(percentage):.1f}% {direction} the nationwide raw median "
            f"of every {target.year} {target.make} {target.model} fixed-price listing found ({len(accepted_items)} deduplicated)."
        )
    else:
        reason = (
            f"The asking price is {abs(percentage):.1f}% {direction} a {method.lower().replace('_', ' ')} "
            f"estimate based on {len(accepted_items)} deduplicated NZ asking prices. The raw evidence median was "
            f"${raw_median / 100:,.0f}."
        )
    return ValuationResult(
        status="VALUED" if method == "EXACT" else "PROVISIONAL",
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
