"""Persistence operations for jobs, comparables, coverage and valuations."""

from __future__ import annotations

import json
from datetime import timedelta
from hashlib import sha256
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .dedupe import dedupe_key
from .models import (
    ComparableListing, DealerSite, PriceObservation, ScrapeRun, Source, TargetVehicle,
    ValuationComparable, ValuationJob, ValuationPublication, ValuationRun, utcnow,
)
from .normalization import canonical_url, clean_text, source_listing_id, vehicle_from_text
from .schemas import TargetRequest
from .scrapers.base import RawListing, SearchResult
from .scrapers.catalog import source_definitions
from .scrapers.directories import DiscoveryResult
from .valuation import ValuationResult


def stable_crm_listing_id(url: str) -> str:
    from hashlib import sha1
    return "listing_" + sha1(canonical_url(url).encode("utf-8")).hexdigest()[:24]


def seed_sources(session: Session) -> None:
    for definition in source_definitions():
        source = session.get(Source, str(definition["id"]))
        values = {
            "name": str(definition["name"]), "base_url": str(definition["base_url"]),
            "role": str(definition["role"]), "adapter": str(definition["adapter"]),
            "crawl_delay_seconds": int(definition["crawl_delay"]),
        }
        if source is None:
            session.add(Source(id=str(definition["id"]), **values))
        else:
            for key, value in values.items():
                setattr(source, key, value)
    session.flush()


def request_to_target(request: TargetRequest) -> tuple[str, str, int, dict[str, Any]]:
    url = request.facebookUrl or request.url or ""
    if "/marketplace/item/" not in url:
        raise ValueError("A Facebook Marketplace item URL is required.")
    asking_price = request.askingPriceCents
    if asking_price is None and request.price is not None:
        asking_price = round(request.price * 100)
    if asking_price is None or asking_price < 0:
        raise ValueError("A valid asking price is required.")
    listing_id = request.listingId or stable_crm_listing_id(url)
    supplied = {
        "year": request.year, "make": request.make, "model": request.model,
        "variant": request.variant, "kms": request.kms, "transmission": request.transmission,
        "fuelType": request.fuelType, "bodyType": request.bodyType, "region": request.region,
    }
    return listing_id, canonical_url(url), asking_price, supplied


def queue_target(session: Session, request: TargetRequest, priority: int = 100, force: bool = False) -> ValuationJob:
    listing_id, url, asking_price, supplied = request_to_target(request)
    vehicle = vehicle_from_text(request.title, request.description or "", supplied)
    target = session.scalar(select(TargetVehicle).where(TargetVehicle.facebook_url == url))
    if target is None:
        target = session.scalar(select(TargetVehicle).where(TargetVehicle.crm_listing_id == listing_id))
    payload = request.model_dump(mode="json")
    is_new = target is None
    if target is None:
        target = TargetVehicle(
            crm_listing_id=listing_id, facebook_url=url, title=request.title,
            asking_price_cents=asking_price,
        )
        session.add(target)
    previous_signature = (
        target.facebook_url, target.title, target.asking_price_cents, target.year,
        target.make, target.model, target.variant, target.kms, target.transmission,
        target.fuel_type, target.body_type, target.region,
    )
    if request.listingId:
        target.crm_listing_id = listing_id
    target.facebook_url = url
    target.title = clean_text(request.title)
    target.asking_price_cents = asking_price
    for field, value in (
        ("year", vehicle.year), ("make", vehicle.make), ("model", vehicle.model),
        ("variant", vehicle.variant), ("kms", vehicle.kms),
        ("transmission", vehicle.transmission), ("fuel_type", vehicle.fuel_type),
        ("body_type", vehicle.body_type), ("region", vehicle.region),
    ):
        if value is not None:
            setattr(target, field, value)
    target.region = target.region or "Auckland"
    if request.numberPlate:
        target.number_plate = request.numberPlate
    if request.description:
        target.description = request.description
    if request.imageUrls:
        target.image_urls_json = json.dumps(request.imageUrls)
    target.source_payload_json = json.dumps(payload, default=str)
    if target.extraction_confidence == "LOW" or is_new:
        target.extraction_confidence = "MEDIUM" if target.make and target.model and target.year else "LOW"
    session.flush()

    current_signature = (
        target.facebook_url, target.title, target.asking_price_cents, target.year,
        target.make, target.model, target.variant, target.kms, target.transmission,
        target.fuel_type, target.body_type, target.region,
    )
    materially_changed = is_new or current_signature != previous_signature

    existing = session.scalar(
        select(ValuationJob)
        .where(ValuationJob.target_id == target.id, ValuationJob.status.in_(["PENDING", "RUNNING", "RETRY"]))
        .order_by(ValuationJob.created_at.desc())
    )
    if existing:
        return existing
    latest_job = session.scalar(
        select(ValuationJob)
        .where(ValuationJob.target_id == target.id)
        .order_by(ValuationJob.created_at.desc())
        .limit(1)
    )
    latest_run = session.scalar(
        select(ValuationRun)
        .where(ValuationRun.target_id == target.id)
        .order_by(ValuationRun.created_at.desc())
        .limit(1)
    )
    cutoff = utcnow() - timedelta(hours=24)
    if latest_run and latest_run.created_at and latest_run.created_at.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=None)
    valuation_is_fresh = bool(latest_run and latest_run.created_at >= cutoff)
    if latest_job and valuation_is_fresh and not materially_changed and not force:
        return latest_job
    job = ValuationJob(
        target_id=target.id, status="PENDING", priority=priority,
        deadline_at=utcnow() + timedelta(minutes=5),
    )
    session.add(job)
    session.flush()
    return job


