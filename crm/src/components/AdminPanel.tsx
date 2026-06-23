"use client";

import {
  type ChangeEvent,
  type FormEvent,
  type ReactNode,
  useEffect,
  useMemo,
  useState
} from "react";
import { useRouter } from "next/navigation";

import { SafeCarImage } from "@/components/SafeCarImage";
import {
  adminPriorities,
  adminPriorityLabels,
  flipStatusLabels,
  flipStatuses,
  type AdminPriority,
  type AdminStats,
  type FlipStatus
} from "@/lib/admin-shared";
import { formatMoney } from "@/lib/money";

export type AdminFlipView = {
  id: string;
  listingId: string | null;
  listingAvailabilityStatus: string | null;
  listingAvailabilityReason: string | null;
  listingLastCheckedAt: string | null;
  vehicleTitle: string;
  status: FlipStatus;
  sourceUrl: string | null;
  askingPriceCents: number | null;
  thumbnailPath: string | null;
  kms: number | null;
  rego: string | null;
  sellerContacted: boolean;
  sellerContactedAt: string | null;
  priority: AdminPriority;
  nextAction: string | null;
  purchaseDate: string | null;
  saleDate: string | null;
  valuationCents: number | null;
  targetSellPriceCents: number | null;
  maxBuyPriceCents: number | null;
  estimatedProfitCents: number | null;
  valuationCheckedAt: string | null;
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
  askingPrice: string;
  thumbnailPath: string;
  kms: string;
  rego: string;
  sellerContacted: boolean;
  sellerContactedAt: string;
  priority: AdminPriority;
  nextAction: string;
  valuation: string;
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

type AddMode = "WATCHING" | "BOUGHT" | "SOLD";
type AdminGroupKey = "watching" | "active" | "sold" | "passed";

type AdminPanelProps = {
  flips: AdminFlipView[];
  stats: AdminStats;
};

const blankDraft: DraftState = {
  vehicleTitle: "",
  status: "WATCHING",
  sourceUrl: "",
  askingPrice: "",
  thumbnailPath: "",
  kms: "",
  rego: "",
  sellerContacted: false,
  sellerContactedAt: "",
  priority: "MEDIUM",
  nextAction: "",
  valuation: "",
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

const addModes: Record<
  AddMode,
  {
    description: string;
    label: string;
    nextAction: string;
    status: FlipStatus;
  }
> = {
  WATCHING: {
    description: "Found outside the Dashboard and worth keeping an eye on.",
    label: "Watching lead",
    nextAction: "Decide whether to contact seller.",
    status: "WATCHING"
  },
  BOUGHT: {
    description: "Already purchased and now part of active stock.",
    label: "Bought car",
    nextAction: "Log costs, repairs, and prep for sale.",
    status: "BOUGHT"
  },
  SOLD: {
    description: "Backfill a completed flip and write the lesson down.",
    label: "Sold flip",
    nextAction: "Complete journal and review the numbers.",
    status: "SOLD"
  }
};

const adminGroups: Array<{
  description: string;
  key: AdminGroupKey;
  statuses: FlipStatus[];
  title: string;
}> = [
  {
    description: "Cars you are watching, checking, or deciding whether to contact.",
    key: "watching",
    statuses: ["WATCHING"],
    title: "Watching"
  },
  {
    description: "Cars you own or are actively preparing/listing.",
    key: "active",
    statuses: ["BOUGHT", "IN_REPAIR", "LISTED"],
    title: "Active stock"
  },
  {
    description: "Completed flips, numbers, and journal lessons.",
    key: "sold",
    statuses: ["SOLD"],
    title: "Sold history"
  },
  {
    description: "Cars you decided not to chase, kept for reference.",
    key: "passed",
    statuses: ["PASSED"],
    title: "Passed"
  }
];

const statusTone: Record<FlipStatus, string> = {
  WATCHING: "bg-sky-100 text-sky-800",
  BOUGHT: "bg-violet-100 text-violet-800",
  IN_REPAIR: "bg-amber-100 text-amber-800",
  LISTED: "bg-cyan-100 text-cyan-800",
  SOLD: "bg-emerald-100 text-emerald-800",
  PASSED: "bg-slate-100 text-slate-700"
};

const workflowConfig: Record<
  FlipStatus,
  {
    accent: string;
    description: string;
    eyebrow: string;
    headerTone: string;
    title: string;
  }
> = {
  WATCHING: {
    accent: "border-l-sky-400",
    description: "Qualify the opportunity, contact the seller, and decide whether the numbers justify a purchase.",
    eyebrow: "Acquisition",
    headerTone: "border-sky-200 bg-sky-50 text-sky-950",
    title: "Lead assessment"
  },
  BOUGHT: {
    accent: "border-l-violet-400",
    description: "The purchase is complete. Record the true buy price and plan the work needed before sale.",
    eyebrow: "Owned stock",
    headerTone: "border-violet-200 bg-violet-50 text-violet-950",
    title: "Acquisition record"
  },
  IN_REPAIR: {
    accent: "border-l-amber-400",
    description: "Track preparation spend and the next job without the noise of seller-contact fields.",
    eyebrow: "Workshop",
    headerTone: "border-amber-200 bg-amber-50 text-amber-950",
    title: "Repair and preparation"
  },
  LISTED: {
    accent: "border-l-cyan-400",
    description: "Manage the sale campaign, advertised price, listing link, and next buyer follow-up.",
    eyebrow: "For sale",
    headerTone: "border-cyan-200 bg-cyan-50 text-cyan-950",
    title: "Sale campaign"
  },
  SOLD: {
    accent: "border-l-emerald-400",
    description: "Review the final result and preserve the lessons that should improve the next flip.",
    eyebrow: "Completed",
    headerTone: "border-emerald-200 bg-emerald-50 text-emerald-950",
    title: "Completed flip"
  },
  PASSED: {
    accent: "border-l-slate-300",
    description: "Keep only the useful reference numbers and the reason this opportunity was closed.",
    eyebrow: "Closed lead",
    headerTone: "border-slate-200 bg-slate-50 text-slate-950",
    title: "Decision record"
  }
};

const priorityTone: Record<AdminPriority, string> = {
  LOW: "bg-slate-100 text-slate-700",
  MEDIUM: "bg-amber-100 text-amber-800",
  HIGH: "bg-rose-100 text-rose-800"
};

const marketplaceAvailabilityTone: Record<string, string> = {
  ACTIVE: "bg-emerald-100 text-emerald-800",
  NEEDS_REVIEW: "bg-amber-100 text-amber-800",
  POSSIBLY_SOLD: "bg-orange-100 text-orange-800",
  CONFIRMED_SOLD: "bg-rose-100 text-rose-800",
  SOLD: "bg-rose-100 text-rose-800",
  UNAVAILABLE: "bg-orange-100 text-orange-800",
  EXPIRED: "bg-slate-200 text-slate-700",
  UNKNOWN: "bg-amber-100 text-amber-800"
};

const marketplaceAvailabilityLabel: Record<string, string> = {
  ACTIVE: "Marketplace active",
  NEEDS_REVIEW: "Marketplace needs review",
  POSSIBLY_SOLD: "Marketplace needs confirmation",
  CONFIRMED_SOLD: "Marketplace confirmed sold",
  SOLD: "Marketplace sold",
  UNAVAILABLE: "Marketplace unavailable",
  EXPIRED: "Marketplace expired",
  UNKNOWN: "Marketplace checking"
};

const nzDateFormatter = new Intl.DateTimeFormat("en-NZ", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Pacific/Auckland"
});

const nzDayFormatter = new Intl.DateTimeFormat("en-NZ", {
  dateStyle: "medium",
  timeZone: "Pacific/Auckland"
});

const statusOptions = flipStatuses.map((status) => ({
  label: flipStatusLabels[status],
  value: status
}));

const priorityOptions = adminPriorities.map((priority) => ({
  label: adminPriorityLabels[priority],
  value: priority
}));

function draftForMode(mode: AddMode): DraftState {
  const config = addModes[mode];

  return {
    ...blankDraft,
    status: config.status,
    nextAction: config.nextAction
  };
}

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
    askingPrice: inputMoney(flip.askingPriceCents),
    thumbnailPath: flip.thumbnailPath ?? "",
    kms: flip.kms ? String(flip.kms) : "",
    rego: flip.rego ?? "",
    sellerContacted: flip.sellerContacted,
    sellerContactedAt: inputDate(flip.sellerContactedAt),
    priority: flip.priority,
    nextAction: flip.nextAction ?? "",
    valuation: inputMoney(flip.valuationCents),
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

function updatedLabel(value: string) {
  return nzDateFormatter.format(new Date(value));
}

function dayLabel(value: string | null) {
  return value ? nzDayFormatter.format(new Date(value)) : "Not logged";
}

function buildPayload(draft: DraftState) {
  return {
    vehicleTitle: draft.vehicleTitle,
    status: draft.status,
    sourceUrl: draft.sourceUrl,
    askingPrice: draft.askingPrice,
    thumbnailPath: draft.thumbnailPath,
    kms: draft.kms,
    rego: draft.rego,
    sellerContacted: draft.sellerContacted,
    sellerContactedAt: draft.sellerContactedAt,
    priority: draft.priority,
    nextAction: draft.nextAction,
    valuation: draft.valuation,
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

function updateSet<T extends string>(current: Set<T>, id: T) {
  const next = new Set(current);
  if (next.has(id)) {
    next.delete(id);
  } else {
    next.add(id);
  }

  return next;
}

async function compressImage(file: File) {
  if (!file.type.startsWith("image/") || file.type === "image/svg+xml") {
    throw new Error("Please choose a JPEG, PNG, or WebP photo.");
  }

  if (file.size > 8 * 1024 * 1024) {
    throw new Error("Photo is too large. Please choose an image under 8MB.");
  }

  const objectUrl = URL.createObjectURL(file);

  try {
    const image = new Image();
    image.decoding = "async";
    const loaded = new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () =>
        reject(new Error("Could not read that image. Try a different photo."));
    });
    image.src = objectUrl;
    await loaded;

    const maxSide = 960;
    const scale = Math.min(
      1,
      maxSide / Math.max(image.naturalWidth, image.naturalHeight)
    );
    const width = Math.max(1, Math.round(image.naturalWidth * scale));
    const height = Math.max(1, Math.round(image.naturalHeight * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");

    if (!context) {
      throw new Error("Your browser could not prepare the photo.");
    }

    context.drawImage(image, 0, 0, width, height);
    return canvas.toDataURL("image/jpeg", 0.82);
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

function Field({
  label,
  name,
  onChange,
  placeholder,
  required = false,
  type = "text",
  value
}: {
  label: string;
  name: keyof DraftState;
  onChange: (name: keyof DraftState, value: string) => void;
  placeholder?: string;
  required?: boolean;
  type?: string;
  value: string;
}) {
  return (
    <label className="grid gap-1.5">
      <span className="text-[0.68rem] font-bold uppercase tracking-[0.16em] text-slate-400">
        {label}
      </span>
      <input
        className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none ring-violet-200 transition focus:ring-4"
        onChange={(event) => onChange(name, event.target.value)}
        placeholder={placeholder}
        required={required}
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
    <label className="grid gap-1.5">
      <span className="text-[0.68rem] font-bold uppercase tracking-[0.16em] text-slate-400">
        {label}
      </span>
      <textarea
        className="min-h-24 resize-y rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm leading-6 outline-none ring-violet-200 transition focus:ring-4"
        onChange={(event) => onChange(name, event.target.value)}
        placeholder={placeholder}
        value={value}
      />
    </label>
  );
}

function SelectField({
  label,
  onChange,
  options,
  value
}: {
  label: string;
  onChange: (value: string) => void;
  options: Array<{ label: string; value: string }>;
  value: string;
}) {
  return (
    <label className="grid gap-1.5">
      <span className="text-[0.68rem] font-bold uppercase tracking-[0.16em] text-slate-400">
        {label}
      </span>
      <select
        className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none ring-violet-200 transition focus:ring-4"
        onChange={(event) => onChange(event.target.value)}
        value={value}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function PhotoField({
  onChange,
  title = "Car photo",
  value
}: {
  onChange: (value: string) => void;
  title?: string;
  value: string;
}) {
  const [error, setError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";

    if (!file) {
      return;
    }

    setIsProcessing(true);
    setError(null);

    try {
      const dataUrl = await compressImage(file);
      onChange(dataUrl);
    } catch (photoError) {
      setError(
        photoError instanceof Error
          ? photoError.message
          : "Could not prepare that photo."
      );
    } finally {
      setIsProcessing(false);
    }
  }

  return (
    <div className="grid gap-3 rounded-[1.5rem] border border-slate-100 bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-[0.68rem] font-bold uppercase tracking-[0.16em] text-slate-400">
            Photo
          </p>
          <p className="mt-1 text-sm font-bold text-slate-950">{title}</p>
        </div>
        {value ? (
          <button
            className="rounded-full border border-slate-200 px-3 py-1.5 text-xs font-bold text-slate-600 transition hover:bg-slate-50"
            onClick={() => onChange("")}
            type="button"
          >
            Remove photo
          </button>
        ) : null}
      </div>

      <SafeCarImage
        alt={title}
        className="h-44 w-full rounded-3xl object-cover shadow-md ring-1 ring-slate-200"
        fallbackClassName="flex h-44 items-center justify-center rounded-3xl bg-slate-100 text-sm font-bold text-slate-400 ring-1 ring-slate-200"
        src={value}
      />

      <label className="inline-flex cursor-pointer items-center justify-center rounded-2xl bg-slate-950 px-4 py-3 text-sm font-bold text-white shadow-lg shadow-slate-200 transition hover:-translate-y-0.5 hover:bg-slate-800">
        {isProcessing ? "Preparing photo..." : value ? "Replace photo" : "Upload photo"}
        <input
          accept="image/jpeg,image/png,image/webp"
          className="sr-only"
          disabled={isProcessing}
          onChange={handleFile}
          type="file"
        />
      </label>
      <p className="text-xs leading-5 text-slate-500">
        Photos are resized in your browser before saving, so manual and sold
        flips keep a clean thumbnail without extra setup.
      </p>
      {error ? (
        <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs font-bold text-rose-700">
          {error}
        </p>
      ) : null}
    </div>
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

function PhotoPreview({
  title,
  value
}: {
  title: string;
  value: string | null;
}) {
  return (
    <SafeCarImage
      alt={title}
      className="h-28 w-36 rounded-3xl object-cover shadow-md ring-1 ring-slate-200"
      fallbackClassName="flex h-28 w-36 items-center justify-center rounded-3xl bg-slate-100 text-xs font-bold text-slate-400 ring-1 ring-slate-200"
      src={value}
    />
  );
}

type SnapshotMetric = {
  label: string;
  tone?: "default" | "good" | "muted" | "warning";
  value: string;
};

function loggedMoney(value: number | null | undefined, fallback = "Not logged") {
  return value != null && value > 0 ? formatMoney(value) : fallback;
}

function calculatedMoney(
  value: number | null | undefined,
  fallback = "Not ready"
) {
  return value == null ? fallback : formatMoney(value);
}

function WorkflowSnapshot({ flip }: { flip: AdminFlipView }) {
  const runningCosts = flip.repairCostCents + flip.otherCostCents;
  const invested = totalCost(flip);
  const targetSale = flip.targetSellPriceCents ?? flip.valuationCents;
  const projectedProfit =
    targetSale != null && flip.purchasePriceCents > 0
      ? targetSale - invested
      : null;
  const realizedProfit = profit(flip);
  const expectedSale = flip.salePriceCents ?? targetSale;
  const listedProfit =
    expectedSale != null && flip.purchasePriceCents > 0
      ? expectedSale - invested
      : null;
  const roi =
    realizedProfit != null && invested > 0
      ? `${Math.round((realizedProfit / invested) * 100)}%`
      : "Pending";

  const metrics: Record<FlipStatus, SnapshotMetric[]> = {
    WATCHING: [
      { label: "Asking", value: loggedMoney(flip.askingPriceCents) },
      { label: "Market value", value: loggedMoney(flip.valuationCents) },
      { label: "Buy ceiling", value: loggedMoney(flip.maxBuyPriceCents) },
      {
        label: "Expected margin",
        tone:
          flip.estimatedProfitCents == null
            ? "muted"
            : flip.estimatedProfitCents >= 0
              ? "good"
              : "warning",
        value: calculatedMoney(flip.estimatedProfitCents)
      }
    ],
    BOUGHT: [
      { label: "Purchase price", value: loggedMoney(flip.purchasePriceCents) },
      { label: "Added costs", value: formatMoney(runningCosts) },
      { label: "Total invested", value: loggedMoney(invested) },
      {
        label: "Projected profit",
        tone:
          projectedProfit == null
            ? "muted"
            : projectedProfit >= 0
              ? "good"
              : "warning",
        value: calculatedMoney(projectedProfit, "Set purchase price")
      }
    ],
    IN_REPAIR: [
      { label: "Purchase price", value: loggedMoney(flip.purchasePriceCents) },
      { label: "Repair spend", value: formatMoney(flip.repairCostCents) },
      { label: "Other costs", value: formatMoney(flip.otherCostCents) },
      { label: "Total invested", value: loggedMoney(invested) },
      {
        label: "Target headroom",
        tone:
          projectedProfit == null
            ? "muted"
            : projectedProfit >= 0
              ? "good"
              : "warning",
        value: calculatedMoney(projectedProfit, "Set target")
      }
    ],
    LISTED: [
      { label: "Total invested", value: loggedMoney(invested) },
      { label: "Target sale", value: loggedMoney(targetSale) },
      { label: "Advertised price", value: loggedMoney(flip.salePriceCents) },
      {
        label: "Projected profit",
        tone:
          listedProfit == null
            ? "muted"
            : listedProfit >= 0
              ? "good"
              : "warning",
        value: calculatedMoney(listedProfit, "Set sale price")
      }
    ],
    SOLD: [
      { label: "Purchase price", value: loggedMoney(flip.purchasePriceCents) },
      { label: "Added costs", value: formatMoney(runningCosts) },
      { label: "Total cost", value: loggedMoney(invested) },
      { label: "Sale price", value: loggedMoney(flip.salePriceCents) },
      {
        label: "Realized profit",
        tone:
          realizedProfit == null
            ? "muted"
            : realizedProfit >= 0
              ? "good"
              : "warning",
        value: calculatedMoney(realizedProfit, "Not complete")
      },
      {
        label: "ROI",
        tone:
          realizedProfit == null
            ? "muted"
            : realizedProfit >= 0
              ? "good"
              : "warning",
        value: roi
      }
    ],
    PASSED: [
      { label: "Asking", value: loggedMoney(flip.askingPriceCents) },
      { label: "Market value", value: loggedMoney(flip.valuationCents) },
      { label: "Decision", tone: "muted", value: "Opportunity closed" }
    ]
  };

  const valueTone = {
    default: "text-slate-950",
    good: "text-emerald-700",
    muted: "text-slate-500",
    warning: "text-rose-700"
  };

  return (
    <div className="grid min-w-0 grid-cols-2 gap-x-4 gap-y-3 rounded-3xl bg-slate-50 p-4 text-sm md:grid-cols-3 xl:min-w-[38rem] xl:grid-cols-4">
      {metrics[flip.status].map((metric) => (
        <div className="min-w-0" key={metric.label}>
          <p className="text-[0.65rem] font-bold uppercase tracking-[0.14em] text-slate-400">
            {metric.label}
          </p>
          <p
            className={`mt-1 truncate font-bold ${valueTone[metric.tone ?? "default"]}`}
            title={metric.value}
          >
            {metric.value}
          </p>
        </div>
      ))}
    </div>
  );
}

function FormSection({
  children,
  description,
  title
}: {
  children: ReactNode;
  description?: string;
  title: string;
}) {
  return (
    <section className="rounded-[1.5rem] border border-slate-100 bg-slate-50/70 p-4">
      <div>
        <h4 className="text-sm font-bold uppercase tracking-[0.18em] text-slate-600">
          {title}
        </h4>
        {description ? (
          <p className="mt-1 text-sm leading-6 text-slate-500">{description}</p>
        ) : null}
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {children}
      </div>
    </section>
  );
}

function WorkflowEditor({
  draft,
  onChange
}: {
  draft: DraftState;
  onChange: (name: keyof DraftState, value: string | boolean) => void;
}) {
  const config = workflowConfig[draft.status];
  const fieldChange = (name: keyof DraftState, value: string) =>
    onChange(name, value);

  return (
    <div className="grid gap-5">
      <div
        className={`grid gap-4 rounded-[1.5rem] border p-4 lg:grid-cols-[minmax(0,1fr)_16rem] lg:items-end ${config.headerTone}`}
      >
        <div>
          <p className="text-[0.68rem] font-bold uppercase tracking-[0.18em] opacity-65">
            {config.eyebrow}
          </p>
          <h4 className="mt-1 text-2xl font-semibold tracking-tight">
            {config.title}
          </h4>
          <p className="mt-1 max-w-2xl text-sm leading-6 opacity-75">
            {config.description}
          </p>
        </div>
        <SelectField
          label="Workflow status"
          onChange={(value) => onChange("status", value)}
          options={statusOptions}
          value={draft.status}
        />
      </div>

      <FormSection
        description="Core vehicle details stay available at every stage."
        title="Vehicle record"
      >
        <Field
          label="Vehicle"
          name="vehicleTitle"
          onChange={fieldChange}
          required
          value={draft.vehicleTitle}
        />
        <Field
          label="KMs"
          name="kms"
          onChange={fieldChange}
          value={draft.kms}
        />
        <Field
          label="Rego"
          name="rego"
          onChange={fieldChange}
          value={draft.rego}
        />
      </FormSection>

      {draft.status === "WATCHING" ? (
        <FormSection
          description="Only the information needed to decide whether this car is worth buying."
          title="Lead assessment"
        >
          <Field
            label="Source URL"
            name="sourceUrl"
            onChange={fieldChange}
            value={draft.sourceUrl}
          />
          <Field
            label="Asking $"
            name="askingPrice"
            onChange={fieldChange}
            value={draft.askingPrice}
          />
          <Field
            label="Trade Me value"
            name="valuation"
            onChange={fieldChange}
            value={draft.valuation}
          />
          <SelectField
            label="Priority"
            onChange={(value) => onChange("priority", value)}
            options={priorityOptions}
            value={draft.priority}
          />
          <label className="flex min-h-[4.15rem] items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-bold text-slate-700">
            <input
              checked={draft.sellerContacted}
              className="h-4 w-4"
              onChange={(event) =>
                onChange("sellerContacted", event.target.checked)
              }
              type="checkbox"
            />
            Contacted seller
          </label>
          <Field
            label="Contacted date"
            name="sellerContactedAt"
            onChange={fieldChange}
            type="date"
            value={draft.sellerContactedAt}
          />
          <Field
            label="Next action"
            name="nextAction"
            onChange={fieldChange}
            value={draft.nextAction}
          />
        </FormSection>
      ) : null}

      {draft.status === "BOUGHT" ? (
        <FormSection
          description="The asking price is history now; this is the actual acquisition record."
          title="Purchase"
        >
          <Field
            label="Purchase date"
            name="purchaseDate"
            onChange={fieldChange}
            type="date"
            value={draft.purchaseDate}
          />
          <Field
            label="Purchase $"
            name="purchasePrice"
            onChange={fieldChange}
            value={draft.purchasePrice}
          />
          <Field
            label="Next action"
            name="nextAction"
            onChange={fieldChange}
            placeholder="Inspection, registration, workshop booking..."
            value={draft.nextAction}
          />
        </FormSection>
      ) : null}

      {draft.status === "IN_REPAIR" ? (
        <>
          <FormSection title="Cost basis">
            <Field
              label="Purchase date"
              name="purchaseDate"
              onChange={fieldChange}
              type="date"
              value={draft.purchaseDate}
            />
            <Field
              label="Purchase $"
              name="purchasePrice"
              onChange={fieldChange}
              value={draft.purchasePrice}
            />
          </FormSection>
          <FormSection
            description="Keep the current spend and the next workshop task together."
            title="Repair and preparation"
          >
            <Field
              label="Repair $"
              name="repairCost"
              onChange={fieldChange}
              value={draft.repairCost}
            />
            <Field
              label="Other $"
              name="otherCost"
              onChange={fieldChange}
              value={draft.otherCost}
            />
            <Field
              label="Next action"
              name="nextAction"
              onChange={fieldChange}
              placeholder="WOF, parts, paint, detail..."
              value={draft.nextAction}
            />
          </FormSection>
        </>
      ) : null}

      {draft.status === "LISTED" ? (
        <>
          <FormSection title="Investment">
            <Field
              label="Purchase $"
              name="purchasePrice"
              onChange={fieldChange}
              value={draft.purchasePrice}
            />
            <Field
              label="Repair $"
              name="repairCost"
              onChange={fieldChange}
              value={draft.repairCost}
            />
            <Field
              label="Other $"
              name="otherCost"
              onChange={fieldChange}
              value={draft.otherCost}
            />
          </FormSection>
          <FormSection
            description="Track the live advert and the price buyers currently see."
            title="Sale campaign"
          >
            <Field
              label="Sale listing URL"
              name="sourceUrl"
              onChange={fieldChange}
              value={draft.sourceUrl}
            />
            <Field
              label="Advertised $"
              name="salePrice"
              onChange={fieldChange}
              value={draft.salePrice}
            />
            <Field
              label="Next action"
              name="nextAction"
              onChange={fieldChange}
              placeholder="Follow up buyer, refresh advert, adjust price..."
              value={draft.nextAction}
            />
          </FormSection>
        </>
      ) : null}

      {draft.status === "SOLD" ? (
        <>
          <FormSection title="Final cost basis">
            <Field
              label="Purchase date"
              name="purchaseDate"
              onChange={fieldChange}
              type="date"
              value={draft.purchaseDate}
            />
            <Field
              label="Purchase $"
              name="purchasePrice"
              onChange={fieldChange}
              value={draft.purchasePrice}
            />
            <Field
              label="Repair $"
              name="repairCost"
              onChange={fieldChange}
              value={draft.repairCost}
            />
            <Field
              label="Other $"
              name="otherCost"
              onChange={fieldChange}
              value={draft.otherCost}
            />
          </FormSection>
          <FormSection
            description="These figures drive realized profit and ROI in the summary above."
            title="Sale result"
          >
            <Field
              label="Sale date"
              name="saleDate"
              onChange={fieldChange}
              type="date"
              value={draft.saleDate}
            />
            <Field
              label="Sale $"
              name="salePrice"
              onChange={fieldChange}
              value={draft.salePrice}
            />
          </FormSection>
        </>
      ) : null}

      {draft.status === "PASSED" ? (
        <FormSection
          description="Keep enough context to avoid repeating the same dead-end research."
          title="Reference"
        >
          <Field
            label="Source URL"
            name="sourceUrl"
            onChange={fieldChange}
            value={draft.sourceUrl}
          />
          <Field
            label="Asking $"
            name="askingPrice"
            onChange={fieldChange}
            value={draft.askingPrice}
          />
          <Field
            label="Trade Me value"
            name="valuation"
            onChange={fieldChange}
            value={draft.valuation}
          />
        </FormSection>
      ) : null}

      <FormSection
        description={
          draft.status === "SOLD"
            ? "Close the loop with a concise record of what the deal taught you."
            : "Keep operational detail here without cluttering the status summary."
        }
        title={draft.status === "SOLD" ? "Review and journal" : "Working notes"}
      >
        <TextAreaField
          label={draft.status === "PASSED" ? "Why you passed" : "Admin notes"}
          name="notes"
          onChange={fieldChange}
          placeholder={
            draft.status === "PASSED"
              ? "Price, condition, seller, location, or risk that ended the opportunity..."
              : "Checks, reminders, parts, buyers, or other operational details..."
          }
          value={draft.notes}
        />
        {draft.status === "SOLD" ? (
          <>
            <TextAreaField
              label="What went right"
              name="journalWentRight"
              onChange={fieldChange}
              placeholder="Good buy reason, negotiation win, repair that paid off..."
              value={draft.journalWentRight}
            />
            <TextAreaField
              label="What went wrong"
              name="journalWentWrong"
              onChange={fieldChange}
              placeholder="Hidden cost, slow sale reason, inspection miss..."
              value={draft.journalWentWrong}
            />
            <TextAreaField
              label="Look out for next time"
              name="journalLookOutFor"
              onChange={fieldChange}
              placeholder="Model issues, seller red flags, price ceiling lesson..."
              value={draft.journalLookOutFor}
            />
          </>
        ) : null}
      </FormSection>
    </div>
  );
}

export function AdminPanel({ flips, stats }: AdminPanelProps) {
  const router = useRouter();
  const [addMode, setAddMode] = useState<AddMode>("WATCHING");
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [expandedFlipIds, setExpandedFlipIds] = useState<Set<string>>(
    () => new Set()
  );
  const [expandedGroups, setExpandedGroups] = useState<Set<AdminGroupKey>>(
    () => new Set(["watching", "active", "sold"])
  );
  const [newDraft, setNewDraft] = useState<DraftState>(() =>
    draftForMode("WATCHING")
  );
  const [drafts, setDrafts] = useState<Record<string, DraftState>>({});
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDrafts(
      Object.fromEntries(flips.map((flip) => [flip.id, flipToDraft(flip)]))
    );
    setExpandedFlipIds((current) => {
      const liveIds = new Set(flips.map((flip) => flip.id));
      return new Set([...current].filter((id) => liveIds.has(id)));
    });
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

  const groupedSections = useMemo(
    () =>
      adminGroups.map((group) => ({
        ...group,
        flips: flips.filter((flip) => group.statuses.includes(flip.status))
      })),
    [flips]
  );

  function chooseAddMode(mode: AddMode) {
    setAddMode(mode);
    setNewDraft(draftForMode(mode));
    setIsAddOpen(true);
    setMessage(null);
    setError(null);
  }

  const updateNewDraft = (name: keyof DraftState, value: string) => {
    setNewDraft((current) => ({ ...current, [name]: value }));
  };

  const updateDraft = (
    id: string,
    name: keyof DraftState,
    value: string | boolean
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
      return true;
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "The admin update failed."
      );
      return false;
    } finally {
      setPendingAction(null);
    }
  }

  async function addFlip(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const created = await submitRequest({
      actionId: "create",
      body: buildPayload(newDraft),
      method: "POST",
      successMessage: "Car added.",
      url: "/api/admin/flips"
    });

    if (created) {
      setNewDraft(draftForMode(addMode));
    }
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

  async function deleteFlip(id: string) {
    const deleted = await submitRequest({
      actionId: `delete-${id}`,
      method: "DELETE",
      successMessage: "Car removed.",
      url: `/api/admin/flips/${id}`
    });

    if (deleted) {
      setDeleteConfirmId(null);
    }
  }

  function toggleGroup(key: AdminGroupKey) {
    setExpandedGroups((current) => updateSet(current, key));
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
              One tidy place for every flip.
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-slate-300">
              Save leads from the Dashboard, add cars found elsewhere, backfill
              sold flips, track the money, and keep a useful journal without
              digging through a giant form.
            </p>
          </div>
          <div className="rounded-[2rem] border border-white/10 bg-white/10 p-5 backdrop-blur">
            <p className="text-sm font-medium text-slate-300">
              Workflow proof
            </p>
            <div className="mt-4 space-y-3 text-sm text-slate-200">
              <div className="flex justify-between gap-4">
                <span>Spot a lead</span>
                <strong>Watching</strong>
              </div>
              <div className="flex justify-between gap-4">
                <span>Buy it</span>
                <strong>Costs start</strong>
              </div>
              <div className="flex justify-between gap-4">
                <span>Sell it</span>
                <strong>Journal the lesson</strong>
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

      <section className="mt-8 grid gap-4">
        <section className="overflow-hidden rounded-[2rem] border border-white/80 bg-white/90 shadow-xl shadow-slate-200/70">
          <div className="flex items-center justify-between gap-4 p-5">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.22em] text-violet-500">
                Add car
              </p>
              <h2 className="mt-1 text-2xl font-semibold tracking-tight">
                Quick entry for leads, purchases, and sold flips
              </h2>
            </div>
            <button
              aria-controls="admin-add-panel"
              aria-expanded={isAddOpen}
              className="shrink-0 rounded-full bg-slate-950 px-5 py-3 text-sm font-bold text-white transition hover:bg-slate-800"
              onClick={() => setIsAddOpen((current) => !current)}
              type="button"
            >
              {isAddOpen ? "Collapse" : "Expand"}
            </button>
          </div>

          {isAddOpen ? (
            <div className="border-t border-slate-100 p-5" id="admin-add-panel">
              <div className="grid gap-3 md:grid-cols-3">
                {(Object.keys(addModes) as AddMode[]).map((mode) => (
                  <button
                    className={`rounded-3xl border p-4 text-left transition hover:-translate-y-0.5 ${
                      addMode === mode
                        ? "border-slate-950 bg-slate-950 text-white shadow-xl shadow-slate-300"
                        : "border-slate-200 bg-white text-slate-950"
                    }`}
                    key={mode}
                    onClick={() => chooseAddMode(mode)}
                    type="button"
                  >
                    <span className="block text-sm font-bold">
                      {addModes[mode].label}
                    </span>
                    <span
                      className={`mt-2 block text-sm leading-6 ${
                        addMode === mode ? "text-slate-300" : "text-slate-500"
                      }`}
                    >
                      {addModes[mode].description}
                    </span>
                  </button>
                ))}
              </div>

              <form className="mt-5 grid gap-5" onSubmit={addFlip}>
                <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
                  <div className="grid gap-5">
                    <section className="rounded-[1.5rem] border border-slate-100 bg-slate-50/70 p-4">
                      <h3 className="text-sm font-bold uppercase tracking-[0.18em] text-slate-500">
                        Lead
                      </h3>
                      <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                        <Field
                          label="Vehicle"
                          name="vehicleTitle"
                          onChange={updateNewDraft}
                          placeholder="e.g. 2007 Toyota Auris"
                          required
                          value={newDraft.vehicleTitle}
                        />
                        <SelectField
                          label="Status"
                          onChange={(value) =>
                            updateNewDraft("status", value as FlipStatus)
                          }
                          options={statusOptions}
                          value={newDraft.status}
                        />
                        <Field
                          label="Source URL"
                          name="sourceUrl"
                          onChange={updateNewDraft}
                          placeholder="Facebook or Trade Me link"
                          value={newDraft.sourceUrl}
                        />
                        <Field
                          label="Asking $"
                          name="askingPrice"
                          onChange={updateNewDraft}
                          placeholder="3500"
                          value={newDraft.askingPrice}
                        />
                        <Field
                          label="Trade Me value"
                          name="valuation"
                          onChange={updateNewDraft}
                          placeholder="5100"
                          value={newDraft.valuation}
                        />
                        <Field
                          label="KMs"
                          name="kms"
                          onChange={updateNewDraft}
                          placeholder="181000"
                          value={newDraft.kms}
                        />
                        <Field
                          label="Rego"
                          name="rego"
                          onChange={updateNewDraft}
                          placeholder="ABC123"
                          value={newDraft.rego}
                        />
                        <SelectField
                          label="Priority"
                          onChange={(value) =>
                            updateNewDraft("priority", value as AdminPriority)
                          }
                          options={priorityOptions}
                          value={newDraft.priority}
                        />
                        <label className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-bold text-slate-700">
                          <input
                            checked={newDraft.sellerContacted}
                            className="h-4 w-4"
                            onChange={(event) =>
                              setNewDraft((current) => ({
                                ...current,
                                sellerContacted: event.target.checked
                              }))
                            }
                            type="checkbox"
                          />
                          Contacted seller
                        </label>
                        <Field
                          label="Contacted date"
                          name="sellerContactedAt"
                          onChange={updateNewDraft}
                          type="date"
                          value={newDraft.sellerContactedAt}
                        />
                        <Field
                          label="Next action"
                          name="nextAction"
                          onChange={updateNewDraft}
                          placeholder="Message seller"
                          value={newDraft.nextAction}
                        />
                      </div>
                    </section>

                    {addMode !== "WATCHING" ? (
                      <section className="rounded-[1.5rem] border border-slate-100 bg-slate-50/70 p-4">
                        <h3 className="text-sm font-bold uppercase tracking-[0.18em] text-slate-500">
                          Purchase and sale
                        </h3>
                        <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                          <Field
                            label="Purchase date"
                            name="purchaseDate"
                            onChange={updateNewDraft}
                            type="date"
                            value={newDraft.purchaseDate}
                          />
                          <Field
                            label="Purchase $"
                            name="purchasePrice"
                            onChange={updateNewDraft}
                            placeholder="2500"
                            value={newDraft.purchasePrice}
                          />
                          <Field
                            label="Repair $"
                            name="repairCost"
                            onChange={updateNewDraft}
                            placeholder="450"
                            value={newDraft.repairCost}
                          />
                          <Field
                            label="Other $"
                            name="otherCost"
                            onChange={updateNewDraft}
                            placeholder="120"
                            value={newDraft.otherCost}
                          />
                          {addMode === "SOLD" ? (
                            <>
                              <Field
                                label="Sale date"
                                name="saleDate"
                                onChange={updateNewDraft}
                                type="date"
                                value={newDraft.saleDate}
                              />
                              <Field
                                label="Sale $"
                                name="salePrice"
                                onChange={updateNewDraft}
                                placeholder="5200"
                                value={newDraft.salePrice}
                              />
                            </>
                          ) : null}
                        </div>
                      </section>
                    ) : null}

                    {addMode === "SOLD" ? (
                      <section className="rounded-[1.5rem] border border-slate-100 bg-slate-50/70 p-4">
                        <h3 className="text-sm font-bold uppercase tracking-[0.18em] text-slate-500">
                          Journal
                        </h3>
                        <div className="mt-4 grid gap-4 xl:grid-cols-3">
                          <TextAreaField
                            label="What went right"
                            name="journalWentRight"
                            onChange={updateNewDraft}
                            placeholder="Negotiation, repair, resale, timing..."
                            value={newDraft.journalWentRight}
                          />
                          <TextAreaField
                            label="What went wrong"
                            name="journalWentWrong"
                            onChange={updateNewDraft}
                            placeholder="Hidden costs, slow sale, missed checks..."
                            value={newDraft.journalWentWrong}
                          />
                          <TextAreaField
                            label="Look out for next time"
                            name="journalLookOutFor"
                            onChange={updateNewDraft}
                            placeholder="Model issue, seller red flag, price ceiling..."
                            value={newDraft.journalLookOutFor}
                          />
                        </div>
                      </section>
                    ) : null}
                  </div>

                  <div className="grid content-start gap-4">
                    <PhotoField
                      onChange={(value) =>
                        updateNewDraft("thumbnailPath", value)
                      }
                      value={newDraft.thumbnailPath}
                    />
                    <TextAreaField
                      label="Admin notes"
                      name="notes"
                      onChange={updateNewDraft}
                      placeholder="Seller details, pickup plan, checks, reminders..."
                      value={newDraft.notes}
                    />
                    <button
                      className="rounded-2xl bg-slate-950 px-5 py-4 text-sm font-bold text-white shadow-lg shadow-slate-300 transition hover:-translate-y-0.5 hover:bg-slate-800 disabled:opacity-50"
                      disabled={pendingAction === "create"}
                    >
                      {pendingAction === "create"
                        ? "Adding..."
                        : `Add ${addModes[addMode].label}`}
                    </button>
                  </div>
                </div>
              </form>
            </div>
          ) : null}
        </section>

        {flips.length === 0 ? (
          <div className="rounded-[2rem] border border-white/80 bg-white/90 p-10 text-center shadow-xl shadow-slate-200/70">
            <p className="text-2xl font-semibold text-slate-950">
              No admin cars yet.
            </p>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              Use Save to Admin on the Dashboard, or expand Add car above.
            </p>
          </div>
        ) : (
          groupedSections.map((group) => {
            const isGroupExpanded = expandedGroups.has(group.key);

            return (
              <section
                className="overflow-hidden rounded-[2rem] border border-white/80 bg-white/90 shadow-xl shadow-slate-200/70"
                key={group.key}
              >
                <button
                  aria-expanded={isGroupExpanded}
                  className="flex w-full items-center justify-between gap-4 p-5 text-left transition hover:bg-slate-50"
                  onClick={() => toggleGroup(group.key)}
                  type="button"
                >
                  <span>
                    <span className="text-xs font-bold uppercase tracking-[0.22em] text-violet-500">
                      Admin section
                    </span>
                    <span className="mt-1 block text-2xl font-semibold tracking-tight text-slate-950">
                      {group.title}
                    </span>
                    <span className="mt-1 block text-sm leading-6 text-slate-500">
                      {group.description}
                    </span>
                  </span>
                  <span className="flex shrink-0 items-center gap-3">
                    <span className="rounded-full bg-slate-100 px-4 py-2 text-sm font-bold text-slate-700">
                      {group.flips.length}
                    </span>
                    <span className="rounded-full bg-slate-950 px-5 py-3 text-sm font-bold text-white">
                      {isGroupExpanded ? "Collapse" : "Expand"}
                    </span>
                  </span>
                </button>

                {isGroupExpanded ? (
                  group.flips.length === 0 ? (
                    <div className="border-t border-slate-100 p-6 text-sm font-semibold text-slate-500">
                      No cars in {group.title.toLowerCase()} yet.
                    </div>
                  ) : (
                    <div className="grid gap-4 border-t border-slate-100 p-4">
                      {group.flips.map((flip) => {
                        const draft = drafts[flip.id] ?? flipToDraft(flip);
                        const isExpanded = expandedFlipIds.has(flip.id);
                        const panelId = `admin-flip-${flip.id}`;

                        return (
                          <article
                            className={`overflow-hidden rounded-[2rem] border border-l-4 border-slate-100 bg-white/95 shadow-lg shadow-slate-200/60 ${workflowConfig[flip.status].accent}`}
                            key={flip.id}
                          >
                <div className="grid gap-4 p-4 md:grid-cols-[9rem_minmax(0,1fr)] xl:grid-cols-[9rem_minmax(0,1fr)_auto_auto] xl:items-center">
                  <PhotoPreview
                    title={flip.vehicleTitle}
                    value={flip.thumbnailPath}
                  />
                  <div className="min-w-0">
                    <div className="flex flex-wrap gap-2">
                      <span
                        className={`rounded-full px-3 py-1 text-xs font-bold ${statusTone[flip.status]}`}
                      >
                        {flipStatusLabels[flip.status]}
                      </span>
                      {flip.status === "WATCHING" ? (
                        <>
                          <span
                            className={`rounded-full px-3 py-1 text-xs font-bold ${priorityTone[flip.priority]}`}
                          >
                            {adminPriorityLabels[flip.priority]} priority
                          </span>
                          <span
                            className={`rounded-full px-3 py-1 text-xs font-bold ${
                              flip.sellerContacted
                                ? "bg-emerald-100 text-emerald-800"
                                : "bg-slate-100 text-slate-600"
                            }`}
                          >
                            {flip.sellerContacted ? "Contacted" : "Not contacted"}
                          </span>
                        </>
                      ) : null}
                      {(flip.status === "WATCHING" || flip.status === "PASSED") &&
                      flip.listingAvailabilityStatus &&
                      flip.listingAvailabilityStatus !== "ACTIVE" ? (
                        <span
                          className={`rounded-full px-3 py-1 text-xs font-bold ${
                            marketplaceAvailabilityTone[
                              flip.listingAvailabilityStatus
                            ] ?? "bg-slate-100 text-slate-700"
                          }`}
                          title={flip.listingAvailabilityReason ?? undefined}
                        >
                          {marketplaceAvailabilityLabel[
                            flip.listingAvailabilityStatus
                          ] ?? "Marketplace issue"}
                        </span>
                      ) : null}
                    </div>
                    <h3 className="mt-3 truncate text-2xl font-semibold tracking-tight text-slate-950">
                      {flip.vehicleTitle}
                    </h3>
                    <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm text-slate-500">
                      <span>
                        KMs{" "}
                        {flip.kms
                          ? flip.kms.toLocaleString("en-NZ")
                          : "Unknown"}
                      </span>
                      <span>Rego {flip.rego ?? "Unknown"}</span>
                      {flip.status === "WATCHING" ? (
                        <span>Next: {flip.nextAction ?? "No next action"}</span>
                      ) : null}
                      {flip.status === "BOUGHT" ||
                      flip.status === "IN_REPAIR" ||
                      flip.status === "LISTED" ||
                      flip.status === "SOLD" ? (
                        <span>Purchased {dayLabel(flip.purchaseDate)}</span>
                      ) : null}
                      {flip.status === "BOUGHT" ||
                      flip.status === "IN_REPAIR" ||
                      flip.status === "LISTED" ? (
                        <span>Next: {flip.nextAction ?? "No next action"}</span>
                      ) : null}
                      {flip.status === "SOLD" ? (
                        <span>Sold {dayLabel(flip.saleDate)}</span>
                      ) : null}
                      {flip.status === "PASSED" ? (
                        <span>Closed for reference</span>
                      ) : null}
                    </div>
                  </div>
                  <WorkflowSnapshot flip={flip} />
                  <button
                    aria-controls={panelId}
                    aria-expanded={isExpanded}
                    className="rounded-2xl bg-slate-950 px-5 py-3 text-sm font-bold text-white shadow-lg shadow-slate-200 transition hover:-translate-y-0.5 hover:bg-slate-800"
                    onClick={() =>
                      setExpandedFlipIds((current) =>
                        updateSet(current, flip.id)
                      )
                    }
                    type="button"
                  >
                    {isExpanded ? "Collapse" : "Expand"}
                  </button>
                </div>

                {isExpanded ? (
                  <div className="border-t border-slate-100 p-5" id={panelId}>
                    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
                      <WorkflowEditor
                        draft={draft}
                        onChange={(name, value) =>
                          updateDraft(flip.id, name, value)
                        }
                      />

                      <div className="grid content-start gap-4">
                        <PhotoField
                          onChange={(value) =>
                            updateDraft(flip.id, "thumbnailPath", value)
                          }
                          title={draft.vehicleTitle || flip.vehicleTitle}
                          value={draft.thumbnailPath}
                        />
                        <div className="rounded-[1.5rem] border border-slate-100 bg-slate-50/70 p-4">
                          <p className="text-sm text-slate-500">
                            Updated {updatedLabel(flip.updatedAt)}
                          </p>
                          {(draft.status === "WATCHING" ||
                            draft.status === "PASSED") &&
                          flip.listingAvailabilityStatus &&
                          flip.listingAvailabilityStatus !== "ACTIVE" ? (
                            <p className="mt-2 text-sm text-slate-500">
                              Marketplace status:{" "}
                              <strong>
                                {marketplaceAvailabilityLabel[
                                  flip.listingAvailabilityStatus
                                ] ?? flip.listingAvailabilityStatus}
                              </strong>
                            </p>
                          ) : null}
                          {draft.sourceUrl &&
                          (draft.status === "WATCHING" ||
                            draft.status === "LISTED" ||
                            draft.status === "PASSED") ? (
                            <a
                              className="mt-3 inline-flex rounded-2xl bg-cyan-100 px-4 py-3 text-sm font-bold text-cyan-800 transition hover:bg-cyan-200"
                              href={draft.sourceUrl}
                              rel="noreferrer"
                              target="_blank"
                            >
                              {draft.status === "LISTED"
                                ? "Open sale listing"
                                : "Open source listing"}
                            </a>
                          ) : null}
                        </div>
                        <div className="flex flex-wrap gap-3">
                          {deleteConfirmId === flip.id ? (
                            <>
                              <button
                                className="rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-bold text-slate-700 transition hover:bg-slate-50"
                                onClick={() => setDeleteConfirmId(null)}
                                type="button"
                              >
                                Cancel
                              </button>
                              <button
                                className="rounded-2xl bg-rose-600 px-5 py-3 text-sm font-bold text-white shadow-lg shadow-rose-200 transition hover:-translate-y-0.5 hover:bg-rose-700 disabled:opacity-50"
                                disabled={pendingAction === `delete-${flip.id}`}
                                onClick={() => deleteFlip(flip.id)}
                                type="button"
                              >
                                {pendingAction === `delete-${flip.id}`
                                  ? "Removing..."
                                  : "Confirm remove"}
                              </button>
                            </>
                          ) : (
                            <button
                              className="rounded-2xl border border-rose-200 bg-white px-5 py-3 text-sm font-bold text-rose-700 transition hover:bg-rose-50"
                              onClick={() => setDeleteConfirmId(flip.id)}
                              type="button"
                            >
                              Remove
                            </button>
                          )}
                          <button
                            className="rounded-2xl bg-slate-950 px-5 py-3 text-sm font-bold text-white shadow-lg shadow-slate-300 transition hover:-translate-y-0.5 hover:bg-slate-800 disabled:opacity-50"
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
                    </div>
                  </div>
                ) : null}
                          </article>
                        );
                      })}
                    </div>
                  )
                ) : null}
              </section>
            );
          })
        )}
      </section>
    </>
  );
}
