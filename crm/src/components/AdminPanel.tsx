"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  flipStatusLabels,
  flipStatuses,
  type AdminStats,
  type FlipStatus
} from "@/lib/admin-shared";
import { formatMoney } from "@/lib/money";

export type AdminFlipView = {
  id: string;
  vehicleTitle: string;
  status: FlipStatus;
  sourceUrl: string | null;
  purchaseDate: string | null;
  saleDate: string | null;
  purchasePriceCents: number;
  repairCostCents: number;
  otherCostCents: number;
  salePriceCents: number | null;
  notes: string | null;
  journalWentRight: string | null;
  journalWentWrong: string | null;
  journalLookOutFor: string | null;
  createdAt: string;
  updatedAt: string;
};

type DraftState = {
  vehicleTitle: string;
  status: FlipStatus;
  sourceUrl: string;
  purchaseDate: string;
  saleDate: string;
  purchasePrice: string;
  repairCost: string;
  otherCost: string;
  salePrice: string;
  notes: string;
  journalWentRight: string;
  journalWentWrong: string;
  journalLookOutFor: string;
};

type AdminPanelProps = {
  flips: AdminFlipView[];
  stats: AdminStats;
};

const blankDraft: DraftState = {
  vehicleTitle: "",
  status: "WATCHING",
  sourceUrl: "",
  purchaseDate: "",
  saleDate: "",
  purchasePrice: "",
  repairCost: "",
  otherCost: "",
  salePrice: "",
  notes: "",
  journalWentRight: "",
  journalWentWrong: "",
  journalLookOutFor: ""
};

const statusTone: Record<FlipStatus, string> = {
  WATCHING: "bg-sky-100 text-sky-800",
  BOUGHT: "bg-violet-100 text-violet-800",
  IN_REPAIR: "bg-amber-100 text-amber-800",
  LISTED: "bg-cyan-100 text-cyan-800",
  SOLD: "bg-emerald-100 text-emerald-800",
  PASSED: "bg-slate-100 text-slate-700"
};

function inputMoney(cents: number | null | undefined) {
  if (cents == null || cents === 0) {
    return "";
  }

  return String(cents / 100);
}

function inputDate(value: string | null) {
  return value ? value.slice(0, 10) : "";
}

function flipToDraft(flip: AdminFlipView): DraftState {
  return {
    vehicleTitle: flip.vehicleTitle,
    status: flip.status,
    sourceUrl: flip.sourceUrl ?? "",
    purchaseDate: inputDate(flip.purchaseDate),
    saleDate: inputDate(flip.saleDate),
    purchasePrice: inputMoney(flip.purchasePriceCents),
    repairCost: inputMoney(flip.repairCostCents),
    otherCost: inputMoney(flip.otherCostCents),
    salePrice: inputMoney(flip.salePriceCents),
    notes: flip.notes ?? "",
    journalWentRight: flip.journalWentRight ?? "",
    journalWentWrong: flip.journalWentWrong ?? "",
    journalLookOutFor: flip.journalLookOutFor ?? ""
  };
}

function totalCost(flip: AdminFlipView) {
  return (
    flip.purchasePriceCents + flip.repairCostCents + flip.otherCostCents
  );
}

function profit(flip: AdminFlipView) {
  if (flip.salePriceCents == null) {
    return null;
  }

  return flip.salePriceCents - totalCost(flip);
}

