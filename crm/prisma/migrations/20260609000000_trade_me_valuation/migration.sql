ALTER TABLE "Listing" ADD COLUMN "numberPlate" TEXT;
ALTER TABLE "Listing" ADD COLUMN "numberPlateConfidence" INTEGER;
ALTER TABLE "Listing" ADD COLUMN "kmsConfidence" INTEGER;
ALTER TABLE "Listing" ADD COLUMN "listingDescription" TEXT;
ALTER TABLE "Listing" ADD COLUMN "valuationStatus" TEXT NOT NULL DEFAULT 'NOT_STARTED';
ALTER TABLE "Listing" ADD COLUMN "valuationError" TEXT;
ALTER TABLE "Listing" ADD COLUMN "valuationCheckedAt" DATETIME;
ALTER TABLE "Listing" ADD COLUMN "valuationSource" TEXT;
