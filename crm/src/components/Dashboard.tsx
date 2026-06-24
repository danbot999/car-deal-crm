import Link from "next/link";

import { AppNav } from "@/components/AppNav";
import { SaveToAdminButton } from "@/components/SaveToAdminButton";
import { SafeCarImage } from "@/components/SafeCarImage";
import { ValuationButton } from "@/components/ValuationButton";
import {
  availabilityLabels,
  ListingStatus,
  statusLabels
} from "@/lib/listings";
import type { AvailabilityStatus } from "@/lib/listings";
import { formatMoney } from "@/lib/money";
import {
  isVehicleOrigin,
  vehicleOriginLabels,
  vehicleOrigins
} from "@/lib/vehicle-origin";
import type { VehicleOrigin } from "@/lib/vehicle-origin";

type DashboardListing = {
  id: string;
  facebookUrl: string;
  title: string;
  askingPriceCents: number;
  thumbnailPath: string | null;
  status: ListingStatus;
  availabilityStatus: AvailabilityStatus;
  availabilityConfidence: string;
  availabilityReason: string | null;
  lastVerifiedAt: Date | null;
  lastCheckedAt: Date | null;
  unavailableSince: Date | null;
  consecutiveUnavailableChecks: number;
  unavailableCheckCount: number;
  firstSeenAt: Date;
  numberPlate: string | null;
  numberPlateConfidence: number | null;
  kms: number | null;
  kmsConfidence: number | null;
  valuationCents: number | null;
  valuationStatus: string;
  valuationError: string | null;
  valuationCheckedAt: Date | null;
  valuationSource: string | null;
  marketValuationStatus: string;
  marketValuationError: string | null;
  marketValueCents: number | null;
  marketComparableCount: number;
  marketLowestComparableCents: number | null;
  marketHighestComparableCents: number | null;
  marketAucklandMedianCents: number | null;
  marketDifferenceCents: number | null;
  marketDifferencePercent: number | null;
  marketRelation: string | null;
  marketVerdict: string | null;
  marketConfidence: string | null;
  marketValuationMethod: string | null;
  marketRawMedianCents: number | null;
  marketExactComparableCount: number;
  marketAdjustmentJson: string | null;
  marketCoverageJson: string | null;
  marketSearchIdentity: string | null;
  marketSearchStage: string;
  marketSearchProgressJson: string | null;
  marketConfigurationWarning: string | null;
  marketReason: string | null;
  marketTargetSellCents: number | null;
  marketMaxBuyCents: number | null;
  marketExpectedSpreadCents: number | null;
  marketSourcesAttempted: number;
  marketSourcesSuccessful: number;
  marketSourceBreakdownJson: string | null;
  marketComparablesJson: string | null;
  marketValuedAt: Date | null;
  displayTargetSellPriceCents: number | null;
  displayMaxBuyPriceCents: number | null;
  displayEstimatedProfitCents: number | null;
  displayValuationCents: number | null;
  aiSummary: string | null;
  dealScore: number | null;
  riskLevel: string;
  aiEvaluationStatus: string;
  aiEvaluatedAt: Date | null;
  aiEvaluationError: string | null;
  profitabilitySummary: string | null;
  commonIssues: string | null;
  inspectionChecklist: string | null;
  sellerQuestions: string | null;
  riskFlags: string | null;
  recommendedAction: string | null;
  adminFlip: {
    id: string;
    vehicleTitle: string;
    status: string;
    sourceUrl: string | null;
    askingPriceCents: number | null;
    thumbnailPath: string | null;
    kms: number | null;
    rego: string | null;
    sellerContacted: boolean;
    sellerContactedAt: Date | null;
    priority: string;
    nextAction: string | null;
    purchaseDate: Date | null;
    saleDate: Date | null;
    purchasePriceCents: number;
    repairCostCents: number;
    otherCostCents: number;
    salePriceCents: number | null;
    notes: string | null;
    journalWentRight: string | null;
    journalWentWrong: string | null;
    journalLookOutFor: string | null;
  } | null;
};

type DashboardProps = {
  listings: DashboardListing[];
  stats: {
    total: number;
    activeTotal: number;
    visible: number;
    hiddenInactive: number;
    newCount: number;
    awaitingValuation: number;
    potentialLeads: number;
  };
  filters: Record<string, string | undefined>;
};

