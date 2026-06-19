import { NextResponse } from "next/server";

import { normalizeFlipInput } from "@/lib/admin";
import {
  adminApiErrorResponse,
  isPrismaRecordNotFound
} from "@/lib/adminApiErrors";
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
    return adminApiErrorResponse(error, "Could not update car.");
  }
}

export async function DELETE(_request: Request, context: RouteContext) {
  const { id } = await context.params;

  try {
    await prisma.adminFlip.delete({ where: { id } });
    return NextResponse.json({ message: "Car removed from admin tracker." });
  } catch (error) {
    if (isPrismaRecordNotFound(error)) {
      return NextResponse.json({
        message: "Car already removed from admin tracker."
      });
    }

    return adminApiErrorResponse(error, "Could not remove car.");
  }
}
