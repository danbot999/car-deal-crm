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
LISTING_ID = "listing_lead_report_api_test"


def post(path: str) -> requests.Response:
    return requests.post(f"{BASE_URL}{path}", timeout=120)


def get(path: str) -> requests.Response:
    return requests.get(f"{BASE_URL}{path}", timeout=30)


def create_listing() -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("DELETE FROM Listing WHERE id = ?", (LISTING_ID,))
        connection.execute(
            """
            INSERT INTO Listing (
              id, facebookUrl, facebookItemId, title, askingPriceCents, category,
              source, status, riskLevel, firstSeenAt, createdAt, updatedAt,
              valuationCents, targetSellPriceCents, maxBuyPriceCents,
              estimatedProfitCents, valuationStatus, valuationSource,
              aiEvaluationStatus, researchStatus, listingDescription,
              extractedYear, make, model, kms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP,
              CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                LISTING_ID,
                "https://www.facebook.com/marketplace/item/lead-report-test/",
                "lead-report-test",
                "TEMP Lead Report API Test BMW 320i N20",
                480000,
                "Cars & Trucks",
                "LEAD_REPORT_API_TEST",
                "NEW",
                "UNKNOWN",
                now,
                700000,
                560000,
                460000,
                80000,
                "VALUED",
                "TRADE_ME_MANUAL",
                "NOT_STARTED",
                "NOT_STARTED",
                "Test BMW 320i listing. Seller says tidy car with WOF and service history.",
                2013,
                "BMW",
                "320i",
                145000,
            ),
        )
        connection.commit()


def listing_row() -> sqlite3.Row:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        """
        SELECT aiEvaluationStatus, researchStatus, leadReportJson, leadSourcesJson,
          leadSavedAt, recommendedAction, commonIssues
        FROM Listing WHERE id = ?
        """,
        (LISTING_ID,),
    ).fetchone()
    connection.close()
    if row is None:
        raise AssertionError("Temporary lead-report listing row was not found.")
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
        response = post(f"/api/listings/{LISTING_ID}/evaluate")
        assert_true(response.status_code == 200, response.text)
        payload = response.json()
        assert_true(
            payload.get("redirectUrl") == f"/leads/{LISTING_ID}",
            "Evaluation should return Leads redirect URL.",
        )

        row = listing_row()
        assert_true(row["aiEvaluationStatus"] == "COMPLETED", "AI status mismatch.")
        assert_true(row["researchStatus"] == "COMPLETED", "Research status mismatch.")
        assert_true(bool(row["leadSavedAt"]), "Lead saved timestamp missing.")
        assert_true(bool(row["leadReportJson"]), "Lead report JSON missing.")

        report = json.loads(row["leadReportJson"])
        report_text = json.dumps(report).lower()
        assert_true("failurePoints" in report, "Report failure points missing.")
        assert_true("timing" in report_text, "BMW mock should mention timing-chain risk.")

        lead_page = get(f"/leads/{LISTING_ID}")
        assert_true(lead_page.status_code == 200, "Lead detail page should render.")

        print(
            json.dumps(
                {
                    "leadReportApi": "ok",
                    "redirectUrl": payload["redirectUrl"],
                    "failurePoints": len(report["failurePoints"]),
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
