import { AppNav } from "@/components/AppNav";
import { readSystemHealth, type ServiceHealth } from "@/lib/system-health";

export const dynamic = "force-dynamic";

function label(value: string) {
  return value.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[-_]/g, " ");
}

function serviceState(service: ServiceHealth) {
  if (service.healthy) return { text: "Healthy", classes: "bg-emerald-100 text-emerald-800" };
  return { text: "Needs attention", classes: "bg-rose-100 text-rose-800" };
}

function value(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default async function SystemHealthPage() {
  const health = await readSystemHealth();
  const queue = health.valuationQueue.counts ?? {};
  const overallClasses = health.overall === "healthy"
    ? "bg-emerald-500/15 text-emerald-200"
    : health.overall === "repairing"
      ? "bg-amber-500/15 text-amber-200"
      : "bg-rose-500/15 text-rose-200";

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_#cffafe,_transparent_34rem),radial-gradient(circle_at_top_right,_#ede9fe,_transparent_30rem),linear-gradient(180deg,_#f8fafc,_#eef2ff)] px-4 py-8 text-slate-950 md:px-6">
      <main className="mx-auto max-w-[95rem]">
        <AppNav active="system-health" />
        <section className="overflow-hidden rounded-[2.5rem] bg-slate-950 p-8 text-white shadow-2xl shadow-slate-300 md:p-10">
          <div className="flex flex-wrap items-start justify-between gap-5">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.28em] text-cyan-300">Self-healing automation</p>
              <h1 className="mt-4 text-4xl font-semibold tracking-tight md:text-6xl">CRM system health</h1>
              <p className="mt-4 max-w-3xl text-base leading-7 text-slate-300">
                The watchdog checks localhost, n8n, the Marketplace collector, listing sync, and safe valuation queue every five minutes.
              </p>
            </div>
            <span className={`rounded-full px-5 py-3 text-sm font-bold capitalize ${overallClasses}`}>{health.overall}</span>
          </div>
          <p className="mt-6 text-sm text-slate-400">Last checked {health.checkedAt ? new Date(health.checkedAt).toLocaleString("en-NZ") : "not yet"}</p>
        </section>

        <section className="mt-7 grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          {Object.entries(health.services).map(([name, service]) => {
            const state = serviceState(service);
            return (
              <article className="rounded-3xl border border-white bg-white/85 p-5 shadow-lg shadow-slate-200/70" key={name}>
                <div className="flex items-center justify-between gap-3">
                  <h2 className="font-semibold capitalize">{label(name)}</h2>
                  <span className={`rounded-full px-3 py-1 text-xs font-bold ${state.classes}`}>{state.text}</span>
                </div>
                <dl className="mt-4 space-y-2 text-sm text-slate-600">
                  {service.status ? <div className="flex justify-between gap-3"><dt>Status</dt><dd className="text-right">{label(service.status)}</dd></div> : null}
                  {service.httpStatus !== undefined ? <div className="flex justify-between gap-3"><dt>HTTP</dt><dd>{value(service.httpStatus)}</dd></div> : null}
                  {service.ageSeconds !== undefined ? <div className="flex justify-between gap-3"><dt>Heartbeat age</dt><dd>{value(service.ageSeconds)}s</dd></div> : null}
                </dl>
                {service.message ? <p className="mt-4 text-xs leading-5 text-slate-500">{service.message}</p> : null}
              </article>
            );
          })}
        </section>

        <section className="mt-7 grid gap-6 lg:grid-cols-2">
          <article className="rounded-[2rem] border border-slate-200 bg-white p-6 shadow-xl shadow-slate-200/70">
            <h2 className="text-2xl font-semibold">Valuation queue</h2>
            <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
              {Object.entries(queue).map(([status, count]) => (
                <div className="rounded-2xl bg-slate-50 p-4" key={status}>
                  <strong className="block text-2xl">{count}</strong>
                  <span className="mt-1 block text-xs font-bold uppercase tracking-wide text-slate-400">{label(status)}</span>
                </div>
              ))}
            </div>
          </article>
          <article className="rounded-[2rem] border border-slate-200 bg-white p-6 shadow-xl shadow-slate-200/70">
            <h2 className="text-2xl font-semibold">Listing reconciliation</h2>
            <dl className="mt-5 grid gap-3 sm:grid-cols-2">
              {Object.entries(health.listings).map(([name, item]) => (
                <div className="rounded-2xl bg-slate-50 p-4" key={name}>
                  <dt className="text-xs font-bold uppercase tracking-wide text-slate-400">{label(name)}</dt>
                  <dd className="mt-2 break-words text-lg font-semibold">{value(item)}</dd>
                </div>
              ))}
            </dl>
          </article>
        </section>

        <section className="mt-7 grid gap-6 lg:grid-cols-3">
          <article className="rounded-[2rem] border border-slate-200 bg-white p-6 shadow-xl shadow-slate-200/70">
            <h2 className="text-2xl font-semibold">Valuation source coverage</h2>
            <ul className="mt-5 grid gap-3 text-sm">
              {(health.valuationQueue.sources ?? []).map((source) => (
                <li className="rounded-2xl bg-slate-50 p-4" key={String(source.name)}>
                  <strong className="block">{value(source.name)}</strong>
                  <span className="mt-1 block text-slate-500">{label(String(source.health ?? "unknown"))} · last success {value(source.lastSuccessAt)}</span>
                </li>
              ))}
              {health.valuationQueue.sources?.length ? null : <li className="text-slate-500">No enabled valuation sources reported.</li>}
            </ul>
          </article>
          <article className="rounded-[2rem] border border-slate-200 bg-white p-6 shadow-xl shadow-slate-200/70">
            <h2 className="text-2xl font-semibold">Safety audit</h2>
            <dl className="mt-5 grid gap-3 text-sm">
              {Object.entries(health.qualityAudit).map(([name, item]) => (
                <div className="rounded-2xl bg-slate-50 p-4" key={name}>
                  <dt className="text-xs font-bold uppercase tracking-wide text-slate-400">{label(name)}</dt>
                  <dd className="mt-2 break-words font-semibold">{value(item)}</dd>
                </div>
              ))}
            </dl>
          </article>
          <article className="rounded-[2rem] border border-slate-200 bg-white p-6 shadow-xl shadow-slate-200/70">
            <h2 className="text-2xl font-semibold">Recent repairs</h2>
            <ul className="mt-5 grid gap-3 text-sm">
              {health.recentRepairs.slice(0, 5).map((repair, index) => (
                <li className="rounded-2xl bg-slate-50 p-4" key={`${String(repair.at)}-${index}`}>
                  <strong className="block">{value(repair.at)}</strong>
                  <span className="mt-1 block break-words text-slate-500">{value(repair.actions)}</span>
                </li>
              ))}
              {health.recentRepairs.length ? null : <li className="text-slate-500">No automated repairs recorded yet.</li>}
            </ul>
          </article>
        </section>

        <section className="mt-7 rounded-[2rem] border border-slate-200 bg-white p-6 shadow-xl shadow-slate-200/70">
          <h2 className="text-2xl font-semibold">Unresolved incidents</h2>
          {health.issues.length ? (
            <ul className="mt-5 grid gap-3">
              {health.issues.map((issue) => <li className="rounded-2xl bg-rose-50 px-4 py-3 text-sm font-medium text-rose-900" key={issue}>{issue}</li>)}
            </ul>
          ) : <p className="mt-4 text-sm text-emerald-700">No unresolved incidents.</p>}
        </section>
      </main>
    </div>
  );
}
