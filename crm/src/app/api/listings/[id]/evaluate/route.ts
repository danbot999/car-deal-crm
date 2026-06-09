import { readdir, readFile, stat } from "node:fs/promises";
import { extname, join, resolve } from "node:path";

import { NextResponse } from "next/server";

import {
  legacyFieldsFromReport,
  leadReportSchema,
  normalizeLeadReport,
  type LeadReport,
  type LeadSource
} from "@/lib/lead-report";
import { prisma } from "@/lib/db";
import { calculateDealMetrics, formatMoney } from "@/lib/money";

export const dynamic = "force-dynamic";

const TRADE_ME_VALUE_URL = "https://www.trademe.co.nz/a/value-my-car";
const MAX_IMAGES = 4;
const MAX_IMAGE_BYTES = 2_500_000;
const DEFAULT_RESEARCH_MODEL = "gpt-5.4-mini";

type RouteContext = {
  params: Promise<{
    id: string;
  }>;
};

type OpenAiContentPart = {
  text?: string;
  annotations?: unknown[];
};

function publicRoot() {
  return resolve(process.cwd(), "public");
}

function mimeTypeForPath(path: string) {
  const extension = extname(path).toLowerCase();
  if (extension === ".png") {
    return "image/png";
  }
  if (extension === ".webp") {
    return "image/webp";
  }
  return "image/jpeg";
}

async function fileToImageInput(path: string) {
  const stats = await stat(path);
  if (!stats.isFile() || stats.size > MAX_IMAGE_BYTES) {
    return null;
  }

  const bytes = await readFile(path);
  return {
    type: "input_image",
    detail: "low",
    image_url: `data:${mimeTypeForPath(path)};base64,${bytes.toString("base64")}`
  };
}

async function listingImageInputs(listing: {
  thumbnailPath: string | null;
  facebookItemId: string | null;
}) {
  const root = publicRoot();
  const candidates: string[] = [];

  if (listing.thumbnailPath) {
    const thumbnailPath = resolve(root, listing.thumbnailPath.replace(/^\/+/, ""));
    if (thumbnailPath.startsWith(root)) {
      candidates.push(thumbnailPath);
    }
  }

  if (listing.facebookItemId) {
    const detailDir = join(root, "listing-images", "detail");
    try {
      const files = await readdir(detailDir);
      for (const file of files) {
        if (file.startsWith(`${listing.facebookItemId}-`)) {
          candidates.push(join(detailDir, file));
        }
      }
    } catch {
      // Detail images are optional.
    }
  }

  const uniqueCandidates = [...new Set(candidates)].slice(0, MAX_IMAGES);
  const images = await Promise.all(
    uniqueCandidates.map((candidate) => fileToImageInput(candidate).catch(() => null))
  );

  return images.filter((image): image is NonNullable<typeof image> => image != null);
}

function sourceFromAnnotation(annotation: unknown): LeadSource | null {
  if (!annotation || typeof annotation !== "object") {
    return null;
  }

  const candidate = annotation as {
    title?: unknown;
    url?: unknown;
  };

  if (typeof candidate.url !== "string" || !candidate.url) {
    return null;
  }

  return {
    title:
      typeof candidate.title === "string" && candidate.title
        ? candidate.title
        : "Web source",
    url: candidate.url,
    note: "OpenAI web-search citation."
  };
}

function extractResponse(payload: unknown) {
  const citations: LeadSource[] = [];

  if (
    payload &&
    typeof payload === "object" &&
    "output_text" in payload &&
    typeof payload.output_text === "string"
  ) {
    return { outputText: payload.output_text, citations };
  }

  if (!payload || typeof payload !== "object" || !("output" in payload)) {
    return { outputText: null, citations };
  }

  const output = payload.output;
  if (!Array.isArray(output)) {
    return { outputText: null, citations };
  }

  let outputText: string | null = null;
  for (const item of output) {
    if (!item || typeof item !== "object" || !("content" in item)) {
      continue;
    }

    const content = item.content;
    if (!Array.isArray(content)) {
      continue;
    }

    for (const part of content as OpenAiContentPart[]) {
      if (typeof part.text === "string") {
        outputText = part.text;
      }

      if (Array.isArray(part.annotations)) {
        for (const annotation of part.annotations) {
          const source = sourceFromAnnotation(annotation);
          if (source) {
            citations.push(source);
          }
        }
      }
    }
  }

  return { outputText, citations };
}

