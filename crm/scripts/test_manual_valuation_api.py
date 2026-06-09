from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "prisma" / "dev.db"
BASE_URL = "http://localhost:3001"
LISTING_ID = "listing_manual_valuation_api_test"


def post(path: str, payload: dict[str, str] | None = None) -> requests.Response:
    return requests.post(
        f"{BASE_URL}{path}",
        json=payload,
        timeout=90,
    )


def create_listing() -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("DELETE FROM Listing WHERE id = ?", (LISTING_ID,))
        connection.execute(
            """
            INSERT INTO Listing (
              id, facebookUrl, facebookItemId, title, askingPriceCents, category,
              source, status, riskLevel, firstSeenAt, createdAt, updatedAt,
              valuationStatus, aiEvaluationStatus, listingDescription
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP,
              CURRENT_TIMESTAMP, ?, ?, ?)
            """,
            (
                LISTING_ID,
                "https://www.facebook.com/marketplace/item/manual-valuation-test/",
                "manual-valuation-test",
                "TEMP Manual Valuation API Test Car",
                380000,
                "Cars & Trucks",
                "MANUAL_VALUATION_API_TEST",
                "NEW",
                "UNKNOWN",
                now,
                "NOT_STARTED",
                "NOT_STARTED",
                "Test description: tidy small hatchback, WOF and rego claimed.",
            ),
        )
        connection.commit()


def listing_row() -> sqlite3.Row:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        """
        SELECT valuationCents, targetSellPriceCents, maxBuyPriceCents,
          estimatedProfitCents, valuationStatus, valuationSource,
          aiEvaluationStatus, aiEvaluationError
        FROM Listing WHERE id = ?
        """,
        (LISTING_ID,),
    ).fetchone()
    connection.close()
    if row is None:
        raise AssertionError("Temporary listing row was not found.")
    return row


def cleanup() -> None:
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("DELETE FROM Listing WHERE id = ?", (LISTING_ID,))
        connection.commit()


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    create_listing()
    try:
        invalid = post(
            f"/api/listings/{LISTING_ID}/valuation/manual",
            {"valuation": "-123"},
        )
        assert_true(invalid.status_code == 400, "Invalid valuation should be rejected.")

        response = post(
            f"/api/listings/{LISTING_ID}/valuation/manual",
            {"valuation": "$5,247.50"},
        )
        assert_true(response.status_code == 200, response.text)

        row = listing_row()
        assert_true(row["valuationCents"] == 524750, "Valuation cents mismatch.")
        assert_true(row["targetSellPriceCents"] == 419800, "Target sell mismatch.")
        assert_true(row["maxBuyPriceCents"] == 319800, "Max buy mismatch.")
        assert_true(row["estimatedProfitCents"] == 39800, "Profit mismatch.")
        assert_true(row["valuationStatus"] == "VALUED", "Valuation status mismatch.")
        assert_true(row["valuationSource"] == "TRADE_ME_MANUAL", "Source mismatch.")

        evaluate = post(f"/api/listings/{LISTING_ID}/evaluate")
        row = listing_row()
        if evaluate.status_code == 500:
            assert_true(
                row["aiEvaluationStatus"] == "FAILED",
                "Failed evaluation should update status.",
            )
            assert_true(
                bool(row["aiEvaluationError"]),
                "Failed evaluation should store an error.",
            )
        else:
            assert_true(evaluate.status_code == 200, evaluate.text)

        print(
            json.dumps(
                {
                    "manualValuationApi": "ok",
                    "aiEvaluationPath": "ok",
                    "evaluateStatusCode": evaluate.status_code,
                },
                indent=2,
            )
        )
    finally:
        cleanup()


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as error:
        print(
            f"[TEST] Local dashboard API is not reachable at {BASE_URL}: {error}",
            file=sys.stderr,
        )
        raise
