"""FastAPI surface for n8n, dashboard diagnostics and retries."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from sqlalchemy import select

from .config import shared_token
from .database import init_database, session_scope
from .models import ValuationJob
from .health import valuation_health
from .repositories import (
    coverage_summary, latest_valuation, queue_target, retry_job, seed_sources,
    valuation_comparables,
)
from .schemas import BatchTargetRequest, JobResponse, TargetRequest, ValuationResponse


app = FastAPI(title="NZ Vehicle Valuation Service", version="1.0.0")


def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
    token = shared_token()
    if not token:
        return
    if authorization != f"Bearer {token}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@app.on_event("startup")
def startup() -> None:
    init_database()
    with session_scope() as session:
        seed_sources(session)


def job_response(job: ValuationJob) -> JobResponse:
    try:
        progress = json.loads(job.progress_json or "{}")
    except ValueError:
        progress = {}
    return JobResponse(
        id=job.id, listingId=job.target.crm_listing_id, status=job.status,
        attempts=job.attempts, lastError=job.last_error,
        progressStage=job.progress_stage, progress=progress,
        searchIdentity=job.target.identity_key,
        createdAt=job.created_at, updatedAt=job.updated_at,
    )


@app.get("/health")
def health() -> dict[str, Any]:
    return valuation_health()


@app.post("/v1/jobs", response_model=JobResponse, status_code=202, dependencies=[Depends(authorize)])
def create_job(request: TargetRequest) -> JobResponse:
    with session_scope() as session:
        job = queue_target(session, request)
        session.flush()
        return job_response(job)


@app.post("/v1/jobs/n8n", response_model=JobResponse, status_code=202)
def create_n8n_job(request: TargetRequest) -> JobResponse:
    """Loopback-only n8n ingress; the API itself binds to 127.0.0.1 by default."""
    with session_scope() as session:
        job = queue_target(session, request)
        session.flush()
        return job_response(job)


@app.post("/v1/jobs/batch", dependencies=[Depends(authorize)])
def create_jobs(request: BatchTargetRequest) -> dict[str, object]:
    jobs = []
    with session_scope() as session:
        for item in request.items:
            jobs.append(job_response(queue_target(session, item)))
    return {"queued": len(jobs), "jobs": jobs}


@app.get("/v1/jobs", dependencies=[Depends(authorize)])
def list_jobs(
    job_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    with session_scope() as session:
        query = select(ValuationJob).order_by(ValuationJob.created_at.desc()).limit(limit)
        if job_status:
            statuses = [value.strip().upper() for value in job_status.split(",") if value.strip()]
            query = query.where(ValuationJob.status.in_(statuses))
        jobs = list(session.scalars(query))
        return {
            "jobs": [
                {
                    **job_response(job).model_dump(mode="json"),
                    "title": job.target.title,
                    "facebookUrl": job.target.facebook_url,
                    "askingPriceCents": job.target.asking_price_cents,
                    "make": job.target.make,
                    "model": job.target.model,
                    "year": job.target.year,
                }
                for job in jobs
            ]
        }


@app.get("/v1/admin/jobs")
def list_admin_jobs() -> dict[str, object]:
    return list_jobs("PENDING,RUNNING,RETRY,EXPANDING_SEARCH", 100)


@app.get("/v1/jobs/{job_id}", response_model=JobResponse, dependencies=[Depends(authorize)])
def get_job(job_id: str) -> JobResponse:
    with session_scope() as session:
        job = session.get(ValuationJob, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job_response(job)


@app.post("/v1/jobs/{job_id}/retry", response_model=JobResponse, dependencies=[Depends(authorize)])
def retry(job_id: str) -> JobResponse:
    with session_scope() as session:
        try:
            job = retry_job(session, job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found")
        return job_response(job)


@app.post("/v1/admin/jobs/{job_id}/retry", response_model=JobResponse)
def retry_admin_job(job_id: str) -> JobResponse:
    return retry(job_id)


@app.get("/v1/valuations/{listing_id}", response_model=ValuationResponse, dependencies=[Depends(authorize)])
def get_valuation(listing_id: str) -> ValuationResponse:
    with session_scope() as session:
        found = latest_valuation(session, listing_id)
        if not found:
            raise HTTPException(status_code=404, detail="Valuation not found")
        target, run = found
        return ValuationResponse(
            listingId=listing_id, status=run.status, vehicle=target.title,
            askingPriceCents=target.asking_price_cents, marketValueCents=run.market_value_cents,
            comparableCount=run.comparable_count, lowestComparableCents=run.lowest_cents,
            highestComparableCents=run.highest_cents, aucklandMedianCents=run.auckland_median_cents,
            differenceCents=run.difference_cents, differencePercent=run.difference_percent,
            relation=run.relation, verdict=run.verdict, confidence=run.confidence,
            valuationMethod=run.valuation_method, rawMedianCents=run.raw_median_cents,
            exactComparableCount=run.exact_comparable_count,
            adjustment=json.loads(run.adjustment_json or "{}"),
            coverage=json.loads(run.coverage_json or "{}"),
            reason=run.reason, targetSellCents=run.target_sell_cents, maxBuyCents=run.max_buy_cents,
            expectedSpreadCents=run.expected_spread_cents, sourcesAttempted=run.sources_attempted,
            sourcesSuccessful=run.sources_successful,
            sourceBreakdown=json.loads(run.source_breakdown_json or "{}"), valuedAt=run.created_at,
        )


@app.get("/v1/valuations/{listing_id}/comparables", dependencies=[Depends(authorize)])
def get_comparables(listing_id: str) -> dict[str, object]:
    with session_scope() as session:
        found = latest_valuation(session, listing_id)
        if not found:
            raise HTTPException(status_code=404, detail="Valuation not found")
        _target, run = found
        rows = valuation_comparables(session, run.id)
        return {
            "valuationRunId": run.id,
            "items": [
                {
                    "accepted": row.accepted, "matchTier": row.match_tier,
                    "matchScore": row.match_score, "exclusionReason": row.exclusion_reason,
                    "source": row.comparable.source_id, "title": row.comparable.title,
                    "url": row.comparable.canonical_url, "priceCents": row.comparable.asking_price_cents,
                    "year": row.comparable.year, "make": row.comparable.make,
                    "model": row.comparable.model, "variant": row.comparable.variant,
                    "kms": row.comparable.kms, "transmission": row.comparable.transmission,
                    "fuelType": row.comparable.fuel_type, "bodyType": row.comparable.body_type,
                    "region": row.comparable.region, "observedAt": row.comparable.last_seen_at,
                }
                for row in rows
            ],
        }


@app.get("/v1/sources/coverage", dependencies=[Depends(authorize)])
def source_coverage() -> dict[str, object]:
    with session_scope() as session:
        return {"sources": coverage_summary(session)}
