"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { formatMoney } from "@/lib/money";

const TRADE_ME_VALUE_URL = "https://www.trademe.co.nz/a/value-my-car";

type ValuationButtonProps = {
  aiEvaluatedAtLabel?: string | null;
  aiEvaluationError?: string | null;
  aiEvaluationStatus: string;
  aiSummary?: string | null;
  askingPriceCents: number;
  checkedAtLabel?: string | null;
  commonIssues?: string[];
  dealScore?: number | null;
  disabled?: boolean;
  estimatedProfitCents?: number | null;
  facebookUrl: string;
  inspectionChecklist?: string[];
  kms?: number | null;
  kmsConfidence?: number | null;
  listingId: string;
  maxBuyPriceCents?: number | null;
  numberPlate?: string | null;
  numberPlateConfidence?: number | null;
  profitabilitySummary?: string | null;
  recommendedAction?: string | null;
  riskFlags?: string[];
  riskLevel: string;
  sellerQuestions?: string[];
  targetSellPriceCents?: number | null;
  title: string;
  valuationCents?: number | null;
  valuationError?: string | null;
  valuationStatus: string;
};

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

function formatKms(kms: number | null | undefined) {
  if (kms == null) {
    return "Unknown kms";
  }

  return `${new Intl.NumberFormat("en-NZ").format(kms)} km`;
}

function confidenceLabel(confidence: number | null | undefined) {
  if (confidence == null) {
    return "";
  }

  return ` (${confidence}% confidence)`;
}

function MiniList({ items, title }: { items?: string[]; title: string }) {
  if (!items || items.length === 0) {
    return null;
  }

  return (
    <div className="rounded-3xl border border-slate-200 bg-white/85 p-4">
      <p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">
        {title}
      </p>
      <ul className="mt-3 space-y-2 text-sm leading-6 text-slate-600">
        {items.slice(0, 5).map((item) => (
          <li key={item}>- {item}</li>
        ))}
      </ul>
    </div>
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
    <div className="flex items-center justify-between gap-4 rounded-2xl bg-white/80 px-4 py-3">
      <span className="text-sm text-slate-500">{label}</span>
      <span className={`text-sm font-bold ${valueClass}`}>{value}</span>
    </div>
  );
}

