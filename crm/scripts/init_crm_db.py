from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = ROOT / "prisma" / "dev.db"
MIGRATION_PATH = ROOT / "prisma" / "migrations" / "20260608000000_init" / "migration.sql"

TRADE_ME_COLUMNS = {
    "numberPlate": "TEXT",
    "numberPlateConfidence": "INTEGER",
    "kmsConfidence": "INTEGER",
    "listingDescription": "TEXT",
    "valuationStatus": "TEXT NOT NULL DEFAULT 'NOT_STARTED'",
    "valuationError": "TEXT",
    "valuationCheckedAt": "DATETIME",
    "valuationSource": "TEXT",
}

AI_EVALUATION_COLUMNS = {
    "aiEvaluationStatus": "TEXT NOT NULL DEFAULT 'NOT_STARTED'",
    "aiEvaluatedAt": "DATETIME",
    "aiEvaluationError": "TEXT",
    "profitabilitySummary": "TEXT",
    "commonIssues": "TEXT",
    "inspectionChecklist": "TEXT",
    "sellerQuestions": "TEXT",
    "riskFlags": "TEXT",
    "recommendedAction": "TEXT",
}

LEAD_REPORT_COLUMNS = {
    "leadReportJson": "TEXT",
    "leadSourcesJson": "TEXT",
    "leadSavedAt": "DATETIME",
    "researchModel": "TEXT",
    "researchStatus": "TEXT NOT NULL DEFAULT 'NOT_STARTED'",
    "researchError": "TEXT",
}

AVAILABILITY_COLUMNS = {
    "availabilityStatus": "TEXT NOT NULL DEFAULT 'ACTIVE'",
    "availabilityConfidence": "TEXT NOT NULL DEFAULT 'HIGH'",
    "availabilityReason": "TEXT",
    "lastVerifiedAt": "DATETIME",
    "lastSeenAt": "DATETIME",
    "lastCheckedAt": "DATETIME",
    "unavailableSince": "DATETIME",
    "consecutiveUnavailableChecks": "INTEGER NOT NULL DEFAULT 0",
    "unavailableCheckCount": "INTEGER NOT NULL DEFAULT 0",
}

MARKET_VALUATION_COLUMNS = {
    "variant": "TEXT",
    "transmission": "TEXT",
    "fuelType": "TEXT",
    "bodyType": "TEXT",
    "region": "TEXT",
    "marketValuationStatus": "TEXT NOT NULL DEFAULT 'NOT_STARTED'",
    "marketValuationError": "TEXT",
    "marketValueCents": "INTEGER",
    "marketComparableCount": "INTEGER NOT NULL DEFAULT 0",
    "marketLowestComparableCents": "INTEGER",
    "marketHighestComparableCents": "INTEGER",
    "marketAucklandMedianCents": "INTEGER",
    "marketDifferenceCents": "INTEGER",
    "marketDifferencePercent": "REAL",
    "marketRelation": "TEXT",
    "marketVerdict": "TEXT",
    "marketConfidence": "TEXT",
    "marketReason": "TEXT",
    "marketTargetSellCents": "INTEGER",
    "marketMaxBuyCents": "INTEGER",
    "marketExpectedSpreadCents": "INTEGER",
    "marketSourcesAttempted": "INTEGER NOT NULL DEFAULT 0",
    "marketSourcesSuccessful": "INTEGER NOT NULL DEFAULT 0",
    "marketSourceBreakdownJson": "TEXT",
    "marketComparablesJson": "TEXT",
    "marketValuedAt": "DATETIME",
    "marketValuationRunId": "TEXT",
}

ADMIN_FLIP_COLUMNS = {
    "listingId": "TEXT",
    "askingPriceCents": "INTEGER",
    "thumbnailPath": "TEXT",
    "kms": "INTEGER",
    "rego": "TEXT",
    "sellerContacted": "BOOLEAN NOT NULL DEFAULT false",
    "sellerContactedAt": "DATETIME",
    "priority": "TEXT NOT NULL DEFAULT 'MEDIUM'",
    "nextAction": "TEXT",
    "valuationCents": "INTEGER",
    "targetSellPriceCents": "INTEGER",
    "maxBuyPriceCents": "INTEGER",
    "estimatedProfitCents": "INTEGER",
    "valuationCheckedAt": "DATETIME",
}


