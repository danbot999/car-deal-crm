"""Upgrade the local n8n workflow to accept verified active passenger cars only."""

from __future__ import annotations

import argparse
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
N8N_DB = Path.home() / ".n8n" / "database.sqlite"
WORKFLOW_ID = "z08K09PwtzaaDmZN"
WORKFLOW_EXPORTS = (
    ROOT / "work" / "n8n-polished-workflow.json",
    ROOT / "work" / "current-workflow-after-polish.json",
)

N8N_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("title", "string", "TEXT"),
    ("price", "number", "REAL"),
    ("url", "string", "TEXT"),
    ("firstSeen", "string", "TEXT"),
    ("category", "string", "TEXT"),
    ("availabilityStatus", "string", "TEXT"),
    ("availabilityConfidence", "string", "TEXT"),
    ("filterReason", "string", "TEXT"),
    ("lastSeen", "string", "TEXT"),
    ("sourceSearchUrl", "string", "TEXT"),
)

PREPARE_JS = r"""const source = $('Webhook').first().json;
const listings = source.body?.items ?? source.items ?? [];

if (!Array.isArray(listings)) {
  return [];
}

const now = new Date().toISOString();
const seenInPayload = new Set();
const output = [];

const excludedTitlePattern = /\b(go[\s-]?kart|kart|mini[\s-]?bike|minibike|motorbike|motorcycle|scooter|trailer|boat|jet\s*ski|quad\s*bike|atv|utv|bus|coach|school\s*bus|tour\s*bus|mini[\s-]?bus|motorhome|camper(?:van)?|caravan|rv|commercial\s*truck|box\s*truck|flat[\s-]?deck|tipper|tractor\s*unit|lorry|isuzu\s+gala|mitsubishi\s+rosa|toyota\s+coaster|tyres?|tires?|wheels?|rims?|mags?|parts?|wrecking|dismantling|canopy|bumper|gearbox|transmission|headlight|tail\s*light|seat\s*covers?)\b/i;
const financeOnlyPattern = /(\$\s*\d[\d,]*(?:\.\d{1,2})?\s*(?:per|\/)\s*(?:week|wk)|\b(?:per week|weekly payments?|from\s+\$\s*\d[\d,]*\s*\/?\s*(?:week|wk))\b)/i;
const excludedCategories = ['powersport', 'motorcycle', 'motorbike', 'scooter', 'rvs & campers', 'rvs and campers', 'rv & camper', 'commercial truck', 'bus', 'coach', 'trailer', 'boat', 'bicycle', 'bike', 'parts', 'wheels', 'tyres', 'tires'];
const allowedCategories = ['cars & trucks', 'cars and trucks'];
const hardRejectionReasons = new Set(['excluded_category', 'excluded_vehicle_type', 'finance_only']);
const validStatuses = new Set(['ACTIVE', 'NEEDS_REVIEW', 'POSSIBLY_SOLD', 'CONFIRMED_SOLD', 'UNAVAILABLE', 'EXPIRED', 'UNKNOWN']);
const validConfidence = new Set(['HIGH', 'MEDIUM', 'LOW']);

function clean(value) {
  return String(value ?? '').replace(/\s+/g, ' ').trim();
}

function normalizeStatus(listing) {
  const raw = clean(listing?.availabilityStatus ?? listing?.availability_status).toUpperCase();
  if (raw === 'SOLD') {
    return 'POSSIBLY_SOLD';
  }
  if (validStatuses.has(raw)) {
    return raw;
  }
  if (listing?.available === false) {
    return 'POSSIBLY_SOLD';
  }
  if (listing?.verified === false || clean(listing?.rejection_reason)) {
    return 'NEEDS_REVIEW';
  }
  return 'ACTIVE';
}

function normalizeConfidence(listing, status) {
  const raw = clean(listing?.availabilityConfidence ?? listing?.availability_confidence).toUpperCase();
  if (validConfidence.has(raw)) {
    return raw;
  }
  if (status === 'ACTIVE') {
    return listing?.verified === false ? 'LOW' : 'HIGH';
  }
  if (status === 'POSSIBLY_SOLD') {
    return 'MEDIUM';
  }
  return 'LOW';
}

for (const listing of listings) {
  const title = clean(listing?.title);
  const price = Number(listing?.price);
  const url = clean(listing?.url);
  const category = clean(listing?.category);
  const categoryLower = category.toLowerCase();
  const reason = clean(listing?.filterReason ?? listing?.rejection_reason);

  const categoryExcluded = excludedCategories.some((value) => categoryLower.includes(value));
  const categoryAllowed = allowedCategories.some((value) => categoryLower.includes(value));
  const financeOnly = price < 1000 && financeOnlyPattern.test(`${title} ${reason}`);
  const availabilityStatus = normalizeStatus(listing);
  const strictActiveCar =
    availabilityStatus === 'ACTIVE' &&
    listing?.verified === true &&
    listing?.available === true &&
    listing?.in_scope === true;
  const hardReject =
    !title ||
    title === 'Untitled Marketplace vehicle' ||
    !Number.isFinite(price) ||
    price < 0 ||
    price > 7000 ||
    !url.includes('/marketplace/item/') ||
    seenInPayload.has(url) ||
    categoryExcluded ||
    !categoryAllowed ||
    excludedTitlePattern.test(title) ||
    financeOnly ||
    hardRejectionReasons.has(reason) ||
    !strictActiveCar;

  if (hardReject) {
    continue;
  }

  const availabilityConfidence = normalizeConfidence(listing, availabilityStatus);

  seenInPayload.add(url);
  output.push({
    json: {
      title,
      price,
      url,
      firstSeen: clean(listing?.firstSeen) || now,
      category,
      availabilityStatus,
      availabilityConfidence,
      filterReason: reason || (availabilityStatus === 'ACTIVE' ? 'detail_page_loaded' : 'needs_review'),
      lastSeen: now,
      sourceSearchUrl: clean(listing?.sourceSearchUrl),
    },
  });
}

return output;"""


