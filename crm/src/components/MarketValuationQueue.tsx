"use client";

import { useCallback, useEffect, useState } from "react";

import { formatMoney } from "@/lib/money";

type QueueJob = {
  id: string;
  listingId: string;
  status: string;
  attempts: number;
  lastError: string | null;
  title: string;
  facebookUrl: string;
  askingPriceCents: number;
  year: number | null;
  make: string | null;
  model: string | null;
};

export function MarketValuationQueue() {
  const [jobs, setJobs] = useState<QueueJob[]>([]);
  const [unavailable, setUnavailable] = useState(false);
  const [open, setOpen] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    const response = await fetch("/api/market-valuations/jobs", { cache: "no-store" });
    const payload = (await response.json()) as { jobs?: QueueJob[]; unavailable?: boolean };
    setJobs(payload.jobs ?? []);
    setUnavailable(Boolean(payload.unavailable));
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 30_000);
    return () => window.clearInterval(timer);
  }, [load]);

  async function retry(jobId: string) {
    setBusyId(jobId);
    try {
      await fetch(`/api/market-valuations/jobs/${jobId}/retry`, { method: "POST" });
      await load();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="mb-6 overflow-hidden rounded-[2rem] border border-white/80 bg-white/90 shadow-xl shadow-slate-200/60">
      <button
        className="flex w-full items-center justify-between gap-4 p-5 text-left"
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        <span>
          <span className="block text-xs font-bold uppercase tracking-[0.2em] text-cyan-700">Market index</span>
          <span className="mt-1 block text-lg font-semibold text-slate-950">Valuation queue</span>
          <span className="mt-1 block text-sm text-slate-500">
            {unavailable ? "Local valuation service is offline." : `${jobs.length} cars need attention or are still processing.`}
          </span>
        </span>
        <span className="rounded-full bg-slate-950 px-4 py-2 text-sm font-bold text-white">
          {open ? "Hide" : "Open queue"}
        </span>
      </button>
      {open ? (
        <div className="border-t border-slate-100 p-4">
          {jobs.length === 0 ? (
            <p className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-600">
              {unavailable ? "Start the local valuation API and worker to load this queue." : "The queue is clear."}
            </p>
          ) : (
            <div className="grid gap-2">
              {jobs.map((job) => (
                <div className="grid gap-3 rounded-2xl bg-slate-50 p-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-center" key={job.id}>
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded-full bg-cyan-100 px-2.5 py-1 text-xs font-bold text-cyan-800">
                        {job.status.replaceAll("_", " ").toLowerCase()}
                      </span>
                      <span className="text-xs font-semibold text-slate-500">Attempt {job.attempts}</span>
                    </div>
                    <a className="mt-2 block font-semibold text-slate-950 hover:text-cyan-800" href={job.facebookUrl} rel="noreferrer" target="_blank">
                      {job.title}
                    </a>
                    <p className="mt-1 text-sm text-slate-500">
                      {formatMoney(job.askingPriceCents)}
                      {job.lastError ? ` | ${job.lastError}` : ""}
                    </p>
                  </div>
                  {job.status === "FAILED" || job.status === "INSUFFICIENT_DATA" ? (
                    <button
                      className="rounded-xl bg-slate-950 px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
                      disabled={busyId === job.id}
                      onClick={() => void retry(job.id)}
                      type="button"
                    >
                      {busyId === job.id ? "Retrying..." : "Retry"}
                    </button>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}
