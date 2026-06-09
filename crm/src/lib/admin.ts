import { prisma } from "@/lib/db";
import { flipStatuses, type FlipStatus } from "@/lib/admin-shared";

export type AdminFlipInput = {
  vehicleTitle: string;
  status: string;
  sourceUrl?: string | null;
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

export function normalizeFlipInput(input: AdminFlipInput) {
  const vehicleTitle = cleanText(input.vehicleTitle);
  if (!vehicleTitle) {
    throw new Error("Vehicle name is required.");
  }

  const status = flipStatuses.includes(input.status as FlipStatus)
    ? (input.status as FlipStatus)
    : "WATCHING";

  return {
    vehicleTitle,
    status,
    sourceUrl: cleanText(input.sourceUrl) || null,
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
