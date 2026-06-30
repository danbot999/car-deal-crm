import "server-only";

import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

export type ServiceHealth = {
  healthy?: boolean;
  status?: string;
  message?: string;
  httpStatus?: number | null;
  ageSeconds?: number | null;
  heartbeat?: Record<string, unknown> | null;
  worker?: ServiceHealth;
};

export type SystemHealthReport = {
  checkedAt: string | null;
  overall: "healthy" | "repairing" | "degraded" | "unknown";
  services: Record<string, ServiceHealth>;
  workflow: Record<string, unknown>;
  listings: Record<string, unknown>;
  valuationQueue: {
    counts?: Record<string, number>;
    oldestRunnableAt?: string | null;
    oldestRunnableAgeSeconds?: number | null;
    publicationFailures?: number;
    sources?: Array<Record<string, unknown>>;
  };
  qualityAudit: Record<string, unknown>;
  actions: Array<Record<string, unknown>>;
  recentRepairs: Array<Record<string, unknown>>;
  issues: string[];
};

const reportPath = resolve(process.cwd(), "..", "work", "system-health.json");

export async function readSystemHealth(): Promise<SystemHealthReport> {
  try {
    const parsed = JSON.parse(await readFile(reportPath, "utf8")) as Partial<SystemHealthReport>;
    return {
      checkedAt: typeof parsed.checkedAt === "string" ? parsed.checkedAt : null,
      overall: ["healthy", "repairing", "degraded"].includes(String(parsed.overall))
        ? (parsed.overall as SystemHealthReport["overall"])
        : "unknown",
      services: parsed.services && typeof parsed.services === "object" ? parsed.services : {},
      workflow: parsed.workflow && typeof parsed.workflow === "object" ? parsed.workflow : {},
      listings: parsed.listings && typeof parsed.listings === "object" ? parsed.listings : {},
      valuationQueue: parsed.valuationQueue && typeof parsed.valuationQueue === "object" ? parsed.valuationQueue : {},
      qualityAudit: parsed.qualityAudit && typeof parsed.qualityAudit === "object" ? parsed.qualityAudit : {},
      actions: Array.isArray(parsed.actions) ? parsed.actions : [],
      recentRepairs: Array.isArray(parsed.recentRepairs) ? parsed.recentRepairs : [],
      issues: Array.isArray(parsed.issues) ? parsed.issues.map(String) : []
    };
  } catch {
    return {
      checkedAt: null,
      overall: "unknown",
      services: {},
      workflow: {},
      listings: {},
      valuationQueue: {},
      qualityAudit: {},
      actions: [],
      recentRepairs: [],
      issues: ["The watchdog has not written its first health report yet."]
    };
  }
}
