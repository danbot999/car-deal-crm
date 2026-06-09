ALTER TABLE "Listing" ADD COLUMN "leadReportJson" TEXT;
ALTER TABLE "Listing" ADD COLUMN "leadSourcesJson" TEXT;
ALTER TABLE "Listing" ADD COLUMN "leadSavedAt" DATETIME;
ALTER TABLE "Listing" ADD COLUMN "researchModel" TEXT;
ALTER TABLE "Listing" ADD COLUMN "researchStatus" TEXT NOT NULL DEFAULT 'NOT_STARTED';
ALTER TABLE "Listing" ADD COLUMN "researchError" TEXT;

CREATE INDEX "Listing_leadSavedAt_idx" ON "Listing"("leadSavedAt");
CREATE INDEX "Listing_researchStatus_idx" ON "Listing"("researchStatus");
