"""End-to-end valuation job orchestration."""

from __future__ import annotations

import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import requests
from sqlalchemy import select

from .config import (
    CRM_DATABASE_PATH, LIVE_SEARCH_BUDGET_SECONDS, MAX_SOURCE_WORKERS,
    N8N_DATABASE_PATH, crm_targets, shared_token,
)
from .database import session_scope
from .enrichment import enrich_target
from .models import (
    TargetVehicle, ValuationComparable, ValuationJob, ValuationPublication,
    ValuationRun,
)
from .normalization import NormalizedVehicle
from .repositories import (
    active_dealer_sites, comparable_candidates, enqueue_publication, fail_job,
    finish_publication, latest_valuation, queue_target, recent_targets,
    record_discovery_result, record_search_result, save_valuation, seed_sources,
)
from .schemas import TargetRequest
from .scrapers import build_inventory_adapters, source_definitions
from .scrapers.directories import discover_directory
from .valuation import value_vehicle


def target_vehicle(target: TargetVehicle) -> NormalizedVehicle:
    return NormalizedVehicle(
        title=target.title, year=target.year, make=target.make, model=target.model,
        variant=target.variant, kms=target.kms, transmission=target.transmission,
        fuel_type=target.fuel_type, body_type=target.body_type, region=target.region,
    )


def collect_sources(target: NormalizedVehicle, deadline: float):
    with session_scope() as session:
        dealer_sites = active_dealer_sites(session)
    adapters = build_inventory_adapters(dealer_sites)
    results = []
    with ThreadPoolExecutor(max_workers=MAX_SOURCE_WORKERS) as executor:
        futures = {executor.submit(adapter.search, target, deadline): adapter for adapter in adapters}
        for future in as_completed(futures):
            adapter = futures[future]
            try:
                results.append(future.result())
            except Exception as error:
                from .scrapers.base import SearchResult
                results.append(SearchResult(source_id=adapter.source_id, status="FAILED", error=str(error)))
            if time.monotonic() >= deadline:
                for pending in futures:
                    pending.cancel()
                break
    return results, len(adapters)


def discover_dealer_inventory_sites(budget_seconds: int = 300) -> dict[str, int]:
    deadline = time.monotonic() + budget_seconds
    definitions = [
        definition for definition in source_definitions()
        if definition["role"] in {"DIRECTORY", "DISCOVERY"}
    ]
    attempted = 0
    discovered = 0
    for definition in definitions:
        if time.monotonic() >= deadline:
            break
        result = discover_directory(definition, deadline)
        with session_scope() as session:
            seed_sources(session)
            discovered += record_discovery_result(session, result)
        attempted += 1
    return {"attempted": attempted, "newDealerSites": discovered}


def refresh_market_index(target_limit: int = 10, per_target_seconds: int = 90) -> dict[str, int]:
    with session_scope() as session:
        seed_sources(session)
        targets = recent_targets(session, target_limit)
        target_snapshots = [target_vehicle(target) for target in targets]
    sources_attempted = 0
    sources_successful = 0
    collected = 0
    for target in target_snapshots:
        results, attempted = collect_sources(target, time.monotonic() + per_target_seconds)
        with session_scope() as session:
            seed_sources(session)
            for result in results:
                stored = record_search_result(session, None, result)
                sources_successful += int(result.status == "SUCCESS")
                collected += len(stored)
        sources_attempted += attempted
    return {
        "targets": len(target_snapshots),
        "sourcesAttempted": sources_attempted,
        "sourcesSuccessful": sources_successful,
        "recordsCollected": collected,
    }


