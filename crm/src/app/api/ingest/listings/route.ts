import { createHash, timingSafeEqual } from "node:crypto";

import { NextResponse } from "next/server";

import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const maxBatchSize = 200;
const maxPriceCents = 700_000;
const facebookItemPattern = /\/marketplace\/item\/(\d+)/i;
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
    category: cleanString(item.category, 120),
    remoteImageUrl:
      remoteImageUrl && /^https?:\/\//i.test(remoteImageUrl)
        ? remoteImageUrl
        : null,
    extractedYear: parseOptionalInteger(item.extractedYear, 1900, 2100),
    make: cleanString(item.make, 100),
    model: cleanString(item.model, 150),
    availabilityStatus,
    availabilityConfidence,
    availabilityReason: cleanString(item.availabilityReason, 500),
    firstSeenAt,
    lastSeenAt,
    lastVerifiedAt
  };
}

function isAuthorized(request: Request) {
  const expectedHash = process.env.CRM_INGEST_TOKEN_SHA256?.trim().toLowerCase();
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

  let items: PreparedListing[];
  try {
    const byUrl = new Map<string, PreparedListing>();
    for (const rawItem of rawItems) {
      const prepared = prepareListing(rawItem);
      byUrl.set(prepared.facebookUrl, prepared);
    }
    items = [...byUrl.values()];
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Invalid listing payload." },
      { status: 400 }
    );
  }

  const existingRows = await prisma.listing.findMany({
    where: { facebookUrl: { in: items.map((item) => item.facebookUrl) } },
    select: { facebookUrl: true }
  });
  const existingUrls = new Set(existingRows.map((item) => item.facebookUrl));

  await prisma.$transaction(
    items.map((item) =>
      prisma.listing.upsert({
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
          availabilityStatus: item.availabilityStatus,
          availabilityConfidence: item.availabilityConfidence,
          availabilityReason: item.availabilityReason,
          lastSeenAt: item.lastSeenAt,
          lastVerifiedAt: item.lastVerifiedAt,
          consecutiveUnavailableChecks:
            item.availabilityStatus === "ACTIVE" ? 0 : undefined,
          unavailableCheckCount:
            item.availabilityStatus === "ACTIVE" ? 0 : undefined,
          unavailableSince:
            item.availabilityStatus === "ACTIVE" ? null : undefined
        }
      })
    )
  );

  const created = items.filter((item) => !existingUrls.has(item.facebookUrl)).length;
  return NextResponse.json({
    ok: true,
    received: rawItems.length,
    stored: items.length,
    created,
    updated: items.length - created
  });
}
