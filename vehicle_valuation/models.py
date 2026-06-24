"""Persistent valuation-index models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    base_url: Mapped[str] = mapped_column(String(1000))
    role: Mapped[str] = mapped_column(String(40), default="INVENTORY")
    adapter: Mapped[str] = mapped_column(String(120))
    crawl_delay_seconds: Mapped[int] = mapped_column(Integer, default=2)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    health: Mapped[str] = mapped_column(String(40), default="UNKNOWN")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class DealerSite(Base):
    __tablename__ = "dealer_sites"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    dealer_name: Mapped[str | None] = mapped_column(String(250))
    inventory_url: Mapped[str] = mapped_column(String(1500), unique=True)
    domain: Mapped[str] = mapped_column(String(300), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ComparableListing(Base):
    __tablename__ = "comparable_listings"
    __table_args__ = (
        UniqueConstraint("source_id", "source_listing_id", name="uq_source_listing"),
        Index("ix_comparable_identity", "make", "model", "year"),
        Index("ix_comparable_last_seen", "last_seen_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    source_listing_id: Mapped[str] = mapped_column(String(250))
    canonical_url: Mapped[str] = mapped_column(String(1500), unique=True)
    title: Mapped[str] = mapped_column(String(500))
    asking_price_cents: Mapped[int] = mapped_column(Integer, index=True)
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    make: Mapped[str | None] = mapped_column(String(120), index=True)
    model: Mapped[str | None] = mapped_column(String(180), index=True)
    variant: Mapped[str | None] = mapped_column(String(220))
    kms: Mapped[int | None] = mapped_column(Integer)
    transmission: Mapped[str | None] = mapped_column(String(60))
    fuel_type: Mapped[str | None] = mapped_column(String(60))
    body_type: Mapped[str | None] = mapped_column(String(80))
    region: Mapped[str | None] = mapped_column(String(120))
    seller_name: Mapped[str | None] = mapped_column(String(250))
    seller_type: Mapped[str] = mapped_column(String(40), default="UNKNOWN")
    sale_type: Mapped[str] = mapped_column(String(40), default="FIXED_PRICE")
    stock_number: Mapped[str | None] = mapped_column(String(120))
    plate: Mapped[str | None] = mapped_column(String(20), index=True)
    vin: Mapped[str | None] = mapped_column(String(40), index=True)
    image_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(128), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(40), default="ACTIVE", index=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(250))
    raw_facts_json: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    source: Mapped[Source] = relationship()


class PriceObservation(Base):
    __tablename__ = "price_observations"
    __table_args__ = (Index("ix_price_listing_observed", "comparable_id", "observed_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    comparable_id: Mapped[str] = mapped_column(ForeignKey("comparable_listings.id", ondelete="CASCADE"))
    asking_price_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40), default="ACTIVE")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ComparableSearch(Base):
    __tablename__ = "comparable_searches"
    __table_args__ = (Index("ix_search_status_updated", "status", "updated_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    identity_key: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    target_year: Mapped[int | None] = mapped_column(Integer)
    make: Mapped[str | None] = mapped_column(String(120), index=True)
    model: Mapped[str | None] = mapped_column(String(180), index=True)
    status: Mapped[str] = mapped_column(String(40), default="QUEUED", index=True)
    stage: Mapped[str] = mapped_column(String(80), default="IDENTIFYING_VEHICLE")
    progress_json: Mapped[str | None] = mapped_column(Text)
    coverage_json: Mapped[str | None] = mapped_column(Text)
    exact_count: Mapped[int] = mapped_column(Integer, default=0)
    broader_count: Mapped[int] = mapped_column(Integer, default=0)
    valuation_method: Mapped[str | None] = mapped_column(String(60))
    raw_median_cents: Mapped[int | None] = mapped_column(Integer)
    adjusted_estimate_cents: Mapped[int | None] = mapped_column(Integer)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cache_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class TargetVehicle(Base):
    __tablename__ = "target_vehicles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    crm_listing_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    facebook_url: Mapped[str] = mapped_column(String(1500), unique=True)
    title: Mapped[str] = mapped_column(String(500))
    asking_price_cents: Mapped[int] = mapped_column(Integer)
    year: Mapped[int | None] = mapped_column(Integer)
    make: Mapped[str | None] = mapped_column(String(120), index=True)
    model: Mapped[str | None] = mapped_column(String(180), index=True)
    variant: Mapped[str | None] = mapped_column(String(220))
    kms: Mapped[int | None] = mapped_column(Integer)
    transmission: Mapped[str | None] = mapped_column(String(60))
    fuel_type: Mapped[str | None] = mapped_column(String(60))
    body_type: Mapped[str | None] = mapped_column(String(80))
    region: Mapped[str | None] = mapped_column(String(120))
    number_plate: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text)
    image_urls_json: Mapped[str | None] = mapped_column(Text)
    extraction_evidence_json: Mapped[str | None] = mapped_column(Text)
    extraction_confidence: Mapped[str] = mapped_column(String(30), default="LOW")
    field_confidence_json: Mapped[str | None] = mapped_column(Text)
    identity_key: Mapped[str | None] = mapped_column(String(300), index=True)
    search_id: Mapped[str | None] = mapped_column(ForeignKey("comparable_searches.id"), index=True)
    source_payload_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ValuationJob(Base):
    __tablename__ = "valuation_jobs"
    __table_args__ = (Index("ix_job_status_created", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    target_id: Mapped[str] = mapped_column(ForeignKey("target_vehicles.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    search_id: Mapped[str | None] = mapped_column(ForeignKey("comparable_searches.id"), index=True)
    progress_stage: Mapped[str] = mapped_column(String(80), default="QUEUED")
    progress_json: Mapped[str | None] = mapped_column(Text)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    target: Mapped[TargetVehicle] = relationship()


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("valuation_jobs.id"), index=True)
    search_id: Mapped[str | None] = mapped_column(ForeignKey("comparable_searches.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    status: Mapped[str] = mapped_column(String(40))
    pages_scanned: Mapped[int] = mapped_column(Integer, default=0)
    records_collected: Mapped[int] = mapped_column(Integer, default=0)
    records_rejected: Mapped[int] = mapped_column(Integer, default=0)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ValuationRun(Base):
    __tablename__ = "valuation_runs"
    __table_args__ = (Index("ix_valuation_target_created", "target_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    target_id: Mapped[str] = mapped_column(ForeignKey("target_vehicles.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("valuation_jobs.id"))
    search_id: Mapped[str | None] = mapped_column(ForeignKey("comparable_searches.id"), index=True)
    status: Mapped[str] = mapped_column(String(40))
    market_value_cents: Mapped[int | None] = mapped_column(Integer)
    comparable_count: Mapped[int] = mapped_column(Integer, default=0)
    lowest_cents: Mapped[int | None] = mapped_column(Integer)
    highest_cents: Mapped[int | None] = mapped_column(Integer)
    auckland_median_cents: Mapped[int | None] = mapped_column(Integer)
    difference_cents: Mapped[int | None] = mapped_column(Integer)
    difference_percent: Mapped[float | None] = mapped_column(Float)
    relation: Mapped[str | None] = mapped_column(String(40))
    verdict: Mapped[str | None] = mapped_column(String(60))
    confidence: Mapped[str] = mapped_column(String(30), default="INSUFFICIENT")
    reason: Mapped[str] = mapped_column(Text)
    target_sell_cents: Mapped[int | None] = mapped_column(Integer)
    max_buy_cents: Mapped[int | None] = mapped_column(Integer)
    expected_spread_cents: Mapped[int | None] = mapped_column(Integer)
    sources_attempted: Mapped[int] = mapped_column(Integer, default=0)
    sources_successful: Mapped[int] = mapped_column(Integer, default=0)
    source_breakdown_json: Mapped[str | None] = mapped_column(Text)
    coverage_json: Mapped[str | None] = mapped_column(Text)
    valuation_method: Mapped[str | None] = mapped_column(String(60))
    raw_median_cents: Mapped[int | None] = mapped_column(Integer)
    exact_comparable_count: Mapped[int] = mapped_column(Integer, default=0)
    adjustment_json: Mapped[str | None] = mapped_column(Text)
    criteria_json: Mapped[str | None] = mapped_column(Text)
    algorithm_version: Mapped[str] = mapped_column(String(40), default="1.0.0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ValuationComparable(Base):
    __tablename__ = "valuation_comparables"
    __table_args__ = (UniqueConstraint("valuation_run_id", "comparable_id", name="uq_run_comparable"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    valuation_run_id: Mapped[str] = mapped_column(ForeignKey("valuation_runs.id", ondelete="CASCADE"), index=True)
    comparable_id: Mapped[str] = mapped_column(ForeignKey("comparable_listings.id", ondelete="CASCADE"), index=True)
    accepted: Mapped[bool] = mapped_column(Boolean)
    match_tier: Mapped[str | None] = mapped_column(String(30))
    match_score: Mapped[float] = mapped_column(Float, default=0)
    exclusion_reason: Mapped[str | None] = mapped_column(String(250))

    comparable: Mapped[ComparableListing] = relationship()


class ValuationPublication(Base):
    __tablename__ = "valuation_publications"
    __table_args__ = (Index("ix_publication_status_next", "status", "next_attempt_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    valuation_run_id: Mapped[str] = mapped_column(
        ForeignKey("valuation_runs.id", ondelete="CASCADE"), unique=True, index=True
    )
    payload_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    destination_results_json: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
