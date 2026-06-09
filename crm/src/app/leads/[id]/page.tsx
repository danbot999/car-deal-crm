import { AppNav } from "@/components/AppNav";
import { getLead } from "@/lib/leads";
import { FailurePoint, LeadSource } from "@/lib/lead-report";
import { formatMoney } from "@/lib/money";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{
    id: string;
  }>;
};

function dateLabel(date: Date | null) {
  if (!date) {
    return "Not saved";
  }

  return new Intl.DateTimeFormat("en-NZ", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}

function Section({
  children,
  defaultOpen = false,
  kicker,
  title
}: {
  children: React.ReactNode;
  defaultOpen?: boolean;
  kicker?: string;
  title: string;
}) {
  return (
    <details
      className="group rounded-[1.75rem] border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/60 open:shadow-xl open:shadow-slate-200/70"
      open={defaultOpen}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 [&::-webkit-details-marker]:hidden">
        <span>
          {kicker ? (
            <span className="text-xs font-bold uppercase tracking-[0.18em] text-cyan-700">
              {kicker}
            </span>
          ) : null}
          <span className="block text-xl font-semibold tracking-tight text-slate-950">
            {title}
          </span>
        </span>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-sm font-bold text-slate-500 group-open:bg-slate-950 group-open:text-white">
          Open
        </span>
      </summary>
      <div className="mt-5 border-t border-slate-100 pt-5">{children}</div>
    </details>
  );
}

function SimpleList({ items }: { items: string[] }) {
  if (items.length === 0) {
    return (
      <p className="text-sm leading-6 text-slate-500">
        No specific notes were returned for this section.
      </p>
    );
  }

  return (
    <ul className="grid gap-3">
      {items.map((item) => (
        <li
          className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700"
          key={item}
        >
          {item}
        </li>
      ))}
    </ul>
  );
}

function Metric({
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
    <div className="rounded-3xl bg-white/85 p-4">
      <p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">
        {label}
      </p>
      <p className={`mt-2 text-lg font-semibold ${valueClass}`}>{value}</p>
    </div>
  );
}

function FailurePointCard({ point }: { point: FailurePoint }) {
  const severityClass =
    point.severity === "HIGH"
      ? "bg-rose-100 text-rose-800"
      : point.severity === "MEDIUM"
        ? "bg-amber-100 text-amber-800"
        : "bg-slate-100 text-slate-700";

  return (
    <article className="rounded-[1.5rem] border border-slate-200 bg-white p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">
            {point.area}
          </p>
          <h3 className="mt-2 text-lg font-semibold text-slate-950">
            {point.component}
          </h3>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-bold ${severityClass}`}>
          {point.severity} severity
        </span>
      </div>
      <p className="mt-4 text-sm font-semibold leading-6 text-slate-900">
        {point.specificFailure}
      </p>
      <p className="mt-3 text-sm leading-6 text-slate-600">
        {point.whyItMatters}
      </p>
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <div className="rounded-2xl bg-slate-50 p-3">
          <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-400">
            Likelihood
          </p>
          <p className="mt-1 text-sm font-bold text-slate-900">
            {point.likelihood}
          </p>
        </div>
        <div className="rounded-2xl bg-slate-50 p-3">
          <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-400">
            Cost range
          </p>
          <p className="mt-1 text-sm font-bold text-slate-900">
            {point.roughCostRange}
          </p>
        </div>
        <div className="rounded-2xl bg-slate-50 p-3">
          <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-400">
            Inspect for
          </p>
          <p className="mt-1 text-sm font-bold text-slate-900">
            {point.inspectionSignal}
          </p>
        </div>
      </div>
      {point.sourceHint ? (
        <p className="mt-4 text-xs font-medium text-slate-500">
          Source note: {point.sourceHint}
        </p>
      ) : null}
    </article>
  );
}

function Sources({ sources }: { sources: LeadSource[] }) {
  if (sources.length === 0) {
    return (
      <p className="text-sm leading-6 text-slate-500">
        No web citations were saved. This usually means the evaluation failed
        before web research completed, or it was generated in mock mode.
      </p>
    );
  }

  return (
    <div className="grid gap-3 md:grid-cols-2">
      {sources.map((source) => (
        <a
          className="rounded-2xl border border-slate-200 bg-slate-50 p-4 transition hover:border-cyan-200 hover:bg-cyan-50"
          href={source.url}
          key={source.url}
          rel="noreferrer"
          target="_blank"
        >
          <p className="text-sm font-bold text-slate-950">{source.title}</p>
          {source.note ? (
            <p className="mt-2 text-sm leading-6 text-slate-600">
              {source.note}
            </p>
          ) : null}
          <p className="mt-2 break-all text-xs font-semibold text-cyan-700">
            {source.url}
          </p>
        </a>
      ))}
    </div>
  );
}

export default async function LeadDetailPage({ params }: PageProps) {
  const { id } = await params;
  const lead = await getLead(id);
  const report = lead.report;
  const profitTone =
    lead.displayEstimatedProfitCents == null
      ? "default"
      : lead.displayEstimatedProfitCents > 0
        ? "good"
        : "bad";

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_#dbeafe,_transparent_32rem),linear-gradient(180deg,_#f8fafc,_#eef2ff)] px-4 py-8 text-slate-950 md:px-6">
      <main className="mx-auto max-w-[95rem]">
        <AppNav active="leads" />

        <section className="grid gap-6 rounded-[2rem] border border-white/70 bg-slate-950 p-5 text-white shadow-2xl shadow-slate-300 lg:grid-cols-[28rem_minmax(0,1fr)] lg:p-8">
          {lead.thumbnailPath ? (
            <img
              alt={lead.title}
              className="h-80 w-full rounded-[1.8rem] object-cover shadow-2xl shadow-slate-950/40 ring-1 ring-white/20 lg:h-full"
              src={lead.thumbnailPath}
            />
          ) : (
            <div className="flex h-80 items-center justify-center rounded-[1.8rem] bg-white/10 text-sm font-semibold text-slate-300">
              No photo
            </div>
          )}

          <div className="flex flex-col justify-between gap-8">
            <div>
              <div className="flex flex-wrap gap-2 text-xs font-bold">
                <span className="rounded-full bg-cyan-300 px-3 py-1 text-slate-950">
                  {report.recommendedAction.replace(/_/g, " ")}
                </span>
                <span className="rounded-full bg-white/10 px-3 py-1 text-slate-200">
                  Risk {report.riskLevel.toLowerCase()}
                </span>
                <span className="rounded-full bg-white/10 px-3 py-1 text-slate-200">
                  Saved {dateLabel(lead.leadSavedAt)}
                </span>
              </div>
              <h1 className="mt-5 text-4xl font-semibold tracking-tight md:text-6xl">
                {lead.title}
              </h1>
              <p className="mt-5 max-w-3xl text-base leading-7 text-slate-300">
                {report.verdict}
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Metric label="Ask" value={formatMoney(lead.askingPriceCents)} />
              <Metric
                label="Max buy"
                value={formatMoney(lead.displayMaxBuyPriceCents)}
              />
              <Metric
                label="Target sell"
                value={formatMoney(lead.displayTargetSellPriceCents)}
              />
              <Metric
                label="Profit at ask"
                tone={profitTone}
                value={formatMoney(lead.displayEstimatedProfitCents)}
              />
            </div>
          </div>
        </section>

        <section className="mt-6 grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="rounded-[1.75rem] border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/70">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-cyan-700">
              Vehicle identity
            </p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-950">
              {report.vehicleIdentity.summary}
            </h2>
            <div className="mt-5 grid gap-3 text-sm md:grid-cols-2">
              <Metric
                label="Engine"
                value={
                  report.vehicleIdentity.engineCode ??
                  report.vehicleIdentity.likelyEngineFamily ??
                  "Verify"
                }
              />
              <Metric
                label="Transmission"
                value={report.vehicleIdentity.transmission ?? "Verify"}
              />
              <Metric
                label="Kms"
                value={
                  report.vehicleIdentity.kms == null
                    ? "Unknown"
                    : `${new Intl.NumberFormat("en-NZ").format(
                        report.vehicleIdentity.kms
                      )} km`
                }
              />
              <Metric
                label="Confidence"
                value={`${report.vehicleIdentity.confidence}/100`}
              />
            </div>
          </div>

          <div className="rounded-[1.75rem] border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/70">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-cyan-700">
              Deal thesis
            </p>
            <p className="mt-3 text-lg font-semibold leading-7 text-slate-950">
              {report.aiSummary}
            </p>
            <p className="mt-4 text-sm leading-6 text-slate-600">
              {report.marketPosition}
            </p>
          </div>
        </section>

        <section className="mt-6 grid gap-4">
          <Section defaultOpen kicker="Most important" title="Failure points">
            <div className="grid gap-4">
              {report.failurePoints.map((point) => (
                <FailurePointCard
                  key={`${point.area}-${point.component}-${point.specificFailure}`}
                  point={point}
                />
              ))}
            </div>
          </Section>

          <Section defaultOpen kicker="Buyer workflow" title="Questions to ask seller">
            <SimpleList items={report.sellerQuestions} />
          </Section>

          <Section kicker="Inspection" title="Inspection checklist">
            <SimpleList items={report.inspectionChecklist} />
          </Section>

          <Section kicker="Road test" title="Test-drive checklist">
            <SimpleList items={report.testDriveChecklist} />
          </Section>

          <Section kicker="Stop signs" title="Walk-away triggers">
            <SimpleList items={report.walkAwayTriggers} />
          </Section>

          <Section kicker="Ownership" title="Costs, parts, WOF, and rego risk">
            <div className="grid gap-4 lg:grid-cols-3">
              <div className="rounded-3xl bg-slate-50 p-4">
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">
                  Ownership costs
                </p>
                <div className="mt-3">
                  <SimpleList items={report.ownershipCosts} />
                </div>
              </div>
              <div className="rounded-3xl bg-slate-50 p-4">
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">
                  Parts availability
                </p>
                <p className="mt-3 text-sm leading-6 text-slate-700">
                  {report.partsAvailability}
                </p>
              </div>
              <div className="rounded-3xl bg-slate-50 p-4">
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">
                  WOF and rego
                </p>
                <div className="mt-3">
                  <SimpleList items={report.wofRegoComplianceRisks} />
                </div>
              </div>
            </div>
          </Section>

          <Section kicker="Research" title="Sources">
            <Sources sources={lead.sources.length > 0 ? lead.sources : report.sourceNotes} />
          </Section>
        </section>
      </main>
    </div>
  );
}
