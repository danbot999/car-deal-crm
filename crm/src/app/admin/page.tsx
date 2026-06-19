import { AppNav } from "@/components/AppNav";
import { AdminPanel, type AdminFlipView } from "@/components/AdminPanel";
import { getAdminData } from "@/lib/admin";

export const dynamic = "force-dynamic";

function serializeFlip(
  flip: Awaited<ReturnType<typeof getAdminData>>["flips"][number]
): AdminFlipView {
  return {
    id: flip.id,
    listingId: flip.listingId,
    listingAvailabilityStatus: flip.listing?.availabilityStatus ?? null,
    listingAvailabilityReason: flip.listing?.availabilityReason ?? null,
    listingLastCheckedAt: flip.listing?.lastCheckedAt?.toISOString() ?? null,
    vehicleTitle: flip.vehicleTitle,
    status: flip.status as AdminFlipView["status"],
    sourceUrl: flip.sourceUrl,
    askingPriceCents: flip.askingPriceCents,
    thumbnailPath: flip.thumbnailPath,
    kms: flip.kms,
    rego: flip.rego,
    sellerContacted: flip.sellerContacted,
    sellerContactedAt: flip.sellerContactedAt?.toISOString() ?? null,
    priority: flip.priority as AdminFlipView["priority"],
    nextAction: flip.nextAction,
    purchaseDate: flip.purchaseDate?.toISOString() ?? null,
    saleDate: flip.saleDate?.toISOString() ?? null,
    valuationCents: flip.valuationCents,
    targetSellPriceCents: flip.targetSellPriceCents,
    maxBuyPriceCents: flip.maxBuyPriceCents,
    estimatedProfitCents: flip.estimatedProfitCents,
    valuationCheckedAt: flip.valuationCheckedAt?.toISOString() ?? null,
    purchasePriceCents: flip.purchasePriceCents,
    repairCostCents: flip.repairCostCents,
    otherCostCents: flip.otherCostCents,
    salePriceCents: flip.salePriceCents,
    notes: flip.notes,
    journalWentRight: flip.journalWentRight,
    journalWentWrong: flip.journalWentWrong,
    journalLookOutFor: flip.journalLookOutFor,
    createdAt: flip.createdAt.toISOString(),
    updatedAt: flip.updatedAt.toISOString()
  };
}

export default async function AdminPage() {
  const data = await getAdminData();

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_#ede9fe,_transparent_32rem),radial-gradient(circle_at_top_right,_#cffafe,_transparent_30rem),linear-gradient(180deg,_#f8fafc,_#eef2ff)] px-4 py-8 text-slate-950 md:px-6">
      <main className="mx-auto max-w-[95rem]">
        <AppNav active="admin" />
        <AdminPanel
          flips={data.flips.map(serializeFlip)}
          stats={data.stats}
        />
      </main>
    </div>
  );
}
