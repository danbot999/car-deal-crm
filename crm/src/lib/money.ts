export function formatMoney(cents: number | null | undefined): string {
  if (cents == null) {
    return "Awaiting valuation";
  }

  return new Intl.NumberFormat("en-NZ", {
    style: "currency",
    currency: "NZD",
    maximumFractionDigits: 0
  }).format(cents / 100);
}

export function calculateDealMetrics(
  valuationCents: number | null,
  askingPriceCents: number
) {
  if (valuationCents == null) {
    return {
      targetSellPriceCents: null,
      maxBuyPriceCents: null,
      estimatedProfitCents: null
    };
  }

  const targetSellPriceCents = Math.round(valuationCents * 0.8);
  const maxBuyPriceCents = targetSellPriceCents - 100_000;
  const estimatedProfitCents = targetSellPriceCents - askingPriceCents;

  return {
    targetSellPriceCents,
    maxBuyPriceCents,
    estimatedProfitCents
  };
}

export function parseManualValuationToCents(value: string): number | null {
  const normalized = value.replace(/[$,\s]/g, "").trim();
  if (!normalized) {
    return null;
  }

  const dollars = Number(normalized);
  if (!Number.isFinite(dollars) || dollars <= 0) {
    return null;
  }

  return Math.round(dollars * 100);
}
