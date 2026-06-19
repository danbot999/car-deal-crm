ALTER TABLE "Listing" ADD COLUMN "availabilityStatus" TEXT NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE "Listing" ADD COLUMN "availabilityReason" TEXT;
ALTER TABLE "Listing" ADD COLUMN "lastSeenAt" DATETIME;
ALTER TABLE "Listing" ADD COLUMN "lastCheckedAt" DATETIME;
ALTER TABLE "Listing" ADD COLUMN "unavailableSince" DATETIME;
ALTER TABLE "Listing" ADD COLUMN "unavailableCheckCount" INTEGER NOT NULL DEFAULT 0;

UPDATE "Listing"
SET "lastSeenAt" = COALESCE("lastSeenAt", "createdAt")
WHERE "lastSeenAt" IS NULL;

CREATE INDEX "Listing_availabilityStatus_idx" ON "Listing"("availabilityStatus");
CREATE INDEX "Listing_lastCheckedAt_idx" ON "Listing"("lastCheckedAt");
