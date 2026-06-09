import { notFound } from "next/navigation";

import { prisma } from "@/lib/db";
import {
  LeadReport,
  parseLeadReport,
  parseLeadSources,
  type LeadSource
} from "@/lib/lead-report";
import { calculateDealMetrics } from "@/lib/money";

function withDisplayMetrics<T extends { valuationCents: number | null; askingPriceCents: number }>(
  listing: T
) {
  const metrics = calculateDealMetrics(
    listing.valuationCents,
    listing.askingPriceCents
  );

  return {
    ...listing,
    displayTargetSellPriceCents:
      "targetSellPriceCents" in listing &&
      typeof listing.targetSellPriceCents === "number"
        ? listing.targetSellPriceCents
        : metrics.targetSellPriceCents,
    displayMaxBuyPriceCents:
      "maxBuyPriceCents" in listing && typeof listing.maxBuyPriceCents === "number"
        ? listing.maxBuyPriceCents
        : metrics.maxBuyPriceCents,
    displayEstimatedProfitCents:
      "estimatedProfitCents" in listing &&
      typeof listing.estimatedProfitCents === "number"
        ? listing.estimatedProfitCents
        : metrics.estimatedProfitCents
  };
}

export async function getLeads() {
  const listings = await prisma.listing.findMany({
    where: {
      leadReportJson: { not: null },
      aiEvaluationStatus: "COMPLETED"
    },
    orderBy: [{ leadSavedAt: "desc" }, { aiEvaluatedAt: "desc" }]
  });

  return listings.map((listing) => ({
    ...withDisplayMetrics(listing),
    report: parseLeadReport(listing.leadReportJson),
    sources: parseLeadSources(listing.leadSourcesJson)
  }));
}

export type LeadListing = Awaited<ReturnType<typeof getLeads>>[number];

export async function getLead(id: string) {
  const listing = await prisma.listing.findUnique({ where: { id } });
  const report = parseLeadReport(listing?.leadReportJson);

  if (!listing || !report) {
    notFound();
  }

  return {
    ...withDisplayMetrics(listing),
    report,
    sources: parseLeadSources(listing.leadSourcesJson)
  };
}
