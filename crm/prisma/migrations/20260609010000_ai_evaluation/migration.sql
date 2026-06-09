ALTER TABLE "Listing" ADD COLUMN "aiEvaluationStatus" TEXT NOT NULL DEFAULT 'NOT_STARTED';
ALTER TABLE "Listing" ADD COLUMN "aiEvaluatedAt" DATETIME;
ALTER TABLE "Listing" ADD COLUMN "aiEvaluationError" TEXT;
ALTER TABLE "Listing" ADD COLUMN "profitabilitySummary" TEXT;
ALTER TABLE "Listing" ADD COLUMN "commonIssues" TEXT;
ALTER TABLE "Listing" ADD COLUMN "inspectionChecklist" TEXT;
ALTER TABLE "Listing" ADD COLUMN "sellerQuestions" TEXT;
ALTER TABLE "Listing" ADD COLUMN "riskFlags" TEXT;
ALTER TABLE "Listing" ADD COLUMN "recommendedAction" TEXT;
