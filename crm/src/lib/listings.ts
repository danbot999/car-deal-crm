import { Prisma } from "@prisma/client";

import { prisma } from "@/lib/db";
import { calculateDealMetrics } from "@/lib/money";
import {
  germanVehicleBrands,
  isVehicleOrigin,
  japaneseVehicleBrands
} from "@/lib/vehicle-origin";
import type { VehicleOrigin } from "@/lib/vehicle-origin";

export type ListingFilters = {
  q?: string;
  origin?: string;
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

export const availabilityStatuses = [
  "ACTIVE",
  "NEEDS_REVIEW",
  "POSSIBLY_SOLD",
  "CONFIRMED_SOLD",
  "SOLD",
  "UNAVAILABLE",
  "EXPIRED",
  "UNKNOWN"
] as const;

export type AvailabilityStatus = (typeof availabilityStatuses)[number];

export const hiddenAvailabilityStatuses: AvailabilityStatus[] = [
  "NEEDS_REVIEW",
  "POSSIBLY_SOLD",
  "CONFIRMED_SOLD",
  "SOLD",
  "UNAVAILABLE",
  "EXPIRED",
  "UNKNOWN"
];

export const dashboardVisibleAvailabilityStatuses: AvailabilityStatus[] = [
  "ACTIVE"
];

export const availabilityLabels: Record<AvailabilityStatus, string> = {
  ACTIVE: "Active",
  NEEDS_REVIEW: "Needs review",
  POSSIBLY_SOLD: "Needs confirmation",
  CONFIRMED_SOLD: "Confirmed sold",
  SOLD: "Sold",
  UNAVAILABLE: "Unavailable",
  EXPIRED: "Expired",
  UNKNOWN: "Checking"
};

export function isListingStatus(value: string): value is ListingStatus {
  return listingStatuses.includes(value as ListingStatus);
}

export function isAvailabilityStatus(value: string): value is AvailabilityStatus {
  return availabilityStatuses.includes(value as AvailabilityStatus);
}

function brandSearchFilter(
  brands: readonly string[]
): Prisma.ListingWhereInput {
  return {
    OR: brands.flatMap((brand) => [
      { make: { contains: brand } },
      { model: { contains: brand } },
      { title: { contains: brand } }
    ])
  };
}

function originFilter(origin?: string): Prisma.ListingWhereInput | null {
  if (!origin || origin === "all" || !isVehicleOrigin(origin)) {
    return null;
  }

  const germanFilter = brandSearchFilter(germanVehicleBrands);
  const japaneseFilter = brandSearchFilter(japaneseVehicleBrands);

  if (origin === "german") {
    return germanFilter;
  }

  if (origin === "japanese") {
    return japaneseFilter;
  }

  return {
    NOT: {
      OR: [
        ...(germanFilter.OR ?? []),
        ...(japaneseFilter.OR ?? [])
      ] as Prisma.ListingWhereInput[]
    }
  };
}

export async function getDashboardData(filters: ListingFilters) {
  const valuedMarketWhere: Prisma.ListingWhereInput = {
    marketValuationStatus: "VALUED",
    marketValueCents: { not: null }
  };
  const where: Prisma.ListingWhereInput = {
    availabilityStatus: { in: dashboardVisibleAvailabilityStatuses },
    status: { notIn: ["SOLD", "ARCHIVED"] },
    ...valuedMarketWhere
  };
  const activeWhere: Prisma.ListingWhereInput = {
    availabilityStatus: { in: dashboardVisibleAvailabilityStatuses },
    status: { notIn: ["SOLD", "ARCHIVED"] }
  };
  const activeValuedWhere: Prisma.ListingWhereInput = {
    ...activeWhere,
    ...valuedMarketWhere
  };
  const query = filters.q?.trim();
  const selectedOrigin: VehicleOrigin =
    filters.origin && isVehicleOrigin(filters.origin) ? filters.origin : "all";
  const selectedOriginFilter = originFilter(selectedOrigin);

  if (query) {
    where.OR = [
      { title: { contains: query } },
      { make: { contains: query } },
      { model: { contains: query } },
      { facebookUrl: { contains: query } }
    ];
  }

  if (selectedOriginFilter) {
    where.AND = [selectedOriginFilter];
  }

  const [
    listings,
    total,
    activeTotal,
    hiddenInactive,
    newCount,
    awaitingValuation,
  ] = await Promise.all([
    prisma.listing.findMany({
      where,
      // Comparable evidence can be several megabytes per listing. Loading it for
      // every dashboard card overwhelms Prisma/Node; the detail route fetches it
      // only for the selected listing.
      omit: {
        marketComparablesJson: true
      },
      include: {
        adminFlip: true
      },
      orderBy: [{ firstSeenAt: "desc" }, { createdAt: "desc" }]
    }),
    prisma.listing.count(),
    prisma.listing.count({ where: activeValuedWhere }),
    prisma.listing.count({
      where: {
        OR: [
          { availabilityStatus: { in: hiddenAvailabilityStatuses } },
          { status: { in: ["SOLD", "ARCHIVED"] } }
        ]
      }
    }),
    prisma.listing.count({ where: { ...activeWhere, status: "NEW" } }),
    prisma.listing.count({
      where: {
        ...activeWhere,
        OR: [
          { marketValuationStatus: { not: "VALUED" } },
          { marketValueCents: null }
        ]
      }
    })
  ]);

  const visibleListings = listings.map((listing) => {
    const primaryValuationCents = listing.valuationCents ?? listing.marketValueCents;
    const metrics = calculateDealMetrics(primaryValuationCents, listing.askingPriceCents);
    const useManualValuation = listing.valuationCents != null;

    return {
      ...listing,
      status: isListingStatus(listing.status) ? listing.status : "NEW",
      availabilityStatus: isAvailabilityStatus(listing.availabilityStatus)
        ? listing.availabilityStatus
        : "ACTIVE",
      displayTargetSellPriceCents:
        (useManualValuation ? listing.targetSellPriceCents : listing.marketTargetSellCents) ??
        metrics.targetSellPriceCents,
      displayMaxBuyPriceCents:
        (useManualValuation ? listing.maxBuyPriceCents : listing.marketMaxBuyCents) ??
        metrics.maxBuyPriceCents,
      displayEstimatedProfitCents:
        (useManualValuation ? listing.estimatedProfitCents : listing.marketExpectedSpreadCents) ??
        metrics.estimatedProfitCents,
      displayValuationCents: primaryValuationCents
    };
  });

  const potentialLeads = await prisma.listing.count({
    where: {
      ...activeValuedWhere,
      marketExpectedSpreadCents: {
        gt: 0
      }
    }
  });

  return {
    listings: visibleListings,
    stats: {
      total,
      activeTotal,
      visible: listings.length,
      hiddenInactive,
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
