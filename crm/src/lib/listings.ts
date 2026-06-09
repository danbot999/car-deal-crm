import { Prisma } from "@prisma/client";

import { prisma } from "@/lib/db";
import { calculateDealMetrics } from "@/lib/money";

export type ListingFilters = {
  q?: string;
  status?: string;
  minPrice?: string;
  maxPrice?: string;
  valuation?: string;
};

export const listingStatuses = [
  "NEW",
  "REVIEWING",
  "CONTACTED",
  "VIEWED",
  "OFFER_MADE",
  "BOUGHT",
  "PASSED",
  "SOLD",
  "ARCHIVED"
] as const;

export type ListingStatus = (typeof listingStatuses)[number];

export function isListingStatus(value: string): value is ListingStatus {
  return listingStatuses.includes(value as ListingStatus);
}

function parseDollarsToCents(value?: string): number | undefined {
  if (!value) {
    return undefined;
  }

  const dollars = Number(value.replace(/[$,\s]/g, ""));
  if (!Number.isFinite(dollars) || dollars < 0) {
    return undefined;
  }

  return Math.round(dollars * 100);
}

export async function getDashboardData(filters: ListingFilters) {
  const where: Prisma.ListingWhereInput = {};
  const query = filters.q?.trim();
  const minPriceCents = parseDollarsToCents(filters.minPrice);
  const maxPriceCents = parseDollarsToCents(filters.maxPrice);

  if (query) {
    where.OR = [
      { title: { contains: query } },
      { make: { contains: query } },
      { model: { contains: query } },
      { facebookUrl: { contains: query } }
    ];
  }

  if (
    filters.status &&
    listingStatuses.includes(filters.status as ListingStatus)
  ) {
    where.status = filters.status;
  }

  if (minPriceCents != null || maxPriceCents != null) {
    where.askingPriceCents = {
      gte: minPriceCents,
      lte: maxPriceCents
    };
  }

  if (filters.valuation === "missing") {
    where.valuationCents = null;
  }

  if (filters.valuation === "valued") {
    where.valuationCents = { not: null };
  }

  const [listings, total, newCount, awaitingValuation] = await Promise.all([
    prisma.listing.findMany({
      where,
      orderBy: [{ firstSeenAt: "desc" }, { createdAt: "desc" }]
    }),
    prisma.listing.count(),
    prisma.listing.count({ where: { status: "NEW" } }),
    prisma.listing.count({ where: { valuationCents: null } })
  ]);

  const visibleListings = listings.map((listing) => {
    const metrics = calculateDealMetrics(
      listing.valuationCents,
      listing.askingPriceCents
    );

    return {
      ...listing,
      status: isListingStatus(listing.status) ? listing.status : "NEW",
      displayTargetSellPriceCents:
        listing.targetSellPriceCents ?? metrics.targetSellPriceCents,
      displayMaxBuyPriceCents:
        listing.maxBuyPriceCents ?? metrics.maxBuyPriceCents,
      displayEstimatedProfitCents:
        listing.estimatedProfitCents ?? metrics.estimatedProfitCents
    };
  });

  const potentialLeads = await prisma.listing.count({
    where: {
      estimatedProfitCents: {
        gt: 0
      }
    }
  });

  return {
    listings: visibleListings,
    stats: {
      total,
      visible: listings.length,
      newCount,
      awaitingValuation,
      potentialLeads
    }
  };
}

export const statusLabels: Record<ListingStatus, string> = {
  NEW: "New",
  REVIEWING: "Reviewing",
  CONTACTED: "Contacted",
  VIEWED: "Viewed",
  OFFER_MADE: "Offer made",
  BOUGHT: "Bought",
  PASSED: "Passed",
  SOLD: "Sold",
  ARCHIVED: "Archived"
};
