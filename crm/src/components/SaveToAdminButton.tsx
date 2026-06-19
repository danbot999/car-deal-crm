"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import {
  adminPriorities,
  adminPriorityLabels,
  type AdminPriority,
  type FlipStatus
} from "@/lib/admin-shared";

type AdminFlipQuick = {
  id: string;
  vehicleTitle: string;
  status: string;
  sourceUrl: string | null;
  askingPriceCents: number | null;
  thumbnailPath: string | null;
  kms: number | null;
  rego: string | null;
  sellerContacted: boolean;
  sellerContactedAt: Date | string | null;
  priority: string;
  nextAction: string | null;
  purchaseDate: Date | string | null;
  saleDate: Date | string | null;
  purchasePriceCents: number;
  repairCostCents: number;
  otherCostCents: number;
  salePriceCents: number | null;
  notes: string | null;
  journalWentRight: string | null;
  journalWentWrong: string | null;
  journalLookOutFor: string | null;
};

type SaveToAdminButtonProps = {
  adminFlip: AdminFlipQuick | null;
  askingPriceCents: number;
  facebookUrl: string;
  listingId: string;
  thumbnailPath: string | null;
  title: string;
};

function moneyInput(cents: number | null | undefined) {
  if (cents == null || cents === 0) {
    return "";
  }

  return String(cents / 100);
}

function dateInput(value: Date | string | null) {
  if (!value) {
    return "";
  }

  return typeof value === "string"
    ? value.slice(0, 10)
    : value.toISOString().slice(0, 10);
}

function quickDraft(flip: AdminFlipQuick | null) {
  return {
    kms: flip?.kms ? String(flip.kms) : "",
    rego: flip?.rego ?? "",
    sellerContacted: flip?.sellerContacted ?? false,
    priority: adminPriorities.includes(flip?.priority as AdminPriority)
      ? (flip?.priority as AdminPriority)
      : "MEDIUM",
    nextAction: flip?.nextAction ?? "",
    notes: flip?.notes ?? ""
  };
}

function flipPayload({
  draft,
  fallback,
  flip
}: {
  draft: ReturnType<typeof quickDraft>;
  fallback: SaveToAdminButtonProps;
  flip: AdminFlipQuick;
}) {
  return {
    vehicleTitle: flip.vehicleTitle || fallback.title,
    status: flip.status || "WATCHING",
    sourceUrl: flip.sourceUrl ?? fallback.facebookUrl,
    askingPrice: moneyInput(flip.askingPriceCents ?? fallback.askingPriceCents),
    thumbnailPath: flip.thumbnailPath ?? fallback.thumbnailPath,
    kms: draft.kms,
    rego: draft.rego,
    sellerContacted: draft.sellerContacted,
    sellerContactedAt: draft.sellerContacted
      ? dateInput(flip.sellerContactedAt) || new Date().toISOString().slice(0, 10)
      : "",
    priority: draft.priority,
    nextAction: draft.nextAction,
    purchaseDate: dateInput(flip.purchaseDate),
    saleDate: dateInput(flip.saleDate),
    purchasePrice: moneyInput(flip.purchasePriceCents),
    repairCost: moneyInput(flip.repairCostCents),
    otherCost: moneyInput(flip.otherCostCents),
    salePrice: moneyInput(flip.salePriceCents),
    notes: draft.notes,
    journalWentRight: flip.journalWentRight ?? "",
    journalWentWrong: flip.journalWentWrong ?? "",
    journalLookOutFor: flip.journalLookOutFor ?? ""
  };
}

