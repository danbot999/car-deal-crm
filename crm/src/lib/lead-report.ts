import { formatMoney } from "@/lib/money";

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "UNKNOWN";

export type RecommendedAction =
  | "GREAT_LEAD"
  | "CONSIDER"
  | "INSPECT_FIRST"
  | "PASS";

export type LeadSource = {
  title: string;
  url: string;
  note: string;
};

export type FailurePoint = {
  area: string;
  component: string;
  specificFailure: string;
  whyItMatters: string;
  likelihood: RiskLevel;
  severity: RiskLevel;
  inspectionSignal: string;
  roughCostRange: string;
  sourceHint: string;
};

export type LeadReport = {
  aiSummary: string;
  verdict: string;
  dealScore: number;
  riskLevel: RiskLevel;
  recommendedAction: RecommendedAction;
  vehicleIdentity: {
    summary: string;
    year: number | null;
    make: string;
    model: string;
    trim: string | null;
    engineCode: string | null;
    likelyEngineFamily: string | null;
    transmission: string | null;
    drivetrain: string | null;
    kms: number | null;
    confidence: number;
    assumptions: string[];
    verificationNeeded: string[];
  };
  dealNumbers: {
    askingPrice: string;
    tradeMeValuation: string;
    targetSellPrice: string;
    maxBuyPrice: string;
    estimatedProfitAtAsk: string;
    recommendedOfferLow: string;
    recommendedOfferHigh: string;
    negotiationAngle: string;
    expectedRepairAllowance: string;
  };
  marketPosition: string;
  failurePoints: FailurePoint[];
  ownershipCosts: string[];
  partsAvailability: string;
  wofRegoComplianceRisks: string[];
  sellerQuestions: string[];
  inspectionChecklist: string[];
  testDriveChecklist: string[];
  walkAwayTriggers: string[];
  riskFlags: string[];
  sourceNotes: LeadSource[];
};

const stringArraySchema = {
  type: "array",
  items: { type: "string" }
} as const;

const sourceSchema = {
  type: "object",
  additionalProperties: false,
  required: ["title", "url", "note"],
  properties: {
    title: { type: "string" },
    url: { type: "string" },
    note: { type: "string" }
  }
} as const;

const failurePointSchema = {
  type: "object",
  additionalProperties: false,
  required: [
    "area",
    "component",
    "specificFailure",
    "whyItMatters",
    "likelihood",
    "severity",
    "inspectionSignal",
    "roughCostRange",
    "sourceHint"
  ],
  properties: {
    area: { type: "string" },
    component: { type: "string" },
    specificFailure: { type: "string" },
    whyItMatters: { type: "string" },
    likelihood: { type: "string", enum: ["LOW", "MEDIUM", "HIGH", "UNKNOWN"] },
    severity: { type: "string", enum: ["LOW", "MEDIUM", "HIGH", "UNKNOWN"] },
    inspectionSignal: { type: "string" },
    roughCostRange: { type: "string" },
    sourceHint: { type: "string" }
  }
} as const;