function dateLabel(date: Date) {
  return new Intl.DateTimeFormat("en-NZ", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}

function shortDateLabel(date: Date | null) {
  if (!date) {
    return null;
  }

  return new Intl.DateTimeFormat("en-NZ", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}

function jsonList(value: string | null) {
  if (!value) {
    return [];
  }

  try {
    const parsed = JSON.parse(value) as unknown;
    if (Array.isArray(parsed)) {
      return parsed.map(String).filter(Boolean);
    }
  } catch {
    return value
      .split(/\r?\n|;/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  return [];
}

const actionLabels: Record<string, string> = {
  GREAT_LEAD: "Strong lead",
  CONSIDER: "Consider",
  INSPECT_FIRST: "Inspect first",
  PASS: "Pass"
};

const aiStatusLabels: Record<string, string> = {
  NOT_STARTED: "Not evaluated",
  RUNNING: "Running",
  COMPLETED: "Evaluated",
  FAILED: "Failed"
};

const availabilityTone: Record<AvailabilityStatus, string> = {
  ACTIVE: "bg-emerald-100 text-emerald-800",
  NEEDS_REVIEW: "bg-amber-100 text-amber-800",
  POSSIBLY_SOLD: "bg-orange-100 text-orange-800",
  CONFIRMED_SOLD: "bg-rose-100 text-rose-800",
  SOLD: "bg-rose-100 text-rose-800",
  UNAVAILABLE: "bg-orange-100 text-orange-800",
  EXPIRED: "bg-slate-200 text-slate-700",
  UNKNOWN: "bg-amber-100 text-amber-800"
};

function StatCard({
  hint,
  label,
  value
}: {
  hint: string;
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white/85 p-5 shadow-sm shadow-slate-200/70">
      <p className="text-sm font-medium text-slate-500">{label}</p>
      <p className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
        {value}
      </p>
      <p className="mt-2 text-sm text-slate-500">{hint}</p>
    </div>
  );
}

function CompactMetric({
  label,
  tone = "default",
  value
}: {
  label: string;
  tone?: "default" | "good" | "bad";
  value: string;
}) {
  const valueClass =
    tone === "good"
      ? "text-emerald-700"
      : tone === "bad"
        ? "text-rose-700"
        : "text-slate-950";

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
        {label}
      </p>
      <p className={`mt-1 text-sm font-bold ${valueClass}`}>{value}</p>
    </div>
  );
}

function DealSnapshot({ listing }: { listing: DashboardListing }) {
  const profit = listing.displayEstimatedProfitCents;
  const profitTone = profit == null ? "default" : profit > 0 ? "good" : "bad";

  return (
    <div className="grid grid-cols-2 gap-3 rounded-3xl border border-slate-200 bg-slate-50/80 p-4 sm:grid-cols-4 xl:grid-cols-2">
      <CompactMetric label="Value" value={formatMoney(listing.displayValuationCents)} />
      <CompactMetric
        label="Max buy"
        value={formatMoney(listing.displayMaxBuyPriceCents)}
      />
      <CompactMetric
        label="Target"
        value={formatMoney(listing.displayTargetSellPriceCents)}
      />
      <CompactMetric
        label="Profit"
        tone={profitTone}
        value={formatMoney(profit)}
      />
    </div>
  );
}

function AiSnapshot({ listing }: { listing: DashboardListing }) {
  const actionLabel =
    actionLabels[listing.recommendedAction ?? ""] ??
    aiStatusLabels[listing.aiEvaluationStatus] ??
    "Not evaluated";
  const scoreLabel = listing.dealScore == null ? "No score" : `${listing.dealScore}/100`;
  const isStrong = listing.recommendedAction === "GREAT_LEAD";
  const isRisky = listing.recommendedAction === "PASS" || listing.riskLevel === "HIGH";
  const badgeClass = isStrong
    ? "bg-emerald-100 text-emerald-800"
    : isRisky
      ? "bg-rose-100 text-rose-800"
      : "bg-violet-100 text-violet-800";

  return (
    <div className="rounded-3xl border border-slate-200 bg-white/80 p-4">
      <div className="flex flex-wrap gap-2">
        <span className={`rounded-full px-3 py-1 text-xs font-bold ${badgeClass}`}>
          {actionLabel}
        </span>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-600">
          {scoreLabel}
        </span>
      </div>
      <p className="mt-3 line-clamp-3 text-sm leading-6 text-slate-600">
        {listing.aiSummary ??
          "Save a valuation, then open the Valuation button to run AI analysis."}
      </p>
    </div>
  );
}

type MarketComparable = {
  source?: string;
  title?: string;
  url?: string;
  priceCents?: number;
  year?: number | null;
  kms?: number | null;
  region?: string | null;
  matchTier?: string;
  matchScore?: number;
  accepted?: boolean;
  exclusionReason?: string | null;
};

function marketComparables(value: string | null): MarketComparable[] {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value) as unknown;
    return Array.isArray(parsed)
      ? parsed.filter((item): item is MarketComparable => Boolean(item && typeof item === "object"))
      : [];
  } catch {
    return [];
  }
}

const marketVerdictLabels: Record<string, string> = {
  EXCELLENT_DEAL: "Excellent deal",
  GOOD_DEAL: "Good deal",
  FAIR_MARKET_VALUE: "Fair market value",
  OVERPRICED: "Overpriced",
  VERY_OVERPRICED: "Very overpriced"
};

const marketMethodLabels: Record<string, string> = {
  EXACT: "Exact year/model median",
  GENERATION_ADJUSTED: "Generation-adjusted estimate",
  MODEL_ADJUSTED: "Model regression estimate",
  MAKE_CLASS_PROVISIONAL: "Make/class provisional estimate",
  CLASS_PROVISIONAL: "NZ class provisional estimate"
};

function marketProgress(value: string | null) {
  if (!value) return null;
  try {
    return JSON.parse(value) as {
      stage?: string;
      sourcesCompleted?: number;
      sourcesTotal?: number;
      comparablesFound?: number;
      updatedAt?: string;
    };
  } catch {
    return null;
  }
}

function MarketValuationPanel({ listing }: { listing: DashboardListing }) {
  const valued = listing.marketValueCents != null;
  const allEvidence = marketComparables(listing.marketComparablesJson);
  const evidence = allEvidence.filter((item) => item.accepted !== false);
  const progress = marketProgress(listing.marketSearchProgressJson);
  const difference = listing.marketDifferenceCents;
  const good = difference != null && difference > 0;
  const verdict = marketVerdictLabels[listing.marketVerdict ?? ""] ??
    "Valuation in progress";
  const badgeClass = !valued
    ? "bg-amber-100 text-amber-800"
    : good
      ? "bg-emerald-100 text-emerald-800"
      : difference === 0
        ? "bg-slate-100 text-slate-700"
        : "bg-rose-100 text-rose-800";

  return (
    <section className="rounded-[1.8rem] border border-cyan-100 bg-gradient-to-br from-cyan-50 via-white to-indigo-50 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-cyan-700">
            NZ asking-market index
          </p>
          <h3 className="mt-2 text-xl font-semibold text-slate-950">{verdict}</h3>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className={`rounded-full px-3 py-1 text-xs font-bold ${badgeClass}`}>
            {listing.marketValuationStatus.replaceAll("_", " ").toLowerCase()}
          </span>
          {listing.marketConfidence ? (
            <span className="rounded-full bg-white px-3 py-1 text-xs font-bold text-slate-600 ring-1 ring-slate-200">
              {listing.marketConfidence.toLowerCase()} confidence
            </span>
          ) : null}
        </div>
      </div>

      {valued ? (
        <>
          <div className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-6">
            <CompactMetric label="Market median" value={formatMoney(listing.marketValueCents)} />
            {listing.marketRawMedianCents != null && listing.marketRawMedianCents !== listing.marketValueCents ? (
              <CompactMetric label="Raw evidence median" value={formatMoney(listing.marketRawMedianCents)} />
            ) : null}
            <CompactMetric
              label="Difference"
              tone={good ? "good" : difference && difference < 0 ? "bad" : "default"}
              value={`${difference != null && difference > 0 ? "+" : ""}${formatMoney(difference)}`}
            />
            <CompactMetric
              label="Percent"
              tone={good ? "good" : difference && difference < 0 ? "bad" : "default"}
              value={listing.marketDifferencePercent == null ? "Awaiting valuation" : `${listing.marketDifferencePercent > 0 ? "+" : ""}${listing.marketDifferencePercent.toFixed(1)}%`}
            />
            <CompactMetric label="Comparables" value={String(listing.marketComparableCount)} />
            <CompactMetric
              label="Comparable range"
              value={`${formatMoney(listing.marketLowestComparableCents)} to ${formatMoney(listing.marketHighestComparableCents)}`}
            />
            <CompactMetric label="80% sell target" value={formatMoney(listing.marketTargetSellCents)} />
          </div>
          <p className="mt-4 text-sm leading-6 text-slate-600">{listing.marketReason}</p>
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs font-semibold text-slate-500">
            <span>{marketMethodLabels[listing.marketValuationMethod ?? ""] ?? listing.marketValuationMethod ?? "Evidence-backed estimate"}</span>
            <span>{listing.marketExactComparableCount} exact matches</span>
            <span>{listing.marketSourcesSuccessful}/{listing.marketSourcesAttempted} sources responded</span>
            <span>Max buy {formatMoney(listing.marketMaxBuyCents)}</span>
            <span>Expected spread {formatMoney(listing.marketExpectedSpreadCents)}</span>
            {listing.marketAucklandMedianCents ? (
              <span>Auckland median {formatMoney(listing.marketAucklandMedianCents)}</span>
            ) : null}
            {listing.marketValuedAt ? <span>Updated {dateLabel(listing.marketValuedAt)}</span> : null}
          </div>
        </>
      ) : (
        <div className="mt-4 grid gap-3">
          <p className="text-sm font-semibold text-slate-800">
            {listing.marketSearchStage.replaceAll("_", " ").toLowerCase()}
          </p>
          <p className="text-sm leading-6 text-slate-600">
            {listing.marketReason ?? listing.marketValuationError ??
              "The valuation worker is identifying this car and exhausting nationwide comparable sources."}
          </p>
          {progress ? (
            <div className="flex flex-wrap gap-2 text-xs font-semibold text-slate-500">
              {progress.sourcesTotal ? <span>{progress.sourcesCompleted ?? 0}/{progress.sourcesTotal} sources complete</span> : null}
              {progress.comparablesFound != null ? <span>{progress.comparablesFound} candidates found</span> : null}
            </div>
          ) : null}
        </div>
      )}

      {listing.marketConfigurationWarning ? (
        <p className="mt-4 rounded-2xl bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-800">
          {listing.marketConfigurationWarning}
        </p>
      ) : null}

      <div className="mt-5 flex flex-wrap gap-3">
        <Link
          className="inline-flex rounded-full bg-slate-950 px-5 py-2.5 text-sm font-bold text-white transition hover:-translate-y-0.5 hover:bg-slate-800"
          href={`/market-evidence/${listing.id}`}
        >
          Open Market Evidence
        </Link>
      </div>

      {evidence.length > 0 ? (
        <details className="mt-5 rounded-2xl border border-slate-200 bg-white/90">
          <summary className="cursor-pointer list-none px-4 py-3 text-sm font-bold text-slate-800">
            View {evidence.length} accepted comparable{evidence.length === 1 ? "" : "s"}
          </summary>
          <div className="grid gap-2 border-t border-slate-100 p-3">
            {evidence.map((item, index) => (
              <a
                className="grid gap-2 rounded-2xl bg-slate-50 p-3 text-sm transition hover:bg-cyan-50 sm:grid-cols-[minmax(0,1fr)_auto]"
                href={item.url}
                key={`${item.url ?? item.title}-${index}`}
                rel="noreferrer"
                target="_blank"
              >
                <span>
                  <strong className="block text-slate-900">{item.title ?? "Comparable vehicle"}</strong>
                  <span className="mt-1 block text-xs text-slate-500">
                    {[item.source, item.year, item.kms ? `${item.kms.toLocaleString("en-NZ")} km` : null, item.region, item.matchTier]
                      .filter(Boolean)
                      .join(" | ")}
                  </span>
                </span>
                <strong className="text-slate-950">{formatMoney(item.priceCents ?? null)}</strong>
              </a>
            ))}
          </div>
        </details>
      ) : null}
    </section>
  );
}

function ListingCard({ listing }: { listing: DashboardListing }) {
  return (
    <article className="rounded-[2rem] border border-slate-200 bg-white p-4 shadow-sm shadow-slate-200/60 transition hover:-translate-y-0.5 hover:shadow-xl hover:shadow-slate-200/80 md:p-5">
      <div className="grid gap-5">
        <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_24rem] lg:grid-cols-[minmax(0,1fr)_27rem] md:items-start">
          <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-cyan-100 px-3 py-1 text-xs font-semibold text-cyan-800">
              Facebook
            </span>
            <span
              className={`rounded-full px-3 py-1 text-xs font-bold ${availabilityTone[listing.availabilityStatus]}`}
              title={listing.availabilityReason ?? undefined}
            >
              {availabilityLabels[listing.availabilityStatus]}
            </span>
            <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-bold text-emerald-800">
              {statusLabels[listing.status]}
            </span>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
              {dateLabel(listing.firstSeenAt)}
            </span>
          </div>
          <h2 className="mt-3 text-xl font-semibold leading-snug text-slate-950">
            {listing.title}
          </h2>
          <a
            className="mt-3 inline-flex text-sm font-semibold text-cyan-700 hover:text-cyan-900"
            href={listing.facebookUrl}
            rel="noreferrer"
            target="_blank"
          >
            Open Marketplace listing
          </a>
          {listing.availabilityStatus !== "ACTIVE" ? (
            <p className="mt-3 rounded-2xl bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-800">
              {listing.availabilityStatus === "POSSIBLY_SOLD"
                ? "Needs confirmation"
                : listing.availabilityStatus === "NEEDS_REVIEW"
                  ? "Needs review"
                  : "Availability note"}
              :{" "}
              {listing.availabilityReason ??
                "Marketplace listing is no longer verified active."}
              {listing.availabilityConfidence ? (
                <span className="ml-1 font-medium">
                  ({listing.availabilityConfidence.toLowerCase()} confidence)
                </span>
              ) : null}
            </p>
          ) : null}
        </div>

          <div className="flex md:justify-end">
            <SafeCarImage
              alt={listing.title}
              className="h-64 w-full rounded-[1.8rem] object-cover shadow-xl shadow-slate-200/80 ring-1 ring-slate-200 md:h-72 md:w-96 lg:h-80 lg:w-[27rem]"
              fallbackClassName="flex h-64 w-full items-center justify-center rounded-[1.8rem] bg-slate-100 text-xs font-semibold text-slate-400 ring-1 ring-slate-200 md:h-72 md:w-96 lg:h-80 lg:w-[27rem]"
              src={listing.thumbnailPath}
            />
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-[120px_minmax(210px,0.85fr)_minmax(210px,1fr)]">
          <div className="rounded-3xl bg-slate-50 p-4 xl:bg-transparent xl:p-0">
          <p className="text-3xl font-semibold tracking-tight text-slate-950 xl:text-2xl">
            {formatMoney(listing.askingPriceCents)}
          </p>
          <p className="mt-1 text-sm text-slate-500">Asking price</p>
        </div>

        <DealSnapshot listing={listing} />
        <AiSnapshot listing={listing} />

        </div>

        <MarketValuationPanel listing={listing} />

        <ValuationButton
          aiEvaluatedAtLabel={shortDateLabel(listing.aiEvaluatedAt)}
          aiEvaluationError={listing.aiEvaluationError}
          aiEvaluationStatus={listing.aiEvaluationStatus}
          aiSummary={listing.aiSummary}
          askingPriceCents={listing.askingPriceCents}
          checkedAtLabel={shortDateLabel(listing.valuationCheckedAt)}
          commonIssues={jsonList(listing.commonIssues)}
          dealScore={listing.dealScore}
          disabled={listing.valuationStatus === "RUNNING"}
          estimatedProfitCents={listing.displayEstimatedProfitCents}
          facebookUrl={listing.facebookUrl}
          inspectionChecklist={jsonList(listing.inspectionChecklist)}
          kms={listing.kms}
          kmsConfidence={listing.kmsConfidence}
          listingId={listing.id}
          maxBuyPriceCents={listing.displayMaxBuyPriceCents}
          marketValueCents={listing.marketValueCents}
          numberPlate={listing.numberPlate}
          numberPlateConfidence={listing.numberPlateConfidence}
          profitabilitySummary={listing.profitabilitySummary}
          recommendedAction={listing.recommendedAction}
          riskFlags={jsonList(listing.riskFlags)}
          riskLevel={listing.riskLevel}
          sellerQuestions={jsonList(listing.sellerQuestions)}
          targetSellPriceCents={listing.displayTargetSellPriceCents}
          title={listing.title}
          valuationCents={listing.valuationCents}
          valuationError={listing.valuationError}
          valuationStatus={listing.valuationStatus}
        />

        <SaveToAdminButton
          adminFlip={listing.adminFlip}
          askingPriceCents={listing.askingPriceCents}
          facebookUrl={listing.facebookUrl}
          listingId={listing.id}
          thumbnailPath={listing.thumbnailPath}
          title={listing.title}
        />
      </div>
    </article>
  );
}

