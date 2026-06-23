import { NextResponse } from "next/server";

import { valuationServiceFetch } from "@/lib/valuation-service";

export const dynamic = "force-dynamic";

type RouteProps = { params: Promise<{ id: string }> };

export async function POST(_request: Request, { params }: RouteProps) {
  const { id } = await params;
  try {
    const response = await valuationServiceFetch(
      `/v1/admin/jobs/${encodeURIComponent(id)}/retry`,
      { method: "POST" }
    );
    return NextResponse.json(await response.json(), { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Valuation service is unavailable." },
      { status: 503 }
    );
  }
}
