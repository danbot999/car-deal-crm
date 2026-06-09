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


def ensure_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row[1] for row in connection.execute('PRAGMA table_info("Listing")')
    }
    for column_name, column_type in {
        **TRADE_ME_COLUMNS,
        **AI_EVALUATION_COLUMNS,
        **LEAD_REPORT_COLUMNS,
    }.items():
        if column_name not in existing_columns:
            connection.execute(
                f'ALTER TABLE "Listing" ADD COLUMN "{column_name}" {column_type}'
            )


def ensure_admin_flips_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS "AdminFlip" (
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
        )
        """
    )
    connection.execute(
        'CREATE INDEX IF NOT EXISTS "AdminFlip_status_idx" ON "AdminFlip"("status")'
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
