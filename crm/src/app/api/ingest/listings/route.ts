import { createHash, timingSafeEqual } from "node:crypto";

import { NextResponse } from "next/server";

import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const maxBatchSize = 200;
const maxPriceCents = 700_000;
const defaultIngestTokenHash =
  "b9e1a9065d25a89a42ab97a38945fa1e021ddb954c24e1902169c8ad00e8bc11";
const facebookItemPattern = /\/marketplace\/item\/(\d+)/i;
const allowedCarCategoryPattern = /\bcars?\s*(?:&|and)\s*trucks?\b/i;
const excludedCarCategoryPattern = /\b(?:rvs?\s*(?:&|and)\s*campers?|commercial\s+trucks?|buses?|coaches?|motorcycles?|motorbikes?|scooters?|trailers?|boats?|parts?)\b/i;
const excludedVehicleTitlePattern = /\b(?:bus|coach|school\s*bus|tour\s*bus|mini[\s-]?bus|motorhome|camper(?:van)?|caravan|rv|commercial\s*truck|box\s*truck|flat[\s-]?deck|tipper|tractor\s*unit|lorry|isuzu\s+gala|mitsubishi\s+rosa|toyota\s+coaster|go[\s-]?kart|motorcycle|motorbike|scooter|trailer|boat|jet\s*ski|quad\s*bike|atv|utv|tyres?|tires?|wheels?|rims?|mags?|parts?|wrecking|dismantling|canopy|bumper|gearbox|transmission|headlight|tail\s*light|seat\s*covers?)\b/i;
const allowedAvailabilityStatuses = new Set([
  "ACTIVE",
  "NEEDS_REVIEW",
  "POSSIBLY_SOLD",
  "CONFIRMED_SOLD",
  "UNAVAILABLE",
  "EXPIRED",
  "UNKNOWN"
]);
const allowedAvailabilityConfidences = new Set(["HIGH", "MEDIUM", "LOW"]);

type IncomingListing = Record<string, unknown>;

type PreparedListing = {
  facebookUrl: string;
  facebookItemId: string;
  title: string;
  askingPriceCents: number;
  category: string | null;
  remoteImageUrl: string | null;
  extractedYear: number | null;
  make: string | null;
  model: string | null;
  variant: string | null;
  kms: number | null;
  transmission: string | null;
  fuelType: string | null;
  bodyType: string | null;
  region: string | null;
  marketValuationStatus: string;
  marketValuationError: string | null;
  marketValueCents: number | null;
  marketComparableCount: number;
  marketLowestComparableCents: number | null;
  marketHighestComparableCents: number | null;
  marketAucklandMedianCents: number | null;
  marketDifferenceCents: number | null;
  marketDifferencePercent: number | null;
  marketRelation: string | null;
  marketVerdict: string | null;
  marketConfidence: string | null;
  marketValuationMethod: string | null;
  marketRawMedianCents: number | null;
  marketExactComparableCount: number;
  marketAdjustmentJson: string | null;
  marketCoverageJson: string | null;
  marketSearchIdentity: string | null;
  marketSearchStage: string;
  marketSearchProgressJson: string | null;
  marketConfigurationWarning: string | null;
  marketReason: string | null;
  marketTargetSellCents: number | null;
  marketMaxBuyCents: number | null;
  marketExpectedSpreadCents: number | null;
  marketSourcesAttempted: number;
  marketSourcesSuccessful: number;
  marketSourceBreakdownJson: string | null;
  marketComparablesJson: string | null;
  marketValuedAt: Date | null;
  marketValuationRunId: string | null;
  availabilityStatus: string;
  availabilityConfidence: string;
  availabilityReason: string | null;
  firstSeenAt: Date;
  lastSeenAt: Date | null;
  lastVerifiedAt: Date | null;
};

function cleanString(value: unknown, maxLength = 500) {
  if (typeof value !== "string") {
    return null;
  }
  const cleaned = value.replace(/\s+/g, " ").trim();
  return cleaned ? cleaned.slice(0, maxLength) : null;
}

