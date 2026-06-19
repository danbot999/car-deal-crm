import Link from "next/link";

import { getAdminData } from "@/lib/admin";
import { getDashboardData } from "@/lib/listings";
import { formatMoney } from "@/lib/money";

export const dynamic = "force-dynamic";

function ChoiceCard({
  accent,
  description,
  href,
  kicker,
  metrics,
  title
}: {
  accent: "cyan" | "violet";
  description: string;
  href: string;
  kicker: string;
  metrics: Array<{ label: string; value: string | number }>;
  title: string;
}) {
  const gradient =
    accent === "cyan"
      ? "from-cyan-300/35 via-white to-white"
      : "from-violet-300/35 via-white to-white";
  const button =
    accent === "cyan"
      ? "bg-cyan-700 hover:bg-cyan-800"
      : "bg-violet-700 hover:bg-violet-800";

  return (
    <article
      className={`group flex min-h-[32rem] flex-col justify-between overflow-hidden rounded-[2.5rem] border border-white/80 bg-gradient-to-br ${gradient} p-7 shadow-2xl shadow-slate-300/70 transition hover:-translate-y-1 hover:shadow-slate-400/60`}
    >
      <div>
        <div className="flex items-center justify-between gap-4">
          <p className="text-xs font-bold uppercase tracking-[0.28em] text-slate-500">
            {kicker}
          </p>
          <span className="rounded-full bg-slate-950 px-4 py-2 text-xs font-bold text-white">
            Open
          </span>
        </div>
        <h2 className="mt-8 text-5xl font-semibold tracking-tight text-slate-950 md:text-6xl">
          {title}
        </h2>
        <p className="mt-5 max-w-xl text-base leading-7 text-slate-600">
          {description}
        </p>
      </div>

      <div>
        <div className="grid gap-3 sm:grid-cols-3">
          {metrics.map((metric) => (
            <div
              className="rounded-3xl border border-white/80 bg-white/75 p-4 shadow-sm shadow-slate-200/60"
              key={metric.label}
            >
              <p className="text-2xl font-semibold text-slate-950">
                {metric.value}
              </p>
              <p className="mt-1 text-xs font-bold uppercase tracking-[0.14em] text-slate-400">
                {metric.label}
              </p>
            </div>
          ))}
        </div>
        <Link
          className={`mt-5 inline-flex w-full items-center justify-center rounded-3xl px-5 py-4 text-sm font-bold text-white shadow-xl shadow-slate-300/70 transition hover:scale-[1.01] ${button}`}
          href={href}
        >
          Open {title}
        </Link>
      </div>
    </article>
  );
}

export default async function HomePage() {
  const [dashboard, admin] = await Promise.all([
    getDashboardData({}),
    getAdminData()
  ]);

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_#dbeafe,_transparent_34rem),radial-gradient(circle_at_top_right,_#ede9fe,_transparent_30rem),linear-gradient(180deg,_#f8fafc,_#eef2ff)] px-4 py-8 text-slate-950 md:px-6">
      <main className="mx-auto max-w-[95rem]">
        <section className="overflow-hidden rounded-[2.5rem] border border-white/70 bg-slate-950 p-8 text-white shadow-2xl shadow-slate-300 md:p-10">
          <p className="text-sm font-semibold uppercase tracking-[0.32em] text-cyan-300">
            Auckland Car Flip Command Centre
          </p>
          <div className="mt-6 grid gap-6 lg:grid-cols-[1.2fr_0.8fr] lg:items-end">
            <div>
              <h1 className="max-w-5xl text-5xl font-semibold tracking-tight md:text-7xl">
                Choose where you want to work.
              </h1>
              <p className="mt-5 max-w-2xl text-base leading-7 text-slate-300">
                Dashboard is for finding and evaluating Marketplace leads. Admin
                is for running the business side: money in, money out, cars
                bought, cars sold, and lessons from every flip.
              </p>
            </div>
            <div className="rounded-[2rem] border border-white/10 bg-white/10 p-5 backdrop-blur">
              <p className="text-sm font-medium text-slate-300">
                Current snapshot
              </p>
              <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-2xl bg-white/10 p-3">
                  <strong className="block text-2xl">
                    {dashboard.stats.total}
                  </strong>
                  <span className="text-slate-300">CRM listings</span>
                </div>
                <div className="rounded-2xl bg-white/10 p-3">
                  <strong className="block text-2xl">
                    {admin.stats.carsBought}
                  </strong>
                  <span className="text-slate-300">Cars bought</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="mt-8 grid gap-6 xl:grid-cols-2">
          <ChoiceCard
            accent="violet"
            description="Track cash spent, cars bought, active inventory, sales, profit, and your journal notes without touching code."
            href="/admin"
            kicker="Operations"
            metrics={[
              { label: "Cars tracked", value: admin.stats.carsTracked },
              { label: "Open capital", value: formatMoney(admin.stats.openCapitalCents) },
              { label: "Profit", value: formatMoney(admin.stats.realizedProfitCents) }
            ]}
            title="ADMIN"
          />
          <ChoiceCard
            accent="cyan"
            description="Review live Auckland under-$7,000 Marketplace finds, save valuations, evaluate leads, and open comprehensive reports."
            href="/dashboard"
            kicker="Research"
            metrics={[
              { label: "Listings", value: dashboard.stats.total },
              { label: "Awaiting value", value: dashboard.stats.awaitingValuation },
              { label: "Potential leads", value: dashboard.stats.potentialLeads }
            ]}
            title="DASHBOARD"
          />
        </section>
      </main>
    </div>
  );
}