function mergeSources(...sourceGroups: LeadSource[][]) {
  const byUrl = new Map<string, LeadSource>();

  for (const source of sourceGroups.flat()) {
    if (!source.url || byUrl.has(source.url)) {
      continue;
    }
    byUrl.set(source.url, source);
  }

  return [...byUrl.values()];
}

function compactOpenAiError(errorText: string) {
  try {
    const parsed = JSON.parse(errorText) as {
      error?: {
        message?: string;
      };
    };
    if (parsed.error?.message) {
      return parsed.error.message.slice(0, 600);
    }
  } catch {
    // Plain text error bodies are fine.
  }

  return errorText.slice(0, 600);
}

function buildResearchContext(
  listing: Awaited<ReturnType<typeof prisma.listing.findUnique>>,
  metrics: ReturnType<typeof calculateDealMetrics>
) {
  if (!listing) {
    throw new Error("Listing not found.");
  }

  return {
    task:
      "Create a serious NZ used-car buyer due-diligence report for this Facebook Marketplace listing. Use live web research for model, engine, gearbox, and platform-specific failure points. Do not give shallow generic advice.",
    hardRules: [
      "Do not say generic things like check oil leaks, check electrics, or check service history unless tied to a specific model, engine, gearbox, platform, or known failure pattern.",
      "Identify the likely engine family and gearbox. If uncertain, list candidates, confidence, and exactly what the buyer must verify.",
      "Prioritize expensive failure points, parts availability, WOF/rego/compliance risk, and negotiation leverage.",
      "Keep all seller contact manual. Provide questions only; do not automate outreach.",
      "Include sourceNotes with URLs for researched claims whenever possible."
    ],
    listing: {
      title: listing.title,
      facebookUrl: listing.facebookUrl,
      askingPrice: formatMoney(listing.askingPriceCents),
      tradeMeValuation: formatMoney(listing.valuationCents),
      targetSellPrice: formatMoney(
        listing.targetSellPriceCents ?? metrics.targetSellPriceCents
      ),
      maxBuyPrice: formatMoney(
        listing.maxBuyPriceCents ?? metrics.maxBuyPriceCents
      ),
      estimatedProfitAtAsk: formatMoney(
        listing.estimatedProfitCents ?? metrics.estimatedProfitCents
      ),
      category: listing.category,
      status: listing.status,
      notes: listing.notes,
      numberPlate: listing.numberPlate,
      kms: listing.kms,
      make: listing.make,
      model: listing.model,
      extractedYear: listing.extractedYear,
      listingDescription: listing.listingDescription
    },
    pricingRule: {
      targetSell: "Trade Me valuation x 80%",
      maxBuy: "target sell price minus $1,000",
      profitAtAsk: "target sell price minus asking price"
    },
    tradeMeValueUrl: TRADE_ME_VALUE_URL
  };
}

