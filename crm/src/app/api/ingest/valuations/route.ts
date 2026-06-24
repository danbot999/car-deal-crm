import { createHash, timingSafeEqual } from "node:crypto";

import { NextResponse } from "next/server";

import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const defaultIngestTokenHash =
  "b9e1a9065d25a89a42ab97a38945fa1e021ddb954c24e1902169c8ad00e8bc11";
const publishableStatuses = new Set(["VALUED", "PROVISIONAL", "INDICATIVE"]);
const knownStatuses = new Set([
  "NOT_STARTED",
  "PENDING",
  "RUNNING",
  "EXPANDING_SEARCH",
  "RETRYING",
  "VALUED",
  "PROVISIONAL",
  "INDICATIVE",
  "INSUFFICIENT_DATA",
  "FAILED"
]);

function cleanString(value: unknown, maxLength = 2_000) {
  if (typeof value !== "string") return null;
  const cleaned = value.replace(/\s+/g, " ").trim();
  return cleaned ? cleaned.slice(0, maxLength) : null;
}

function optionalInteger(value: unknown, minimum = -100_000_000, maximum = 100_000_000) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= minimum && parsed <= maximum
    ? parsed
    : null;
}

function optionalNumber(value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseDate(value: unknown) {
  if (typeof value !== "string") return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function canonicalFacebookUrl(value: unknown) {
  const raw = cleanString(value, 4_000);
  if (!raw) throw new Error("A Facebook Marketplace URL is required.");
  const parsed = new URL(raw);
  if (!/(^|\.)facebook\.com$/i.test(parsed.hostname)) {
    throw new Error("Only Facebook Marketplace URLs are accepted.");
  }
  const match = parsed.pathname.match(/\/marketplace\/item\/(\d+)/i);
  if (!match) throw new Error("Marketplace item ID is missing.");
  return {
    facebookItemId: match[1],
    facebookUrl: `https://www.facebook.com/marketplace/item/${match[1]}/`
  };
}

function isAuthorized(request: Request) {
  const expectedHash = (
    process.env.CRM_INGEST_TOKEN_SHA256 || defaultIngestTokenHash
  ).trim().toLowerCase();
  if (!/^[a-f0-9]{64}$/.test(expectedHash)) return null;
  const authorization = request.headers.get("authorization") ?? "";
  const token = authorization.startsWith("Bearer ")
    ? authorization.slice("Bearer ".length).trim()
    : "";
  const actualHash = createHash("sha256").update(token).digest("hex");
  return timingSafeEqual(
    Buffer.from(expectedHash, "hex"),
    Buffer.from(actualHash, "hex")
  );
}

export async function POST(request: Request) {
  const authorized = isAuthorized(request);
  if (authorized === null) {
    return NextResponse.json({ error: "Cloud ingestion is not configured." }, { status: 503 });
  }
  if (!authorized) {
    return NextResponse.json({ error: "Unauthorized." }, { status: 401 });
  }

  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }

  try {
    const { facebookItemId, facebookUrl } = canonicalFacebookUrl(body.facebookUrl);
    const title = cleanString(body.title, 300);
    const askingPriceCents = optionalInteger(body.askingPriceCents, 0, 700_000);
    const rawStatus = cleanString(body.marketValuationStatus, 40)?.toUpperCase();
    const marketValuationStatus = rawStatus && knownStatuses.has(rawStatus)
      ? rawStatus
      : "FAILED";
    if (!title || askingPriceCents === null) {
      throw new Error("A title and valid asking price are required.");
    }

    const marketValueCents = optionalInteger(body.marketValueCents, 0);
    const marketReason = cleanString(body.marketReason, 4_000);
    const valuationData = {
      title,
      askingPriceCents,
      extractedYear: optionalInteger(body.year, 1900, 2100),
      make: cleanString(body.make, 100),
      model: cleanString(body.model, 150),
      variant: cleanString(body.variant, 200),
      kms: optionalInteger(body.kms, 0, 2_000_000),
      transmission: cleanString(body.transmission, 60),
      fuelType: cleanString(body.fuelType, 60),
      bodyType: cleanString(body.bodyType, 80),
      region: cleanString(body.region, 120),
      listingDescription: cleanString(body.listingDescription, 20_000),
      marketValuationStatus,
      marketValuationError: publishableStatuses.has(marketValuationStatus) ? null : marketReason,
      marketValueCents,
      marketComparableCount: optionalInteger(body.marketComparableCount, 0, 100_000) ?? 0,
      marketLowestComparableCents: optionalInteger(body.marketLowestComparableCents, 0),
      marketHighestComparableCents: optionalInteger(body.marketHighestComparableCents, 0),
      marketAucklandMedianCents: optionalInteger(body.marketAucklandMedianCents, 0),
      marketDifferenceCents: optionalInteger(body.marketDifferenceCents),
      marketDifferencePercent: optionalNumber(body.marketDifferencePercent),
      marketRelation: cleanString(body.marketRelation, 40),
      marketVerdict: cleanString(body.marketVerdict, 60),
      marketConfidence: cleanString(body.marketConfidence, 30),
      marketValuationMethod: cleanString(body.marketValuationMethod, 60),
      marketRawMedianCents: optionalInteger(body.marketRawMedianCents, 0),
      marketExactComparableCount: optionalInteger(body.marketExactComparableCount, 0, 100_000) ?? 0,
      marketAdjustmentJson: cleanString(body.marketAdjustmentJson, 500_000),
      marketCoverageJson: cleanString(body.marketCoverageJson, 2_000_000),
      marketSearchIdentity: cleanString(body.marketSearchIdentity, 300),
      marketSearchStage: cleanString(body.marketSearchStage, 80) ?? "QUEUED",
      marketSearchProgressJson: cleanString(body.marketSearchProgressJson, 500_000),
      marketConfigurationWarning: cleanString(body.marketConfigurationWarning, 2_000),
      marketReason,
      marketTargetSellCents: optionalInteger(body.marketTargetSellCents),
      marketMaxBuyCents: optionalInteger(body.marketMaxBuyCents),
      marketExpectedSpreadCents: optionalInteger(body.marketExpectedSpreadCents),
      marketSourcesAttempted: optionalInteger(body.marketSourcesAttempted, 0, 10_000) ?? 0,
      marketSourcesSuccessful: optionalInteger(body.marketSourcesSuccessful, 0, 10_000) ?? 0,
      marketSourceBreakdownJson: cleanString(body.marketSourceBreakdownJson, 100_000),
      marketComparablesJson: cleanString(body.marketComparablesJson, 10_000_000),
      marketValuedAt:
        parseDate(body.marketValuedAt) ??
        (publishableStatuses.has(marketValuationStatus) ? new Date() : null),
      marketValuationRunId: cleanString(body.marketValuationRunId, 100)
    };

    const listing = await prisma.listing.upsert({
      where: { facebookUrl },
      create: {
        facebookUrl,
        facebookItemId,
        category: "Cars & Trucks",
        source: "FACEBOOK_MARKETPLACE",
        status: "NEW",
        riskLevel: "UNKNOWN",
        availabilityStatus: "ACTIVE",
        availabilityConfidence: "MEDIUM",
        firstSeenAt: new Date(),
        ...valuationData
      },
      update: valuationData
    });

    return NextResponse.json({ ok: true, stored: true, listingId: listing.id });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Invalid valuation payload." },
      { status: 400 }
    );
  }
}
