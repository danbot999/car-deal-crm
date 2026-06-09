CREATE TABLE "AdminFlip" (
  "id" TEXT NOT NULL PRIMARY KEY,
  "vehicleTitle" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'WATCHING',
  "sourceUrl" TEXT,
  "purchaseDate" DATETIME,
  "saleDate" DATETIME,
  "purchasePriceCents" INTEGER NOT NULL DEFAULT 0,
  "repairCostCents" INTEGER NOT NULL DEFAULT 0,
  "otherCostCents" INTEGER NOT NULL DEFAULT 0,
  "salePriceCents" INTEGER,
  "notes" TEXT,
  "journalWentRight" TEXT,
  "journalWentWrong" TEXT,
  "journalLookOutFor" TEXT,
  "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX "AdminFlip_status_idx" ON "AdminFlip"("status");
CREATE INDEX "AdminFlip_purchaseDate_idx" ON "AdminFlip"("purchaseDate");
CREATE INDEX "AdminFlip_saleDate_idx" ON "AdminFlip"("saleDate");