def claim_next_job(session: Session) -> ValuationJob | None:
    job = session.scalar(
        select(ValuationJob)
        .where(ValuationJob.status.in_(["PENDING", "RETRY"]))
        .order_by(ValuationJob.priority.desc(), ValuationJob.created_at.asc())
        .limit(1)
    )
    if job is None:
        return None
    job.status = "RUNNING"
    job.attempts += 1
    job.started_at = utcnow()
    job.last_error = None
    session.flush()
    return job


def recover_stale_work(session: Session, stale_minutes: int = 10) -> dict[str, int]:
    cutoff = utcnow() - timedelta(minutes=stale_minutes)
    stale_jobs = list(session.scalars(
        select(ValuationJob).where(
            ValuationJob.status == "RUNNING",
            ValuationJob.started_at < cutoff,
        )
    ))
    for job in stale_jobs:
        job.status = "RETRY"
        job.last_error = "Recovered after the previous worker stopped mid-job."
        job.deadline_at = utcnow() + timedelta(minutes=5)

    stale_publications = list(session.scalars(
        select(ValuationPublication).where(
            ValuationPublication.status == "DELIVERING",
            ValuationPublication.updated_at < cutoff,
        )
    ))
    for publication in stale_publications:
        publication.status = "RETRY"
        publication.next_attempt_at = utcnow()
        publication.last_error = "Recovered after the previous publisher stopped mid-delivery."
    session.flush()
    return {"jobs": len(stale_jobs), "publications": len(stale_publications)}


def retry_job(session: Session, job_id: str) -> ValuationJob:
    job = session.get(ValuationJob, job_id)
    if job is None:
        raise KeyError(job_id)
    job.status = "RETRY"
    job.last_error = None
    job.deadline_at = utcnow() + timedelta(minutes=5)
    session.flush()
    return job


def fail_job(session: Session, job_id: str, error: str) -> None:
    job = session.get(ValuationJob, job_id)
    if job is None:
        return
    job.status = "RETRY" if job.attempts < 3 else "FAILED"
    job.last_error = clean_text(error)[:4000]
    job.completed_at = utcnow() if job.status == "FAILED" else None


def upsert_comparable(session: Session, item: RawListing) -> ComparableListing:
    url = canonical_url(item.url)
    existing = session.scalar(
        select(ComparableListing).where(
            or_(
                ComparableListing.canonical_url == url,
                (ComparableListing.source_id == item.source_id) &
                (ComparableListing.source_listing_id == item.source_listing_id),
            )
        )
    )
    content = {
        "title": item.title, "price": item.asking_price_cents, "year": item.year,
        "make": item.make, "model": item.model, "variant": item.variant, "kms": item.kms,
        "transmission": item.transmission, "fuel": item.fuel_type, "body": item.body_type,
        "region": item.region, "status": item.status,
    }
    content_hash = sha256(json.dumps(content, sort_keys=True, default=str).encode()).hexdigest()
    is_new = existing is None
    if is_new:
        existing = ComparableListing(
            source_id=item.source_id,
            source_listing_id=item.source_listing_id or source_listing_id(url),
            canonical_url=url,
            title=item.title,
            asking_price_cents=item.asking_price_cents,
            dedupe_key="",
            content_hash=content_hash,
        )
        session.add(existing)
    previous_price = existing.asking_price_cents
    for field in (
        "title", "asking_price_cents", "year", "make", "model", "variant", "kms",
        "transmission", "fuel_type", "body_type", "region", "seller_name", "seller_type",
        "sale_type", "stock_number", "plate", "vin", "image_hash", "status",
    ):
        setattr(existing, field, getattr(item, field))
    existing.content_hash = content_hash
    existing.raw_facts_json = json.dumps(item.raw_facts, default=str)[:20_000]
    existing.last_seen_at = item.observed_at
    existing.dedupe_key = dedupe_key(existing)
    session.flush()
    if is_new or previous_price != item.asking_price_cents:
        session.add(PriceObservation(
            comparable_id=existing.id,
            asking_price_cents=item.asking_price_cents,
            status=item.status,
            observed_at=item.observed_at,
        ))
    elif not session.scalar(select(PriceObservation.id).where(PriceObservation.comparable_id == existing.id).limit(1)):
        session.add(PriceObservation(
            comparable_id=existing.id,
            asking_price_cents=item.asking_price_cents,
            status=item.status,
            observed_at=item.observed_at,
        ))
    return existing


