import { NextResponse } from "next/server";

import { readSystemHealth } from "@/lib/system-health";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  const health = await readSystemHealth();
  return NextResponse.json(health, {
    status: health.overall === "unknown" ? 503 : 200,
    headers: { "Cache-Control": "no-store" }
  });
}