export const leadReportSchema = {
  type: "object",
  additionalProperties: false,
  required: [
    "aiSummary",
    "verdict",
    "dealScore",
    "riskLevel",
    "recommendedAction",
    "vehicleIdentity",
    "dealNumbers",
    "marketPosition",
    "failurePoints",
    "ownershipCosts",
    "partsAvailability",
    "wofRegoComplianceRisks",
    "sellerQuestions",
    "inspectionChecklist",
    "testDriveChecklist",
    "walkAwayTriggers",
    "riskFlags",
    "sourceNotes"
  ],
  properties: {
    aiSummary: { type: "string" },
    verdict: { type: "string" },
    dealScore: { type: "integer", minimum: 0, maximum: 100 },
    riskLevel: { type: "string", enum: ["LOW", "MEDIUM", "HIGH", "UNKNOWN"] },
    recommendedAction: {
      type: "string",
      enum: ["GREAT_LEAD", "CONSIDER", "INSPECT_FIRST", "PASS"]
    },
    vehicleIdentity: {
      type: "object",
      additionalProperties: false,
      required: [
        "summary",
        "year",
        "make",
        "model",
        "trim",
        "engineCode",
        "likelyEngineFamily",
        "transmission",
        "drivetrain",
        "kms",
        "confidence",
        "assumptions",
        "verificationNeeded"
      ],
      properties: {
        summary: { type: "string" },
        year: { type: ["integer", "null"] },
        make: { type: "string" },
        model: { type: "string" },
        trim: { type: ["string", "null"] },
        engineCode: { type: ["string", "null"] },
        likelyEngineFamily: { type: ["string", "null"] },
        transmission: { type: ["string", "null"] },
        drivetrain: { type: ["string", "null"] },
        kms: { type: ["integer", "null"] },
        confidence: { type: "integer", minimum: 0, maximum: 100 },
        assumptions: stringArraySchema,
        verificationNeeded: stringArraySchema
      }
    },
    dealNumbers: {
      type: "object",
      additionalProperties: false,
      required: [
        "askingPrice",
        "tradeMeValuation",
        "targetSellPrice",
        "maxBuyPrice",
        "estimatedProfitAtAsk",
        "recommendedOfferLow",
        "recommendedOfferHigh",
        "negotiationAngle",
        "expectedRepairAllowance"
      ],
      properties: {
        askingPrice: { type: "string" },
        tradeMeValuation: { type: "string" },
        targetSellPrice: { type: "string" },
        maxBuyPrice: { type: "string" },
        estimatedProfitAtAsk: { type: "string" },
        recommendedOfferLow: { type: "string" },
        recommendedOfferHigh: { type: "string" },
        negotiationAngle: { type: "string" },
        expectedRepairAllowance: { type: "string" }
      }
    },
    marketPosition: { type: "string" },
    failurePoints: {
      type: "array",
      items: failurePointSchema
    },
    ownershipCosts: stringArraySchema,
    partsAvailability: { type: "string" },
    wofRegoComplianceRisks: stringArraySchema,
    sellerQuestions: stringArraySchema,
    inspectionChecklist: stringArraySchema,
    testDriveChecklist: stringArraySchema,
    walkAwayTriggers: stringArraySchema,
    riskFlags: stringArraySchema,
    sourceNotes: {
      type: "array",
      items: sourceSchema
    }
  }
} as const;