export function ValuationButton({
  aiEvaluatedAtLabel,
  aiEvaluationError,
  aiEvaluationStatus,
  aiSummary,
  askingPriceCents,
  checkedAtLabel,
  commonIssues,
  dealScore,
  disabled,
  estimatedProfitCents,
  facebookUrl,
  inspectionChecklist,
  kms,
  kmsConfidence,
  listingId,
  maxBuyPriceCents,
  numberPlate,
  numberPlateConfidence,
  profitabilitySummary,
  recommendedAction,
  riskFlags,
  riskLevel,
  sellerQuestions,
  targetSellPriceCents,
  title,
  valuationCents,
  valuationError,
  valuationStatus
}: ValuationButtonProps) {
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);
  const [valuation, setValuation] = useState(
    valuationCents == null ? "" : String(valuationCents / 100)
  );
  const [isSaving, setIsSaving] = useState(false);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [hasValuation, setHasValuation] = useState(valuationCents != null);
  const [message, setMessage] = useState<string | null>(null);
  const actionLabel =
    actionLabels[recommendedAction ?? ""] ??
    aiStatusLabels[aiEvaluationStatus] ??
    "Not evaluated";
  const profitTone =
    estimatedProfitCents == null
      ? "default"
      : estimatedProfitCents > 0
        ? "good"
        : "bad";

  async function saveValuation() {
    setIsSaving(true);
    setMessage(null);

    try {
      const response = await fetch(
        `/api/listings/${listingId}/valuation/manual`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ valuation })
        }
      );
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Could not save valuation.");
      }

      setHasValuation(true);
      setMessage(payload.message || "Trade Me valuation saved.");
      router.refresh();
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Could not save valuation."
      );
    } finally {
      setIsSaving(false);
    }
  }

  async function runEvaluation() {
    if (!hasValuation) {
      setMessage("Add Trade Me value first.");
      return;
    }

    setIsEvaluating(true);
    setMessage(null);

    try {
      const response = await fetch(`/api/listings/${listingId}/evaluate`, {
        method: "POST"
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "AI evaluation failed.");
      }

      setMessage(payload.message || "AI deal evaluation saved.");
      if (typeof payload.redirectUrl === "string") {
        router.push(payload.redirectUrl);
      } else {
        router.refresh();
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "AI evaluation failed.");
    } finally {
      setIsEvaluating(false);
    }
  }

  return (
    <div className="grid gap-4">
      <button
        aria-expanded={isOpen}
        className={`ml-auto flex w-fit items-center justify-center rounded-full px-7 py-3 text-sm font-bold text-white shadow-lg shadow-slate-300/70 transition hover:-translate-y-0.5 ${
          disabled
            ? "cursor-not-allowed bg-slate-300"
            : isOpen
              ? "bg-slate-800 hover:bg-slate-700"
              : "bg-slate-950 hover:bg-slate-800"
        }`}
        disabled={disabled}
        onClick={() => {
          if (!disabled) {
            setIsOpen((current) => !current);
          }
        }}
        type="button"
      >
        Valuation
      </button>

      {isOpen ? (
        <section className="overflow-hidden rounded-[1.75rem] border border-slate-200 bg-[linear-gradient(135deg,_#ffffff,_#f8fbff)] p-5 shadow-inner shadow-slate-100 md:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-200 pb-5">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.24em] text-cyan-700">
              Deal workspace
            </p>
            <h3 className="mt-2 text-xl font-semibold tracking-tight text-slate-950">
              {title}
            </h3>
          </div>
          <div className="flex flex-wrap gap-2 text-xs font-bold">
            <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">
              Ask {formatMoney(askingPriceCents)}
            </span>
            <span className="rounded-full bg-cyan-100 px-3 py-1 text-cyan-800">
              {valuationStatus === "VALUED" ? "Valued" : "Awaiting value"}
            </span>
            <span className="rounded-full bg-violet-100 px-3 py-1 text-violet-800">
              {actionLabel}
            </span>
          </div>
        </div>

        <div className="mt-6 grid gap-5 xl:grid-cols-[0.9fr_0.85fr_1.1fr]">
          <div className="rounded-[1.5rem] border border-cyan-100 bg-cyan-50/70 p-5">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-cyan-800">
              Manual valuation
            </p>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Open Trade Me, enter the car details there, then paste the value
              back here.
            </p>

            <div className="mt-4 grid gap-3">
              <a
                className="inline-flex items-center justify-center rounded-2xl bg-white px-4 py-3 text-sm font-bold text-cyan-800 shadow-sm transition hover:bg-cyan-100"
                href={TRADE_ME_VALUE_URL}
                rel="noreferrer"
                target="_blank"
              >
                Open Trade Me Valuation
              </a>
              <a
                className="inline-flex items-center justify-center rounded-2xl border border-slate-200 bg-white/70 px-4 py-3 text-sm font-bold text-slate-700 transition hover:bg-white"
                href={facebookUrl}
                rel="noreferrer"
                target="_blank"
              >
                Open Facebook listing
              </a>
              <input
                className="rounded-2xl border border-cyan-100 bg-white px-4 py-3 text-sm outline-none ring-cyan-100 transition focus:ring-4"
                disabled={disabled || isSaving}
                onChange={(event) => setValuation(event.target.value)}
                placeholder="Paste value e.g. $5,247.50"
                value={valuation}
              />
              <button
                className="rounded-2xl bg-slate-950 px-4 py-3 text-sm font-bold text-white shadow-sm transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                disabled={disabled || isSaving || !valuation.trim()}
                onClick={saveValuation}
                type="button"
              >
                {isSaving ? "Saving valuation..." : "Save valuation"}
              </button>
            </div>

            <div className="mt-5 rounded-3xl bg-white/80 p-4 text-sm text-slate-600">
              <p>
                <span className="font-bold text-slate-900">Plate:</span>{" "}
                {numberPlate ?? "Unknown"}
                {confidenceLabel(numberPlateConfidence)}
              </p>
              <p className="mt-2">
                <span className="font-bold text-slate-900">Odometer:</span>{" "}
                {formatKms(kms)}
                {confidenceLabel(kmsConfidence)}
              </p>
              {checkedAtLabel ? (
                <p className="mt-3 text-xs text-slate-400">
                  Last valuation check {checkedAtLabel}
                </p>
              ) : null}
              {valuationError ? (
                <p className="mt-3 rounded-2xl bg-rose-50 p-3 text-xs font-semibold text-rose-700">
                  {valuationError}
                </p>
              ) : null}
            </div>
          </div>

          <div className="rounded-[1.5rem] border border-slate-200 bg-slate-50 p-5">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">
              Deal math
            </p>
            <div className="mt-4 grid gap-3">
              <Metric label="Trade Me value" value={formatMoney(valuationCents)} />
              <Metric
                label="Target sell"
                value={formatMoney(targetSellPriceCents)}
              />
              <Metric label="Max buy" value={formatMoney(maxBuyPriceCents)} />
              <Metric
                label="Profit at ask"
                tone={profitTone}
                value={formatMoney(estimatedProfitCents)}
              />
            </div>
            <button
              className="mt-5 w-full rounded-2xl bg-gradient-to-r from-violet-700 to-cyan-700 px-4 py-3 text-sm font-bold text-white shadow-sm transition hover:from-violet-800 hover:to-cyan-800 disabled:cursor-not-allowed disabled:from-slate-300 disabled:to-slate-300"
              disabled={disabled || isEvaluating || !hasValuation}
              onClick={runEvaluation}
              type="button"
            >
              {isEvaluating ? "Researching lead..." : "Evaluate with AI"}
            </button>
            {aiEvaluationStatus === "COMPLETED" ? (
              <a
                className="mt-3 inline-flex w-full items-center justify-center rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-bold text-slate-700 transition hover:bg-slate-100"
                href={`/leads/${listingId}`}
              >
                Open saved lead report
              </a>
            ) : null}
            {!hasValuation ? (
              <p className="mt-3 text-xs font-medium text-amber-700">
                Add Trade Me value first.
              </p>
            ) : null}
            {message ? (
              <p className="mt-3 rounded-2xl bg-white/80 p-3 text-xs font-medium text-slate-600">
                {message}
              </p>
            ) : null}
          </div>

          <div className="rounded-[1.5rem] border border-violet-100 bg-violet-50/60 p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-violet-800">
                AI evaluation
              </p>
              {dealScore != null ? (
                <span className="rounded-full bg-slate-950 px-3 py-1 text-xs font-bold text-white">
                  {dealScore}/100
                </span>
              ) : null}
            </div>

            {aiSummary ? (
              <p className="mt-4 text-sm font-medium leading-6 text-slate-800">
                {aiSummary}
              </p>
            ) : (
              <p className="mt-4 text-sm leading-6 text-slate-600">
                Once valuation is saved, AI will summarise profitability, common
                model issues, seller questions, and inspection checks.
              </p>
            )}

            {profitabilitySummary ? (
              <div className="mt-4 rounded-3xl bg-white/80 p-4">
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">
                  Profitability
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  {profitabilitySummary}
                </p>
              </div>
            ) : null}

            <div className="mt-4 grid gap-3">
              <MiniList title="Common issues" items={commonIssues} />
              <MiniList title="Ask seller" items={sellerQuestions} />
              <MiniList title="Inspect" items={inspectionChecklist} />
              <MiniList title="Risk flags" items={riskFlags} />
            </div>

            {aiEvaluationError ? (
              <p className="mt-4 rounded-3xl bg-rose-50 p-4 text-xs font-semibold text-rose-700">
                {aiEvaluationError}
              </p>
            ) : null}

            <div className="mt-4 flex flex-wrap gap-2 text-xs font-bold">
              <span className="rounded-full bg-white px-3 py-1 text-slate-600">
                {aiStatusLabels[aiEvaluationStatus] ?? aiEvaluationStatus}
              </span>
              <span className="rounded-full bg-white px-3 py-1 text-slate-600">
                Risk {riskLevel.toLowerCase()}
              </span>
              {aiEvaluatedAtLabel ? (
                <span className="rounded-full bg-white px-3 py-1 text-slate-600">
                  {aiEvaluatedAtLabel}
                </span>
              ) : null}
            </div>
          </div>
        </div>
        </section>
      ) : null}
    </div>
  );
}
