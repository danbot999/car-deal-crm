import Link from "next/link";

import { AppNav } from "@/components/AppNav";
import { getLeads } from "@/lib/leads";
import { formatMoney } from "@/lib/money";

export const dynamic = "force-dynamic";

function dateLabel(date: Date | null) {
  if (!date) {
    return "Not saved";
  }

  return new Intl.DateTimeFormat("en-NZ", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}

function actionLabel(value: string | null) {
  const labels: Record<string, string> = {
    GREAT_LEAD: "Strong lead",
    CONSIDER: "Consider",
    INSPECT_FIRST: "Inspect first",
    PASS: "Pass"
  };

  return labels[value ?? ""] ?? "Review";
}

export default async function LeadsPage() {
  const leads = await getLeads();
  const strongLeads = leads.filter(
    (lead) => lead.recommendedAction === "GREAT_LEAD"
  ).length;
  const highRisk = leads.filter((lead) => lead.riskLevel === "HIGH").length;

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_#dbeafe,_transparent_32rem),linear-gradient(180deg,_#f8fafc,_#eef2ff)] px-4 py-8 text-slate-950 md:px-6">
      <main className="mx-auto max-w-[95rem]">
        <AppNav active="leads" />

        <section className="overflow-hidden rounded-[2rem] border border-white/70 bg-slate-950 p-8 text-white shadow-2xl shadow-slate-300">
          <p className="text-sm font-semibold uppercase tracking-[0.3em] text-cyan-300">
            Leads
          </p>
          <div className="mt-5 grid gap-6 lg:grid-cols-[1.2fr_0.8fr] lg:items-end">
            <div>
              <h1 className="max-w-4xl text-4xl font-semibold tracking-tight md:text-6xl">
                Evaluated cars with the full due-diligence report ready.
              </h1>
              <p className="mt-5 max-w-2xl text-base leading-7 text-slate-300">
                This is where finished AI reports land after you press Evaluate:
                price math, risk profile, engine and gearbox failure research,
                and inspection questions in one clean workspace.
              </p>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-3xl bg-white/10 p-4">
                <p className="text-3xl font-semibold">{leads.length}</p>
                <p className="mt-1 text-sm text-slate-300">Reports</p>
              </div>
              <div className="rounded-3xl bg-white/10 p-4">
                <p className="text-3xl font-semibold">{strongLeads}</p>
                <p className="mt-1 text-sm text-slate-300">Strong</p>
              </div>
              <div className="rounded-3xl bg-white/10 p-4">
                <p className="text-3xl font-semibold">{highRisk}</p>
                <p className="mt-1 text-sm text-slate-300">High risk</p>
              </div>
            </div>
          </div>
        </section>

        <section className="mt-8 grid gap-4">
          {leads.length === 0 ? (
            <div className="rounded-[2rem] border border-slate-200 bg-white p-10 text-center shadow-xl shadow-slate-200/80">
              <p className="text-lg font-semibold text-slate-900">
                No evaluated leads yet.
              </p>
              <p className="mt-2 text-sm text-slate-500">
                Save a Trade Me valuation on the dashboard, then press Evaluate.
              </p>
            </div>
          ) : (
            leads.map((lead) => (
              <article
                className="grid gap-5 rounded-[2rem] border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/70 transition hover:-translate-y-0.5 hover:shadow-xl hover:shadow-slate-200/80 lg:grid-cols-[20rem_minmax(0,1fr)_14rem]"
                key={lead.id}
              >
                {lead.thumbnailPath ? (
                  <img
                    alt={lead.title}
                    className="h-64 w-full rounded-[1.8rem] object-cover shadow-xl shadow-slate-200/80 ring-1 ring-slate-200 lg:h-56"
                    src={lead.thumbnailPath}
                  />
                ) : (
                  <div className="flex h-64 items-center justify-center rounded-[1.8rem] bg-slate-100 text-sm font-semibold text-slate-400 lg:h-56">
                    No photo
                  </div>
                )}

                <div>
                  <div className="flex flex-wrap gap-2 text-xs font-bold">
                    <span className="rounded-full bg-cyan-100 px-3 py-1 text-cyan-800">
                      {actionLabel(lead.recommendedAction)}
                    </span>
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">
                      Risk {lead.riskLevel.toLowerCase()}
                    </span>
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">
                      {dateLabel(lead.leadSavedAt)}
                    </span>
                  </div>
                  <h2 className="mt-4 text-2xl font-semibold tracking-tight text-slate-950">
                    {lead.title}
                  </h2>
                  <p className="mt-3 line-clamp-3 text-sm leading-6 text-slate-600">
                    {lead.report?.aiSummary ?? lead.aiSummary}
                  </p>
                  <div className="mt-4 flex flex-wrap gap-2 text-sm">
                    <a
                      className="font-bold text-cyan-700 hover:text-cyan-900"
                      href={lead.facebookUrl}
                      rel="noreferrer"
                      target="_blank"
                    >
                      Marketplace listing
                    </a>
                    <span className="text-slate-300">/</span>
                    <span className="font-semibold text-slate-500">
                      Score {lead.dealScore ?? 0}/100
                    </span>
                  </div>
                </div>

                <div className="rounded-3xl bg-slate-50 p-4">
                  <p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">
                    Deal math
                  </p>
                  <div className="mt-3 space-y-3 text-sm">
                    <div className="flex justify-between gap-3">
                      <span className="text-slate-500">Ask</span>
                      <strong>{formatMoney(lead.askingPriceCents)}</strong>
                    </div>
                    <div className="flex justify-between gap-3">
                      <span className="text-slate-500">Max buy</span>
                      <strong>{formatMoney(lead.displayMaxBuyPriceCents)}</strong>
                    </div>
                    <div className="flex justify-between gap-3">
                      <span className="text-slate-500">Profit</span>
                      <strong>{formatMoney(lead.displayEstimatedProfitCents)}</strong>
                    </div>
                  </div>
                  <Link
                    className="mt-5 inline-flex w-full items-center justify-center rounded-2xl bg-slate-950 px-4 py-3 text-sm font-bold text-white transition hover:bg-slate-800"
                    href={`/leads/${lead.id}`}
                  >
                    Open report
                  </Link>
                </div>
              </article>
            ))
          )}
        </section>
      </main>
    </div>
  );
}