function parseDate(value: unknown) {
  if (typeof value !== "string" || !value.trim()) {
    return null;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function parseOptionalInteger(value: unknown, minimum: number, maximum: number) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < minimum || parsed > maximum) {
    return null;
  }
  return parsed;
}

function parseOptionalNumber(value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function canonicalFacebookUrl(value: unknown) {
  const raw = cleanString(value, 2_000);
  if (!raw) {
    throw new Error("A Facebook Marketplace URL is required.");
  }

  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    throw new Error("The Marketplace URL is invalid.");
  }

  if (!/(^|\.)facebook\.com$/i.test(parsed.hostname)) {
    throw new Error("Only Facebook Marketplace URLs are accepted.");
  }

  const itemMatch = parsed.pathname.match(facebookItemPattern);
  if (!itemMatch) {
    throw new Error("The URL does not contain a Marketplace item ID.");
  }

  return {
    facebookItemId: itemMatch[1],
    facebookUrl: `https://www.facebook.com/marketplace/item/${itemMatch[1]}/`
  };
}

function isPassengerCarListing(title: string, category: string | null) {
  if (!category || !allowedCarCategoryPattern.test(category)) {
    return false;
  }
  if (excludedCarCategoryPattern.test(category)) {
    return false;
  }
  return !excludedVehicleTitlePattern.test(title);
}