function mockReport(
  listing: NonNullable<Awaited<ReturnType<typeof prisma.listing.findUnique>>>,
  metrics: ReturnType<typeof calculateDealMetrics>
): LeadReport {
  const isBmw = /bmw/i.test(listing.title);
  const specificFailure = isBmw
    ? "N20/N26 timing-chain guide wear or chain stretch if this car is one of the turbo four-cylinder variants."
    : "Model-specific engine and transmission weak points need confirmation from the exact trim, engine code, and service records.";

  return normalizeLeadReport({
    aiSummary:
      "Mock lead report generated locally. Replace with live OpenAI research once API quota is available.",
    verdict:
      "Research-ready lead. Verify exact engine and gearbox before treating the margin as real.",
    dealScore: isBmw ? 58 : 64,
    riskLevel: isBmw ? "HIGH" : "MEDIUM",
    recommendedAction: "INSPECT_FIRST",
    vehicleIdentity: {
      summary: listing.title,
      year: listing.extractedYear,
      make: listing.make ?? "Unknown",
      model: listing.model ?? listing.title,
      trim: null,
      engineCode: isBmw ? "N20/N26 candidate" : null,
      likelyEngineFamily: isBmw ? "BMW N20/N26 candidate" : null,
      transmission: null,
      drivetrain: null,
      kms: listing.kms,
      confidence: isBmw ? 55 : 40,
      assumptions: [
        "Exact trim and engine code were not verified by live research in mock mode."
      ],
      verificationNeeded: [
        "Confirm engine code from registration, VIN, engine bay label, or seller paperwork.",
        "Confirm full service history and any major repairs."
      ]
    },
    dealNumbers: {
      askingPrice: formatMoney(listing.askingPriceCents),
      tradeMeValuation: formatMoney(listing.valuationCents),
      targetSellPrice: formatMoney(metrics.targetSellPriceCents),
      maxBuyPrice: formatMoney(metrics.maxBuyPriceCents),
      estimatedProfitAtAsk: formatMoney(metrics.estimatedProfitCents),
      recommendedOfferLow: formatMoney(
        metrics.maxBuyPriceCents == null ? null : metrics.maxBuyPriceCents - 50_000
      ),
      recommendedOfferHigh: formatMoney(metrics.maxBuyPriceCents),
      negotiationAngle:
        "Use uncertainty around service history, WOF issues, and major repair risk to justify an offer below max buy.",
      expectedRepairAllowance:
        "Hold back at least $1,000-$2,500 until exact engine and inspection results are known."
    },
    marketPosition:
      "The deal only becomes attractive if inspection confirms no major deferred maintenance and the seller accepts below max buy.",
    failurePoints: [
      {
        area: "Engine",
        component: isBmw ? "Timing chain system" : "Engine family",
        specificFailure,
        whyItMatters:
          "This is the type of failure that can wipe out the flip margin quickly.",
        likelihood: isBmw ? "HIGH" : "UNKNOWN",
        severity: "HIGH",
        inspectionSignal:
          "Cold-start rattle, fault codes, poor service records, or seller avoiding engine-code questions.",
        roughCostRange: "$1,500-$5,000+ depending on engine and damage",
        sourceHint: "Mock mode. Live web citations will replace this."
      }
    ],
    ownershipCosts: ["Budget for diagnostic scan, WOF check, fluids, tyres, and hidden deferred maintenance."],
    partsAvailability:
      "Confirm NZ parts availability and specialist labour before buying.",
    wofRegoComplianceRisks: [
      "Check WOF expiry, rego status, tyre condition, warning lights, and any structural or rust issues."
    ],
    sellerQuestions: [
      "What is the exact engine code and transmission?",
      "Has the timing chain, gearbox, or cooling system had any major work?",
      "Can you provide service history and current WOF/rego proof?"
    ],
    inspectionChecklist: [
      "Scan all modules for stored codes before purchase.",
      "Check cold start from overnight, not already warmed up.",
      "Inspect tyres, brakes, suspension noises, leaks, and cooling-system evidence."
    ],
    testDriveChecklist: [
      "Test from cold through full operating temperature.",
      "Check gearbox shifts under light and moderate load.",
      "Listen for timing-chain rattle, driveline clunks, wheel bearing noise, and misfires."
    ],
    walkAwayTriggers: [
      "Seller cannot verify engine/gearbox or hides service history.",
      "Cold-start rattle, overheating signs, major warning lights, or failed scan.",
      "Repair allowance destroys expected profit."
    ],
    riskFlags: [
      "Exact drivetrain not verified.",
      "Major failure points can exceed expected margin."
    ],
    sourceNotes: []
  });
}

