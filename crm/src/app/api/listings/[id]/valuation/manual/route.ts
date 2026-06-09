import { NextResponse } from "next/server";

import { calculateDealMetrics, parseManualValuationToCents } from "@/lib/money";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{
    id: string;
  }>;
};

type RequestPayload = {
  valuation?: string;
};

export async function POST(request: Request, context: RouteContext) {
  const { id } = await context.params;
  const payload = (await request.json().catch(() => ({}))) as RequestPayload;
  const valuation = typeof payload.valuation === "string" ? payload.valuation : "";
  const valuationCents = parseManualValuationToCents(valuation);

  if (valuationCents == null) {
    return NextResponse.json(
      { error: "Enter a valid Trade Me valuation, for example $5,247.50." },
      { status: 400 }
    );
  }

  const listing = await prisma.listing.findUnique({
    where: { id }
  });

  if (!listing) {
    return NextResponse.json({ error: "Listing not found." }, { status: 404 });
  }

  const metrics = calculateDealMetrics(valuationCents, listing.askingPriceCents);
  const updated = await prisma.listing.update({
    where: { id },
    data: {
      valuationCents,
      targetSellPriceCents: metrics.targetSellPriceCents,
      maxBuyPriceCents: metrics.maxBuyPriceCents,
      estimatedProfitCents: metrics.estimatedProfitCents,
      valuationStatus: "VALUED",
      valuationError: null,
      valuationCheckedAt: new Date(),
      valuationSource: "TRADE_ME_MANUAL"
    },
    select: {
      valuationCents: true,
      targetSellPriceCents: true,
      maxBuyPriceCents: true,
      estimatedProfitCents: true,
      valuationStatus: true,
      valuationCheckedAt: true,
      valuationSource: true
    }
  });

  return NextResponse.json({
    message: "Trade Me valuation saved.",
    listing: updated
  });
}
