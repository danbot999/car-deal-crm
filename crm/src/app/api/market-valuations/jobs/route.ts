import { NextResponse } from "next/server";

import { valuationServiceFetch } from "@/lib/valuation-service";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const response = await valuationServiceFetch(
      "/v1/admin/jobs"
    );
    const payload = await response.json();
    return NextResponse.json(payload, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        jobs: [],
        unavailable: true,
        error: error instanceof Error ? error.message : "Valuation service is unavailable."
      },
      { status: 200 }
    );
  }
}
