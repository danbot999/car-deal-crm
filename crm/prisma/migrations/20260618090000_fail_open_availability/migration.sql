ALTER TABLE "Listing" ADD COLUMN "availabilityConfidence" TEXT NOT NULL DEFAULT 'HIGH';
ALTER TABLE "Listing" ADD COLUMN "lastVerifiedAt" DATETIME;
ALTER TABLE "Listing" ADD COLUMN "consecutiveUnavailableChecks" INTEGER NOT NULL DEFAULT 0;

UPDATE "Listing"
SET
  "lastVerifiedAt" = COALESCE("lastVerifiedAt", "lastCheckedAt"),
  "consecutiveUnavailableChecks" = COALESCE("consecutiveUnavailableChecks", "unavailableCheckCount", 0);

CREATE INDEX "Listing_lastVerifiedAt_idx" ON "Listing"("lastVerifiedAt");