function asString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function asNumber(value: unknown, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asNullableNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asRisk(value: unknown): RiskLevel {
  return ["LOW", "MEDIUM", "HIGH", "UNKNOWN"].includes(String(value))
    ? (value as RiskLevel)
    : "UNKNOWN";
}

function asAction(value: unknown): RecommendedAction {
  return ["GREAT_LEAD", "CONSIDER", "INSPECT_FIRST", "PASS"].includes(
    String(value)
  )
    ? (value as RecommendedAction)
    : "INSPECT_FIRST";
}

export function asStringArray(value: unknown) {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

export function parseJsonArray(value: string | null | undefined) {
  if (!value) {
    return [];
  }

  try {
    const parsed = JSON.parse(value) as unknown;
    return asStringArray(parsed);
  } catch {
    return value
      .split(/\r?\n|;/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
}

export function parseLeadSources(value: string | null | undefined): LeadSource[] {
  if (!value) {
    return [];
  }

  try {
    const parsed = JSON.parse(value) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }

    return parsed
      .map((item) => {
        const source = item as Partial<LeadSource>;
        return {
          title: asString(source.title, "Source"),
          url: asString(source.url),
          note: asString(source.note)
        };
      })
      .filter((source) => source.url);
  } catch {
    return [];
  }
}

export function normalizeLeadReport(value: unknown): LeadReport {
  const report = value as Partial<LeadReport>;
  const identity = (report.vehicleIdentity ?? {}) as Partial<
    LeadReport["vehicleIdentity"]
  >;
  const dealNumbers = (report.dealNumbers ?? {}) as Partial<
    LeadReport["dealNumbers"]
  >;

  return {
    aiSummary: asString(report.aiSummary),
    verdict: asString(report.verdict),
    dealScore: Math.max(0, Math.min(100, Math.round(asNumber(report.dealScore)))),
    riskLevel: asRisk(report.riskLevel),
    recommendedAction: asAction(report.recommendedAction),
    vehicleIdentity: {
      summary: asString(identity.summary),
      year: asNullableNumber(identity.year),
      make: asString(identity.make, "Unknown"),
      model: asString(identity.model, "Unknown"),
      trim: typeof identity.trim === "string" ? identity.trim : null,
      engineCode:
        typeof identity.engineCode === "string" ? identity.engineCode : null,
      likelyEngineFamily:
        typeof identity.likelyEngineFamily === "string"
          ? identity.likelyEngineFamily
          : null,
      transmission:
        typeof identity.transmission === "string" ? identity.transmission : null,
      drivetrain:
        typeof identity.drivetrain === "string" ? identity.drivetrain : null,
      kms: asNullableNumber(identity.kms),
      confidence: Math.max(
        0,
        Math.min(100, Math.round(asNumber(identity.confidence)))
      ),
      assumptions: asStringArray(identity.assumptions),
      verificationNeeded: asStringArray(identity.verificationNeeded)
    },
    dealNumbers: {
      askingPrice: asString(dealNumbers.askingPrice),
      tradeMeValuation: asString(dealNumbers.tradeMeValuation),
      targetSellPrice: asString(dealNumbers.targetSellPrice),
      maxBuyPrice: asString(dealNumbers.maxBuyPrice),
      estimatedProfitAtAsk: asString(dealNumbers.estimatedProfitAtAsk),
      recommendedOfferLow: asString(dealNumbers.recommendedOfferLow),
      recommendedOfferHigh: asString(dealNumbers.recommendedOfferHigh),
      negotiationAngle: asString(dealNumbers.negotiationAngle),
      expectedRepairAllowance: asString(dealNumbers.expectedRepairAllowance)
    },
    marketPosition: asString(report.marketPosition),
    failurePoints: Array.isArray(report.failurePoints)
      ? report.failurePoints.map((item) => {
          const point = item as Partial<FailurePoint>;
          return {
            area: asString(point.area),
            component: asString(point.component),
            specificFailure: asString(point.specificFailure),
            whyItMatters: asString(point.whyItMatters),
            likelihood: asRisk(point.likelihood),
            severity: asRisk(point.severity),
            inspectionSignal: asString(point.inspectionSignal),
            roughCostRange: asString(point.roughCostRange),
            sourceHint: asString(point.sourceHint)
          };
        })
      : [],
    ownershipCosts: asStringArray(report.ownershipCosts),
    partsAvailability: asString(report.partsAvailability),
    wofRegoComplianceRisks: asStringArray(report.wofRegoComplianceRisks),
    sellerQuestions: asStringArray(report.sellerQuestions),
    inspectionChecklist: asStringArray(report.inspectionChecklist),
    testDriveChecklist: asStringArray(report.testDriveChecklist),
    walkAwayTriggers: asStringArray(report.walkAwayTriggers),
    riskFlags: asStringArray(report.riskFlags),
    sourceNotes: Array.isArray(report.sourceNotes)
      ? report.sourceNotes
          .map((item) => {
            const source = item as Partial<LeadSource>;
            return {
              title: asString(source.title, "Source"),
              url: asString(source.url),
              note: asString(source.note)
            };
          })
          .filter((source) => source.url)
      : []
  };
}

export function parseLeadReport(value: string | null | undefined) {
  if (!value) {
    return null;
  }

  try {
    return normalizeLeadReport(JSON.parse(value));
  } catch {
    return null;
  }
}

export function legacyFieldsFromReport(report: LeadReport) {
  const commonIssues = report.failurePoints.map((point) =>
    [
      point.component || point.area,
      point.specificFailure,
      point.roughCostRange ? `Cost: ${point.roughCostRange}` : ""
    ]
      .filter(Boolean)
      .join(" - ")
  );

  return {
    aiSummary: report.aiSummary,
    dealScore: report.dealScore,
    riskLevel: report.riskLevel,
    recommendedAction: report.recommendedAction,
    profitabilitySummary: report.marketPosition,
    commonIssues: JSON.stringify(commonIssues),
    inspectionChecklist: JSON.stringify([
      ...report.inspectionChecklist,
      ...report.testDriveChecklist
    ]),
    sellerQuestions: JSON.stringify(report.sellerQuestions),
    riskFlags: JSON.stringify([
      ...report.riskFlags,
      ...report.walkAwayTriggers.slice(0, 4)
    ])
  };
}

export function fallbackDealReportText(cents: number | null | undefined) {
  return cents == null ? "Awaiting valuation" : formatMoney(cents);
}
