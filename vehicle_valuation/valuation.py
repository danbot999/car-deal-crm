"""Median market valuation and deal classification."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Iterable

from .dedupe import deduplicate
from .matching import MatchResult, match_comparable
from .normalization import NormalizedVehicle


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


def choose_accepted(decisions: list[ComparableDecision]) -> list[ComparableDecision]:
    strict = [decision for decision in decisions if decision.match.accepted and decision.match.tier == "STRICT"]
    widened = [decision for decision in decisions if decision.match.accepted and decision.match.tier in {"STRICT", "WIDENED"}]
    broad = [decision for decision in decisions if decision.match.accepted]
    if len(strict) >= 5:
        return strict
    if len(widened) >= 3:
        return widened
    return broad


def value_vehicle(target: NormalizedVehicle, asking_price_cents: int, items: Iterable[Any]) -> ValuationResult:
    unique_items = deduplicate(items)
    decisions = [ComparableDecision(item=item, match=match_comparable(target, item)) for item in unique_items]
    accepted = choose_accepted(decisions)
    accepted_ids = {id(decision.item) for decision in accepted}
    for decision in decisions:
        if decision.match.accepted and id(decision.item) not in accepted_ids:
            decision.match = MatchResult(False, decision.match.tier, decision.match.score, "stronger_match_tier_available")

    if not accepted:
        return ValuationResult(
            status="INSUFFICIENT_DATA", market_value_cents=None, comparable_count=0,
            lowest_cents=None, highest_cents=None, auckland_median_cents=None,
            difference_cents=None, difference_percent=None, relation=None, verdict=None,
            confidence="INSUFFICIENT", reason="No same-make/model comparable asking prices were found.",
            target_sell_cents=None, max_buy_cents=None, expected_spread_cents=None,
            decisions=decisions,
        )

    prices = [int(decision.item.asking_price_cents) for decision in accepted]
    market_value = round(median(prices))
    difference = market_value - asking_price_cents
    percentage = round((difference / market_value) * 100, 2) if market_value else 0.0
    verdict, relation = verdict_for_percentage(percentage)
    strict_count = sum(decision.match.tier == "STRICT" for decision in accepted)
    materially_missing = not target.year or not target.kms or not target.variant
    if strict_count >= 8 and not materially_missing:
        confidence = "HIGH"
    elif len(accepted) >= 5:
        confidence = "MEDIUM"
    elif len(accepted) >= 3:
        confidence = "LOW"
    else:
        confidence = "INDICATIVE"
    auckland_prices = [
        int(decision.item.asking_price_cents)
        for decision in accepted
        if str(getattr(decision.item, "region", "")).lower() == "auckland"
    ]
    auckland_median = round(median(auckland_prices)) if len(auckland_prices) >= 5 else None
    source_counts = Counter(str(getattr(decision.item, "source_id", "unknown")) for decision in accepted)
    target_sell = round(market_value * 0.8)
    direction = "below" if difference > 0 else "above" if difference < 0 else "at"
    reason = (
        f"The asking price is {abs(percentage):.1f}% {direction} the nationwide median "
        f"of {len(accepted)} deduplicated comparable fixed asking prices."
    )
    return ValuationResult(
        status="VALUED" if confidence != "INDICATIVE" else "INDICATIVE",
        market_value_cents=market_value, comparable_count=len(accepted),
        lowest_cents=min(prices), highest_cents=max(prices), auckland_median_cents=auckland_median,
        difference_cents=difference, difference_percent=percentage, relation=relation, verdict=verdict,
        confidence=confidence, reason=reason, target_sell_cents=target_sell,
        max_buy_cents=target_sell - 100_000, expected_spread_cents=target_sell - asking_price_cents,
        source_breakdown=dict(source_counts), decisions=decisions,
    )