def publish_payload(target: TargetVehicle, run, comparables: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "listingId": target.crm_listing_id,
        "facebookUrl": target.facebook_url,
        "title": target.title,
        "askingPriceCents": target.asking_price_cents,
        "year": target.year,
        "make": target.make,
        "model": target.model,
        "variant": target.variant,
        "kms": target.kms,
        "transmission": target.transmission,
        "fuelType": target.fuel_type,
        "bodyType": target.body_type,
        "region": target.region,
        "listingDescription": target.description,
        "marketValuationStatus": run.status,
        "marketValueCents": run.market_value_cents,
        "marketComparableCount": run.comparable_count,
        "marketLowestComparableCents": run.lowest_cents,
        "marketHighestComparableCents": run.highest_cents,
        "marketAucklandMedianCents": run.auckland_median_cents,
        "marketDifferenceCents": run.difference_cents,
        "marketDifferencePercent": run.difference_percent,
        "marketRelation": run.relation,
        "marketVerdict": run.verdict,
        "marketConfidence": run.confidence,
        "marketReason": run.reason,
        "marketTargetSellCents": run.target_sell_cents,
        "marketMaxBuyCents": run.max_buy_cents,
        "marketExpectedSpreadCents": run.expected_spread_cents,
        "marketSourcesAttempted": run.sources_attempted,
        "marketSourcesSuccessful": run.sources_successful,
        "marketSourceBreakdownJson": run.source_breakdown_json,
        "marketComparablesJson": json.dumps(comparables, default=str),
        "marketValuedAt": run.created_at.isoformat(),
        "marketValuationRunId": run.id,
    }


def publish_to_crm(payload: dict[str, Any]) -> dict[str, str]:
    token = shared_token()
    if not token:
        return {"status": "skipped", "error": "CRM ingestion token is missing"}
    results: dict[str, str] = {}
    for base_url in crm_targets():
        try:
            response = requests.post(
                f"{base_url}/api/ingest/valuations",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
                timeout=90,
            )
            response.raise_for_status()
            results[base_url] = "ok"
        except Exception as error:
            results[base_url] = str(error)[:500]
    return results


def deliver_publication(publication_id: str) -> dict[str, str]:
    with session_scope() as session:
        publication = session.get(ValuationPublication, publication_id)
        if publication is None:
            raise KeyError(publication_id)
        payload = json.loads(publication.payload_json)
    results = publish_to_crm(payload)
    with session_scope() as session:
        finish_publication(session, publication_id, results)
    return results


def backfill_publication_outbox() -> int:
    created = 0
    with session_scope() as session:
        runs = list(session.scalars(
            select(ValuationRun)
            .outerjoin(
                ValuationPublication,
                ValuationPublication.valuation_run_id == ValuationRun.id,
            )
            .where(ValuationPublication.id.is_(None))
            .order_by(ValuationRun.created_at.asc())
        ))
        for run in runs:
            target = session.get(TargetVehicle, run.target_id)
            if target is None:
                continue
            evidence_rows = list(session.scalars(
                select(ValuationComparable)
                .where(
                    ValuationComparable.valuation_run_id == run.id,
                    ValuationComparable.accepted.is_(True),
                )
                .order_by(ValuationComparable.match_score.desc())
                .limit(100)
            ))
            evidence = [
                {
                    "source": row.comparable.source_id,
                    "title": row.comparable.title,
                    "url": row.comparable.canonical_url,
                    "priceCents": row.comparable.asking_price_cents,
                    "year": row.comparable.year,
                    "kms": row.comparable.kms,
                    "region": row.comparable.region,
                    "matchTier": row.match_tier,
                    "matchScore": row.match_score,
                }
                for row in evidence_rows
            ]
            enqueue_publication(session, run.id, publish_payload(target, run, evidence))
            created += 1
    return created


