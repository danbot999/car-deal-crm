import { NextResponse } from "next/server";

import { createOrGetAdminFlipFromListing } from "@/lib/admin";
import { adminApiErrorResponse } from "@/lib/adminApiErrors";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as { listingId?: unknown };
    const listingId =
      typeof body.listingId === "string" ? body.listingId.trim() : "";

    if (!listingId) {
      return NextResponse.json(
        { error: "Listing ID is required." },
        { status: 400 }
      );
    }

    const result = await createOrGetAdminFlipFromListing(listingId);

    return NextResponse.json({
      created: result.created,
      flip: result.flip,
      message: result.created
        ? "Saved to Admin pipeline."
        : "Already saved to Admin pipeline."
    });
  } catch (error) {
    return adminApiErrorResponse(error, "Could not save to Admin.");
  }
}
