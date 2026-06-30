"""Structured valuation-service health used by the API and local watchdog."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from runtime_health import heartbeat_age_seconds, read_heartbeat

from .database import session_scope
from .models import Source, ValuationJob, ValuationPublication


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


def valuation_health() -> dict[str, Any]:
    with session_scope() as session:
        job_counts = {
            str(status): int(count)
            for status, count in session.execute(
                select(ValuationJob.status, func.count(ValuationJob.id)).group_by(ValuationJob.status)
            )
        }
        oldest_runnable = session.scalar(
            select(func.min(ValuationJob.created_at)).where(
                ValuationJob.status.in_(["PENDING", "RETRY", "EXPANDING_SEARCH", "AWAITING_SAFE_EVIDENCE"])
            )
        )
        publication_failures = int(
            session.scalar(
                select(func.count(ValuationPublication.id)).where(
                    ValuationPublication.status.in_(["RETRY", "FAILED"])
                )
            )
            or 0
        )
        sources = [
            {
                "id": source.id,
                "name": source.name,
                "health": source.health,
                "lastSuccessAt": _iso(source.last_success_at),
                "lastError": source.last_error,
            }
            for source in session.scalars(select(Source).where(Source.enabled.is_(True)).order_by(Source.name))
        ]

    worker = read_heartbeat("valuation-worker")
    worker_age = heartbeat_age_seconds("valuation-worker")
    worker_healthy = worker_age is not None and worker_age <= 120
    runnable = sum(
        job_counts.get(status, 0)
        for status in ("PENDING", "RETRY", "EXPANDING_SEARCH", "AWAITING_SAFE_EVIDENCE")
    )
    oldest_age = None
    if oldest_runnable is not None:
        oldest_value = oldest_runnable
        if oldest_value.tzinfo is None:
            oldest_value = oldest_value.replace(tzinfo=timezone.utc)
        oldest_age = max(0.0, (datetime.now(timezone.utc) - oldest_value).total_seconds())
    queue_stale = bool(runnable and oldest_age is not None and oldest_age > 3600)
    return {
        "status": "ok" if worker_healthy and publication_failures == 0 and not queue_stale else "degraded",
        "checkedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "worker": {
            "healthy": worker_healthy,
            "ageSeconds": round(worker_age, 1) if worker_age is not None else None,
            "heartbeat": worker,
        },
        "queue": {
            "counts": job_counts,
            "runnable": runnable,
            "oldestRunnableAt": _iso(oldest_runnable),
            "oldestRunnableAgeSeconds": round(oldest_age, 1) if oldest_age is not None else None,
            "stale": queue_stale,
        },
        "publicationFailures": publication_failures,
        "sources": sources,
    }
