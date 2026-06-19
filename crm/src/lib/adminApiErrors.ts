import { NextResponse } from "next/server";

const DATABASE_BUSY_PATTERN =
  /socket timeout|database failed to respond|database is locked|sqlite_busy|timed out/i;

type PrismaLikeError = {
  code?: unknown;
  message?: unknown;
};

export function isDatabaseBusyError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error ?? "");
  return DATABASE_BUSY_PATTERN.test(message);
}

export function isPrismaRecordNotFound(error: unknown) {
  const message = error instanceof Error ? error.message : String(error ?? "");
  if (typeof error !== "object" || error === null) {
    return /record to delete does not exist|record to update not found|no record was found/i.test(
      message
    );
  }

  return (
    (error as PrismaLikeError).code === "P2025" ||
    /record to delete does not exist|record to update not found|no record was found/i.test(
      message
    )
  );
}

export function adminApiErrorResponse(error: unknown, fallback: string) {
  if (isDatabaseBusyError(error)) {
    return NextResponse.json(
      {
        error:
          "The CRM database is busy syncing Marketplace listings. Please try again in a few seconds."
      },
      { status: 503 }
    );
  }

  const message = error instanceof Error ? error.message : fallback;
  return NextResponse.json({ error: message || fallback }, { status: 400 });
}
