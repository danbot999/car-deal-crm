"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TargetRequest(BaseModel):
    listingId: str | None = None
    facebookUrl: str | None = None
    url: str | None = None
    title: str
    askingPriceCents: int | None = None
    price: float | None = None
    year: int | None = None
    make: str | None = None
    model: str | None = None
    variant: str | None = None
    kms: int | None = None
    transmission: str | None = None
    fuelType: str | None = None
    bodyType: str | None = None
    region: str | None = None
    numberPlate: str | None = None
    description: str | None = None
    imageUrls: list[str] = Field(default_factory=list)
    sourcePayload: dict[str, Any] = Field(default_factory=dict)


class BatchTargetRequest(BaseModel):
    items: list[TargetRequest]


class JobResponse(BaseModel):
    id: str
    listingId: str
    status: str
    attempts: int
    lastError: str | None = None
    progressStage: str | None = None
    progress: dict[str, Any] = Field(default_factory=dict)
    searchIdentity: str | None = None
    createdAt: datetime
    updatedAt: datetime


class ValuationResponse(BaseModel):
    listingId: str
    status: str
    vehicle: str
    askingPriceCents: int
    marketValueCents: int | None
    comparableCount: int
    lowestComparableCents: int | None
    highestComparableCents: int | None
    aucklandMedianCents: int | None
    differenceCents: int | None
    differencePercent: float | None
    relation: str | None
    verdict: str | None
    confidence: str
    valuationMethod: str | None = None
    rawMedianCents: int | None = None
    exactComparableCount: int = 0
    adjustment: dict[str, Any] = Field(default_factory=dict)
    coverage: dict[str, Any] = Field(default_factory=dict)
    reason: str
    targetSellCents: int | None
    maxBuyCents: int | None
    expectedSpreadCents: int | None
    sourcesAttempted: int
    sourcesSuccessful: int
    sourceBreakdown: dict[str, int]
    valuedAt: datetime
