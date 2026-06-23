"""Remove historical rows that fail the strict active passenger-car policy."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scraper import is_strict_car_listing  # noqa: E402


N8N_DB = Path.home() / ".n8n" / "database.sqlite"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete rejected rows. Without this flag the command is read-only.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not N8N_DB.exists():
        raise FileNotFoundError(f"n8n database not found: {N8N_DB}")

    with sqlite3.connect(N8N_DB) as connection:
        connection.row_factory = sqlite3.Row
        table_row = connection.execute(
            "SELECT id FROM data_table WHERE name = ?",
            ("car_listings",),
        ).fetchone()
        if table_row is None:
            raise RuntimeError("n8n data table 'car_listings' was not found")

        table_name = f"data_table_user_{table_row['id']}"
        rows = connection.execute(
            f'SELECT id, title, category, availabilityStatus FROM "{table_name}"'
        ).fetchall()
        rejected_ids: list[int] = []
        reasons: Counter[str] = Counter()

        for row in rows:
            status = str(row["availabilityStatus"] or "").strip().upper()
            title = str(row["title"] or "").strip()
            category = str(row["category"] or "").strip()
            if status != "ACTIVE":
                rejected_ids.append(int(row["id"]))
                reasons["not_active"] += 1
                continue
            if not is_strict_car_listing(title, category):
                rejected_ids.append(int(row["id"]))
                reasons["not_passenger_car"] += 1

        if args.apply and rejected_ids:
            connection.executemany(
                f'DELETE FROM "{table_name}" WHERE id = ?',
                ((row_id,) for row_id in rejected_ids),
            )
            connection.commit()

        mode = "deleted" if args.apply else "would_delete"
        print(
            {
                "read": len(rows),
                mode: len(rejected_ids),
                "kept": len(rows) - len(rejected_ids),
                "reasons": dict(reasons),
            }
        )


if __name__ == "__main__":
    main()