export function SaveToAdminButton(props: SaveToAdminButtonProps) {
  const router = useRouter();
  const [flip, setFlip] = useState<AdminFlipQuick | null>(props.adminFlip);
  const [draft, setDraft] = useState(() => quickDraft(props.adminFlip));
  const [expanded, setExpanded] = useState(false);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function saveToAdmin() {
    setPending(true);
    setError(null);
    setMessage(null);

    try {
      const response = await fetch("/api/admin/flips/from-listing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ listingId: props.listingId })
      });
      const payload = (await response.json()) as {
        created?: boolean;
        error?: string;
        flip?: AdminFlipQuick;
        message?: string;
      };

      if (!response.ok || !payload.flip) {
        throw new Error(payload.error ?? "Could not save to Admin.");
      }

      setFlip(payload.flip);
      setDraft(quickDraft(payload.flip));
      setExpanded(true);
      setMessage(payload.message ?? "Saved to Admin.");
      router.refresh();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not save to Admin."
      );
    } finally {
      setPending(false);
    }
  }

  async function saveQuickDetails() {
    if (!flip) {
      return;
    }

    setPending(true);
    setError(null);
    setMessage(null);

    try {
      const response = await fetch(`/api/admin/flips/${flip.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(flipPayload({ draft, fallback: props, flip }))
      });
      const payload = (await response.json()) as {
        error?: string;
        flip?: AdminFlipQuick;
        message?: string;
      };

      if (!response.ok || !payload.flip) {
        throw new Error(payload.error ?? "Could not save quick details.");
      }

      setFlip(payload.flip);
      setDraft(quickDraft(payload.flip));
      setMessage("Quick details saved.");
      router.refresh();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not save quick details."
      );
    } finally {
      setPending(false);
    }
  }

  const isSaved = Boolean(flip);

  return (
    <div className="rounded-[1.6rem] border border-slate-200 bg-white/90 p-4 shadow-sm shadow-slate-200/60">
      <div className="flex flex-wrap items-center gap-3">
        <button
          className={`rounded-2xl px-5 py-3 text-sm font-bold shadow-lg shadow-slate-200 transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-60 ${
            isSaved
              ? "bg-emerald-600 text-white hover:bg-emerald-700"
              : "bg-slate-950 text-white hover:bg-slate-800"
          }`}
          disabled={pending}
          onClick={isSaved ? () => setExpanded((value) => !value) : saveToAdmin}
          type="button"
        >
          {pending
            ? "Saving..."
            : isSaved
              ? expanded
                ? "Hide Admin details"
                : "Saved to Admin"
              : "Save to Admin"}
        </button>
        {isSaved ? (
          <span className="rounded-full bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-700">
            Pipeline: Watching
          </span>
        ) : null}
        {message ? (
          <span className="text-sm font-semibold text-emerald-700">
            {message}
          </span>
        ) : null}
        {error ? (
          <span className="text-sm font-semibold text-rose-700">{error}</span>
        ) : null}
      </div>

      {expanded && flip ? (
        <div className="mt-4 grid gap-3 rounded-[1.3rem] bg-slate-50 p-4 lg:grid-cols-[0.7fr_0.7fr_0.8fr_1fr_1.2fr_auto] lg:items-end">
          <label className="grid gap-1">
            <span className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">
              KMs
            </span>
            <input
              className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none ring-cyan-200 transition focus:ring-4"
              onChange={(event) =>
                setDraft((current) => ({ ...current, kms: event.target.value }))
              }
              placeholder="181000"
              value={draft.kms}
            />
          </label>
          <label className="grid gap-1">
            <span className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">
              Rego
            </span>
            <input
              className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm uppercase outline-none ring-cyan-200 transition focus:ring-4"
              onChange={(event) =>
                setDraft((current) => ({ ...current, rego: event.target.value }))
              }
              placeholder="ABC123"
              value={draft.rego}
            />
          </label>
          <label className="grid gap-1">
            <span className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">
              Priority
            </span>
            <select
              className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none ring-cyan-200 transition focus:ring-4"
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  priority: event.target.value as AdminPriority
                }))
              }
              value={draft.priority}
            >
              {adminPriorities.map((priority) => (
                <option key={priority} value={priority}>
                  {adminPriorityLabels[priority]}
                </option>
              ))}
            </select>
          </label>
          <label className="flex h-12 items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 text-sm font-bold text-slate-700">
            <input
              checked={draft.sellerContacted}
              className="h-4 w-4"
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  sellerContacted: event.target.checked
                }))
              }
              type="checkbox"
            />
            Contacted seller
          </label>
          <label className="grid gap-1">
            <span className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">
              Next action
            </span>
            <input
              className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none ring-cyan-200 transition focus:ring-4"
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  nextAction: event.target.value
                }))
              }
              placeholder="Message seller / inspect / pass"
              value={draft.nextAction}
            />
          </label>
          <button
            className="rounded-2xl bg-cyan-700 px-5 py-3 text-sm font-bold text-white shadow-lg shadow-cyan-100 transition hover:bg-cyan-800 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={pending}
            onClick={saveQuickDetails}
            type="button"
          >
            Save details
          </button>
          <label className="grid gap-1 lg:col-span-full">
            <span className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">
              Quick note
            </span>
            <textarea
              className="min-h-20 resize-y rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm leading-6 outline-none ring-cyan-200 transition focus:ring-4"
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  notes: event.target.value
                }))
              }
              placeholder="Seller details, what stood out, questions to ask..."
              value={draft.notes}
            />
          </label>
        </div>
      ) : null}
    </div>
  );
}
