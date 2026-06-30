import Link from "next/link";

import { AppNav } from "@/components/AppNav";
import { SafeCarImage } from "@/components/SafeCarImage";
import { prisma } from "@/lib/db";
import { formatMoney } from "@/lib/money";

export const dynamic = "force-dynamic";

const methodLabels: Record<string, string> = {
  EXACT: "Exact year/model median",
  GENERATION_ADJUSTED: "Generation adjusted",
  MODEL_ADJUSTED: "Model adjusted",
  MAKE_CLASS_PROVISIONAL: "Make/class provisional",
  CLASS_PROVISIONAL: "NZ class provisional"
};

export default async function MarketEvidencePage() {
  const listings = await prisma.listing.findMany({
    where: {
      availabilityStatus: "ACTIVE",
      status: { notIn: ["SOLD", "ARCHIVED"] }
    },
    select: {
      id: true,
      title: true,
      askingPriceCents: true,
      thumbnailPath: true,
      marketValuationStatus: true,
      marketConfidence: true,
      marketValuationMethod: true,
      marketSearchStage: true,
      marketComparableCount: true,
      marketExactComparableCount: true,
      marketValueCents: true,
      marketValuedAt: true,
      firstSeenAt: true
    },
    orderBy: [{ marketValuedAt: "desc" }, { firstSeenAt: "desc" }]
  });

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_#cffafe,_transparent_32rem),linear-gradient(180deg,_#f8fafc,_#eef2ff)] px-4 py-8 text-slate-950 md:px-6">
      <main className="mx-auto max-w-[95rem]">
        <AppNav active="market-evidence" />
        <section className="rounded-[2rem] bg-slate-950 p-8 text-white shadow-2xl shadow-slate-300">
          <p className="text-sm font-bold uppercase tracking-[0.28em] text-cyan-300">Nationwide proof</p>
          <h1 className="mt-4 text-4xl font-semibold tracking-tight md:text-6xl">Market Evidence</h1>
          <p className="mt-4 max-w-3xl leading-7 text-slate-300">
            Every accepted and excluded comparable stays auditable here. Exact listings use a raw median; fallback estimates show their adjustment method openly.
          </p>
        </section>

        <section className="mt-8 grid gap-4">
          {listings.map((listing) => (
            <Link
              className="grid gap-4 rounded-[2rem] border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-xl md:grid-cols-[9rem_minmax(0,1fr)_auto] md:items-center"
              href={`/market-evidence/${listing.id}`}
              key={listing.id}
            >
              <SafeCarImage
                alt={listing.title}
                className="h-28 w-full rounded-2xl object-cover md:w-36"
                fallbackClassName="flex h-28 w-full items-center justify-center rounded-2xl bg-slate-100 text-xs font-bold text-slate-400 md:w-36"
                src={listing.thumbnailPath}
              />
              <div>
                <div className="flex flex-wrap gap-2 text-xs font-bold">
                  <span className="rounded-full bg-cyan-100 px-3 py-1 text-cyan-800">{listing.marketValuationStatus.replaceAll("_", " ")}</span>
                  {listing.marketConfidence ? <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">{listing.marketConfidence.replaceAll("_", " ")}</span> : null}
                </div>
                <h2 className="mt-3 text-xl font-semibold">{listing.title}</h2>
                <p className="mt-2 text-sm text-slate-500">
                  {methodLabels[listing.marketValuationMethod ?? ""] ?? listing.marketSearchStage.replaceAll("_", " ")} | {listing.marketComparableCount} accepted | {listing.marketExactComparableCount} exact
                </p>
              </div>
              <div className="rounded-2xl bg-slate-50 px-5 py-4 text-right">
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">Market estimate</p>
                <p className="mt-1 text-2xl font-semibold">{formatMoney(listing.marketValueCents)}</p>
                <p className="mt-1 text-xs text-slate-500">Ask {formatMoney(listing.askingPriceCents)}</p>
              </div>
            </Link>
          ))}
        </section>
      </main>
    </div>
  );
}
