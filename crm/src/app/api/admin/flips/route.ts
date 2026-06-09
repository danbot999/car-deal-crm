import { NextResponse } from "next/server";

import { normalizeFlipInput } from "@/lib/admin";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const data = normalizeFlipInput(body);
    const flip = await prisma.adminFlip.create({ data });

    return NextResponse.json({
      message: "Car added to admin tracker.",
      flip
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Could not add car.";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