def record_search_result(session: Session, job_id: str | None, result: SearchResult) -> list[ComparableListing]:
    now = utcnow()
    source = session.get(Source, result.source_id)
    if source:
        source.last_attempt_at = now
        source.health = result.status
        source.last_error = result.error
        if result.status == "SUCCESS":
            source.last_success_at = now
    run = ScrapeRun(
        job_id=job_id, source_id=result.source_id, status=result.status,
        pages_scanned=result.pages_scanned, records_collected=len(result.listings),
        records_rejected=result.rejected, failure_reason=result.error,
        completed_at=now,
    )
    session.add(run)
    stored = [upsert_comparable(session, item) for item in result.listings]
    session.flush()
    return stored


def record_discovery_result(session: Session, result: DiscoveryResult) -> int:
    now = utcnow()
    source = session.get(Source, result.source_id)
    if source:
        source.last_attempt_at = now
        source.health = result.status
        source.last_error = result.error
        if result.status in {"SUCCESS", "EMPTY"}:
            source.last_success_at = now
    stored = 0
    for site in result.sites:
        existing = session.scalar(
            select(DealerSite).where(DealerSite.inventory_url == site.inventory_url)
        )
        if existing is None:
            existing = DealerSite(
                source_id=site.source_id,
                inventory_url=site.inventory_url,
                domain=site.domain,
            )
            session.add(existing)
            stored += 1
        existing.dealer_name = site.dealer_name or existing.dealer_name
        existing.last_scanned_at = now
        existing.last_error = None
    session.add(ScrapeRun(
        source_id=result.source_id,
        status=result.status,
        pages_scanned=result.pages_scanned,
        records_collected=len(result.sites),
        records_rejected=0,
        failure_reason=result.error,
        completed_at=now,
    ))
    session.flush()
    return stored


def active_dealer_sites(session: Session, limit: int = 30) -> list[tuple[str, str | None]]:
    rows = session.execute(
        select(DealerSite.inventory_url, DealerSite.dealer_name)
        .where(DealerSite.enabled.is_(True))
        .order_by(DealerSite.last_scanned_at.desc().nullslast(), DealerSite.created_at.desc())
        .limit(limit)
    ).all()
    return [(str(url), name) for url, name in rows]


def recent_targets(session: Session, limit: int) -> list[TargetVehicle]:
    return list(session.scalars(
        select(TargetVehicle)
        .where(TargetVehicle.make.is_not(None), TargetVehicle.model.is_not(None))
        .order_by(TargetVehicle.updated_at.desc())
        .limit(limit)
    ))


def comparable_candidates(session: Session, target: TargetVehicle) -> list[ComparableListing]:
    if not target.make or not target.model:
        return []
    cutoff = utcnow() - timedelta(days=30)
    return list(session.scalars(
        select(ComparableListing)
        .where(
            func.lower(ComparableListing.make) == target.make.lower(),
            ComparableListing.last_seen_at >= cutoff,
        )
        .order_by(ComparableListing.last_seen_at.desc())
        .limit(2000)
    ))


