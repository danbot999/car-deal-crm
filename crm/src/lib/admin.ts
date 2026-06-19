import { prisma } from "@/lib/db";
import {
  adminPriorities,
  flipStatuses,
  type AdminPriority,
  type FlipStatus
} from "@/lib/admin-shared";
import { calculateDealMetrics } from "@/lib/money";

export type AdminFlipInput = {
  vehicleTitle: string;
  status: string;
  sourceUrl?: string | null;
  askingPrice?: string | number | null;
  thumbnailPath?: string | null;
  kms?: string | number | null;
  rego?: string | null;
  sellerContacted?: boolean | string | null;
  sellerContactedAt?: string | null;
  priority?: string | null;
  nextAction?: string | null;
  valuation?: string | number | null;
  purchaseDate?: string | null;
  saleDate?: string | null;
  purchasePrice?: string | number | null;
  repairCost?: string | number | null;
  otherCost?: string | number | null;
  salePrice?: string | number | null;
  notes?: string | null;
  journalWentRight?: string | null;
  journalWentWrong?: string | null;
  journalLookOutFor?: string | null;
};

function cleanText(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function parseOptionalPositiveInt(value: unknown, label: string) {
  if (value == null || value === "") {
    return null;
  }

  const normalized = String(value).replace(/[,\s]/g, "").trim();
  if (!normalized) {
    return null;
  }

  const parsed = Number(normalized);
  if (!Number.isInteger(parsed) || parsed < 0) {
    throw new Error(`${label} must be a whole number.`);
  }

  return parsed;
}

function parseBoolean(value: unknown) {
  if (typeof value === "boolean") {
    return value;
  }

  if (typeof value === "string") {
    return ["true", "yes", "on", "1"].includes(value.toLowerCase());
  }

  return false;
}

export function parseMoneyToCents(value: unknown) {
  if (value == null || value === "") {
    return 0;
  }

  const normalized = String(value).replace(/[$,\s]/g, "").trim();
  if (!normalized) {
    return 0;
  }

  const dollars = Number(normalized);
  if (!Number.isFinite(dollars) || dollars < 0) {
    throw new Error("Money values must be zero or higher.");
  }

  return Math.round(dollars * 100);
}

export function parseOptionalMoneyToCents(value: unknown) {
  if (value == null || value === "") {
    return null;
  }

  return parseMoneyToCents(value);
}

function parseDate(value: unknown) {
  const text = cleanText(value);
  if (!text) {
    return null;
  }

  const date = new Date(`${text}T00:00:00.000+13:00`);
  if (Number.isNaN(date.getTime())) {
    throw new Error("Dates must use YYYY-MM-DD format.");
  }

  return date;
}

function normalizeThumbnailPath(value: unknown) {
  const text = cleanText(value);
  if (!text) {
    return null;
  }

  if (text.length > 2_500_000) {
    throw new Error("Photo is too large after compression.");
  }

  if (/^data:image\/(?:jpeg|jpg|png|webp);base64,/i.test(text)) {
    return text;
  }

  if (/^https?:\/\//i.test(text)) {
    return text;
  }

  if (text.startsWith("/") || /^[a-z0-9_./-]+$/i.test(text)) {
    return text;
  }

  throw new Error("Photo must be an uploaded image, an image URL, or a local image path.");
}

export function normalizeFlipInput(input: AdminFlipInput) {
  const vehicleTitle = cleanText(input.vehicleTitle);
  if (!vehicleTitle) {
    throw new Error("Vehicle name is required.");
  }

  const status = flipStatuses.includes(input.status as FlipStatus)
    ? (input.status as FlipStatus)
    : "WATCHING";
  const priority = adminPriorities.includes(input.priority as AdminPriority)
    ? (input.priority as AdminPriority)
    : "MEDIUM";
  const sellerContacted = parseBoolean(input.sellerContacted);
  const askingPriceCents = parseOptionalMoneyToCents(input.askingPrice);
  const valuationCents = parseOptionalMoneyToCents(input.valuation);
  const valuationMetrics = calculateDealMetrics(
    valuationCents,
    askingPriceCents ?? 0
  );

  return {
    vehicleTitle,
    status,
    sourceUrl: cleanText(input.sourceUrl) || null,
    askingPriceCents,
    thumbnailPath: normalizeThumbnailPath(input.thumbnailPath),
    kms: parseOptionalPositiveInt(input.kms, "KMs"),
    rego: cleanText(input.rego).toUpperCase() || null,
    sellerContacted,
    sellerContactedAt: sellerContacted
      ? parseDate(input.sellerContactedAt) ?? new Date()
      : null,
    priority,
    nextAction: cleanText(input.nextAction) || null,
    valuationCents,
    targetSellPriceCents: valuationMetrics.targetSellPriceCents,
    maxBuyPriceCents: valuationMetrics.maxBuyPriceCents,
    estimatedProfitCents:
      valuationCents == null || askingPriceCents == null
        ? null
        : valuationMetrics.estimatedProfitCents,
    valuationCheckedAt: valuationCents == null ? null : new Date(),
    purchaseDate: parseDate(input.purchaseDate),
    saleDate: parseDate(input.saleDate),
    purchasePriceCents: parseMoneyToCents(input.purchasePrice),
    repairCostCents: parseMoneyToCents(input.repairCost),
    otherCostCents: parseMoneyToCents(input.otherCost),
    salePriceCents: parseOptionalMoneyToCents(input.salePrice),
    notes: cleanText(input.notes) || null,
    journalWentRight: cleanText(input.journalWentRight) || null,
    journalWentWrong: cleanText(input.journalWentWrong) || null,
    journalLookOutFor: cleanText(input.journalLookOutFor) || null
  };
}

export async function createOrGetAdminFlipFromListing(listingId: string) {
  const listing = await prisma.listing.findUnique({
    where: { id: listingId },
    include: { adminFlip: true }
  });

  if (!listing) {
    throw new Error("Listing not found.");
  }

  if (listing.adminFlip) {
    return {
      flip: listing.adminFlip,
      created: false
    };
  }

  const flip = await prisma.adminFlip.create({
    data: {
      listingId: listing.id,
      vehicleTitle: listing.title,
      status: "WATCHING",
      sourceUrl: listing.facebookUrl,
      askingPriceCents: listing.askingPriceCents,
      thumbnailPath: listing.thumbnailPath,
      kms: listing.kms,
      rego: listing.numberPlate,
      valuationCents: listing.valuationCents,
      targetSellPriceCents: listing.targetSellPriceCents,
      maxBuyPriceCents: listing.maxBuyPriceCents,
      estimatedProfitCents: listing.estimatedProfitCents,
      valuationCheckedAt: listing.valuationCheckedAt,
      priority: "MEDIUM",
      nextAction: "Review listing and decide whether to contact seller."
    }
  });

  return {
    flip,
    created: true
  };
}

function activeCost(flip: {
  purchasePriceCents: number;
  repairCostCents: number;
  otherCostCents: number;
}) {
  return (
    flip.purchasePriceCents + flip.repairCostCents + flip.otherCostCents
  );
}

export async function getAdminData() {
  const flips = await prisma.adminFlip.findMany({
    include: {
      listing: true
    },
    orderBy: [{ updatedAt: "desc" }, { createdAt: "desc" }]
  });

  const carsBought = flips.filter((flip) =>
    ["BOUGHT", "IN_REPAIR", "LISTED", "SOLD"].includes(flip.status)
  ).length;
  const carsSold = flips.filter((flip) => flip.status === "SOLD").length;
  const activeInventory = flips.filter((flip) =>
    ["BOUGHT", "IN_REPAIR", "LISTED"].includes(flip.status)
  );
  const totalSpentCents = flips.reduce(
    (sum, flip) => sum + activeCost(flip),
    0
  );
  const openCapitalCents = activeInventory.reduce(
    (sum, flip) => sum + activeCost(flip),
    0
  );
  const revenueCents = flips.reduce(
    (sum, flip) => sum + (flip.salePriceCents ?? 0),
    0
  );
  const realizedProfitCents = flips
    .filter((flip) => flip.status === "SOLD" && flip.salePriceCents != null)
    .reduce(
      (sum, flip) =>
        sum + (flip.salePriceCents ?? 0) - activeCost(flip),
      0
    );
  const journalCount = flips.filter(
    (flip) =>
      flip.journalWentRight ||
      flip.journalWentWrong ||
      flip.journalLookOutFor
  ).length;

  return {
    flips,
    stats: {
      carsTracked: flips.length,
      carsBought,
      carsSold,
      activeInventory: activeInventory.length,
      totalSpentCents,
      openCapitalCents,
      revenueCents,
      realizedProfitCents,
      journalCount
    }
  };
}