function prepareListing(value: unknown): PreparedListing {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Each item must be an object.");
  }

  const item = value as IncomingListing;
  const { facebookItemId, facebookUrl } = canonicalFacebookUrl(
    item.facebookUrl ?? item.url
  );
  const title = cleanString(item.title, 300);
  if (!title) {
    throw new Error(`Listing ${facebookItemId} is missing a title.`);
  }
  const category = cleanString(item.category, 120);
  if (!isPassengerCarListing(title, category)) {
    throw new Error(`Listing ${facebookItemId} is not a passenger car.`);
  }

  const askingPriceCents = Number(item.askingPriceCents);
  if (
    !Number.isInteger(askingPriceCents) ||
    askingPriceCents < 0 ||
    askingPriceCents > maxPriceCents
  ) {
    throw new Error(`Listing ${facebookItemId} has an invalid asking price.`);
  }

  const rawStatus = cleanString(item.availabilityStatus, 40)?.toUpperCase();
  const availabilityStatus =
    rawStatus && allowedAvailabilityStatuses.has(rawStatus) ? rawStatus : "ACTIVE";
  const rawConfidence = cleanString(
    item.availabilityConfidence,
    20
  )?.toUpperCase();
  const availabilityConfidence =
    rawConfidence && allowedAvailabilityConfidences.has(rawConfidence)
      ? rawConfidence
      : availabilityStatus === "ACTIVE"
        ? "HIGH"
        : "LOW";
  const remoteImageUrl = cleanString(item.remoteImageUrl, 4_000);
  const firstSeenAt = parseDate(item.firstSeenAt) ?? new Date();
  const lastSeenAt = parseDate(item.lastSeenAt);
  const lastVerifiedAt = parseDate(item.lastVerifiedAt) ?? lastSeenAt;

  return {
    facebookUrl,
    facebookItemId,
    title,
    askingPriceCents,
    category,
    remoteImageUrl:
      remoteImageUrl && /^https?:\/\//i.test(remoteImageUrl)
        ? remoteImageUrl
        : null,
    extractedYear: parseOptionalInteger(item.extractedYear, 1900, 2100),
    make: cleanString(item.make, 100),
    model: cleanString(item.model, 150),
    variant: cleanString(item.variant, 200),
    kms: parseOptionalInteger(item.kms, 0, 2_000_000),
    transmission: cleanString(item.transmission, 60),
    fuelType: cleanString(item.fuelType, 60),
    bodyType: cleanString(item.bodyType, 80),
    region: cleanString(item.region, 120),
    marketValuationStatus: cleanString(item.marketValuationStatus, 40) ?? "NOT_STARTED",
    marketValuationError: cleanString(item.marketValuationError, 4_000),
    marketValueCents: parseOptionalInteger(item.marketValueCents, 0, 100_000_000),
    marketComparableCount: parseOptionalInteger(item.marketComparableCount, 0, 100_000) ?? 0,
    marketLowestComparableCents: parseOptionalInteger(item.marketLowestComparableCents, 0, 100_000_000),
    marketHighestComparableCents: parseOptionalInteger(item.marketHighestComparableCents, 0, 100_000_000),
    marketAucklandMedianCents: parseOptionalInteger(item.marketAucklandMedianCents, 0, 100_000_000),
    marketDifferenceCents: parseOptionalInteger(item.marketDifferenceCents, -100_000_000, 100_000_000),
    marketDifferencePercent: parseOptionalNumber(item.marketDifferencePercent),
    marketRelation: cleanString(item.marketRelation, 40),
    marketVerdict: cleanString(item.marketVerdict, 60),
    marketConfidence: cleanString(item.marketConfidence, 30),
    marketValuationMethod: cleanString(item.marketValuationMethod, 60),
    marketRawMedianCents: parseOptionalInteger(item.marketRawMedianCents, 0, 100_000_000),
    marketExactComparableCount: parseOptionalInteger(item.marketExactComparableCount, 0, 100_000) ?? 0,
    marketAdjustmentJson: cleanString(item.marketAdjustmentJson, 500_000),
    marketCoverageJson: cleanString(item.marketCoverageJson, 2_000_000),
    marketSearchIdentity: cleanString(item.marketSearchIdentity, 300),
    marketSearchStage: cleanString(item.marketSearchStage, 80) ?? "QUEUED",
    marketSearchProgressJson: cleanString(item.marketSearchProgressJson, 500_000),
    marketConfigurationWarning: cleanString(item.marketConfigurationWarning, 2_000),
    marketReason: cleanString(item.marketReason, 4_000),
    marketTargetSellCents: parseOptionalInteger(item.marketTargetSellCents, -100_000_000, 100_000_000),
    marketMaxBuyCents: parseOptionalInteger(item.marketMaxBuyCents, -100_000_000, 100_000_000),
    marketExpectedSpreadCents: parseOptionalInteger(item.marketExpectedSpreadCents, -100_000_000, 100_000_000),
    marketSourcesAttempted: parseOptionalInteger(item.marketSourcesAttempted, 0, 10_000) ?? 0,
    marketSourcesSuccessful: parseOptionalInteger(item.marketSourcesSuccessful, 0, 10_000) ?? 0,
    marketSourceBreakdownJson: cleanString(item.marketSourceBreakdownJson, 100_000),
    marketComparablesJson: cleanString(item.marketComparablesJson, 10_000_000),
    marketValuedAt: parseDate(item.marketValuedAt),
    marketValuationRunId: cleanString(item.marketValuationRunId, 100),
    availabilityStatus,
    availabilityConfidence,
    availabilityReason: cleanString(item.availabilityReason, 500),
    firstSeenAt,
    lastSeenAt,
    lastVerifiedAt
  };
}

