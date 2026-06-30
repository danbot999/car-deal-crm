import Link from "next/link";
import { notFound } from "next/navigation";

import { AppNav } from "@/components/AppNav";
import { SafeCarImage } from "@/components/SafeCarImage";
import { prisma } from "@/lib/db";
import { formatMoney } from "@/lib/money";

export const dynamic = "force-dynamic";

type Evidence = {
  source?: string;
  title?: string;
  url?: string;
  priceCents?: number;
  year?: number | null;
  make?: string | null;
  model?: string | null;
  variant?: string | null;
  kms?: number | null;
  transmission?: string | null;
  fuelType?: string | null;
  bodyType?: string | null;
  region?: string | null;
  observedAt?: string | null;
  matchTier?: string | null;
  matchScore?: number;
  accepted?: boolean;
  exclusionReason?: string | null;
};

function parseArray(value: string | null): Evidence[] {
  try {
    const parsed = JSON.parse(value ?? "[]") as unknown;
    return Array.isArray(parsed) ? parsed.filter((item): item is Evidence => Boolean(item && typeof item === "object")) : [];
  } catch {
    return [];
  }
}

function parseObject(value: string | null): Record<string, unknown> {
  try {
    const parsed = JSON.parse(value ?? "{}") as unknown;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
  } catch {
    return {};
  }
}

function EvidenceRows({ items }: { items: Evidence[] }) {
  if (items.length === 0) return <p className="text-sm text-slate-500">No rows have been recorded for this section yet.</p>;
  return (
    <div className="grid gap-3">
      {items.map((item, index) => (
        <a
          className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 transition hover:border-cyan-300 hover:bg-cyan-50/40 lg:grid-cols-[minmax(0,1fr)_auto]"
          href={item.url}
          key={`${item.url ?? item.title}-${index}`}
          rel="noreferrer"
          target="_blank"
        >
          <div>
            <p className="font-bold text-slate-900">{item.title ?? "Comparable listing"}</p>
            <p className="mt-1 text-xs leading-5 text-slate-500">
              {[item.source, item.year, item.make, item.model, item.variant, item.kms ? `${item.kms.toLocaleString("en-NZ")} km` : null, item.transmission, item.fuelType, item.bodyType, item.region]
                .filter(Boolean).join(" | ")}
            </p>
            {item.exclusionReason ? <p className="mt-2 text-xs font-semibold text-amber-700">Excluded: {item.exclusionReason.replaceAll("_", " ")}</p> : null}
          </div>
          <div className="text-left lg:text-right">
            <p className="text-lg font-bold">{formatMoney(item.priceCents ?? null)}</p>
            <p className="mt-1 text-xs text-slate-500">{item.matchTier?.replaceAll("_", " ") ?? "Outside selected cohort"}</p>
          </div>
        </a>
      ))}
    </div>
  );
}

export default async function MarketEvidenceDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const listing = await prisma.listing.findUnique({ where: { id } });
  if (!listing) notFound();
  const rows = parseArray(listing.marketComparablesJson);
  const accepted = rows.filter((row) => row.accepted !== false);
  const excluded = rows.filter((row) => row.accepted === false);
  const coverage = parseObject(listing.marketCoverageJson);
  const adjustment = parseObject(listing.marketAdjustmentJson);

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-8 text-slate-950 md:px-6">
      <main className="mx-auto max-w-[95rem]">
        <AppNav active="market-evidence" />
        <Link className="text-sm font-bold text-cyan-700" href="/market-evidence">&lt;- All market evidence</Link>
        <section className="mt-5 grid gap-6 rounded-[2rem] bg-slate-950 p-6 text-white shadow-2xl lg:grid-cols-[minmax(0,1fr)_28rem] lg:p-8">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.24em] text-cyan-300">{listing.marketValuationMethod?.replaceAll("_", " ") ?? listing.marketSearchStage.replaceAll("_", " ")}</p>
            <h1 className="mt-4 text-4xl font-semibold tracking-tight">{listing.title}</h1>
            <p className="mt-4 max-w-3xl leading-7 text-slate-300">{listing.marketReason ?? "Nationwide comparable search is still running."}</p>
            <a className="mt-5 inline-flex rounded-full bg-white px-5 py-2.5 text-sm font-bold text-slate-950" href={listing.facebookUrl} rel="noreferrer" target="_blank">Open Facebook listing</a>
          </div>
          <SafeCarImage alt={listing.title} className="h-72 w-full rounded-[1.5rem] object-cover" fallbackClassName="flex h-72 items-center justify-center rounded-[1.5rem] bg-white/10 text-sm text-slate-300" src={listing.thumbnailPath} />
        </section>

        <section className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
          {[
            ["Asking", formatMoney(listing.askingPriceCents)],
            ["Market estimate", formatMoney(listing.marketValueCents)],
            ["Raw median", formatMoney(listing.marketRawMedianCents)],
            ["Accepted", String(listing.marketComparableCount)],
            ["Exact", String(listing.marketExactComparableCount)],
            ["Range", `${formatMoney(listing.marketLowestComparableCents)} to ${formatMoney(listing.marketHighestComparableCents)}`]
          ].map(([label, value]) => (
            <div className="rounded-3xl border border-slate-200 bg-white p-5" key={label}>
              <p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">{label}</p>
              <p className="mt-2 text-lg font-bold">{value}</p>
            </div>
          ))}
        </section>

        <section className="mt-6 grid gap-6 lg:grid-cols-2">
          <div className="rounded-[2rem] border border-slate-200 bg-white p-6">
            <h2 className="text-xl font-semibold">Calculation</h2>
            <pre className="mt-4 overflow-auto rounded-2xl bg-slate-950 p-4 text-xs leading-6 text-cyan-100">{JSON.stringify(adjustment, null, 2)}</pre>
          </div>
          <div className="rounded-[2rem] border border-slate-200 bg-white p-6">
            <h2 className="text-xl font-semibold">Source coverage</h2>
            <pre className="mt-4 max-h-80 overflow-auto rounded-2xl bg-slate-950 p-4 text-xs leading-6 text-cyan-100">{JSON.stringify(coverage, null, 2)}</pre>
          </div>
        </section>

        <section className="mt-6 rounded-[2rem] border border-slate-200 bg-white p-6">
          <h2 className="text-2xl font-semibold">Accepted comparable links ({accepted.length})</h2>
          <p className="mt-2 text-sm text-slate-500">Only these deduplicated asking prices are used in the market median.</p>
          <div className="mt-5"><EvidenceRows items={accepted} /></div>
        </section>

        <details className="mt-6 rounded-[2rem] border border-slate-200 bg-white p-6">
          <summary className="cursor-pointer text-xl font-semibold">Excluded search results - not used in valuation ({excluded.length})</summary>
          <div className="mt-5"><EvidenceRows items={excluded} /></div>
        </details>
      </main>
    </div>
  );
}