async function runOpenAiEvaluation({
  apiKey,
  images,
  listing,
  metrics,
  model
}: {
  apiKey: string;
  images: Awaited<ReturnType<typeof listingImageInputs>>;
  listing: NonNullable<Awaited<ReturnType<typeof prisma.listing.findUnique>>>;
  metrics: ReturnType<typeof calculateDealMetrics>;
  model: string;
}) {
  const contextText = buildResearchContext(listing, metrics);
  const response = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      model,
      tools: [{ type: "web_search" }],
      tool_choice: "required",
      input: [
        {
          role: "system",
          content: [
            {
              type: "input_text",
              text:
                "You are a cautious NZ used-car due-diligence analyst. You must research model, engine, gearbox, and platform-specific failure points. Return only JSON matching the schema. Keep seller contact manual."
            }
          ]
        },
        {
          role: "user",
          content: [
            {
              type: "input_text",
              text: JSON.stringify(contextText)
            },
            ...images
          ]
        }
      ],
      text: {
        format: {
          type: "json_schema",
          name: "lead_report",
          strict: true,
          schema: leadReportSchema
        }
      }
    })
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`OpenAI research failed: ${compactOpenAiError(errorText)}`);
  }

  const payload = (await response.json()) as unknown;
  const { outputText, citations } = extractResponse(payload);
  if (!outputText) {
    throw new Error("OpenAI did not return readable lead-report JSON.");
  }

  return {
    report: normalizeLeadReport(JSON.parse(outputText)),
    citations
  };
}

export async function POST(_request: Request, context: RouteContext) {
  const { id } = await context.params;
  const listing = await prisma.listing.findUnique({ where: { id } });

  if (!listing) {
    return NextResponse.json({ error: "Listing not found." }, { status: 404 });
  }

  if (listing.valuationCents == null) {
    return NextResponse.json(
      { error: "Add Trade Me value first." },
      { status: 400 }
    );
  }

  const model =
    process.env.OPENAI_RESEARCH_MODEL?.trim() || DEFAULT_RESEARCH_MODEL;

  await prisma.listing.update({
    where: { id },
    data: {
      aiEvaluationStatus: "RUNNING",
      aiEvaluationError: null,
      researchStatus: "RUNNING",
      researchError: null,
      researchModel: model
    }
  });

  try {
    const metrics = calculateDealMetrics(
      listing.valuationCents,
      listing.askingPriceCents
    );
    const images = await listingImageInputs(listing);
    const apiKey = process.env.OPENAI_API_KEY?.trim();
    const useMock = process.env.OPENAI_MOCK_LEAD_REPORT === "1";

    if (!apiKey && !useMock) {
      throw new Error("Missing OPENAI_API_KEY in crm/.env.");
    }

    const result = useMock
      ? { report: mockReport(listing, metrics), citations: [] }
      : await runOpenAiEvaluation({
          apiKey: apiKey as string,
          images,
          listing,
          metrics,
          model
        });

    const report = result.report;
    const sources = mergeSources(report.sourceNotes, result.citations);
    const legacyFields = legacyFieldsFromReport(report);
    const now = new Date();
    const updated = await prisma.listing.update({
      where: { id },
      data: {
        ...legacyFields,
        aiEvaluationStatus: "COMPLETED",
        aiEvaluatedAt: now,
        aiEvaluationError: null,
        leadReportJson: JSON.stringify(report),
        leadSourcesJson: JSON.stringify(sources),
        leadSavedAt: now,
        researchModel: model,
        researchStatus: "COMPLETED",
        researchError: null
      },
      select: {
        id: true,
        aiSummary: true,
        dealScore: true,
        riskLevel: true,
        aiEvaluationStatus: true,
        aiEvaluatedAt: true,
        leadSavedAt: true,
        researchStatus: true,
        recommendedAction: true
      }
    });

    return NextResponse.json({
      message: "Comprehensive lead report saved.",
      redirectUrl: `/leads/${id}`,
      listing: updated
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "AI evaluation failed.";

    await prisma.listing.update({
      where: { id },
      data: {
        aiEvaluationStatus: "FAILED",
        aiEvaluationError: message,
        aiEvaluatedAt: new Date(),
        researchStatus: "FAILED",
        researchError: message,
        researchModel: model
      }
    });

    return NextResponse.json({ error: message }, { status: 500 });
  }
}