def save_valuation(
    session: Session,
    job: ValuationJob,
    result: ValuationResult,
    sources_attempted: int,
    sources_successful: int,
) -> ValuationRun:
    target = job.target
    run = ValuationRun(
        target_id=target.id, job_id=job.id, status=result.status,
        market_value_cents=result.market_value_cents,
        comparable_count=result.comparable_count,
        lowest_cents=result.lowest_cents, highest_cents=result.highest_cents,
        auckland_median_cents=result.auckland_median_cents,
        difference_cents=result.difference_cents, difference_percent=result.difference_percent,
        relation=result.relation, verdict=result.verdict, confidence=result.confidence,
        reason=result.reason, target_sell_cents=result.target_sell_cents,
        max_buy_cents=result.max_buy_cents, expected_spread_cents=result.expected_spread_cents,
        sources_attempted=sources_attempted, sources_successful=sources_successful,
        source_breakdown_json=json.dumps(result.source_breakdown, sort_keys=True),
        criteria_json=json.dumps({
            "yearRange": "strict +/-1, widened +/-2, broad +/-3",
            "kmsRange": "strict max(20000,25%), widened max(30000,35%)",
            "makeModelRequired": True,
        }),
    )
    session.add(run)
    session.flush()
    for decision in result.decisions:
        if not getattr(decision.item, "id", None):
            continue
        session.add(ValuationComparable(
            valuation_run_id=run.id, comparable_id=decision.item.id,
            accepted=decision.match.accepted, match_tier=decision.match.tier,
            match_score=decision.match.score, exclusion_reason=decision.match.reason,
        ))
    job.status = "COMPLETED" if result.status in {"VALUED", "INDICATIVE"} else result.status
    job.completed_at = utcnow()
    job.last_error = None if result.status in {"VALUED", "INDICATIVE"} else result.reason
    session.flush()
    return run


def latest_valuation(session: Session, listing_id: str) -> tuple[TargetVehicle, ValuationRun] | None:
    target = session.scalar(select(TargetVehicle).where(TargetVehicle.crm_listing_id == listing_id))
    if target is None:
        return None
    run = session.scalar(
        select(ValuationRun).where(ValuationRun.target_id == target.id).order_by(ValuationRun.created_at.desc()).limit(1)
    )
    return (target, run) if run else None


def valuation_comparables(session: Session, run_id: str) -> list[ValuationComparable]:
    return list(session.scalars(
        select(ValuationComparable)
        .where(ValuationComparable.valuation_run_id == run_id)
        .order_by(ValuationComparable.accepted.desc(), ValuationComparable.match_score.desc())
    ))


def enqueue_publication(session: Session, run_id: str, payload: dict[str, Any]) -> ValuationPublication:
    publication = session.scalar(
        select(ValuationPublication).where(ValuationPublication.valuation_run_id == run_id)
    )
    if publication is None:
        publication = ValuationPublication(
            valuation_run_id=run_id,
            payload_json=json.dumps(payload, default=str),
            status="PENDING",
        )
        session.add(publication)
    else:
        publication.payload_json = json.dumps(payload, default=str)
        if publication.status != "PUBLISHED":
            publication.status = "RETRY"
            publication.next_attempt_at = utcnow()
    session.flush()
    return publication


def claim_publication(session: Session) -> ValuationPublication | None:
    publication = session.scalar(
        select(ValuationPublication)
        .where(
            ValuationPublication.status.in_(["PENDING", "RETRY"]),
            ValuationPublication.next_attempt_at <= utcnow(),
        )
        .order_by(ValuationPublication.created_at.asc())
        .limit(1)
    )
    if publication:
        publication.status = "DELIVERING"
        publication.attempts += 1
        session.flush()
    return publication


def finish_publication(
    session: Session,
    publication_id: str,
    destination_results: dict[str, str],
) -> ValuationPublication | None:
    publication = session.get(ValuationPublication, publication_id)
    if publication is None:
        return None
    publication.destination_results_json = json.dumps(destination_results, sort_keys=True)
    failures = {key: value for key, value in destination_results.items() if value != "ok"}
    if not failures:
        publication.status = "PUBLISHED"
        publication.published_at = utcnow()
        publication.last_error = None
    else:
        publication.status = "RETRY"
        publication.last_error = "; ".join(f"{key}: {value}" for key, value in failures.items())[:4000]
        backoff_minutes = min(60, 2 ** min(publication.attempts, 5))
        publication.next_attempt_at = utcnow() + timedelta(minutes=backoff_minutes)
    session.flush()
    return publication


def coverage_summary(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(
        select(
            Source.id, Source.name, Source.role, Source.health,
            Source.last_attempt_at, Source.last_success_at, Source.last_error,
            func.count(ScrapeRun.id), func.coalesce(func.sum(ScrapeRun.records_collected), 0),
        )
        .outerjoin(ScrapeRun, ScrapeRun.source_id == Source.id)
        .group_by(Source.id)
        .order_by(Source.name)
    ).all()
    return [
        {
            "id": row[0], "name": row[1], "role": row[2], "health": row[3],
            "lastAttemptAt": row[4], "lastSuccessAt": row[5], "lastError": row[6],
            "runs": int(row[7]), "recordsCollected": int(row[8]),
        }
        for row in rows
    ]