export function Dashboard({ filters, listings, stats }: DashboardProps) {
  const selectedOrigin: VehicleOrigin =
    filters.origin && isVehicleOrigin(filters.origin) ? filters.origin : "all";
  const hasActiveFilters =
    (Boolean(filters.q?.trim()) && filters.q?.trim() !== "") ||
    selectedOrigin !== "all";

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_#dbeafe,_transparent_32rem),linear-gradient(180deg,_#f8fafc,_#eef2ff)] px-4 py-8 text-slate-950 md:px-6">
      <main className="mx-auto max-w-[95rem]">
        <AppNav active="dashboard" />
        <section className="overflow-hidden rounded-[2rem] border border-white/70 bg-slate-950 shadow-2xl shadow-slate-300">
          <div className="grid gap-8 p-8 text-white lg:grid-cols-[1.4fr_0.6fr]">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.3em] text-cyan-300">
                Auckland Car Deal CRM
              </p>
              <h1 className="mt-5 max-w-4xl text-4xl font-semibold tracking-tight md:text-6xl">
                A cleaner command centre for finding underpriced cars.
              </h1>
              <p className="mt-5 max-w-2xl text-base leading-7 text-slate-300">
                Verified Marketplace listings flow in from n8n. One Valuation
                button opens the whole workflow: Trade Me value, deal math, and
                AI inspection guidance.
              </p>
            </div>
            <div className="rounded-3xl border border-white/10 bg-white/10 p-5 backdrop-blur">
              <p className="text-sm font-medium text-slate-300">Pricing rule</p>
              <div className="mt-4 space-y-3 text-sm text-slate-200">
                <div className="flex justify-between">
                  <span>Target sell</span>
                  <strong>Valuation x 80%</strong>
                </div>
                <div className="flex justify-between">
                  <span>Max buy</span>
                  <strong>Target sell - $1,000</strong>
                </div>
                <div className="flex justify-between">
                  <span>Profit</span>
                  <strong>Target sell - asking</strong>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="mt-8 grid gap-4 md:grid-cols-3 xl:grid-cols-6">
          <StatCard label="Total listings" value={stats.total} hint="Imported into the CRM" />
          <StatCard label="Active/checking" value={stats.activeTotal} hint="Shown by default" />
          <StatCard label="Visible now" value={stats.visible} hint="Matching current filters" />
          <StatCard label="Hidden inactive" value={stats.hiddenInactive} hint="Sold, unavailable, or expired" />
          <StatCard label="Awaiting market index" value={stats.awaitingValuation} hint="Queued for comparable search" />
          <StatCard label="Potential leads" value={stats.potentialLeads} hint="Positive 80% target spread" />
        </section>

        <form className="mt-8 rounded-[2rem] border border-slate-200 bg-white/90 p-4 shadow-sm shadow-slate-200/70">
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_17rem_auto_auto] lg:items-end">
            <label className="block">
              <span className="mb-2 block text-xs font-bold uppercase tracking-[0.18em] text-slate-400">
                Search
              </span>
              <input
                className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none ring-cyan-200 transition focus:ring-4"
                name="q"
                placeholder="Search title, make, model ..."
                defaultValue={filters.q ?? ""}
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-xs font-bold uppercase tracking-[0.18em] text-slate-400">
                Select Country
              </span>
              <select
                className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-800 outline-none ring-cyan-200 transition focus:ring-4"
                name="origin"
                defaultValue={selectedOrigin}
              >
                {vehicleOrigins.map((origin) => (
                  <option key={origin} value={origin}>
                    {vehicleOriginLabels[origin]}
                  </option>
                ))}
              </select>
            </label>
            <button className="rounded-2xl bg-slate-950 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-300 transition hover:-translate-y-0.5 hover:bg-slate-800">
              Filter
            </button>
            {hasActiveFilters ? (
              <a
                className="rounded-2xl border border-slate-200 px-6 py-3 text-center text-sm font-semibold text-slate-700 transition hover:-translate-y-0.5 hover:bg-slate-50"
                href="/dashboard"
              >
                Clear
              </a>
            ) : null}
          </div>
        </form>

        <section className="mt-8">
          {listings.length === 0 ? (
            <div className="rounded-[2rem] border border-slate-200 bg-white p-10 text-center shadow-xl shadow-slate-200/80">
              <p className="text-lg font-semibold text-slate-900">
                No listings match those filters.
              </p>
              <p className="mt-2 text-sm text-slate-500">
                Clear the filters or let the monitor collect more cars.
              </p>
            </div>
          ) : (
            <div className="grid gap-4">
              {listings.map((listing) => (
                <ListingCard key={listing.id} listing={listing} />
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
