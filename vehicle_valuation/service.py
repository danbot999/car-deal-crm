"""End-to-end valuation job orchestration."""

from __future__ import annotations

import json
import re
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
    ComparableSearch, TargetVehicle, ValuationComparable, ValuationJob, ValuationPublication,
    ValuationRun,
)
from .normalization import NormalizedVehicle
from .repositories import (
    active_dealer_sites, comparable_candidates, enqueue_publication, fail_job,
    ensure_search_for_target, finish_publication, latest_valuation, queue_target, recent_targets,
    record_discovery_result, record_search_result, save_valuation, seed_sources,
    update_job_progress,
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


def collect_sources(target: NormalizedVehicle, deadline: float, progress=None):
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
            if progress:
                progress(results[-1], len(results), len(adapters))
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
    try:
        extraction_evidence = json.loads(target.extraction_evidence_json or "{}")
    except ValueError:
        extraction_evidence = {}
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
        "marketValuationMethod": run.valuation_method,
        "marketRawMedianCents": run.raw_median_cents,
        "marketExactComparableCount": run.exact_comparable_count,
        "marketAdjustmentJson": run.adjustment_json,
        "marketCoverageJson": run.coverage_json,
        "marketSearchIdentity": target.identity_key,
        "marketSearchStage": "COMPLETED" if run.status in {"VALUED", "PROVISIONAL"} else "EXPANDING_SEARCH",
        "marketSearchProgressJson": run.coverage_json,
        "marketConfigurationWarning": extraction_evidence.get("configurationWarning"),
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


def publish_job_progress(job_id: str, stage: str, **details: Any) -> None:
    with session_scope() as session:
        job = session.get(ValuationJob, job_id)
        if not job:
            return
        target = job.target
        payload = {
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
            "marketValuationStatus": "EXPANDING_SEARCH" if stage == "EXPANDING_SEARCH" else "RUNNING",
            "marketSearchIdentity": target.identity_key,
            "marketSearchStage": stage,
            "marketSearchProgressJson": json.dumps({"stage": stage, **details}, default=str),
            "marketReason": details.get("message") or "Nationwide comparable search is running.",
        }
    publish_to_crm(payload)


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
                )
                .order_by(ValuationComparable.match_score.desc())
            ))
            evidence = [
                {
                    "source": row.comparable.source_id,
                    "title": row.comparable.title,
                    "url": row.comparable.canonical_url,
                    "priceCents": row.comparable.asking_price_cents,
                    "year": row.comparable.year,
                    "make": row.comparable.make,
                    "model": row.comparable.model,
                    "variant": row.comparable.variant,
                    "kms": row.comparable.kms,
                    "transmission": row.comparable.transmission,
                    "fuelType": row.comparable.fuel_type,
                    "bodyType": row.comparable.body_type,
                    "region": row.comparable.region,
                    "observedAt": row.comparable.last_seen_at,
                    "matchTier": row.match_tier,
                    "matchScore": row.match_score,
                    "accepted": row.accepted,
                    "exclusionReason": row.exclusion_reason,
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
        with session_scope() as session:
            update_job_progress(session, job_id, "IDENTIFYING_VEHICLE", comparablesFound=0)
        publish_job_progress(job_id, "IDENTIFYING_VEHICLE", comparablesFound=0)
        try:
            seed_image_urls = json.loads(target.image_urls_json or "[]")
        except ValueError:
            seed_image_urls = []
        enrichment = enrich_target(target.title, target.facebook_url, supplied, seed_image_urls)
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
            target.field_confidence_json = json.dumps(enrichment.evidence.get("fieldConfidence", {}), default=str)
            search = ensure_search_for_target(session, target)
            job.search_id = search.id
            session.flush()
            normalized = target_vehicle(target)

        deadline = time.monotonic() + LIVE_SEARCH_BUDGET_SECONDS
        with session_scope() as session:
            job = session.get(ValuationJob, job_id)
            search = session.get(ComparableSearch, job.search_id) if job and job.search_id else None
            cache_is_fresh = bool(
                search
                and search.status in {"VALUED", "PROVISIONAL"}
                and search.cache_expires_at
                and search.cache_expires_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)
            )

        search_results = []
        attempted = 0
        if not cache_is_fresh:
            with session_scope() as session:
                update_job_progress(session, job_id, "SEARCHING_EXACT_NZ_LISTINGS", comparablesFound=0)
            publish_job_progress(job_id, "SEARCHING_EXACT_NZ_LISTINGS", comparablesFound=0)

            progress_state = {"found": 0}

            def progress(result, completed, total):
                progress_state["found"] += len(result.listings)
                with session_scope() as progress_session:
                    update_job_progress(
                        progress_session, job_id, "SEARCHING_EXACT_NZ_LISTINGS",
                        sourcesCompleted=completed, sourcesTotal=total,
                        comparablesFound=progress_state["found"],
                        latestSource=result.source_id,
                    )
                if completed == 1 or completed == total or completed % 3 == 0:
                    publish_job_progress(
                        job_id, "SEARCHING_EXACT_NZ_LISTINGS",
                        sourcesCompleted=completed, sourcesTotal=total,
                        comparablesFound=progress_state["found"], latestSource=result.source_id,
                    )

            search_results, attempted = collect_sources(normalized, deadline, progress)
        with session_scope() as session:
            seed_sources(session)
            job = session.get(ValuationJob, job_id)
            if job is None:
                raise KeyError(job_id)
            successful = 0
            coverage_items = []
            for search_result in search_results:
                record_search_result(session, job_id, search_result, job.search_id)
                successful += int(search_result.status == "SUCCESS")
                coverage_items.append({
                    "source": search_result.source_id, "status": search_result.status,
                    "pagesScanned": search_result.pages_scanned,
                    "recordsCollected": len(search_result.listings),
                    "recordsRejected": search_result.rejected, "error": search_result.error,
                })
            session.flush()
            candidates = [
                item for item in comparable_candidates(session, job.target)
                if item.canonical_url != job.target.facebook_url
            ]
            result = value_vehicle(target_vehicle(job.target), job.target.asking_price_cents, candidates)

        if result.method != "EXACT" and not cache_is_fresh and time.monotonic() < deadline - 20 and normalized.make and normalized.model:
            with session_scope() as session:
                update_job_progress(
                    session, job_id, "EXPANDING_MODEL_SEARCH",
                    comparablesFound=result.comparable_count, exactComparables=result.exact_count,
                )
            publish_job_progress(
                job_id, "EXPANDING_MODEL_SEARCH",
                comparablesFound=result.comparable_count, exactComparables=result.exact_count,
            )
            expanded = NormalizedVehicle(
                title=f"{normalized.make} {normalized.model}", make=normalized.make, model=normalized.model,
                variant=normalized.variant, kms=normalized.kms, transmission=normalized.transmission,
                fuel_type=normalized.fuel_type, body_type=normalized.body_type, region=normalized.region,
            )
            expanded_results, expanded_attempted = collect_sources(expanded, deadline)
            attempted += expanded_attempted
            with session_scope() as session:
                job = session.get(ValuationJob, job_id)
                if job is None:
                    raise KeyError(job_id)
                for search_result in expanded_results:
                    record_search_result(session, job_id, search_result, job.search_id)
                    successful += int(search_result.status == "SUCCESS")
                    coverage_items.append({
                        "source": search_result.source_id, "stage": "EXPANDED_MODEL",
                        "status": search_result.status, "pagesScanned": search_result.pages_scanned,
                        "recordsCollected": len(search_result.listings),
                        "recordsRejected": search_result.rejected, "error": search_result.error,
                    })
                session.flush()
                candidates = [
                    item for item in comparable_candidates(session, job.target)
                    if item.canonical_url != job.target.facebook_url
                ]
                result = value_vehicle(target_vehicle(job.target), job.target.asking_price_cents, candidates)

        with session_scope() as session:
            job = session.get(ValuationJob, job_id)
            if job is None:
                raise KeyError(job_id)
            if cache_is_fresh:
                successful = 0
                coverage_items = [{"source": "GROUP_CACHE", "status": "SUCCESS"}]
            run = save_valuation(
                session, job, result, attempted, successful,
                {"sources": coverage_items, "deadlineSeconds": LIVE_SEARCH_BUDGET_SECONDS},
            )
            session.flush()
            evidence = [
                {
                    "source": decision.item.source_id,
                    "title": decision.item.title,
                    "url": decision.item.canonical_url,
                    "priceCents": decision.item.asking_price_cents,
                    "year": decision.item.year,
                    "make": decision.item.make,
                    "model": decision.item.model,
                    "variant": decision.item.variant,
                    "kms": decision.item.kms,
                    "transmission": decision.item.transmission,
                    "fuelType": decision.item.fuel_type,
                    "bodyType": decision.item.body_type,
                    "region": decision.item.region,
                    "observedAt": decision.item.last_seen_at,
                    "matchTier": decision.match.tier,
                    "matchScore": decision.match.score,
                    "accepted": decision.match.accepted,
                    "exclusionReason": decision.match.reason,
                }
                for decision in result.decisions
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


def queue_existing_crm(
    limit: int | None = None,
    force: bool = False,
    skip_valued: bool = False,
) -> int:
    if not CRM_DATABASE_PATH.exists():
        return 0
    with sqlite3.connect(CRM_DATABASE_PATH, timeout=30) as connection:
        connection.row_factory = sqlite3.Row
        sql = """
            SELECT id, facebookUrl, title, askingPriceCents, extractedYear, make, model,
                   kms, numberPlate, listingDescription, region, variant, transmission,
                   fuelType, bodyType, thumbnailPath, remoteImageUrl, marketValuationStatus
            FROM Listing
            WHERE availabilityStatus = 'ACTIVE'
              AND status NOT IN ('SOLD', 'ARCHIVED')
              {skip_clause}
            ORDER BY firstSeenAt DESC
        """.format(skip_clause="AND marketValuationStatus != 'VALUED'" if skip_valued else "")
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
            image_urls: list[str] = []
            remote_image = data.get("remoteImageUrl")
            if isinstance(remote_image, str) and remote_image.startswith(("http://", "https://")):
                image_urls.append(remote_image)
            thumbnail = data.get("thumbnailPath")
            public_root = CRM_DATABASE_PATH.parent.parent / "public"
            if isinstance(thumbnail, str) and thumbnail.startswith("/"):
                local_thumbnail = public_root / thumbnail.lstrip("/")
                if local_thumbnail.is_file():
                    image_urls.append(str(local_thumbnail))
            item_match = re.search(r"/marketplace/item/(\d+)", data.get("facebookUrl") or "")
            if item_match:
                detail_dir = public_root / "listing-images" / "detail"
                if detail_dir.exists():
                    image_urls.extend(str(path) for path in sorted(detail_dir.glob(f"{item_match.group(1)}-*")))
            request = TargetRequest(
                listingId=data.get("id"), facebookUrl=data.get("facebookUrl"),
                title=data.get("title"), askingPriceCents=data.get("askingPriceCents"),
                year=data.get("extractedYear"), make=data.get("make"), model=data.get("model"),
                kms=data.get("kms"), numberPlate=data.get("numberPlate"), description=data.get("listingDescription"),
                variant=data.get("variant"), transmission=data.get("transmission"), fuelType=data.get("fuelType"),
                bodyType=data.get("bodyType"), region=data.get("region"),
                imageUrls=list(dict.fromkeys(image_urls)),
            )
            queue_target(session, request, force=force)
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