def ensure_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row[1] for row in connection.execute('PRAGMA table_info("Listing")')
    }
    for column_name, column_type in {
        **TRADE_ME_COLUMNS,
        **AI_EVALUATION_COLUMNS,
        **LEAD_REPORT_COLUMNS,
        **AVAILABILITY_COLUMNS,
        **MARKET_VALUATION_COLUMNS,
    }.items():
        if column_name not in existing_columns:
            connection.execute(
                f'ALTER TABLE "Listing" ADD COLUMN "{column_name}" {column_type}'
            )
    connection.execute(
        """
        UPDATE "Listing"
        SET "lastSeenAt" = COALESCE("lastSeenAt", "createdAt")
        WHERE "lastSeenAt" IS NULL
        """
    )
    connection.execute(
        'CREATE INDEX IF NOT EXISTS "Listing_availabilityStatus_idx" ON "Listing"("availabilityStatus")'
    )
    connection.execute(
        'CREATE INDEX IF NOT EXISTS "Listing_lastCheckedAt_idx" ON "Listing"("lastCheckedAt")'
    )
    connection.execute(
        'CREATE INDEX IF NOT EXISTS "Listing_lastVerifiedAt_idx" ON "Listing"("lastVerifiedAt")'
    )
    connection.execute(
        'CREATE INDEX IF NOT EXISTS "Listing_marketValuationStatus_idx" ON "Listing"("marketValuationStatus")'
    )
    connection.execute(
        'CREATE INDEX IF NOT EXISTS "Listing_marketVerdict_idx" ON "Listing"("marketVerdict")'
    )
    connection.execute(
        'CREATE INDEX IF NOT EXISTS "Listing_marketValuedAt_idx" ON "Listing"("marketValuedAt")'
    )


def ensure_admin_flips_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS "AdminFlip" (
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
          "valuationCents" INTEGER,
          "targetSellPriceCents" INTEGER,
          "maxBuyPriceCents" INTEGER,
          "estimatedProfitCents" INTEGER,
          "valuationCheckedAt" DATETIME,
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
        )
        """
    )
    existing_columns = {
        row[1] for row in connection.execute('PRAGMA table_info("AdminFlip")')
    }
    for column_name, column_type in ADMIN_FLIP_COLUMNS.items():
        if column_name not in existing_columns:
            connection.execute(
                f'ALTER TABLE "AdminFlip" ADD COLUMN "{column_name}" {column_type}'
            )
    connection.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS "AdminFlip_listingId_key" ON "AdminFlip"("listingId")'
    )
    connection.execute(
        'CREATE INDEX IF NOT EXISTS "AdminFlip_status_idx" ON "AdminFlip"("status")'
    )
    connection.execute(
        'CREATE INDEX IF NOT EXISTS "AdminFlip_priority_idx" ON "AdminFlip"("priority")'
    )
    connection.execute(
        'CREATE INDEX IF NOT EXISTS "AdminFlip_sellerContacted_idx" ON "AdminFlip"("sellerContacted")'
    )
    connection.execute(
        'CREATE INDEX IF NOT EXISTS "AdminFlip_purchaseDate_idx" ON "AdminFlip"("purchaseDate")'
    )
    connection.execute(
        'CREATE INDEX IF NOT EXISTS "AdminFlip_saleDate_idx" ON "AdminFlip"("saleDate")'
    )


def main() -> None:
    if not MIGRATION_PATH.exists():
        raise FileNotFoundError(f"Missing migration file: {MIGRATION_PATH}")

    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
        ensure_columns(connection)
        ensure_admin_flips_table(connection)
        connection.commit()

    print(f"[CRM] SQLite database is ready at {DATABASE_PATH}")


if __name__ == "__main__":
    main()