def now_sql() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def random_id() -> str:
    return secrets.token_urlsafe(12).replace("-", "").replace("_", "")[:16]


def ensure_table_columns(connection: sqlite3.Connection) -> None:
    connection.row_factory = sqlite3.Row
    table_row = connection.execute(
        "SELECT id FROM data_table WHERE name = ?", ("car_listings",)
    ).fetchone()
    if table_row is None:
        raise RuntimeError("n8n data table 'car_listings' was not found")

    table_id = str(table_row["id"])
    table_name = f"data_table_user_{table_id}"
    existing_sql_columns = {
        row["name"] for row in connection.execute(f'PRAGMA table_info("{table_name}")')
    }
    existing_meta_columns = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM data_table_column WHERE dataTableId = ?",
            (table_id,),
        )
    }

    next_index = connection.execute(
        "SELECT COALESCE(MAX(\"index\"), -1) + 1 FROM data_table_column WHERE dataTableId = ?",
        (table_id,),
    ).fetchone()[0]

    for column_name, n8n_type, sqlite_type in N8N_COLUMNS:
        if column_name not in existing_sql_columns:
            connection.execute(
                f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {sqlite_type}'
            )
        if column_name not in existing_meta_columns:
            connection.execute(
                """
                INSERT INTO data_table_column (
                    id,
                    name,
                    type,
                    "index",
                    dataTableId,
                    createdAt,
                    updatedAt
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    random_id(),
                    column_name,
                    n8n_type,
                    next_index,
                    table_id,
                    now_sql(),
                    now_sql(),
                ),
            )
            next_index += 1

    connection.execute(
        "UPDATE data_table SET updatedAt = ? WHERE id = ?",
        (now_sql(), table_id),
    )


def schema_for_columns() -> list[dict[str, Any]]:
    return [
        {
            "id": name,
            "displayName": name,
            "required": False,
            "defaultMatch": False,
            "display": True,
            "type": "number" if kind == "number" else "string",
            "readOnly": False,
            "removed": False,
        }
        for name, kind, _sqlite_type in N8N_COLUMNS
    ]


def upsert_node_parameters() -> dict[str, Any]:
    column_values = {
        name: "={{ $json." + name + " }}"
        for name, _kind, _sqlite_type in N8N_COLUMNS
    }
    return {
        "resource": "row",
        "operation": "upsert",
        "dataTableId": {"__rl": True, "mode": "name", "value": "car_listings"},
        "matchType": "allConditions",
        "filters": {
            "conditions": [
                {"keyName": "url", "condition": "eq", "keyValue": "={{ $json.url }}"}
            ]
        },
        "columns": {
            "mappingMode": "defineBelow",
            "value": column_values,
            "schema": schema_for_columns(),
            "matchingColumns": [],
            "attemptToConvertTypes": False,
            "convertFieldsToString": False,
        },
        "options": {},
    }


def update_workflow_payload(nodes: list[dict[str, Any]], connections: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    nodes_by_name = {node["name"]: node for node in nodes}

    ensure_node = nodes_by_name["Ensure Car Listings Table"]
    ensure_node["parameters"]["columns"] = {
        "column": [
            {"name": name, "type": kind}
            for name, kind, _sqlite_type in N8N_COLUMNS
        ]
    }

    prepare_node = nodes_by_name["Prepare Car Listings"]
    prepare_node["parameters"]["mode"] = "runOnceForAllItems"
    prepare_node["parameters"]["language"] = "javaScript"
    prepare_node["parameters"]["jsCode"] = PREPARE_JS

    store_node = nodes_by_name.get("Store New Listing") or nodes_by_name.get("Upsert Car Listing")
    if store_node is None:
        raise RuntimeError("Could not find n8n store/upsert node")
    store_node["name"] = "Upsert Car Listing"
    store_node["parameters"] = upsert_node_parameters()

    nodes = [node for node in nodes if node["name"] != "If Listing Is New"]
    connections = {
        "Webhook": {"main": [[{"node": "Ensure Car Listings Table", "type": "main", "index": 0}]]},
        "Ensure Car Listings Table": {"main": [[{"node": "Prepare Car Listings", "type": "main", "index": 0}]]},
        "Prepare Car Listings": {"main": [[{"node": "Upsert Car Listing", "type": "main", "index": 0}]]},
    }
    return nodes, connections


def update_live_workflow(connection: sqlite3.Connection) -> None:
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        """
        SELECT nodes, connections, versionCounter, versionId, activeVersionId
        FROM workflow_entity
        WHERE id = ?
        """,
        (WORKFLOW_ID,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"n8n workflow {WORKFLOW_ID} was not found")

    nodes, connections = update_workflow_payload(
        json.loads(row["nodes"]),
        json.loads(row["connections"]),
    )
    connection.execute(
        """
        UPDATE workflow_entity
        SET
          nodes = ?,
          connections = ?,
          description = ?,
          versionCounter = ?,
          updatedAt = ?
        WHERE id = ?
        """,
        (
            json.dumps(nodes, separators=(",", ":")),
            json.dumps(connections, separators=(",", ":")),
            "Strict Auckland passenger-car monitor: stores only verified ACTIVE cars under $7k, upserting by URL.",
            int(row["versionCounter"] or 1) + 1,
            now_sql(),
            WORKFLOW_ID,
        ),
    )
    active_version_ids = {
        str(value)
        for value in (row["versionId"], row["activeVersionId"])
        if value
    }
    published_row = connection.execute(
        """
        SELECT publishedVersionId
        FROM workflow_published_version
        WHERE workflowId = ?
        """,
        (WORKFLOW_ID,),
    ).fetchone()
    if published_row is not None:
        active_version_ids.add(str(published_row["publishedVersionId"]))

    for version_id in active_version_ids:
        connection.execute(
            """
            UPDATE workflow_history
            SET
              nodes = ?,
              connections = ?,
              description = ?,
              updatedAt = ?
            WHERE workflowId = ?
              AND versionId = ?
            """,
            (
                json.dumps(nodes, separators=(",", ":")),
                json.dumps(connections, separators=(",", ":")),
                "Strict Auckland passenger-car monitor: stores only verified ACTIVE cars under $7k, upserting by URL.",
                now_sql(),
                WORKFLOW_ID,
                version_id,
            ),
        )


def update_export_file(path: Path) -> None:
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    workflow = payload[0] if isinstance(payload, list) else payload
    nodes, connections = update_workflow_payload(
        workflow["nodes"],
        workflow["connections"],
    )
    workflow["nodes"] = nodes
    workflow["connections"] = connections
    workflow["description"] = (
        "Strict Auckland passenger-car monitor: stores only verified ACTIVE "
        "cars under $7k, upserting by URL."
    )
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-live-workflow", action="store_true")
    parser.add_argument("--skip-exports", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not N8N_DB.exists():
        raise FileNotFoundError(f"n8n database not found: {N8N_DB}")

    with sqlite3.connect(N8N_DB) as connection:
        ensure_table_columns(connection)
        if not args.skip_live_workflow:
            update_live_workflow(connection)
        connection.commit()

    if not args.skip_exports:
        for export_path in WORKFLOW_EXPORTS:
            update_export_file(export_path)

    print("[N8N] Strict active passenger-car workflow/table upgrade complete.")
    print("[N8N] Restart n8n so the active webhook picks up the workflow change.")


if __name__ == "__main__":
    main()
