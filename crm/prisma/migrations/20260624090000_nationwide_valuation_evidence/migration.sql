ALTER TABLE "Listing" ADD COLUMN "marketValuationMethod" TEXT;
ALTER TABLE "Listing" ADD COLUMN "marketRawMedianCents" INTEGER;
ALTER TABLE "Listing" ADD COLUMN "marketExactComparableCount" INTEGER NOT NULL DEFAULT 0;
ALTER TABLE "Listing" ADD COLUMN "marketAdjustmentJson" TEXT;
ALTER TABLE "Listing" ADD COLUMN "marketCoverageJson" TEXT;
ALTER TABLE "Listing" ADD COLUMN "marketSearchIdentity" TEXT;
ALTER TABLE "Listing" ADD COLUMN "marketSearchStage" TEXT NOT NULL DEFAULT 'QUEUED';
ALTER TABLE "Listing" ADD COLUMN "marketSearchProgressJson" TEXT;
ALTER TABLE "Listing" ADD COLUMN "marketConfigurationWarning" TEXT;

CREATE INDEX "Listing_marketSearchStage_idx" ON "Listing"("marketSearchStage");
CREATE INDEX "Listing_marketSearchIdentity_idx" ON "Listing"("marketSearchIdentity");