function isAuthorized(request: Request) {
  const expectedHash = (
    process.env.CRM_INGEST_TOKEN_SHA256 || defaultIngestTokenHash
  )
    .trim()
    .toLowerCase();
  if (!expectedHash || !/^[a-f0-9]{64}$/.test(expectedHash)) {
    return null;
  }

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
    return NextResponse.json(
      { error: "Cloud ingestion is not configured." },
      { status: 503 }
    );
  }
  if (!authorized) {
    return NextResponse.json({ error: "Unauthorized." }, { status: 401 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }

  const rawItems =
    body && typeof body === "object" && !Array.isArray(body)
      ? (body as { items?: unknown }).items
      : null;
  if (!Array.isArray(rawItems) || rawItems.length === 0) {
    return NextResponse.json(
      { error: "Provide a non-empty items array." },
      { status: 400 }
    );
  }
  if (rawItems.length > maxBatchSize) {
    return NextResponse.json(
      { error: `A batch can contain at most ${maxBatchSize} listings.` },
      { status: 413 }
    );
  }

  const byUrl = new Map<string, PreparedListing>();
  const rejected: string[] = [];
  for (const rawItem of rawItems) {
    try {
      const prepared = prepareListing(rawItem);
      byUrl.set(prepared.facebookUrl, prepared);
    } catch (error) {
      rejected.push(
        error instanceof Error ? error.message : "Invalid listing payload."
      );
    }
  }
  const items = [...byUrl.values()];
  if (items.length === 0) {
    return NextResponse.json(
      {
        ok: true,
        received: rawItems.length,
        stored: 0,
        created: 0,
        updated: 0,
        rejected: rejected.length,
        rejectionReasons: rejected.slice(0, 20)
      }
    );
  }

  const existingRows = await prisma.listing.findMany({
    where: { facebookUrl: { in: items.map((item) => item.facebookUrl) } },
    select: { facebookUrl: true, lastCheckedAt: true, availabilityReason: true }
  });
  const existingUrls = new Set(existingRows.map((item) => item.facebookUrl));
  const existingByUrl = new Map(existingRows.map((item) => [item.facebookUrl, item]));
  const storableItems = items.filter(
    (item) =>
      item.availabilityStatus === "ACTIVE" ||
      existingUrls.has(item.facebookUrl)
  );
  const rejectedInactive = items.length - storableItems.length;

  await prisma.$transaction(
    storableItems.map((item) => {
      const existing = existingByUrl.get(item.facebookUrl);
      const preserveNewerLocalAvailability = Boolean(
        existing?.availabilityReason?.includes("user_confirmed_sold") ||
        (existing?.lastCheckedAt &&
          (!item.lastVerifiedAt || existing.lastCheckedAt > item.lastVerifiedAt))
      );
      return prisma.listing.upsert({
        where: { facebookUrl: item.facebookUrl },
        create: {
          facebookUrl: item.facebookUrl,
          facebookItemId: item.facebookItemId,
          title: item.title,
          askingPriceCents: item.askingPriceCents,
          category: item.category,
          source: "FACEBOOK_MARKETPLACE",
          thumbnailPath: item.remoteImageUrl,
          remoteImageUrl: item.remoteImageUrl,
          imageCachedAt: item.remoteImageUrl ? new Date() : null,
          status: "NEW",
          riskLevel: "UNKNOWN",
          extractedYear: item.extractedYear,
          make: item.make,
          model: item.model,
          variant: item.variant,
          kms: item.kms,
          transmission: item.transmission,
          fuelType: item.fuelType,
          bodyType: item.bodyType,
          region: item.region,
          marketValuationStatus: item.marketValuationStatus,
          marketValuationError: item.marketValuationError,
          marketValueCents: item.marketValueCents,
          marketComparableCount: item.marketComparableCount,
          marketLowestComparableCents: item.marketLowestComparableCents,
          marketHighestComparableCents: item.marketHighestComparableCents,
          marketAucklandMedianCents: item.marketAucklandMedianCents,
          marketDifferenceCents: item.marketDifferenceCents,
          marketDifferencePercent: item.marketDifferencePercent,
          marketRelation: item.marketRelation,
          marketVerdict: item.marketVerdict,
          marketConfidence: item.marketConfidence,
          marketValuationMethod: item.marketValuationMethod,
          marketRawMedianCents: item.marketRawMedianCents,
          marketExactComparableCount: item.marketExactComparableCount,
          marketAdjustmentJson: item.marketAdjustmentJson,
          marketCoverageJson: item.marketCoverageJson,
          marketSearchIdentity: item.marketSearchIdentity,
          marketSearchStage: item.marketSearchStage,
          marketSearchProgressJson: item.marketSearchProgressJson,
          marketConfigurationWarning: item.marketConfigurationWarning,
          marketReason: item.marketReason,
          marketTargetSellCents: item.marketTargetSellCents,
          marketMaxBuyCents: item.marketMaxBuyCents,
          marketExpectedSpreadCents: item.marketExpectedSpreadCents,
          marketSourcesAttempted: item.marketSourcesAttempted,
          marketSourcesSuccessful: item.marketSourcesSuccessful,
          marketSourceBreakdownJson: item.marketSourceBreakdownJson,
          marketComparablesJson: item.marketComparablesJson,
          marketValuedAt: item.marketValuedAt,
          marketValuationRunId: item.marketValuationRunId,
          availabilityStatus: item.availabilityStatus,
          availabilityConfidence: item.availabilityConfidence,
          availabilityReason: item.availabilityReason,
          firstSeenAt: item.firstSeenAt,
          lastSeenAt: item.lastSeenAt,
          lastVerifiedAt: item.lastVerifiedAt
        },
        update: {
          title: item.title,
          askingPriceCents: item.askingPriceCents,
          category: item.category,
          thumbnailPath: item.remoteImageUrl,
          remoteImageUrl: item.remoteImageUrl,
          imageCachedAt: item.remoteImageUrl ? new Date() : undefined,
          extractedYear: item.extractedYear,
          make: item.make,
          model: item.model,
          variant: item.variant,
          kms: item.kms,
          transmission: item.transmission,
          fuelType: item.fuelType,
          bodyType: item.bodyType,
          region: item.region,
          marketValuationStatus: item.marketValuationStatus,
          marketValuationError: item.marketValuationError,
          marketValueCents: item.marketValueCents,
          marketComparableCount: item.marketComparableCount,
          marketLowestComparableCents: item.marketLowestComparableCents,
          marketHighestComparableCents: item.marketHighestComparableCents,
          marketAucklandMedianCents: item.marketAucklandMedianCents,
          marketDifferenceCents: item.marketDifferenceCents,
          marketDifferencePercent: item.marketDifferencePercent,
          marketRelation: item.marketRelation,
          marketVerdict: item.marketVerdict,
          marketConfidence: item.marketConfidence,
          marketValuationMethod: item.marketValuationMethod,
          marketRawMedianCents: item.marketRawMedianCents,
          marketExactComparableCount: item.marketExactComparableCount,
          marketAdjustmentJson: item.marketAdjustmentJson,
          marketCoverageJson: item.marketCoverageJson,
          marketSearchIdentity: item.marketSearchIdentity,
          marketSearchStage: item.marketSearchStage,
          marketSearchProgressJson: item.marketSearchProgressJson,
          marketConfigurationWarning: item.marketConfigurationWarning,
          marketReason: item.marketReason,
          marketTargetSellCents: item.marketTargetSellCents,
          marketMaxBuyCents: item.marketMaxBuyCents,
          marketExpectedSpreadCents: item.marketExpectedSpreadCents,
          marketSourcesAttempted: item.marketSourcesAttempted,
          marketSourcesSuccessful: item.marketSourcesSuccessful,
          marketSourceBreakdownJson: item.marketSourceBreakdownJson,
          marketComparablesJson: item.marketComparablesJson,
          marketValuedAt: item.marketValuedAt,
          marketValuationRunId: item.marketValuationRunId,
          availabilityStatus: preserveNewerLocalAvailability ? undefined : item.availabilityStatus,
          availabilityConfidence: preserveNewerLocalAvailability ? undefined : item.availabilityConfidence,
          availabilityReason: preserveNewerLocalAvailability ? undefined : item.availabilityReason,
          lastSeenAt: item.lastSeenAt,
          lastVerifiedAt: preserveNewerLocalAvailability ? undefined : item.lastVerifiedAt,
          consecutiveUnavailableChecks:
            !preserveNewerLocalAvailability && item.availabilityStatus === "ACTIVE" ? 0 : undefined,
          unavailableCheckCount:
            !preserveNewerLocalAvailability && item.availabilityStatus === "ACTIVE" ? 0 : undefined,
          unavailableSince:
            !preserveNewerLocalAvailability && item.availabilityStatus === "ACTIVE" ? null : undefined
        }
      });
    })
  );

  const created = storableItems.filter(
    (item) => !existingUrls.has(item.facebookUrl)
  ).length;
  return NextResponse.json({
    ok: true,
    received: rawItems.length,
    stored: storableItems.length,
    created,
    updated: storableItems.length - created,
    rejected: rejected.length + rejectedInactive,
    rejectionReasons: rejected.slice(0, 20)
  });
}
