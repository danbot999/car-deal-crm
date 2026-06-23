"""Append the local market-valuation queue call to the active n8n workflow."""

from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
N8N_DB = Path.home() / ".n8n" / "database.sqlite"
WORKFLOW_ID = "z08K09PwtzaaDmZN"
NODE_NAME = "Queue Market Valuation"
EXPORTS = (
    ROOT / "work" / "n8n-polished-workflow.json",
    ROOT / "work" / "current-workflow-after-polish.json",
)


def now_sql() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def queue_node(position: list[float]) -> dict[str, Any]:
    return {
        "parameters": {
            "method": "POST",
            "url": "http://127.0.0.1:8010/v1/jobs/n8n",
            "sendBody": True,
            "contentType": "json",
            "specifyBody": "keypair",
            "bodyParameters": {
                "parameters": [
                    {"name": "title", "value": "={{ $json.title }}"},
                    {"name": "price", "value": "={{ $json.price }}"},
                    {"name": "url", "value": "={{ $json.url }}"},
                ]
            },
            "options": {
                "timeout": 10000,
                "response": {"response": {"neverError": True}},
            },
        },
        "id": str(uuid.uuid4()),
        "name": NODE_NAME,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.4,
        "position": position,
        "retryOnFail": True,
        "maxTries": 2,
        "waitBetweenTries": 1000,
        "onError": "continueRegularOutput",
    }


def update_payload(nodes: list[dict[str, Any]], connections: dict[str, Any]):
    store = next((node for node in nodes if node.get("name") == "Upsert Car Listing"), None)
    if store is None:
        raise RuntimeError("Upsert Car Listing node was not found")
    existing = next((node for node in nodes if node.get("name") == NODE_NAME), None)
    position = [float(store.get("position", [900, 300])[0]) + 320, float(store.get("position", [900, 300])[1])]
    replacement = queue_node(position)
    if existing:
        replacement["id"] = existing.get("id", replacement["id"])
        existing.clear()
        existing.update(replacement)
    else:
        nodes.append(replacement)
    connections["Upsert Car Listing"] = {
        "main": [[{"node": NODE_NAME, "type": "main", "index": 0}]]
    }
    return nodes, connections


def update_live(connection: sqlite3.Connection) -> None:
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        "SELECT nodes, connections, versionCounter, versionId, activeVersionId FROM workflow_entity WHERE id = ?",
        (WORKFLOW_ID,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Workflow {WORKFLOW_ID} was not found")
    nodes, connections = update_payload(json.loads(row["nodes"]), json.loads(row["connections"]))
    description = "Auckland car monitor with durable local NZ market-valuation queue and ten-minute reconciliation."
    nodes_json = json.dumps(nodes, separators=(",", ":"))
    connections_json = json.dumps(connections, separators=(",", ":"))
    connection.execute(
        "UPDATE workflow_entity SET nodes=?, connections=?, description=?, versionCounter=?, updatedAt=? WHERE id=?",
        (nodes_json, connections_json, description, int(row["versionCounter"] or 1) + 1, now_sql(), WORKFLOW_ID),
    )
    version_ids = {str(value) for value in (row["versionId"], row["activeVersionId"]) if value}
    published = connection.execute(
        "SELECT publishedVersionId FROM workflow_published_version WHERE workflowId=?",
        (WORKFLOW_ID,),
    ).fetchone()
    if published and published["publishedVersionId"]:
        version_ids.add(str(published["publishedVersionId"]))
    for version_id in version_ids:
        connection.execute(
            "UPDATE workflow_history SET nodes=?, connections=?, description=?, updatedAt=? WHERE workflowId=? AND versionId=?",
            (nodes_json, connections_json, description, now_sql(), WORKFLOW_ID, version_id),
        )


def update_export(path: Path) -> None:
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    workflow = payload[0] if isinstance(payload, list) else payload
    workflow["nodes"], workflow["connections"] = update_payload(
        workflow["nodes"], workflow["connections"]
    )
    workflow["description"] = "Auckland car monitor with durable local NZ market-valuation queue and ten-minute reconciliation."
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    if not N8N_DB.exists():
        raise FileNotFoundError(N8N_DB)
    backup = ROOT / "work" / f"n8n-before-valuation-{datetime.now():%Y%m%d-%H%M%S}.sqlite"
    shutil.copy2(N8N_DB, backup)
    with sqlite3.connect(N8N_DB, timeout=30) as connection:
        update_live(connection)
        connection.commit()
    for path in EXPORTS:
        update_export(path)
    print(f"[N8N] Valuation queue node installed. Backup: {backup}")
    print("[N8N] Restart n8n so the active webhook loads this version.")


if __name__ == "__main__":
    main()