function lastUpdatedLabel(value: string) {
  return new Intl.DateTimeFormat("en-NZ", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

function buildPayload(draft: DraftState) {
  return {
    vehicleTitle: draft.vehicleTitle,
    status: draft.status,
    sourceUrl: draft.sourceUrl,
    purchaseDate: draft.purchaseDate,
    saleDate: draft.saleDate,
    purchasePrice: draft.purchasePrice,
    repairCost: draft.repairCost,
    otherCost: draft.otherCost,
    salePrice: draft.salePrice,
    notes: draft.notes,
    journalWentRight: draft.journalWentRight,
    journalWentWrong: draft.journalWentWrong,
    journalLookOutFor: draft.journalLookOutFor
  };
}

function Field({
  label,
  name,
  onChange,
  placeholder,
  type = "text",
  value
}: {
  label: string;
  name: keyof DraftState;
  onChange: (name: keyof DraftState, value: string) => void;
  placeholder?: string;
  type?: string;
  value: string;
}) {
  return (
    <label className="grid gap-2">
      <span className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">
        {label}
      </span>
      <input
        className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none ring-violet-200 transition focus:ring-4"
        name={name}
        onChange={(event) => onChange(name, event.target.value)}
        placeholder={placeholder}
        type={type}
        value={value}
      />
    </label>
  );
}

function TextAreaField({
  label,
  name,
  onChange,
  placeholder,
  value
}: {
  label: string;
  name: keyof DraftState;
  onChange: (name: keyof DraftState, value: string) => void;
  placeholder: string;
  value: string;
}) {
  return (
    <label className="grid gap-2">
      <span className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">
        {label}
      </span>
      <textarea
        className="min-h-28 resize-y rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm leading-6 outline-none ring-violet-200 transition focus:ring-4"
        name={name}
        onChange={(event) => onChange(name, event.target.value)}
        placeholder={placeholder}
        value={value}
      />
    </label>
  );
}

function StatCard({
  label,
  tone = "default",
  value
}: {
  label: string;
  tone?: "default" | "good" | "warning";
  value: string | number;
}) {
  const valueClass =
    tone === "good"
      ? "text-emerald-700"
      : tone === "warning"
        ? "text-amber-700"
        : "text-slate-950";

  return (
    <div className="rounded-3xl border border-white/80 bg-white/85 p-5 shadow-sm shadow-slate-200/70">
      <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">
        {label}
      </p>
      <p className={`mt-3 text-3xl font-semibold tracking-tight ${valueClass}`}>
        {value}
      </p>
    </div>
  );
}

export function AdminPanel({ flips, stats }: AdminPanelProps) {
  const router = useRouter();
  const [newDraft, setNewDraft] = useState<DraftState>(blankDraft);
  const [drafts, setDrafts] = useState<Record<string, DraftState>>({});
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDrafts(
      Object.fromEntries(flips.map((flip) => [flip.id, flipToDraft(flip)]))
    );
  }, [flips]);

  const pipeline = useMemo(
    () =>
      flipStatuses.map((status) => {
        const matching = flips.filter((flip) => flip.status === status);
        return {
          status,
          count: matching.length,
          valueCents: matching.reduce((sum, flip) => sum + totalCost(flip), 0)
        };
      }),
    [flips]
  );

  const updateNewDraft = (name: keyof DraftState, value: string) => {
    setNewDraft((current) => ({ ...current, [name]: value }));
  };

  const updateDraft = (
    id: string,
    name: keyof DraftState,
    value: string
  ) => {
    setDrafts((current) => ({
      ...current,
      [id]: {
        ...current[id],
        [name]: value
      }
    }));
  };

  async function submitRequest({
    actionId,
    body,
    method,
    successMessage,
    url
  }: {
    actionId: string;
    body?: unknown;
    method: "POST" | "PATCH" | "DELETE";
    successMessage: string;
    url: string;
  }) {
    setPendingAction(actionId);
    setMessage(null);
    setError(null);

    try {
      const response = await fetch(url, {
        method,
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined
      });
      const payload = (await response.json().catch(() => ({}))) as {
        error?: string;
        message?: string;
      };

      if (!response.ok) {
        throw new Error(payload.error ?? "The admin update failed.");
      }

      setMessage(payload.message ?? successMessage);
      router.refresh();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "The admin update failed."
      );
    } finally {
      setPendingAction(null);
    }
  }

  async function addFlip(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitRequest({
      actionId: "create",
      body: buildPayload(newDraft),
      method: "POST",
      successMessage: "Car added.",
      url: "/api/admin/flips"
    });
    setNewDraft(blankDraft);
  }

  async function saveFlip(id: string) {
    const draft = drafts[id];
    if (!draft) {
      return;
    }

    await submitRequest({
      actionId: `save-${id}`,
      body: buildPayload(draft),
      method: "PATCH",
      successMessage: "Car saved.",
      url: `/api/admin/flips/${id}`
    });
  }

  async function deleteFlip(id: string, title: string) {
    const confirmed = window.confirm(`Remove "${title}" from Admin?`);
    if (!confirmed) {
      return;
    }

    await submitRequest({
      actionId: `delete-${id}`,
      method: "DELETE",
      successMessage: "Car removed.",
      url: `/api/admin/flips/${id}`
    });
  }

  return (
    <>
        <section className="overflow-hidden rounded-[2.5rem] border border-white/70 bg-slate-950 p-8 text-white shadow-2xl shadow-slate-300 md:p-10">
          <div className="grid gap-8 lg:grid-cols-[1.3fr_0.7fr] lg:items-end">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.32em] text-violet-300">
                Admin
              </p>
              <h1 className="mt-5 max-w-5xl text-5xl font-semibold tracking-tight md:text-7xl">
                Run the business side without spreadsheets.
              </h1>
              <p className="mt-5 max-w-2xl text-base leading-7 text-slate-300">
                Add cars, track money spent, move vehicles through the flip
                pipeline, record sale outcomes, and keep a short journal so each
                deal makes the next one sharper.
              </p>
            </div>
            <div className="rounded-[2rem] border border-white/10 bg-white/10 p-5 backdrop-blur">
              <p className="text-sm font-medium text-slate-300">
                Operating rule
              </p>
              <div className="mt-4 space-y-3 text-sm text-slate-200">
                <div className="flex justify-between gap-4">
                  <span>Track every purchase cost</span>
                  <strong>Buy + repairs + misc</strong>
                </div>
                <div className="flex justify-between gap-4">
                  <span>Open capital</span>
                  <strong>Money still tied up</strong>
                </div>
                <div className="flex justify-between gap-4">
                  <span>Journal each flip</span>
                  <strong>Repeat the lesson</strong>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="mt-8 grid gap-4 md:grid-cols-4 xl:grid-cols-7">
          <StatCard label="Cars tracked" value={stats.carsTracked} />
          <StatCard label="Cars bought" value={stats.carsBought} />
          <StatCard label="Active stock" value={stats.activeInventory} />
          <StatCard label="Sold" tone="good" value={stats.carsSold} />
          <StatCard
            label="Open capital"
            tone="warning"
            value={formatMoney(stats.openCapitalCents)}
          />
          <StatCard label="Revenue" value={formatMoney(stats.revenueCents)} />
          <StatCard
            label="Profit"
            tone="good"
            value={formatMoney(stats.realizedProfitCents)}
          />
        </section>

        <section className="mt-8 rounded-[2rem] border border-white/80 bg-white/85 p-5 shadow-xl shadow-slate-200/70">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.22em] text-slate-400">
                Flowchart
              </p>
              <h2 className="mt-2 text-2xl font-semibold tracking-tight">
                Flip pipeline
              </h2>
            </div>
            <span className="rounded-full bg-violet-100 px-4 py-2 text-sm font-bold text-violet-800">
              {stats.journalCount} journaled flips
            </span>
          </div>

          <div className="mt-5 grid gap-3 md:grid-cols-3 xl:grid-cols-6">
            {pipeline.map((step) => (
              <div
                className="rounded-3xl border border-slate-200 bg-slate-50 p-4"
                key={step.status}
              >
                <span
                  className={`rounded-full px-3 py-1 text-xs font-bold ${statusTone[step.status]}`}
                >
                  {flipStatusLabels[step.status]}
                </span>
                <p className="mt-4 text-3xl font-semibold text-slate-950">
                  {step.count}
                </p>
                <p className="mt-1 text-sm text-slate-500">
                  {formatMoney(step.valueCents)} tracked cost
                </p>
              </div>
            ))}
          </div>
        </section>

        {(message || error) && (
          <div
            className={`mt-6 rounded-3xl border px-5 py-4 text-sm font-semibold ${
              error
                ? "border-rose-200 bg-rose-50 text-rose-700"
                : "border-emerald-200 bg-emerald-50 text-emerald-700"
            }`}
          >
            {error ?? message}
          </div>
        )}

        <section className="mt-8 grid gap-6 xl:grid-cols-[0.9fr_1.4fr]">
          <form
            className="rounded-[2rem] border border-white/80 bg-white/90 p-5 shadow-xl shadow-slate-200/70"
            onSubmit={addFlip}
          >
            <p className="text-xs font-bold uppercase tracking-[0.22em] text-violet-500">
              Add/remove without code
            </p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight">
              Add a car to Admin
            </h2>
            <div className="mt-5 grid gap-4">
              <Field
                label="Vehicle"
                name="vehicleTitle"
                onChange={updateNewDraft}
                placeholder="e.g. 2007 Toyota Auris"
                value={newDraft.vehicleTitle}
              />
              <label className="grid gap-2">
                <span className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">
                  Status
                </span>
                <select
                  className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none ring-violet-200 transition focus:ring-4"
                  onChange={(event) =>
                    updateNewDraft("status", event.target.value)
                  }
                  value={newDraft.status}
                >
                  {flipStatuses.map((status) => (
                    <option key={status} value={status}>
                      {flipStatusLabels[status]}
                    </option>
                  ))}
                </select>
              </label>
              <Field
                label="Source URL"
                name="sourceUrl"
                onChange={updateNewDraft}
                placeholder="Facebook or Trade Me link"
                value={newDraft.sourceUrl}
              />
              <div className="grid gap-4 sm:grid-cols-2">
                <Field
                  label="Purchase date"
                  name="purchaseDate"
                  onChange={updateNewDraft}
                  type="date"
                  value={newDraft.purchaseDate}
                />
                <Field
                  label="Sale date"
                  name="saleDate"
                  onChange={updateNewDraft}
                  type="date"
                  value={newDraft.saleDate}
                />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field
                  label="Purchase $"
                  name="purchasePrice"
                  onChange={updateNewDraft}
                  placeholder="3500"
                  value={newDraft.purchasePrice}
                />
                <Field
                  label="Repairs $"
                  name="repairCost"
                  onChange={updateNewDraft}
                  placeholder="450"
                  value={newDraft.repairCost}
                />
                <Field
                  label="Other costs $"
                  name="otherCost"
                  onChange={updateNewDraft}
                  placeholder="WOF, rego, fuel"
                  value={newDraft.otherCost}
                />
                <Field
                  label="Sale $"
                  name="salePrice"
                  onChange={updateNewDraft}
                  placeholder="Leave blank until sold"
                  value={newDraft.salePrice}
                />
              </div>
              <TextAreaField
                label="Quick notes"
                name="notes"
                onChange={updateNewDraft}
                placeholder="Why it was bought, what needs doing, who owns the next action..."
                value={newDraft.notes}
              />
              <button
                className="rounded-3xl bg-slate-950 px-5 py-4 text-sm font-bold text-white shadow-xl shadow-slate-300 transition hover:-translate-y-0.5 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={pendingAction === "create"}
              >
                {pendingAction === "create" ? "Adding..." : "Add car"}
              </button>
            </div>
          </form>

          <div className="grid gap-4">
            {flips.length === 0 ? (
              <div className="rounded-[2rem] border border-white/80 bg-white/90 p-10 text-center shadow-xl shadow-slate-200/70">
                <p className="text-2xl font-semibold text-slate-950">
                  No admin cars yet.
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-500">
                  Add your first watched, bought, or sold car and this page will
                  start showing your money flow automatically.
                </p>
              </div>
            ) : (
              flips.map((flip) => {
                const draft = drafts[flip.id] ?? flipToDraft(flip);
                const flipProfit = profit(flip);
                const isProfitable =
                  flipProfit != null ? flipProfit >= 0 : undefined;

                return (
                  <article
                    className="overflow-hidden rounded-[2rem] border border-white/80 bg-white/90 shadow-xl shadow-slate-200/70"
                    key={flip.id}
                  >
                    <div className="grid gap-5 p-5 lg:grid-cols-[1fr_auto] lg:items-start">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span
                            className={`rounded-full px-3 py-1 text-xs font-bold ${statusTone[flip.status]}`}
                          >
                            {flipStatusLabels[flip.status]}
                          </span>
                          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-600">
                            Updated {lastUpdatedLabel(flip.updatedAt)}
                          </span>
                          {flip.sourceUrl ? (
                            <a
                              className="rounded-full bg-cyan-100 px-3 py-1 text-xs font-bold text-cyan-800 hover:bg-cyan-200"
                              href={flip.sourceUrl}
                              rel="noreferrer"
                              target="_blank"
                            >
                              Source link
                            </a>
                          ) : null}
                        </div>
                        <h3 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
                          {flip.vehicleTitle}
                        </h3>
                      </div>
                      <div className="grid grid-cols-3 gap-3 rounded-3xl bg-slate-50 p-4 text-sm">
                        <div>
                          <p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">
                            Cost
                          </p>
                          <p className="mt-1 font-bold">
                            {formatMoney(totalCost(flip))}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">
                            Sold
                          </p>
                          <p className="mt-1 font-bold">
                            {formatMoney(flip.salePriceCents ?? 0)}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">
                            Profit
                          </p>
                          <p
                            className={`mt-1 font-bold ${
                              isProfitable === true
                                ? "text-emerald-700"
                                : isProfitable === false
                                  ? "text-rose-700"
                                  : "text-slate-500"
                            }`}
                          >
                            {flipProfit == null
                              ? "Pending"
                              : formatMoney(flipProfit)}
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="border-t border-slate-100 p-5">
                      <div className="grid gap-4 lg:grid-cols-[1fr_0.7fr]">
                        <div className="grid gap-4 sm:grid-cols-2">
                          <Field
                            label="Vehicle"
                            name="vehicleTitle"
                            onChange={(name, value) =>
                              updateDraft(flip.id, name, value)
                            }
                            value={draft.vehicleTitle}
                          />
                          <label className="grid gap-2">
                            <span className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">
                              Status
                            </span>
                            <select
                              className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none ring-violet-200 transition focus:ring-4"
                              onChange={(event) =>
                                updateDraft(
                                  flip.id,
                                  "status",
                                  event.target.value
                                )
                              }
                              value={draft.status}
                            >
                              {flipStatuses.map((status) => (
                                <option key={status} value={status}>
                                  {flipStatusLabels[status]}
                                </option>
                              ))}
                            </select>
                          </label>
                          <Field
                            label="Source URL"
                            name="sourceUrl"
                            onChange={(name, value) =>
                              updateDraft(flip.id, name, value)
                            }
                            value={draft.sourceUrl}
                          />
                          <Field
                            label="Purchase date"
                            name="purchaseDate"
                            onChange={(name, value) =>
                              updateDraft(flip.id, name, value)
                            }
                            type="date"
                            value={draft.purchaseDate}
                          />
                          <Field
                            label="Sale date"
                            name="saleDate"
                            onChange={(name, value) =>
                              updateDraft(flip.id, name, value)
                            }
                            type="date"
                            value={draft.saleDate}
                          />
                          <Field
                            label="Purchase $"
                            name="purchasePrice"
                            onChange={(name, value) =>
                              updateDraft(flip.id, name, value)
                            }
                            value={draft.purchasePrice}
                          />
                          <Field
                            label="Repair $"
                            name="repairCost"
                            onChange={(name, value) =>
                              updateDraft(flip.id, name, value)
                            }
                            value={draft.repairCost}
                          />
                          <Field
                            label="Other $"
                            name="otherCost"
                            onChange={(name, value) =>
                              updateDraft(flip.id, name, value)
                            }
                            value={draft.otherCost}
                          />
                          <Field
                            label="Sale $"
                            name="salePrice"
                            onChange={(name, value) =>
                              updateDraft(flip.id, name, value)
                            }
                            value={draft.salePrice}
                          />
                        </div>

                        <TextAreaField
                          label="Admin notes"
                          name="notes"
                          onChange={(name, value) =>
                            updateDraft(flip.id, name, value)
                          }
                          placeholder="Tasks, ownership, pickup details, repair plan, listing plan..."
                          value={draft.notes}
                        />
                      </div>

                      <div className="mt-5 rounded-[1.5rem] border border-violet-100 bg-violet-50/60 p-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <p className="text-xs font-bold uppercase tracking-[0.22em] text-violet-500">
                              Flip journal
                            </p>
                            <p className="mt-1 text-sm text-slate-600">
                              Keep the practical lessons attached to the car
                              while they are fresh.
                            </p>
                          </div>
                        </div>
                        <div className="mt-4 grid gap-4 lg:grid-cols-3">
                          <TextAreaField
                            label="What went right"
                            name="journalWentRight"
                            onChange={(name, value) =>
                              updateDraft(flip.id, name, value)
                            }
                            placeholder="Good buy reason, negotiation win, repair that paid off..."
                            value={draft.journalWentRight}
                          />
                          <TextAreaField
                            label="What went wrong"
                            name="journalWentWrong"
                            onChange={(name, value) =>
                              updateDraft(flip.id, name, value)
                            }
                            placeholder="Hidden cost, slow sale reason, inspection miss..."
                            value={draft.journalWentWrong}
                          />
                          <TextAreaField
                            label="Look out for next time"
                            name="journalLookOutFor"
                            onChange={(name, value) =>
                              updateDraft(flip.id, name, value)
                            }
                            placeholder="Model issues, seller red flags, price ceiling lesson..."
                            value={draft.journalLookOutFor}
                          />
                        </div>
                      </div>

                      <div className="mt-5 flex flex-wrap justify-end gap-3">
                        <button
                          className="rounded-2xl border border-rose-200 bg-white px-5 py-3 text-sm font-bold text-rose-700 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50"
                          disabled={pendingAction === `delete-${flip.id}`}
                          onClick={() => deleteFlip(flip.id, flip.vehicleTitle)}
                          type="button"
                        >
                          {pendingAction === `delete-${flip.id}`
                            ? "Removing..."
                            : "Remove"}
                        </button>
                        <button
                          className="rounded-2xl bg-slate-950 px-5 py-3 text-sm font-bold text-white shadow-lg shadow-slate-300 transition hover:-translate-y-0.5 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                          disabled={pendingAction === `save-${flip.id}`}
                          onClick={() => saveFlip(flip.id)}
                          type="button"
                        >
                          {pendingAction === `save-${flip.id}`
                            ? "Saving..."
                            : "Save changes"}
                        </button>
                      </div>
                    </div>
                  </article>
                );
              })
            )}
          </div>
        </section>
    </>
  );
}