def process_job(job_id: str) -> dict[str, Any]:
    with session_scope() as session:
        seed_sources(session)
        job = session.get(ValuationJob, job_id)
        if job is None:
            raise KeyError(job_id)
        target = job.target
        supplied = {
            "year": target.year, "make": target.make, "model": target.model,
            "variant": target.variant, "kms": target.kms, "transmission": target.transmission,
            "fuelType": target.fuel_type, "bodyType": target.body_type, "region": target.region,
        }
    try:
        enrichment = enrich_target(target.title, target.facebook_url, supplied)
        with session_scope() as session:
            job = session.get(ValuationJob, job_id)
            if job is None:
                raise KeyError(job_id)
            target = job.target
            for key, value in enrichment.vehicle.to_dict().items():
                field = {"fuel_type": "fuel_type", "body_type": "body_type"}.get(key, key)
                if hasattr(target, field) and value is not None:
                    setattr(target, field, value)
            target.description = enrichment.description
            target.image_urls_json = json.dumps(enrichment.image_urls)
            target.extraction_evidence_json = json.dumps(enrichment.evidence, default=str)
            target.extraction_confidence = enrichment.confidence
            session.flush()
            normalized = target_vehicle(target)

        deadline = time.monotonic() + LIVE_SEARCH_BUDGET_SECONDS
        search_results, attempted = collect_sources(normalized, deadline)
        with session_scope() as session:
            seed_sources(session)
            job = session.get(ValuationJob, job_id)
            if job is None:
                raise KeyError(job_id)
            successful = 0
            for search_result in search_results:
                record_search_result(session, job_id, search_result)
                successful += int(search_result.status == "SUCCESS")
            session.flush()
            candidates = comparable_candidates(session, job.target)
            result = value_vehicle(target_vehicle(job.target), job.target.asking_price_cents, candidates)
            run = save_valuation(session, job, result, attempted, successful)
            session.flush()
            accepted = [decision for decision in result.decisions if decision.match.accepted]
            evidence = [
                {
                    "source": decision.item.source_id,
                    "title": decision.item.title,
                    "url": decision.item.canonical_url,
                    "priceCents": decision.item.asking_price_cents,
                    "year": decision.item.year,
                    "kms": decision.item.kms,
                    "region": decision.item.region,
                    "matchTier": decision.match.tier,
                    "matchScore": decision.match.score,
                }
                for decision in accepted[:100]
            ]
            payload = publish_payload(job.target, run, evidence)
            publication = enqueue_publication(session, run.id, payload)
            publication_id = publication.id
        publish_results = deliver_publication(publication_id)
        return {"jobId": job_id, "status": result.status, "valuation": payload, "publish": publish_results}
    except Exception as error:
        with session_scope() as session:
            fail_job(session, job_id, str(error))
        raise


def queue_existing_crm(limit: int | None = None) -> int:
    if not CRM_DATABASE_PATH.exists():
        return 0
    with sqlite3.connect(CRM_DATABASE_PATH, timeout=30) as connection:
        connection.row_factory = sqlite3.Row
        sql = """
            SELECT id, facebookUrl, title, askingPriceCents, extractedYear, make, model,
                   kms, numberPlate, listingDescription, region, variant, transmission,
                   fuelType, bodyType
            FROM Listing
            WHERE availabilityStatus = 'ACTIVE'
            ORDER BY firstSeenAt DESC
        """
        try:
            rows = connection.execute(sql + (" LIMIT ?" if limit else ""), (limit,) if limit else ()).fetchall()
        except sqlite3.OperationalError:
            rows = connection.execute(
                "SELECT id, facebookUrl, title, askingPriceCents, extractedYear, make, model, kms, numberPlate, listingDescription FROM Listing WHERE availabilityStatus='ACTIVE' ORDER BY firstSeenAt DESC" + (" LIMIT ?" if limit else ""),
                (limit,) if limit else (),
            ).fetchall()
    queued = 0
    with session_scope() as session:
        seed_sources(session)
        for row in rows:
            data = dict(row)
            request = TargetRequest(
                listingId=data.get("id"), facebookUrl=data.get("facebookUrl"),
                title=data.get("title"), askingPriceCents=data.get("askingPriceCents"),
                year=data.get("extractedYear"), make=data.get("make"), model=data.get("model"),
                kms=data.get("kms"), numberPlate=data.get("numberPlate"), description=data.get("listingDescription"),
                variant=data.get("variant"), transmission=data.get("transmission"), fuelType=data.get("fuelType"),
                bodyType=data.get("bodyType"), region=data.get("region"),
            )
            queue_target(session, request)
            queued += 1
    return queued


def reconcile_n8n(limit: int = 500) -> int:
    if not N8N_DATABASE_PATH.exists():
        return 0
    with sqlite3.connect(N8N_DATABASE_PATH, timeout=30) as connection:
        connection.row_factory = sqlite3.Row
        table_row = connection.execute("SELECT id FROM data_table WHERE name='car_listings'").fetchone()
        if not table_row:
            return 0
        table = f"data_table_user_{table_row['id']}"
        rows = connection.execute(
            f'SELECT title, price, url, firstSeen FROM "{table}" ORDER BY id DESC LIMIT ?',
            (limit,),
        ).fetchall()
    queued = 0
    with session_scope() as session:
        seed_sources(session)
        for row in rows:
            request = TargetRequest(
                facebookUrl=row["url"], title=row["title"], price=float(row["price"]),
                sourcePayload={"firstSeen": row["firstSeen"]},
            )
            queue_target(session, request)
            queued += 1
    return queued
