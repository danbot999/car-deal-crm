import { NextResponse } from "next/server";

import { normalizeFlipInput } from "@/lib/admin";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{
    id: string;
  }>;
};

export async function PATCH(request: Request, context: RouteContext) {
  const { id } = await context.params;

  try {
    const body = await request.json();
    const data = normalizeFlipInput(body);
    const flip = await prisma.adminFlip.update({
      where: { id },
      data
    });

    return NextResponse.json({
      message: "Car admin record updated.",
      flip
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Could not update car.";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}

export async function DELETE(_request: Request, context: RouteContext) {
  const { id } = await context.params;

  try {
    await prisma.adminFlip.delete({ where: { id } });
    return NextResponse.json({ message: "Car removed from admin tracker." });
  } catch {
    return NextResponse.json(
      { error: "Could not remove car." },
      { status: 400 }
    );
  }
}
