-- RedefineTables
PRAGMA defer_foreign_keys=ON;
PRAGMA foreign_keys=OFF;
CREATE TABLE "new_AdminFlip" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "listingId" TEXT,
    "vehicleTitle" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'WATCHING',
    "sourceUrl" TEXT,
    "askingPriceCents" INTEGER,
    "thumbnailPath" TEXT,
    "kms" INTEGER,
    "rego" TEXT,
    "sellerContacted" BOOLEAN NOT NULL DEFAULT false,
    "sellerContactedAt" DATETIME,
    "priority" TEXT NOT NULL DEFAULT 'MEDIUM',
    "nextAction" TEXT,
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
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "AdminFlip_listingId_fkey" FOREIGN KEY ("listingId") REFERENCES "Listing" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);
INSERT INTO "new_AdminFlip" ("createdAt", "id", "journalLookOutFor", "journalWentRight", "journalWentWrong", "notes", "otherCostCents", "purchaseDate", "purchasePriceCents", "repairCostCents", "saleDate", "salePriceCents", "sourceUrl", "status", "updatedAt", "vehicleTitle") SELECT "createdAt", "id", "journalLookOutFor", "journalWentRight", "journalWentWrong", "notes", "otherCostCents", "purchaseDate", "purchasePriceCents", "repairCostCents", "saleDate", "salePriceCents", "sourceUrl", "status", "updatedAt", "vehicleTitle" FROM "AdminFlip";
DROP TABLE "AdminFlip";
ALTER TABLE "new_AdminFlip" RENAME TO "AdminFlip";
CREATE UNIQUE INDEX "AdminFlip_listingId_key" ON "AdminFlip"("listingId");
CREATE INDEX "AdminFlip_status_idx" ON "AdminFlip"("status");
CREATE INDEX "AdminFlip_priority_idx" ON "AdminFlip"("priority");
CREATE INDEX "AdminFlip_sellerContacted_idx" ON "AdminFlip"("sellerContacted");
CREATE INDEX "AdminFlip_purchaseDate_idx" ON "AdminFlip"("purchaseDate");
CREATE INDEX "AdminFlip_saleDate_idx" ON "AdminFlip"("saleDate");
PRAGMA foreign_keys=ON;
PRAGMA defer_foreign_keys=OFF;
